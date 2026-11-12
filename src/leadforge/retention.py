"""Forget a person (C4) and let data expire (C5). L6, ADOPT section 5.

Nothing here reads a clock: every age is computed from the `now` handed in (`util.utcnow()` at the CLI), so a test
sets the date instead of waiting. Nothing here logs the value being forgotten.
"""

from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from leadforge import db
from leadforge.config import Config
from leadforge.util import InputError

MARKER = "retention_armed_at"   # meta key: the first purge pass has been made on this workspace
REDACTED = "[forgotten]"
KEEP_IN_DATA_DIR = ("bin", ".doctor_ok.json")   # the pinned helper program and the doctor's stamp are not personal data

# A row that holds the value in one of these columns is deleted (C4). Suppression is exempt on purpose.
ROW_RULES = {
    "people": ("name", "title", "source_url", "snippet"),
    "contacts": ("value", "meta_json"),
    "evidence": ("fact", "url", "snippet"),
    "enrichment_observations": ("value_json", "source_url", "evidence", "person_name"),
    "outcomes": ("notes",),
    "messages": ("subject", "body_text", "used_fact", "error", "gate_json"),
    "events": ("payload_json", "classification", "dedupe_key"),
    "outreach_targets": ("eligibility_json",),
    "scores": ("factors_json", "need_hooks_json"),
}
BUSINESS_IDENTITY = ("name", "name_norm", "website", "domain", "maps_url", "address_full", "address_street")
BUSINESS_JSON = ("enrich_json", "hours_json")
BUSINESS_TABLES = ("events", "outcomes", "enrichment_observations", "evidence", "scores", "people", "contacts")
LINE_FILES = re.compile(r"\.(log(\.\d+)?|jsonl|ndjson|tsv)$", re.IGNORECASE)
HANDOFF_GLOBS = ("dm_batch*", "dm_labels*", "drafts_packets*", "drafts*.ndjson")


# ------------------------------------------------------------------ the value to forget
@dataclass(frozen=True)
class Needle:
    kind: str       # email | domain | name
    text: str
    pattern: re.Pattern[str]
    bpattern: re.Pattern[bytes]


def make_needle(value: str) -> Needle:
    text = " ".join(value.split())
    if not text:
        raise InputError("nothing to forget: the value is empty")
    kind = "email" if "@" in text else ("domain" if "." in text and " " not in text else "name")
    text = text.lower() if kind != "name" else text
    forms = {text, json.dumps(text)[1:-1]}   # the spelling inside JSON text too
    core = "|".join(re.escape(f).replace(r"\ ", r"\s+") for f in sorted(forms))
    if kind == "name":
        edges = (r"(?<![A-Za-z0-9])", r"(?![A-Za-z0-9])")
    else:   # not inside a longer address or host name
        left = r"(?<![A-Za-z0-9._%+\-])" if kind == "email" else r"(?<![A-Za-z0-9\-])"
        edges = (left, r"(?![A-Za-z0-9\-]|\.[A-Za-z0-9])")
    src = f"{edges[0]}(?:{core}){edges[1]}"
    return Needle(kind, text, re.compile(src, re.IGNORECASE), re.compile(src.encode("utf-8"), re.IGNORECASE))


# ------------------------------------------------------------------ database: delete rows and what hangs on them
def _marks(ids) -> str:
    return ",".join("?" * len(ids))


def _delete_in(conn: sqlite3.Connection, table: str, column: str, ids) -> int:
    ids = sorted(ids)
    n = 0
    for i in range(0, len(ids), 500):
        chunk = ids[i:i + 500]
        n += conn.execute(f"DELETE FROM {table} WHERE {column} IN ({_marks(chunk)})", chunk).rowcount
    return n


def _ids_in(conn: sqlite3.Connection, table: str, column: str, ids) -> set:
    ids = sorted(ids)
    out: set = set()
    for i in range(0, len(ids), 500):
        chunk = ids[i:i + 500]
        out |= {r[0] for r in conn.execute(f"SELECT id FROM {table} WHERE {column} IN ({_marks(chunk)})", chunk)}
    return out


def _delete_everything_on(conn: sqlite3.Connection, business_ids: set, rows: dict[str, set]) -> dict[str, int]:
    """Delete the business rows in `business_ids`, the rows in `rows` (table -> ids), and every dependent."""
    gone = {t: set(rows.get(t, set())) for t in (*ROW_RULES, "businesses")}
    if business_ids:
        for t in ("contacts", "people", "evidence", "enrichment_observations", "outcomes", "scores", "outreach_targets"):
            gone[t] |= _ids_in(conn, t, "business_id", business_ids)
        gone["events"] |= _ids_in(conn, "events", "business_id", business_ids)
    gone["enrichment_observations"] |= _ids_in(conn, "enrichment_observations", "person_id", gone["people"])
    gone["outcomes"] |= _ids_in(conn, "outcomes", "contact_id", gone["contacts"])
    gone["outreach_targets"] |= _ids_in(conn, "outreach_targets", "contact_id", gone["contacts"])
    gone["messages"] |= _ids_in(conn, "messages", "target_id", gone["outreach_targets"])
    gone["events"] |= _ids_in(conn, "events", "message_id", gone["messages"])
    counts = {}
    for t in ("events", "messages", "outcomes", "enrichment_observations", "outreach_targets", "evidence", "scores",
              "people", "contacts"):
        counts[t] = _delete_in(conn, t, "id", gone[t])
    counts["businesses"] = _delete_in(conn, "businesses", "id", business_ids)
    return {k: v for k, v in counts.items() if v}


def _scrub_database_file(conn: sqlite3.Connection) -> None:
    """Rewrite the file so deleted rows do not stay readable inside it (free pages, the log)."""
    conn.commit()
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    conn.execute("VACUUM")
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")


def forget_in_database(conn: sqlite3.Connection, needle: Needle) -> dict[str, int]:
    conn.execute("PRAGMA secure_delete=ON")
    hit = needle.pattern.search
    biz = {r["id"] for r in conn.execute("SELECT * FROM businesses")
           if any(hit(str(r[c] or "")) for c in BUSINESS_IDENTITY)}
    rows: dict[str, set] = {}
    for table, cols in ROW_RULES.items():
        rows[table] = {r["id"] for r in conn.execute(f"SELECT * FROM {table}")
                       if any(hit(str(r[c] or "")) for c in cols)}
    try:
        counts = _delete_everything_on(conn, biz, rows)
        redacted = 0
        for r in conn.execute("SELECT * FROM businesses").fetchall():
            for col in BUSINESS_JSON:
                if r[col] and hit(r[col]):
                    conn.execute(f"UPDATE businesses SET {col}=? WHERE id=?", (needle.pattern.sub(REDACTED, r[col]), r["id"]))
                    redacted += 1
        if redacted:
            counts["businesses_redacted"] = redacted
        db.suppress(conn, needle.kind, needle.text, reason="", source="forget")   # commits
    except Exception:
        conn.rollback()
        raise
    _scrub_database_file(conn)
    return counts


# ------------------------------------------------------------------ files
def _data_dir(cfg: Config) -> Path:
    return Path(cfg.workspace) / cfg.data_dir


def candidate_files(cfg: Config) -> list[Path]:
    data = _data_dir(cfg)
    out: list[Path] = []
    if data.is_dir():
        for p in sorted(data.rglob("*")):
            rel = p.relative_to(data).parts
            if p.is_file() and rel[0] not in KEEP_IN_DATA_DIR and not p.name.startswith("db.sqlite3"):
                out.append(p)
    ws = Path(cfg.workspace)
    for pat in HANDOFF_GLOBS:
        out += [p for p in sorted(ws.glob(pat)) if p.is_file() and p not in out]
    drafts = ws / "drafts"
    if drafts.is_dir():
        out += [p for p in sorted(drafts.rglob("*")) if p.is_file() and p not in out]
    return out


def _holds(path: Path, needle: Needle, raw: bytes) -> bool:
    if needle.bpattern.search(raw):
        return True
    if zipfile.is_zipfile(path):   # a sheet: its text is compressed inside
        try:
            with zipfile.ZipFile(path) as z:
                return any(needle.bpattern.search(z.read(n)) for n in z.namelist())
        except (zipfile.BadZipFile, OSError):
            return False
    return False


def forget_in_files(cfg: Config, needle: Needle) -> tuple[list[str], list[str]]:
    """(files with lines taken out, files deleted), relative to the workspace. Content is never reported."""
    for h in logging.getLogger("leadforge").handlers:
        h.close()   # Windows will not replace a file this process holds open; the handler reopens on the next record
    edited: list[str] = []
    removed: list[str] = []
    ws = Path(cfg.workspace)
    for p in candidate_files(cfg):
        try:
            raw = p.read_bytes()
            if not _holds(p, needle, raw):
                continue
            rel = str(p.relative_to(ws))
            if LINE_FILES.search(p.name) and not zipfile.is_zipfile(p):
                keep = [ln for ln in raw.splitlines(keepends=True) if not needle.bpattern.search(ln)]
                tmp = p.with_name(p.name + ".tmp")
                tmp.write_bytes(b"".join(keep))
                os.replace(tmp, p)
                edited.append(rel)
            else:
                p.unlink()
                removed.append(rel)
        except OSError:
            continue
    return edited, removed


def forget(cfg: Config, value: str) -> dict:
    needle = make_needle(value)
    path = _db_path(cfg)
    counts: dict[str, int] = {}
    if path.exists():
        db.check_schema_before_write(path)
        conn = db.connect(path)
        try:
            counts = forget_in_database(conn, needle)
        finally:
            conn.close()
    edited, removed = forget_in_files(cfg, needle)
    return {"kind": needle.kind, "rows": counts, "files_edited": edited, "files_removed": removed}


# ------------------------------------------------------------------ expiry
def _db_path(cfg: Config) -> Path:
    return _data_dir(cfg) / "db.sqlite3"   # not cfg.db_path: that property creates the folder


def add_months(dt: datetime, n: int) -> datetime:
    month = dt.month - 1 + n
    year, month = dt.year + month // 12, month % 12 + 1
    day = dt.day
    while True:
        try:
            return dt.replace(year=year, month=month, day=day)
        except ValueError:
            day -= 1


def _parse(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        d = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=UTC)


@dataclass
class Expiry:
    expired: list[str]
    soon: list[str]      # expire within the next 30 days
    total: int
    unknown: int         # no age can be told: never expires


def classify(conn: sqlite3.Connection, now: datetime, months: int) -> Expiry:
    """Age = now minus the start of the run named by `first_run_id`; an empty or dangling one counts as the workspace's
    first run; no run at all means no age. `last_seen_at` is never read: a refresh does not renew."""
    first = _parse(conn.execute("SELECT MIN(started_at) FROM runs WHERE started_at IS NOT NULL AND started_at != ''")
                   .fetchone()[0])
    expired, soon, unknown, total = [], [], 0, 0
    horizon = now + timedelta(days=30)
    for r in conn.execute("SELECT b.id, r.started_at AS s FROM businesses b LEFT JOIN runs r ON r.id=b.first_run_id"):
        total += 1
        began = _parse(r["s"]) or first
        if began is None:
            unknown += 1
            continue
        due = add_months(began, months)
        if due <= now:
            expired.append(r["id"])
        elif due <= horizon:
            soon.append(r["id"])
    return Expiry(expired, soon, total, unknown)


def _marker(path: Path) -> str | None:
    with db.readonly_view(path) as conn:
        row = conn.execute("SELECT value FROM meta WHERE key=?", (MARKER,)).fetchone()
    return None if row is None else row[0]


def purge(cfg: Config, now: datetime, mode: str) -> dict:
    """mode: 'auto' (the start of every run), 'report' (changes nothing), 'apply' (the explicit command).

    state: no_workspace | armed | nothing | report | purged | stopped_over_half"""
    months = cfg.retention.months
    path = _db_path(cfg)
    if not path.exists():
        return {"state": "no_workspace", "deleted": 0, "expiring_30d": 0, "months": months}
    db.check_schema_before_write(path)          # an old schema stops here, file untouched
    gaps = db.schema_gaps(path)
    marker = _marker(path)
    if marker is not None and _parse(marker) is None:
        gaps.append("the retention marker is unreadable")
    if gaps:
        raise InputError("this workspace is half upgraded (" + "; ".join(gaps[:4]) + "). Nothing was deleted and "
                         "nothing was changed. Start a new workspace, or `leadforge purge --everything --yes` "
                         "to wipe this one.")
    conn = db.connect(path)
    try:
        exp = classify(conn, now, months)
        out = {"state": "nothing", "deleted": 0, "expired": len(exp.expired), "expiring_30d": len(exp.soon),
               "total": exp.total, "months": months, "armed": marker is not None}
        if mode == "report":
            out["state"] = "report"
            return out
        if marker is None:      # protection 1: the first pass after the upgrade only reports
            conn.execute("INSERT OR REPLACE INTO meta(key,value) VALUES(?,?)", (MARKER, now.strftime("%Y-%m-%dT%H:%M:%SZ")))
            conn.commit()
            out["state"] = "armed"
            return out
        if not exp.expired:
            return out
        if mode == "auto" and 2 * len(exp.expired) > exp.total:   # protection 3
            out["state"] = "stopped_over_half"
            return out
        conn.execute("PRAGMA secure_delete=ON")
        try:
            _delete_everything_on(conn, set(exp.expired), {})
        except Exception:
            conn.rollback()
            raise
        _scrub_database_file(conn)
        out.update(state="purged", deleted=len(exp.expired))
        return out
    finally:
        conn.close()


def purge_everything(cfg: Config) -> dict:
    """Delete the workspace's own data without opening the database: any age, any schema."""
    for h in logging.getLogger("leadforge").handlers:
        h.close()
    files = 0
    data = _data_dir(cfg)
    if data.is_dir():
        for p in sorted(data.rglob("*"), reverse=True):
            rel = p.relative_to(data).parts
            if rel[0] in KEEP_IN_DATA_DIR:
                continue
            if p.is_file():
                p.unlink()
                files += 1
            elif p.is_dir() and not any(p.iterdir()):
                p.rmdir()
    for p in candidate_files(cfg):
        if p.exists() and not str(p).startswith(str(data)):
            p.unlink()
            files += 1
    return {"files_removed": files}
