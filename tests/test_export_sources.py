"""C12 - every exported e-mail and phone carries its source address and date (slice L7, stage B).

One fixture workspace with every way a contact can come to be known: found on a page (observation), known only by its evidence row, imported from a list,
recorded nowhere, inferred, and a number that is the business's own listing (Maps and DVSA). Every name, address and number is invented.
"""
import csv
import re
import zipfile

import openpyxl
import pytest

from leadforge import db
from leadforge.config import load_config
from leadforge.export import ACCOUNT_COLUMNS, DEFAULT_COLUMNS, NOT_RECORDED_DATE, NOT_RECORDED_SOURCE, SOURCE_COLUMNS, export_run
from leadforge.models import ICP, Business, Contact, EnrichmentObservation, Evidence, Person, Score, ScoreFactor
from leadforge.util import now_iso

DAY = re.compile(r"^\d{4}-\d\d-\d\d$")


def _icp(profile="default"):
    return ICP.model_validate({"campaign": "t", "offer": {"what": "web design"}, "scoring": {"profile": profile},
                               "target": {"categories": ["garage"], "geography": {"areas": ["Leeds"], "country": "GB"}}})


def _biz(conn, rid, bid, name, **kw):
    dom = kw.pop("domain", f"{bid}.example")
    db.upsert_business(conn, Business(id=bid, name=name, name_norm=name.lower(), dedupe_key=f"k{bid}", source=kw.pop("source", "gosom"),
                                      website=f"https://{dom}", domain=dom, first_run_id=rid, address_country="GB", **kw))
    db.save_score(conn, Score(business_id=bid, run_id=rid, total=70, tier="B",
                              factors=[ScoreFactor(factor="x", group="fit", weight=1, score=1, points=1, why="w")]))


def _message(conn, business_id, contact_id):
    now = now_iso()
    conn.execute("INSERT INTO outreach_targets(business_id,contact_id,campaign,state,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                 (business_id, contact_id, "t", "drafted", now, now))
    tid = conn.execute("SELECT id FROM outreach_targets WHERE business_id=?", (business_id,)).fetchone()["id"]
    conn.execute("INSERT INTO messages(target_id,step,purpose,subject,body_text,draft_hash,state,gate_json,grade,used_fact,created_at,updated_at)"
                 " VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", (tid, 1, "cold_open", "Hello", "Body.", "h", "drafted", "{}", "A", "f", now, now))


@pytest.fixture
def export(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cfg = load_config(tmp_path)
    conn = db.connect(cfg.db_path)
    rid = db.create_run(conn, "icp.yaml", "h")

    # 1. found on a page: observation with page and time; business phone from a Maps listing; a person's own number seen on another page
    _biz(conn, rid, "p1", "Page Garage", phone_e164="+441174960101", maps_url="https://maps.example/p1", last_seen_at="2026-10-02T08:00:00Z")
    cid = db.add_contact(conn, Contact(business_id="p1", kind="email", value="owner@p1.example", tier="valid", affinity="own_domain",
                                       verified_at="2026-10-09T00:00:00Z"))
    db.add_observation(conn, EnrichmentObservation(business_id="p1", field="email", value="owner@p1.example", source="public_site",
                                                   source_url="https://p1.example/contact", observed_at="2026-10-01T10:00:00Z"))
    db.add_person(conn, Person(business_id="p1", name="Pat Page", title="Owner", is_dm=1, labeled_by="agent", origin="heuristic"))
    pid = db.people_for(conn, "p1")[0]["id"]
    db.add_contact(conn, Contact(business_id="p1", kind="phone", value="+441174960111", tier="valid", label="structured_person"))
    db.add_observation(conn, EnrichmentObservation(business_id="p1", field="phone", value="+441174960111", source="public_site:structured_person",
                                                   source_url="https://p1.example/team", observed_at="2026-10-03T11:00:00Z",
                                                   verification_state="observed", person_id=pid, person_name="Pat Page"))
    _message(conn, "p1", cid)

    # 2. known only by its evidence row
    _biz(conn, rid, "p2", "Evidence Garage", phone_e164="+441174960102", last_seen_at="2026-10-04T08:00:00Z")
    cid2 = db.add_contact(conn, Contact(business_id="p2", kind="email", value="info@p2.example", tier="valid", affinity="own_domain",
                                        verified_at="2026-10-09T00:00:00Z"))
    db.add_evidence(conn, Evidence(business_id="p2", ref_table="contacts", ref_id=cid2, fact="email_found", url="https://p2.example/about",
                                   observed_at="2026-10-05T09:00:00Z"))

    # 3. imported from a list: a source name, no page; the only number is a contact's (no listing number)
    _biz(conn, rid, "p3", "Imported Garage")
    db.add_contact(conn, Contact(business_id="p3", kind="email", value="hello@p3.example", tier="valid", affinity="own_domain", label="byol"))
    db.add_observation(conn, EnrichmentObservation(business_id="p3", field="email", value="hello@p3.example", source="byol_csv",
                                                   observed_at="2026-10-06T09:00:00Z"))
    db.add_contact(conn, Contact(business_id="p3", kind="phone", value="+441174960103", tier="valid", label="byol"))
    db.add_observation(conn, EnrichmentObservation(business_id="p3", field="phone", value="+441174960103", source="byol_csv",
                                                   observed_at="2026-10-06T09:00:00Z"))

    # 4. recorded nowhere: no observation, no evidence, no date on the contact
    _biz(conn, rid, "p4", "Unrecorded Garage")
    db.add_contact(conn, Contact(business_id="p4", kind="email", value="who@p4.example", tier="valid", affinity="own_domain"))
    db.add_contact(conn, Contact(business_id="p4", kind="phone", value="+441174960104", tier="valid"))

    # 5. an inferred address next to a published one
    _biz(conn, rid, "p5", "Inferred Garage")
    db.add_contact(conn, Contact(business_id="p5", kind="email", value="ann.lee@p5.example", tier="inferred", affinity="own_domain",
                                 label="inferred", verified_at="2026-10-07T12:00:00Z", meta={"basis": "pattern first.last", "confidence": 0.8}))

    # 6. a DVSA row: the number is the list's
    _biz(conn, rid, "p6", "Register Garage", source="dvsa", phone_raw="0117 496 0106", last_seen_at="2026-10-08T00:00:00Z")

    conn.commit()
    return cfg, conn, rid


def _rows(arts):
    path = next(a for a in arts if a.endswith(".csv"))
    with open(path, encoding="utf-8-sig") as fh:
        return {r["Business"]: r for r in csv.DictReader(fh)}


def _check_pair(source, date):
    assert source and source != "-", "a value with no source cell"
    assert DAY.match(date) or date == NOT_RECORDED_DATE, f"date cell is {date!r}"


def test_c12_every_exported_email_and_phone_has_a_source_and_a_date(export):
    cfg, conn, rid = export
    rows = _rows(export_run(conn, _icp(), rid, cfg.exports_dir, ["csv"], cfg=cfg))
    paired = []   # (value cell, its source cell, its date cell) for every value that is really an e-mail or a phone number
    for r in rows.values():
        for value, source, date in (("Email", "Email Source", "Email Date"),
                                    ("Email (Inferred)", "Email (Inferred) Source", "Email (Inferred) Date"),
                                    ("Phone", "Phone Source", "Phone Date"), ("DM Phone", "DM Phone Page", "DM Phone Date")):
            if "@" in r[value] or len(re.sub(r"\D", "", r[value])) >= 9:
                paired.append((r[value], r[source], r[date]))
    for _value, source, date in paired:
        _check_pair(source, date)
    assert len(paired) == 11  # 4 e-mails + 1 inferred + 5 phones + 1 DM phone: nothing skipped by an unexpected placeholder


def test_c12_where_each_value_came_from(export):
    cfg, conn, rid = export
    rows = _rows(export_run(conn, _icp(), rid, cfg.exports_dir, ["csv"], cfg=cfg))
    p1, p2, p3, p4, p5, p6 = (rows[n] for n in ("Page Garage", "Evidence Garage", "Imported Garage", "Unrecorded Garage",
                                                "Inferred Garage", "Register Garage"))
    assert (p1["Email Source"], p1["Email Date"]) == ("https://p1.example/contact", "2026-10-01")   # the observation, not the contact's later verified_at
    assert (p1["Phone Source"], p1["Phone Date"]) == ("https://maps.example/p1", "2026-10-02")      # the listing: its page, last_seen_at
    assert (p1["DM Phone Page"], p1["DM Phone Date"]) == ("https://p1.example/team", "2026-10-03")
    assert (p2["Email Source"], p2["Email Date"]) == ("https://p2.example/about", "2026-10-05")     # evidence row only
    assert (p2["Phone Source"], p2["Phone Date"]) == ("gosom", "2026-10-04")                         # no page for a Maps row without a Maps address: the provider
    assert (p3["Email Source"], p3["Email Date"]) == ("byol_csv", "2026-10-06")                      # a list has a name, no page
    assert (p3["Phone Source"], p3["Phone Date"]) == ("byol_csv", "2026-10-06")                      # contact fallback of the Phone cell
    assert (p4["Email Source"], p4["Email Date"]) == (NOT_RECORDED_SOURCE, NOT_RECORDED_DATE)       # said, never blank
    assert (p4["Phone Source"], p4["Phone Date"]) == (NOT_RECORDED_SOURCE, NOT_RECORDED_DATE)
    assert (p5["Email (Inferred) Source"], p5["Email (Inferred) Date"]) == ("inferred, not published: pattern first.last", "2026-10-07")
    assert (p5["Email Source"], p5["Email Date"]) == ("-", "-")                                      # the inferred address is not a published one
    assert (p6["Phone Source"], p6["Phone Date"]) == (cfg.discovery.dvsa.url, "2026-10-08")
    assert (p4["DM Phone Page"], p4["DM Phone Date"]) == ("-", "-")


def test_c12_the_new_columns_are_last_and_nothing_else_moved(export):
    cfg, conn, rid = export
    assert DEFAULT_COLUMNS[-len(SOURCE_COLUMNS):] == SOURCE_COLUMNS and ACCOUNT_COLUMNS[-len(SOURCE_COLUMNS):] == SOURCE_COLUMNS
    arts = export_run(conn, _icp(), rid, cfg.exports_dir, ["csv", "xlsx"], cfg=cfg)
    with open(next(a for a in arts if a.endswith(".csv")), encoding="utf-8-sig") as fh:
        assert next(csv.reader(fh)) == DEFAULT_COLUMNS
    # the account_fit profile has them too
    rid2 = db.create_run(conn, "icp.yaml", "h2")
    for bid in ("p1", "p2"):
        db.save_score(conn, Score(business_id=bid, run_id=rid2, total=70, tier="B", factors=[
            ScoreFactor(factor="status", group="meta", weight=0, score=0, points=0, why="NEW")]))
    arts2 = export_run(conn, _icp("account_fit"), rid2, cfg.exports_dir / "af", ["csv"], cfg=cfg)
    with open(next(a for a in arts2 if a.endswith(".csv")), encoding="utf-8-sig") as fh:
        head = next(csv.reader(fh))
    assert head == ACCOUNT_COLUMNS and head[-8:] == SOURCE_COLUMNS


def test_c12_the_drafts_tab_and_the_summary_carry_it_too(export):
    cfg, conn, rid = export
    arts = export_run(conn, _icp(), rid, cfg.exports_dir, ["xlsx"], cfg=cfg)
    wb = openpyxl.load_workbook(next(a for a in arts if a.endswith(".xlsx")))
    drafts = list(wb["Drafts"].iter_rows(values_only=True))
    assert drafts[0][-2:] == ("To Source", "To Date")
    assert drafts[1][2] == "owner@p1.example" and drafts[1][-2:] == ("https://p1.example/contact", "2026-10-01")
    summary = " ".join(str(c) for row in wb["Summary"].iter_rows(values_only=True) for c in row if c)
    assert "Open Government Licence v3.0" in summary   # a dvsa row is in the sheet: the licence's sentence is too
    with zipfile.ZipFile(next(a for a in arts if a.endswith(".xlsx"))) as z:
        assert z.testzip() is None


def test_c12_a_suppressed_address_is_in_none_of_the_new_cells(export):
    cfg, conn, rid = export
    conn.execute("INSERT INTO suppression(kind,value,reason,added_at) VALUES('email','owner@p1.example','objected',?)", (now_iso(),))
    conn.commit()
    rows = _rows(export_run(conn, _icp(), rid, cfg.exports_dir, ["csv"], cfg=cfg))
    assert "owner@p1.example" not in " ".join(rows["Page Garage"].values())
    assert rows["Page Garage"]["Email Source"] == "-"   # the address is gone, so is the origin of it
