"""The window's commands other than the run group: each one a thin layer over the engine's own function.

Result shapes are those of `app/ui/src/engine.ts`; a field the engine cannot supply is null, and the slice file names it.
"""

from __future__ import annotations

import contextlib
import json
import re
import sqlite3
import tempfile
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from importlib.resources import files
from pathlib import Path
from typing import Any

from leadforge import __version__, db, util
from leadforge.config import Config, load_config
from leadforge.util import InputError, LeadForgeError, setup_logging
from leadforge.window import WindowError, int_arg, keys, object_arg, only, text_arg, usage

# offer.what is required by the engine; the window's form does not ask for it yet (seam change 2 in the slice file)
OFFER_NOT_GIVEN = "not given: the campaign was made in the window"
HANDED_OUT = ("Sheets and files you already handed to someone else, or wrote outside this folder with --out, cannot be reached "
              "from here.")


# ------------------------------------------------------------------ the workspace
def load_cfg() -> Config:
    try:
        cfg = load_config(".")
    except Exception as e:  # noqa: BLE001 — any parse or validation error, reported not stack-traced
        raise WindowError("usage", "The workspace settings file cannot be read.", [f"leadforge.yaml invalid: {type(e).__name__}"],
                          "Repair leadforge.yaml in the workspace folder, then try again.") from None
    setup_logging(Path(cfg.workspace) / cfg.data_dir / "logs")   # not cfg.logs_dir: that creates the folder
    return cfg


def db_file(cfg: Config) -> Path:
    return Path(cfg.workspace) / cfg.data_dir / "db.sqlite3"   # not cfg.db_path: that creates the folder


def exports_dir(cfg: Config) -> Path:
    return Path(cfg.workspace) / cfg.data_dir / "exports"      # not cfg.exports_dir: that creates the folder


@contextmanager
def reading(cfg: Config) -> Iterator[Any]:
    """A connection that changes nothing in the workspace, or None when it has no database."""
    path = db_file(cfg)
    if not path.is_file():
        yield None
        return
    with contextlib.ExitStack() as stack:
        try:
            conn = stack.enter_context(db.readonly_view(path))
        except PermissionError:
            # db.readonly_view copies the database when its WAL holds data; on Windows the locks of a run that has it open
            # refuse that copy. Then the live database is read in SQLite's read-only mode, sharing the run's WAL.
            conn = stack.enter_context(contextlib.closing(sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True, timeout=10)))
            conn.row_factory = sqlite3.Row
        if not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='runs'").fetchone():
            yield None
            return
        yield conn


def writing(cfg: Config):
    db.check_schema_before_write(db_file(cfg))
    return db.connect(cfg.db_path)


def write_settings(changes: dict[str, Any]) -> None:
    """Write dotted keys to leadforge.yaml only after load_config accepts the result: the check `config set` makes."""
    import yaml

    path = Path("leadforge.yaml")
    data = (yaml.safe_load(path.read_text(encoding="utf-8")) if path.is_file() else {}) or {}
    for key, value in changes.items():
        node = data
        parts = key.split(".")
        for p in parts[:-1]:
            node = node.setdefault(p, {})
            if not isinstance(node, dict):
                raise usage("The setting was not saved.", f"'{p}' is not a mapping in leadforge.yaml")
        node[parts[-1]] = value
    merged = yaml.safe_dump(data, sort_keys=False)
    with tempfile.TemporaryDirectory() as td:
        (Path(td) / "leadforge.yaml").write_text(merged, encoding="utf-8")
        try:
            load_config(td)
        except Exception as e:  # noqa: BLE001
            raise usage("The setting was not saved.", f"invalid value for {', '.join(changes)}: {type(e).__name__}") from None
    path.write_text(merged, encoding="utf-8")


def campaign_dir(name: str) -> Path:
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,79}", name):
        raise usage("Not a campaign name.", "a campaign name is lower-case letters, digits and hyphens")
    return Path("campaigns") / name


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60] or "campaign"


def _icp_of(icp_path: str | None):
    from leadforge.intake import load_icp

    try:
        return load_icp(Path(icp_path)) if icp_path else None
    except (LeadForgeError, OSError):
        return None


# ------------------------------------------------------------------ 1 campaign_create
def campaign_create(args: dict) -> dict:
    from leadforge.grid import build_plan, plan_counts
    from leadforge.intake import compile_icp

    only(args, "draft")
    draft = object_arg(args, "draft")
    only(draft, "kinds", "places", "country", "source", "maxLeads")
    kinds, places = draft.get("kinds"), draft.get("places")
    problems = []
    if not isinstance(kinds, list) or not all(isinstance(k, str) for k in kinds) or not any(k.strip() for k in kinds):
        problems.append("target.categories: at least one kind of business")
    if not isinstance(places, list) or not all(isinstance(p, str) for p in places) or not any(p.strip() for p in places):
        problems.append("target.geography.areas: at least one place")
    country = draft.get("country")
    if not isinstance(country, str) or not country.strip():
        problems.append("target.geography.country: country is required")
    max_leads = draft.get("maxLeads")
    if isinstance(max_leads, bool) or not isinstance(max_leads, int) or max_leads < 1:
        problems.append("caps.max_leads: must be a whole number, 1 or more")
    source = draft.get("source")
    if source not in ("dvsa", "companies_house"):
        problems.append("source: dvsa or companies_house")
    elif source == "companies_house":
        problems.append("source companies_house: the engine needs SIC codes for a Companies House campaign, and the window's "
                        "form has none yet")
    if problems:
        raise WindowError("input", "The campaign is not complete.", problems, "Fill in the marked fields and check the plan again.")
    kinds = [k.strip() for k in kinds if k.strip()]
    places = [p.strip() for p in places if p.strip()]
    cfg = load_cfg()
    name = _slug(f"{places[0]}-{kinds[0]}")
    answers = {"version": 1, "campaign": name, "offer": {"what": OFFER_NOT_GIVEN},
               "target": {"categories": kinds, "geography": {"areas": places, "country": country.strip().upper()}},
               "caps": {"max_leads": max_leads}}
    import yaml

    with tempfile.TemporaryDirectory() as td:   # compiled away from the workspace: a refused draft writes nothing
        a_path, i_path = Path(td) / "answers.yaml", Path(td) / "icp.yaml"
        a_path.write_text(yaml.safe_dump(answers, sort_keys=False, allow_unicode=True), encoding="utf-8")
        try:
            icp, warns = compile_icp(a_path, i_path)
            queries = build_plan(icp, cfg)
        except LeadForgeError as e:
            detail = [ln.strip(" -") for ln in str(e).splitlines()[1:] if ln.strip(" -")] or [str(e)]
            raise WindowError("input", "The campaign is not complete.", detail[:8],
                              "Fill in the marked fields and check the plan again.") from None
        out = campaign_dir(name)
        out.mkdir(parents=True, exist_ok=True)
        (out / "answers.yaml").write_bytes(a_path.read_bytes())
        (out / "icp.yaml").write_bytes(i_path.read_bytes())
    (out / "window.json").write_text(json.dumps({"kinds": kinds, "places": places, "source": source}), encoding="utf-8")
    counts = plan_counts(queries, cfg)
    from leadforge.cli import _plan_warnings

    return {"campaign": icp.campaign, "searches": counts["queries"], "estimatedBusinesses": counts["est_max_results"],
            "estimatedSites": counts["est_enrich_sites"], "estimatedMinutes": counts["est_total_min"],
            "warnings": list(warns) + _plan_warnings(counts, icp, cfg), "retentionMonths": cfg.retention.months}


# ------------------------------------------------------------------ 5 campaigns_list, 6 sheet_export, 7 sheet_open
def sheet_of(cfg: Config, conn, run_id: str) -> dict | None:
    """The sheet written for a run, read from the run's own folder under exports; None when there is none."""
    from leadforge.export import top_hooks

    folder = exports_dir(cfg) / run_id
    found = sorted(p for p in folder.iterdir() if p.is_file()) if folder.is_dir() else []
    sheet_files = [(("xlsx" if p.suffix == ".xlsx" else "csv" if p.suffix == ".csv" else "report"), p) for p in found
                   if p.suffix in (".xlsx", ".csv") or p.name == "report.json"]
    if not sheet_files:
        return None
    tabs = []
    xlsx = next((p for kind, p in sheet_files if kind == "xlsx"), None)
    if xlsx is not None:
        from openpyxl import load_workbook

        wb = load_workbook(xlsx, read_only=True)
        try:
            tabs = [{"name": ws.title, "rows": max(0, (ws.max_row or 1) - 1)} for ws in wb.worksheets]
        finally:
            wb.close()
    written = max(p.stat().st_mtime for _, p in sheet_files)
    return {"runId": run_id, "writtenAt": datetime.fromtimestamp(written, UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "leads": len(db.scores_for_run(conn, run_id)), "tabs": tabs,
            "files": [{"kind": kind, "path": str(p.resolve())} for kind, p in sheet_files],
            "highlights": top_hooks(conn, run_id)}


def campaigns_list(args: dict) -> list[dict]:
    from leadforge.retention import _parse as parse_time
    from leadforge.retention import add_months
    from leadforge.window.run import state_of, window_stage

    only(args)
    cfg = load_cfg()
    out = []
    with reading(cfg) as conn:
        if conn is None:
            return []
        for row in conn.execute("SELECT * FROM runs ORDER BY started_at DESC, id DESC").fetchall():
            rid = row["id"]
            stats = json.loads(row["stats_json"] or "{}")
            icp = _icp_of(row["icp_path"])
            side = _side_file(row["icp_path"])
            state, _ = state_of(row, stats)
            started = parse_time(row["started_at"])
            tiers = {r["tier"]: r["n"] for r in conn.execute("SELECT tier, COUNT(*) n FROM scores WHERE run_id=? GROUP BY tier", (rid,))}
            one = lambda sql, rid=rid: conn.execute(sql, (rid,)).fetchone()[0]  # noqa: E731
            out.append({
                "runId": rid,
                "name": icp.campaign if icp else None,
                "kinds": list(icp.target.categories) if icp else [],
                "places": list(icp.target.geography.areas) if icp else [],
                "source": side.get("source") or ("companies_house" if icp and icp.target.mode == "company" else None),
                "state": state, "stage": window_stage(row["stage"]),
                "startedAt": row["started_at"],
                "keptUntil": add_months(started, cfg.retention.months).date().isoformat() if started else None,
                "businesses": one("SELECT COUNT(*) FROM businesses WHERE first_run_id=?"),
                "withEmail": one("SELECT COUNT(DISTINCT c.business_id) FROM contacts c JOIN businesses b ON b.id=c.business_id "
                                 "WHERE b.first_run_id=? AND c.kind='email'"),
                "withPhone": one("SELECT COUNT(*) FROM businesses b WHERE b.first_run_id=? AND (COALESCE(b.phone_e164,'')<>'' OR "
                                 "EXISTS (SELECT 1 FROM contacts c WHERE c.business_id=b.id AND c.kind='phone'))"),
                "tiers": {"a": tiers.get("A", 0), "b": tiers.get("B", 0), "c": tiers.get("C", 0)},
                "sheet": sheet_of(cfg, conn, rid),
            })
    return out


def _side_file(icp_path: str | None) -> dict:
    """What the window's form said that the engine's campaign file does not keep (the source): campaigns/<name>/window.json."""
    if not icp_path:
        return {}
    try:
        return json.loads((Path(icp_path).parent / "window.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def sheet_export(args: dict) -> dict:
    from leadforge.export import export_run, summarize_for_digest

    only(args, "runId")
    run_id = text_arg(args, "runId")
    cfg = load_cfg()
    if not db_file(cfg).is_file():
        raise WindowError("input", "The sheet was not written.", ["no run found"], "Run the campaign first.")
    conn = writing(cfg)
    row = conn.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
    if not row:
        raise WindowError("input", "The sheet was not written.", ["no run found"], "Run the campaign first.")
    icp = _icp_of(row["icp_path"])
    if icp is None:
        raise WindowError("input", "The sheet was not written.", ["the campaign file of this run cannot be read"], None)
    export_run(conn, icp, run_id, cfg.exports_dir, cfg.export.formats, staleness_days=cfg.validation.staleness_days, cfg=cfg)
    db.mark_exported(conn, run_id, **summarize_for_digest(conn, run_id))   # as `leadforge export` does
    return sheet_of(cfg, conn, run_id)


def _default_opener(path: Path) -> None:
    util.open_artifact(path)


def sheet_open(args: dict, opener: Callable[[Path], None] | None = None) -> None:
    only(args, "path")
    raw = text_arg(args, "path")
    cfg = load_cfg()
    refused = WindowError("usage", "That file is not a sheet of this workspace.", ["Only files in the exports folder can be opened."])
    if not raw or "\x00" in raw:
        raise refused
    try:
        target = (Path(cfg.workspace) / raw).resolve(strict=True)   # an absolute `raw` replaces the workspace; links are followed
        root = exports_dir(cfg).resolve(strict=True)
    except (OSError, RuntimeError):
        raise refused from None
    if not target.is_file() or not target.is_relative_to(root) or target == root:
        raise refused
    (opener or _default_opener)(target)
    return None


# ------------------------------------------------------------------ 8 people_list
def people_list(args: dict) -> dict:
    only(args, "query")
    query = object_arg(args, "query")
    only(query, "search", "limit")
    search = text_arg(query, "search").strip().casefold()
    limit = int_arg(query, "limit")
    if not 0 <= limit <= 500:
        raise usage("The argument limit must be 0 to 500.")
    cfg = load_cfg()
    with reading(cfg) as conn:
        if conn is None:
            return {"people": [], "total": 0, "matching": 0}
        found: dict[tuple[str, str], dict[str, str]] = {}   # (business, person name) -> field -> newest value
        for r in conn.execute("SELECT business_id, person_name, field, value_json FROM enrichment_observations "
                              "WHERE person_name<>'' AND field IN ('email','phone') ORDER BY observed_at"):
            try:
                found.setdefault((r["business_id"], r["person_name"]), {})[r["field"]] = str(json.loads(r["value_json"]))
            except ValueError:
                continue
        campaigns: dict[str, str | None] = {}
        people = []
        for r in conn.execute("SELECT p.id, p.name, p.title, p.source_url, b.id bid, b.name bname, b.domain, b.first_run_id "
                              "FROM people p JOIN businesses b ON b.id=p.business_id ORDER BY p.id"):
            run_id = r["first_run_id"] or ""
            if run_id not in campaigns:
                run = conn.execute("SELECT icp_path FROM runs WHERE id=?", (run_id,)).fetchone()
                icp = _icp_of(run["icp_path"]) if run else None
                campaigns[run_id] = icp.campaign if icp else None
            seen = found.get((r["bid"], r["name"]), {})
            email, phone = seen.get("email"), seen.get("phone")
            people.append({
                "id": str(r["id"]), "name": r["name"], "role": r["title"] or "", "business": r["bname"], "domain": r["domain"] or "",
                "email": email, "phone": phone,
                "source": r["source_url"] or None,   # the page the name was read on, when the engine kept it
                "foundAt": None,                     # gap: the engine keeps no date per person (L7, C12)
                "campaign": campaigns[run_id],
                "suppressed": db.is_suppressed(conn, email, r["domain"]),
            })
    hits = [p for p in people if not search or any(search in (v or "").casefold()
                                                     for v in (p["name"], p["email"], p["domain"], p["business"], p["phone"]))]
    return {"people": hits[:limit], "total": len(people), "matching": len(hits)}


# ------------------------------------------------------------------ 9 person_forget, 10 address_suppress
def person_forget(args: dict) -> dict:
    from leadforge import retention

    only(args, "value", "dry_run")
    value = text_arg(args, "value")
    dry_run = args.get("dry_run", False)
    if not isinstance(dry_run, bool):
        raise usage("The argument dry_run must be true or false.")
    cfg = load_cfg()
    try:
        res = (retention.forget_report if dry_run else retention.forget)(cfg, value)
    except InputError as e:
        raise WindowError("input", "Nothing was changed.", [str(e)[:300]], "nothing was changed") from None
    if res["files_failed"] and not dry_run:   # never "forgot" while a file still holds the value
        raise WindowError("input", "Not every file could be cleaned.",
                          ["these files may still hold it, they could not be cleaned or checked: " + ", ".join(res["files_failed"]),
                           f"The database part is done ({sum(res['rows'].values())} rows)."],
                          "Close the program that holds those files, then forget the same value again.")
    warnings = [HANDED_OUT]
    if dry_run:
        warnings.insert(0, "Nothing was deleted: this is what forgetting it would delete.")
        if res["files_failed"]:
            warnings.append("these files could not be read, so they were not checked: " + ", ".join(res["files_failed"]))
    return {"kind": res["kind"], "value": " ".join(value.split()), "rows": sum(res["rows"].values()),
            "filesRemoved": len(res["files_removed"]), "filesEdited": len(res["files_edited"]), "warnings": warnings}


def address_suppress(args: dict) -> dict:
    only(args, "value", "kind")
    value = text_arg(args, "value").strip()
    kind = text_arg(args, "kind", required=False, allow_null=True)
    if not value:
        raise usage("The address was not added.", "empty value: nothing to suppress")
    if kind is not None and kind not in ("email", "domain"):
        raise usage("The address was not added.", f"unknown kind '{kind[:20]}' (email|domain)")
    kind = kind or ("email" if "@" in value else "domain")
    cfg = load_cfg()
    conn = writing(cfg)
    db.suppress(conn, kind, value, reason="window")
    n = conn.execute("SELECT COUNT(*) c FROM suppression").fetchone()["c"]
    return {"kind": kind, "value": value, "suppressed": n}


# ------------------------------------------------------------------ 11 to 15 purge and retention
def _suppressed_count(cfg: Config) -> int:
    with reading(cfg) as conn:
        return 0 if conn is None else conn.execute("SELECT COUNT(*) FROM suppression").fetchone()[0]


def _purge(mode: str) -> dict:
    from leadforge import retention

    cfg = load_cfg()
    try:
        res = retention.purge(cfg, util.utcnow(), mode)
    except InputError as e:
        raise WindowError("input", "Nothing was changed.", [str(e)[:300]], "nothing was changed") from None
    state = res["state"]
    if state == "files_locked":
        raise WindowError("input", "Nothing was deleted.",
                          ["these files could not be deleted, so nothing was deleted from the database: " + ", ".join(res["files_failed"])],
                          "Close whatever holds them open and try again.")
    if state == "nothing":   # apply with nothing past the limit: a clean-up that deleted nothing
        state = "purged"
    return {"state": state, "months": res.get("months", cfg.retention.months), "total": res.get("total", 0),
            "expired": res.get("expired", 0), "expiringIn30Days": res.get("expiring_30d", 0), "deleted": res.get("deleted", 0),
            "armed": bool(res.get("armed")) or state == "armed", "suppressed": _suppressed_count(cfg)}


def purge_report(args: dict) -> dict:
    only(args)
    return _purge("report")


def purge_apply(args: dict) -> dict:
    only(args)
    return _purge("apply")


def purge_everything(args: dict) -> dict:
    from leadforge import retention

    only(args, "confirm")
    if args.get("confirm") is not True:
        raise usage("Nothing was deleted.", 'purge_everything deletes the whole workspace\'s data; it needs "confirm": true')
    cfg = load_cfg()
    return {"filesRemoved": retention.purge_everything(cfg)["files_removed"]}


def _retention_limits() -> tuple[int, int]:
    from leadforge.config import RetentionCfg

    lo, hi = None, None
    for m in RetentionCfg.model_fields["months"].metadata:
        lo = getattr(m, "ge", lo)
        hi = getattr(m, "le", hi)
    return lo, hi


def retention_get(args: dict) -> dict:
    only(args)
    lo, hi = _retention_limits()
    return {"months": load_cfg().retention.months, "min": lo, "max": hi}


def retention_set(args: dict) -> dict:
    only(args, "months")
    months = int_arg(args, "months")
    lo, hi = _retention_limits()
    if not lo <= months <= hi:
        raise usage("The retention period was not changed.", f"invalid value for retention.months: {months}",
                    next_=f"Choose {lo} to {hi} months.")
    load_cfg()
    write_settings({"retention.months": months})
    return retention_get({})


# ------------------------------------------------------------------ 16 to 18 keys
def _keys() -> keys.Keys:
    try:
        return keys.make_keys()
    except keys.KeysNotAvailable as e:
        raise WindowError("not_available", "Keys cannot be kept in the keyring yet.", [str(e)],
                          "This needs the keys slice (L9) in the engine; until then the key stays in leadforge.yaml.") from None


def _key_name(args: dict) -> str:
    name = text_arg(args, "name")
    if name not in keys.KEY_NAMES:
        raise usage("Unknown key.", f"the keys are {', '.join(keys.KEY_NAMES)}")
    return name


def keys_list(args: dict) -> list[dict]:
    only(args)
    return _keys().list()


def key_save(args: dict) -> dict:
    only(args, "name", "value")
    name = _key_name(args)
    value = args.get("value")
    if not isinstance(value, str) or not value.strip():
        raise usage("The key was not saved.", "The key is empty.")
    return _keys().save(name, value.strip())


def key_remove(args: dict) -> dict:
    only(args, "name")
    return _keys().remove(_key_name(args))


# ------------------------------------------------------------------ 19 to 21 settings, about
SHEET_FORMATS = ("xlsx", "csv")


def settings_get(args: dict) -> dict:
    only(args)
    cfg = load_cfg()
    return {"theme": None, "accent": None,   # the shell's own settings: the engine does not keep them
            "workspace": str(Path(cfg.workspace).resolve()),
            "sheetFormats": [f for f in cfg.export.formats if f in SHEET_FORMATS],
            "openSheetWhenDone": cfg.export.auto_open}


def settings_set(args: dict) -> dict:
    only(args, "patch")
    patch = object_arg(args, "patch")
    shell_own = sorted(set(patch) & {"theme", "accent"})
    if shell_own:
        raise usage("The setting was not saved.", *(f"{k} is kept by the window, not by the engine" for k in shell_own))
    only(patch, "sheetFormats", "openSheetWhenDone")
    changes: dict[str, Any] = {}
    if "sheetFormats" in patch:
        f = patch["sheetFormats"]
        if not isinstance(f, list) or not f or not all(x in SHEET_FORMATS for x in f) or len(set(f)) != len(f):
            raise usage("The setting was not saved.", "sheetFormats: one or both of xlsx, csv")
        changes["export.formats"] = list(f)
    if "openSheetWhenDone" in patch:
        if not isinstance(patch["openSheetWhenDone"], bool):
            raise usage("The setting was not saved.", "openSheetWhenDone: true or false")
        changes["export.auto_open"] = patch["openSheetWhenDone"]
    load_cfg()
    if changes:
        write_settings(changes)
    return settings_get({})


def _own_licence() -> str | None:
    from importlib.metadata import PackageNotFoundError, metadata

    try:
        meta = metadata("leadforge")
    except PackageNotFoundError:
        return None
    return meta.get("License-Expression") or meta.get("License")


def about(args: dict) -> dict:
    only(args)
    try:
        notices = json.loads(files("leadforge").joinpath("data", "licences.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise WindowError("failed", "The licence notices are missing from this build.", ["data/licences.json"],
                          "Reinstall LeadForge.") from None
    return {"windowVersion": None,   # the window's own version: the shell knows it, the engine does not
            "engineVersion": __version__, "licence": _own_licence(),
            "licences": [{k: p[k] for k in ("name", "version", "licence", "notice")} for p in notices["packages"]]}


COMMANDS: dict[str, Callable[[dict], Any]] = {
    "campaign_create": campaign_create, "campaigns_list": campaigns_list, "sheet_export": sheet_export, "sheet_open": sheet_open,
    "people_list": people_list, "person_forget": person_forget, "address_suppress": address_suppress,
    "purge_report": purge_report, "purge_apply": purge_apply, "purge_everything": purge_everything,
    "retention_get": retention_get, "retention_set": retention_set, "keys_list": keys_list, "key_save": key_save,
    "key_remove": key_remove, "settings_get": settings_get, "settings_set": settings_set, "about": about,
}
