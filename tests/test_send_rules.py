"""C13 - send rules by country, wired into the real eligibility path (slice L7, stage B).

Planted leads: no country, a country with no rule, Germany (by name and by code), a UK sole trader. Controls: a UK company and a US business stay
eligible, so the "not eligible" results cannot come from a broken fixture. The same planted leads go through `outreach send`'s re-check and `dry_run`.
"""

from __future__ import annotations

import json
import sqlite3

import pytest

from leadforge import compliance as c
from leadforge import send_rules
from leadforge.outreach import send as send_mod
from leadforge.outreach.approve import approve_messages
from tests.outreach_helpers import make_identity, make_mailbox, make_message, make_run, make_scored_business, make_target


def _row(country, entity_json=None):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE t(domain, enrich_json, address_country)")
    conn.execute("INSERT INTO t VALUES('x.co.uk', ?, ?)", (json.dumps(entity_json or {}), country))
    return conn.execute("SELECT * FROM t").fetchone()


def _email():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE c(kind, value, tier, affinity)")
    conn.execute("INSERT INTO c VALUES('email', 'info@x.co.uk', 'valid', 'own_domain')")
    return [conn.execute("SELECT * FROM c").fetchone()]


COMPANY = {"registry_checked": True, "registry_profile": {"company_number": "1", "company_status": "active"}}
SOLE_TRADER = {"registry_checked": True}   # the registry looked and found no company


def _elig(country, enrich, *, profile="uk"):
    entity = c.entity_type(_row(country, enrich))
    return c.email_eligibility(_row(country, enrich), _email(), entity, profile)


@pytest.mark.parametrize("country", [None, "", "  ", "Atlantis", "12"])
def test_c13_unknown_country_means_no_send(country):
    e = _elig(country, COMPANY)
    assert not e["eligible"] and e["basis"] == c.BASIS_NONE and "country_unknown" in e["reasons"]


@pytest.mark.parametrize("country", ["France", "FR", "Canada"])
def test_c13_a_country_with_no_rule_means_no_send(country):
    e = _elig(country, COMPANY)
    assert not e["eligible"] and e["basis"] == c.BASIS_NONE and "country_no_rule" in e["reasons"]


@pytest.mark.parametrize("country", ["Germany", "DE", "germany"])
@pytest.mark.parametrize("profile", ["uk", "eu", "us"])
def test_c13_germany_needs_consent_in_every_campaign_region(country, profile):
    e = _elig(country, COMPANY, profile=profile)
    assert not e["eligible"] and e["basis"] == c.BASIS_CONSENT and "consent_required" in e["reasons"]


@pytest.mark.parametrize("country", ["GB", "United Kingdom", "uk", "England"])
def test_c13_a_uk_sole_trader_needs_consent(country):
    e = _elig(country, SOLE_TRADER)
    assert not e["eligible"] and e["basis"] == c.BASIS_CONSENT and "consent_required" in e["reasons"]


@pytest.mark.parametrize("country,enrich,profile", [("GB", COMPANY, "uk"), ("United Kingdom", COMPANY, "uk"),
                                                    ("US", SOLE_TRADER, "us"), ("United States", COMPANY, "us")])
def test_c13_the_controls_stay_eligible(country, enrich, profile):
    e = _elig(country, enrich, profile=profile)
    assert e["eligible"] and e["basis"] == c.BASIS_B2B and e["reasons"] == []


def test_c13_the_country_names_the_tool_reads():
    assert [send_rules.country_code(v) for v in ("GB", "gb", "United Kingdom", "UK", "Germany", "de", "", None, "Atlantis")] == \
        ["GB", "GB", "GB", "GB", "DE", "DE", "", "", ""]


# ---- the real send path ---------------------------------------------------------------------------------------------
def _queued(conn, tag, country, *, enrich_extra=None):
    run_id = make_run(conn, f"run_{tag}")
    bid = make_scored_business(conn, run_id, id_=f"biz_{tag}", domain=f"{tag}.co.uk", email=f"owner@{tag}.co.uk",
                               enrich_extra=enrich_extra or {})
    conn.execute("UPDATE businesses SET address_country=? WHERE id=?", (country, bid))
    make_identity(conn, label=f"ident_{tag}")
    make_mailbox(conn, identity_label=f"ident_{tag}", address=f"sales@{tag}-agency.com")
    ident = conn.execute("SELECT id FROM sending_identities WHERE label=?", (f"ident_{tag}",)).fetchone()["id"]
    tid = make_target(conn, business_id=bid, campaign=f"camp_{tag}", identity_id=ident, state="drafted",
                      eligibility={"_tier": "A", "_region_profile": "us"})
    make_message(conn, target_id=tid, draft_hash="h1", subject="Hello", body_text="Body text here.")
    approve_messages(conn, campaign=f"camp_{tag}", approver="alice", all_drafted=True)
    conn.commit()
    return bid, tid


CASES = [
    ("nocountry", None, None, "country_unknown", False),
    ("france", "France", None, "country_no_rule", False),
    ("germany", "Germany", None, "consent_required", False),
    ("sole", "United Kingdom", {"registry_checked": True}, "consent_required", False),
    ("ukco", "United Kingdom", {"registry_checked": True,
                                "registry_profile": {"company_number": "1", "company_status": "active"}}, "", True),
    ("usco", "US", None, "", True),
]


@pytest.mark.parametrize("tag,country,enrich,reason,eligible", CASES)
def test_c13_the_live_recheck_in_outreach_send_applies_the_country_rule(cfg, conn, tag, country, enrich, reason, eligible):
    bid, tid = _queued(conn, tag, country, enrich_extra=enrich)
    target = conn.execute("SELECT * FROM outreach_targets WHERE id=?", (tid,)).fetchone()
    biz = conn.execute("SELECT * FROM businesses WHERE id=?", (bid,)).fetchone()
    e = send_mod._recompute_eligibility(conn, cfg, target, biz, False)
    assert e["eligible"] is eligible
    assert (reason in e["reasons"]) if reason else e["reasons"] == []


def test_c13_a_planted_german_lead_is_skipped_by_dry_run_and_writes_nothing(cfg, conn):
    _queued(conn, "germany", "Germany")
    _queued(conn, "usco", "US")
    ger = send_mod.dry_run(conn, cfg, campaign="camp_germany")
    assert ger["counts"]["would_send"] == 0 and ger["counts"]["skipped_ineligible"] == 1 and ger["artifacts"] == []
    ok = send_mod.dry_run(conn, cfg, campaign="camp_usco")
    assert ok["counts"]["would_send"] == 1 and len(ok["artifacts"]) == 1
