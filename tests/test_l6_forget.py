"""L6 items 3 and 4: `leadforge forget` (C4). Every person, company and address here is invented.

A planted person sits in the eight places C4 names (tables, cache, logs, progress file, outbox and inbox, hand-off files,
draft packets, sheets in exports). After `forget`, a byte scan of the whole workspace finds the value only where it must
stay: one suppression row. A second, unrelated person is planted in the same places and must come out untouched.
"""
import hashlib
import json
import re
import shutil
import sqlite3
import zipfile
from pathlib import Path

import pytest
from openpyxl import Workbook
from typer.testing import CliRunner

from leadforge import db
from leadforge.cli import app
from leadforge.models import Business, Contact, Evidence, Person

NAME = "Zora Quillfeather"
EMAIL = "zora.quillfeather@quillfeather-plumbing.example"
DOMAIN = "quillfeather-plumbing.example"
BYSTANDER = "Mavis Underhill"
B_EMAIL = "mavis@underhill-heating.example"
LOOKALIKE_EMAIL = "xzora.quillfeather@other.example"     # longer address: must survive forgetting EMAIL
LOOKALIKE_NAME = "Zora Quillfeatherstone"                # longer word: must survive forgetting NAME

TARGET_LINE = f"{NAME} <{EMAIL}> {DOMAIN}"
BYSTANDER_LINE = f"{BYSTANDER} <{B_EMAIL}> underhill-heating.example"


def _w(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _xlsx(path: Path, cell: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    wb.active.append(["Business", "Email"])
    wb.active.append(["x", cell])
    wb.save(path)


def plant(ws: Path) -> dict:
    """The target and the bystander in all eight places. Returns the bystander's files (to prove they stay)."""
    data = ws / "leadforge_data"
    conn = db.connect(data / "db.sqlite3") if data.exists() else None
    if conn is None:
        data.mkdir(parents=True)
        conn = db.connect(data / "db.sqlite3")
    run = db.create_run(conn, "icp.yaml", "h")
    for bid, name, dom in (("b_q", "Quillfeather Plumbing", DOMAIN), ("b_m", "Underhill Heating", "underhill-heating.example"),
                           ("b_x", "Other Works", "other.example")):
        db.upsert_business(conn, Business(id=bid, name=name, name_norm=name.lower(), dedupe_key=f"k_{bid}",
                                          website=f"https://{dom}", domain=dom, first_run_id=run, source="gosom"))
    # 1. the tables
    db.add_contact(conn, Contact(business_id="b_q", kind="email", value=EMAIL))
    db.add_contact(conn, Contact(business_id="b_m", kind="email", value=B_EMAIL))
    db.add_contact(conn, Contact(business_id="b_x", kind="email", value=LOOKALIKE_EMAIL))
    db.add_person(conn, Person(business_id="b_q", name=NAME, title="Owner", snippet=TARGET_LINE))
    db.add_person(conn, Person(business_id="b_m", name=BYSTANDER, title="Owner", snippet=BYSTANDER_LINE))
    db.add_person(conn, Person(business_id="b_x", name=LOOKALIKE_NAME, title="Owner"))
    db.add_evidence(conn, Evidence(business_id="b_q", fact="contact", snippet=TARGET_LINE))
    db.add_evidence(conn, Evidence(business_id="b_m", fact="contact", snippet=BYSTANDER_LINE))
    cur = conn.execute("INSERT INTO outcomes(business_id,channel,result,notes) VALUES('b_q','email','replied',?)", (TARGET_LINE,))
    conn.execute("INSERT INTO outcomes(business_id,channel,result,notes) VALUES('b_m','email','replied',?)", (BYSTANDER_LINE,))
    conn.execute("INSERT INTO outreach_targets(business_id,campaign,state) VALUES('b_q','c','drafted')")
    conn.execute("INSERT INTO outreach_targets(business_id,campaign,state) VALUES('b_m','c','drafted')")
    tq = conn.execute("SELECT id FROM outreach_targets WHERE business_id='b_q'").fetchone()[0]
    tm = conn.execute("SELECT id FROM outreach_targets WHERE business_id='b_m'").fetchone()[0]
    conn.execute("INSERT INTO messages(target_id,subject,body_text) VALUES(?,?,?)", (tq, "hello", TARGET_LINE))
    conn.execute("INSERT INTO messages(target_id,subject,body_text) VALUES(?,?,?)", (tm, "hello", BYSTANDER_LINE))
    mq = conn.execute("SELECT id FROM messages WHERE target_id=?", (tq,)).fetchone()[0]
    conn.execute("INSERT INTO events(message_id,business_id,kind,payload_json,dedupe_key) VALUES(?,?,?,?,?)",
                 (mq, "b_q", "reply", json.dumps({"from": EMAIL, "who": NAME}), "ev1"))
    # a mention inside another business's own JSON column is redacted, the business stays
    conn.execute("UPDATE businesses SET enrich_json=? WHERE id='b_m'",
                 (json.dumps({"gbp": {"owner_name": "Mavis", "review_names": [NAME]}}),))
    conn.commit()
    del cur
    conn.close()
    # 2. the cache, 3. the logs, 4. the progress file
    _w(data / "cache" / "gosom_q.json", json.dumps([{"title": "Q", "user_reviews": [{"Name": NAME, "Description": EMAIL}]}]))
    _w(data / "cache" / "gosom_m.json", json.dumps([{"title": "M", "user_reviews": [{"Name": BYSTANDER}]}]))
    _w(data / "logs" / "leadforge.log", f"INFO a {TARGET_LINE}\nINFO b {BYSTANDER_LINE}\nINFO c nothing\n")
    _w(data / "logs" / "leadforge.log.1", f"INFO old {TARGET_LINE}\n")
    _w(data / "progress.jsonl", json.dumps({"msg": TARGET_LINE}) + "\n" + json.dumps({"msg": BYSTANDER_LINE}) + "\n")
    # 5. outbox and inbox
    _w(data / "outbox" / "q.eml", f"To: {EMAIL}\n\nHello {NAME}\n")
    b_eml = _w(data / "outbox" / "m.eml", f"To: {B_EMAIL}\n\nHello {BYSTANDER}\n")
    _w(data / "inbox" / "q.json", json.dumps({"from": EMAIL, "text": NAME}))
    b_in = _w(data / "inbox" / "m.json", json.dumps({"from": B_EMAIL, "text": BYSTANDER}))
    # 6. hand-off files, 7. draft packets
    _w(ws / "dm_batch.ndjson", TARGET_LINE + "\n" + BYSTANDER_LINE + "\n")
    _w(ws / "dm_labels.ndjson", TARGET_LINE + "\n" + BYSTANDER_LINE + "\n")
    _w(ws / "drafts_packets.ndjson", json.dumps({"to": EMAIL}) + "\n" + json.dumps({"to": B_EMAIL}) + "\n")
    _w(ws / "drafts" / "1_1.txt", f"To: {EMAIL}\n\n{NAME}\n")
    b_txt = _w(ws / "drafts" / "2_2.txt", f"To: {B_EMAIL}\n\n{BYSTANDER}\n")
    # 8. the sheets in exports (a sheet is compressed inside: the plain byte scan cannot see into it)
    _xlsx(data / "exports" / "run_q" / "c.xlsx", EMAIL)
    _w(data / "exports" / "run_q" / "c.csv", TARGET_LINE + "\n")
    _w(data / "exports" / "run_q" / "report.json", json.dumps({"who": NAME}))
    _xlsx(data / "exports" / "run_m" / "c.xlsx", B_EMAIL)
    b_csv = _w(data / "exports" / "run_m" / "c.csv", BYSTANDER_LINE + "\n")
    (data / "bin").mkdir(exist_ok=True)
    _w(data / "bin" / "helper.txt", "kept")
    return {"files": [b_eml, b_in, b_txt, b_csv, data / "cache" / "gosom_m.json", data / "exports" / "run_m" / "c.xlsx"]}


def scan(root: Path, text: str) -> dict[str, int]:
    """Occurrences of `text` (case-insensitive) per file, also inside zip members, of the whole workspace."""
    # whole word only: "Zora Quillfeatherstone" and "xzora.quillfeather@..." are other people and must not count
    rx = re.compile(rb"(?<![A-Za-z0-9._%+\-])" + re.escape(text.encode()) + rb"(?![A-Za-z0-9])", re.IGNORECASE)
    hits: dict[str, int] = {}
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        raw = p.read_bytes()
        n = len(rx.findall(raw))
        if zipfile.is_zipfile(p):
            with zipfile.ZipFile(p) as z:
                n += sum(len(rx.findall(z.read(m))) for m in z.namelist())
        if n:
            hits[p.relative_to(root).as_posix()] = n
    return hits


def run_forget(ws: Path, monkeypatch, value: str):
    monkeypatch.chdir(ws)
    res = CliRunner().invoke(app, ["forget", value])
    assert res.exit_code == 0, res.output
    digest = [ln for ln in res.output.splitlines() if ln.startswith("LF_DIGEST")][-1]
    assert value.lower() not in digest.lower() and value.lower() not in res.output.lower()  # the value is not echoed
    return res


def bystander_state(ws: Path) -> dict:
    conn = db.connect(ws / "leadforge_data" / "db.sqlite3")
    state = {
        "contacts": sorted(r[0] for r in conn.execute("SELECT value FROM contacts WHERE business_id IN ('b_m','b_x')")),
        "people": sorted(r[0] for r in conn.execute("SELECT name FROM people WHERE business_id IN ('b_m','b_x')")),
        "evidence_m": conn.execute("SELECT snippet FROM evidence WHERE business_id='b_m'").fetchone()[0],
        "msg_m": conn.execute("SELECT body_text FROM messages m JOIN outreach_targets t ON t.id=m.target_id "
                              "WHERE t.business_id='b_m'").fetchone()[0],
        "businesses": sorted(r[0] for r in conn.execute("SELECT id FROM businesses")),
    }
    conn.close()
    return state


@pytest.mark.parametrize("value,left_files", [(EMAIL, None), (NAME, None), (DOMAIN, None)])
def test_forget_removes_the_value_everywhere_and_only_that(tmp_path, monkeypatch, value, left_files):
    ws = tmp_path
    bystander = plant(ws)
    kept_hashes = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in bystander["files"]}
    before = scan(ws, value)
    assert len(before) >= 12, before          # planted: the scan sees it in many places, so a pass below means something

    run_forget(ws, monkeypatch, value)

    after = scan(ws, value)
    # the one place it must stay: the suppression row in the database (the table row, and its UNIQUE index entry when the
    # bytes around it let the whole-word scan see it). Proof that nothing else holds it: delete that row from a copy, rewrite
    # the copy, scan again.
    assert set(after) == {"leadforge_data/db.sqlite3"} and after["leadforge_data/db.sqlite3"] in (1, 2), after
    probe = tmp_path / "probe"
    probe.mkdir()
    shutil.copyfile(ws / "leadforge_data" / "db.sqlite3", probe / "db.sqlite3")
    pc = sqlite3.connect(probe / "db.sqlite3")
    pc.execute("DELETE FROM suppression")
    pc.commit()
    pc.execute("VACUUM")
    pc.close()
    assert scan(probe, value) == {}
    conn = db.connect(ws / "leadforge_data" / "db.sqlite3")
    assert conn.execute("SELECT COUNT(*) FROM suppression").fetchone()[0] == 1
    assert db.is_suppressed(conn, value) if value != NAME else conn.execute(
        "SELECT 1 FROM suppression WHERE kind='name'").fetchone()
    conn.close()
    # what must stay: the bystander's files byte for byte, their lines in shared files, their rows
    for p, h in kept_hashes.items():
        assert hashlib.sha256(p.read_bytes()).hexdigest() == h, p
    assert BYSTANDER_LINE in (ws / "dm_batch.ndjson").read_text(encoding="utf-8")
    assert BYSTANDER_LINE in (ws / "leadforge_data" / "logs" / "leadforge.log").read_text(encoding="utf-8")
    assert B_EMAIL in (ws / "drafts_packets.ndjson").read_text(encoding="utf-8")
    assert (ws / "leadforge_data" / "bin" / "helper.txt").read_text() == "kept"
    state = bystander_state(ws)
    assert B_EMAIL in state["contacts"] and BYSTANDER in state["people"]
    assert state["evidence_m"] == BYSTANDER_LINE and state["msg_m"] == BYSTANDER_LINE
    if value == EMAIL:
        assert LOOKALIKE_EMAIL in state["contacts"]               # a longer address is not this address
    if value == NAME:
        assert LOOKALIKE_NAME in state["people"]                  # a longer word is not this name
    if value == DOMAIN:
        assert "b_q" not in state["businesses"]                   # every business at a forgotten domain goes
    else:
        assert "b_q" in state["businesses"]                       # the company stays, the person goes
    assert {"b_m", "b_x"} <= set(state["businesses"])


def test_forgotten_value_is_not_collected_again(tmp_path):
    ws = tmp_path
    plant(ws)
    from leadforge.config import load_config
    from leadforge.retention import forget
    forget(load_config(ws), EMAIL)
    forget(load_config(ws), NAME)
    conn = db.connect(ws / "leadforge_data" / "db.sqlite3")
    assert db.add_contact(conn, Contact(business_id="b_m", kind="email", value=EMAIL.upper())) == 0
    db.add_person(conn, Person(business_id="b_m", name=NAME.lower()))
    assert conn.execute("SELECT COUNT(*) FROM contacts WHERE value=?", (EMAIL,)).fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM people WHERE lower(name)=?", (NAME.lower(),)).fetchone()[0] == 0
    # a forgotten value does not stop a different person being stored
    assert db.add_contact(conn, Contact(business_id="b_m", kind="email", value="someone.else@underhill-heating.example")) > 0
    conn.close()


def test_forget_in_an_old_workspace_is_refused_and_changes_nothing(tmp_path, monkeypatch):
    ws = tmp_path
    plant(ws)
    c = sqlite3.connect(ws / "leadforge_data" / "db.sqlite3")
    c.execute("UPDATE meta SET value='4' WHERE key='schema_version'")
    c.commit()
    c.close()
    snap = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in ws.rglob("*") if p.is_file()}
    monkeypatch.chdir(ws)
    res = CliRunner().invoke(app, ["forget", EMAIL])
    assert res.exit_code == 4, res.output
    assert snap == {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in ws.rglob("*") if p.is_file()}
