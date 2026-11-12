"""L6 item 6 (C7): an objection is absolute. A suppressed address is in no export file and on no tab.

All names and addresses are invented. The scan reads every file the export wrote, including the inside of the sheet.
"""
import zipfile
from pathlib import Path

import pytest

from leadforge import db
from leadforge.config import load_config
from leadforge.export import export_run
from leadforge.models import ICP, Business, Contact, Score, ScoreFactor
from leadforge.util import now_iso

SUPPRESSED = "quiet.owner@quiet-bakery.example"
SUPPRESSED_INFERRED = "marcus@quiet-bakery.example"
KEPT = "hello@quiet-bakery.example"
OTHER = "orders@rival-bakery.example"


def _icp():
    return ICP.model_validate({"campaign": "t", "offer": {"what": "web design"},
                               "target": {"categories": ["bakery"], "geography": {"areas": ["Leeds"], "country": "GB"}}})


def _message(conn, target_id, body, subject="Quick note"):
    now = now_iso()
    conn.execute(
        "INSERT INTO messages(target_id,step,purpose,subject,body_text,draft_hash,state,gate_json,grade,used_fact,created_at,updated_at)"
        " VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", (target_id, 1, "cold_open", subject, body, "h", "drafted", "{}", "A", "f", now, now))


def _target(conn, business_id, contact_id):
    now = now_iso()
    conn.execute("INSERT INTO outreach_targets(business_id,contact_id,campaign,state,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                 (business_id, contact_id, "t", "drafted", now, now))
    return conn.execute("SELECT id FROM outreach_targets WHERE business_id=?", (business_id,)).fetchone()["id"]


@pytest.fixture
def exported(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cfg = load_config(tmp_path)
    conn = db.connect(cfg.db_path)
    rid = db.create_run(conn, "icp.yaml", "h")
    for bid, name, dom in (("bq", "Quiet Bakery", "quiet-bakery.example"), ("br", "Rival Bakery", "rival-bakery.example")):
        db.upsert_business(conn, Business(id=bid, name=name, name_norm=name.lower(), dedupe_key=f"k{bid}", source="gosom",
                                          website=f"https://{dom}", domain=dom, first_run_id=rid))
        db.save_score(conn, Score(business_id=bid, run_id=rid, total=70, tier="B", factors=[
            ScoreFactor(factor="x", group="fit", weight=1, score=1, points=1, why="w")]))
    sup_id = db.add_contact(conn, Contact(business_id="bq", kind="email", value=SUPPRESSED, tier="valid", affinity="own_domain"))
    db.add_contact(conn, Contact(business_id="bq", kind="email", value=SUPPRESSED_INFERRED, tier="inferred", affinity="own_domain"))
    kept_id = db.add_contact(conn, Contact(business_id="bq", kind="email", value=KEPT, tier="valid", affinity="own_domain"))
    db.add_contact(conn, Contact(business_id="br", kind="email", value=OTHER, tier="valid", affinity="own_domain"))
    # a draft addressed to the suppressed contact, and one that mentions it in its text
    t1 = _target(conn, "bq", sup_id)
    _message(conn, t1, f"Hi, we spoke to {SUPPRESSED} last week.", subject=f"For {SUPPRESSED}")
    conn.commit()
    # the objection arrives after the contacts were stored
    db.suppress(conn, "email", SUPPRESSED, reason="objection")
    db.suppress(conn, "email", SUPPRESSED_INFERRED, reason="objection")
    arts = export_run(conn, _icp(), rid, cfg.exports_dir, ["xlsx", "csv"], cfg=cfg)
    conn.close()
    return arts, kept_id


def holds(paths, text: str) -> list[str]:
    hits = []
    for a in paths:
        p = Path(a)
        if text.encode() in p.read_bytes():
            hits.append(p.name)
        if zipfile.is_zipfile(p):
            with zipfile.ZipFile(p) as z:
                hits += [f"{p.name}:{n}" for n in z.namelist() if text.encode() in z.read(n)]
    return hits


def test_a_suppressed_address_is_in_no_export_file_and_no_tab(exported):
    arts, _ = exported
    assert len(arts) == 3 and any(a.endswith(".xlsx") for a in arts)
    for addr in (SUPPRESSED, SUPPRESSED_INFERRED):
        assert holds(arts, addr) == [], (addr, holds(arts, addr))
    # the same scan sees the addresses that are not suppressed, so a pass above is not an empty export
    assert holds(arts, KEPT) and holds(arts, OTHER)
    # and the business itself is still on the sheet
    assert holds(arts, "Quiet Bakery")


def test_the_draft_addressed_to_it_is_off_the_sheet_and_other_rows_stay(exported):
    arts, _ = exported
    import csv
    csv_path = next(a for a in arts if a.endswith(".csv"))
    with open(csv_path, encoding="utf-8-sig") as fh:
        rows = {r["Business"]: r for r in csv.DictReader(fh)}
    assert rows["Quiet Bakery"]["Draft Subject"] == "no draft"
    assert rows["Quiet Bakery"]["Email"] == KEPT
    assert rows["Quiet Bakery"]["Email (Inferred)"] == "not inferred"
    assert rows["Rival Bakery"]["Email"] == OTHER


def test_a_suppressed_address_inside_other_text_is_masked(tmp_path, monkeypatch):
    """The last net: a draft to someone else that quotes the suppressed address."""
    monkeypatch.chdir(tmp_path)
    cfg = load_config(tmp_path)
    conn = db.connect(cfg.db_path)
    rid = db.create_run(conn, "icp.yaml", "h")
    db.upsert_business(conn, Business(id="br", name="Rival Bakery", name_norm="rival bakery", dedupe_key="kbr", source="gosom",
                                      domain="rival-bakery.example", first_run_id=rid))
    db.save_score(conn, Score(business_id="br", run_id=rid, total=70, tier="B", factors=[
        ScoreFactor(factor="x", group="fit", weight=1, score=1, points=1, why="w")]))
    cid = db.add_contact(conn, Contact(business_id="br", kind="email", value=OTHER, tier="valid", affinity="own_domain"))
    _message(conn, _target(conn, "br", cid), f"Your neighbour {SUPPRESSED.upper()} says hello.")
    conn.commit()
    db.suppress(conn, "email", SUPPRESSED)
    arts = export_run(conn, _icp(), rid, cfg.exports_dir, ["xlsx", "csv"], cfg=cfg)
    conn.close()
    assert holds(arts, SUPPRESSED) == [] and holds(arts, SUPPRESSED.upper()) == []
    assert holds(arts, "[suppressed]")
    assert holds(arts, OTHER)
