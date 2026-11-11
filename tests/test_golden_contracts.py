"""Golden contracts (slice L2, adoption plan section 3): what users and agents rely on, pinned to files in
tests/golden/. A change here is a contract change: it must be listed in the slice that makes it.

To re-record after a DELIBERATE change:  LF_UPDATE_GOLDEN=1 python -m pytest tests/test_golden_contracts.py
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from importlib.resources import files
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]
GOLDEN = Path(__file__).parent / "golden"


def _check(name: str, actual) -> None:
    path = GOLDEN / f"{name}.json"
    text = json.dumps(actual, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    if os.environ.get("LF_UPDATE_GOLDEN") == "1":
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
        return
    assert path.exists(), f"golden {path.name} missing: record it with LF_UPDATE_GOLDEN=1"
    expected = json.loads(path.read_text(encoding="utf-8"))
    assert actual == expected, f"contract '{name}' changed; if deliberate, list it in the slice and re-record"


def _frontmatter(p: Path) -> dict:
    m = re.match(r"^---\n(.*?)\n---\n", p.read_text(encoding="utf-8"), re.S)
    return yaml.safe_load(m.group(1))


# --- 8. the plugin contract: plugin name, skill names, both manifests -------------------------------
def test_golden_plugin_contract():
    claude = json.loads((REPO / ".claude-plugin/plugin.json").read_text(encoding="utf-8"))
    market = json.loads((REPO / ".claude-plugin/marketplace.json").read_text(encoding="utf-8"))
    codex = json.loads((REPO / ".codex-plugin/plugin.json").read_text(encoding="utf-8"))
    agents_market = json.loads((REPO / ".agents/plugins/marketplace.json").read_text(encoding="utf-8"))
    skills = {p.parent.name: _frontmatter(p)["name"] for p in sorted(REPO.glob("skills/*/SKILL.md"))}
    _check("plugin_contract", {
        "claude_plugin_name": claude["name"],
        "codex_plugin_name": codex["name"],
        "claude_marketplace": {"name": market["name"],
                               "plugins": [[p["name"], p.get("source")] for p in market["plugins"]]},
        "agents_marketplace_plugins": [p["name"] for p in agents_market["plugins"]],
        "skills": skills,
        "launcher": "bin/leadforge" if (REPO / "bin/leadforge").exists() else None,
    })


# --- 2. the agent contract: command names and exit codes ---------------------------------------------
def test_golden_agent_contract():
    import typer.main

    from leadforge import util
    from leadforge.agent_runner import AgentFailed, AgentUnavailable
    from leadforge.cli import app

    group = typer.main.get_command(app)
    _check("agent_contract", {
        "commands": sorted(group.commands),
        "exit_codes": {
            "LeadForgeError": util.LeadForgeError.exit_code,
            "EnvError": util.EnvError.exit_code,
            "InputError": util.InputError.exit_code,
            "ProviderFailed": util.ProviderFailed.exit_code,
            "AgentFailed": AgentFailed.exit_code,
            "AgentUnavailable": AgentUnavailable.exit_code,
        },
        "digest_prefix": "LF_DIGEST ",
    })


# --- 4. the sheet: column names and order ------------------------------------------------------------
def test_golden_sheet_columns():
    from leadforge import export

    _check("sheet_columns", {
        "COLUMNS": export.COLUMNS,
        "ACCOUNT_COLUMNS": export.ACCOUNT_COLUMNS,
        "DRAFT_COLUMNS": export.DRAFT_COLUMNS,
        "DEFAULT_COLUMNS": export.DEFAULT_COLUMNS,
    })


# --- 9. the scoring rules data ships in the package, byte for byte ----------------------------------
def test_golden_scoring_rules_data():
    raw = (files("leadforge") / "data" / "scoring.default.yaml").read_bytes()
    data = yaml.safe_load(raw.decode("utf-8"))
    _check("scoring_rules", {
        "sha256": hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest(),
        "top_keys": list(data),
        "factors": list(data["factors"]),
    })


@pytest.mark.parametrize("name", ["plugin_contract", "agent_contract", "sheet_columns", "scoring_rules", "autopilot_builtin_command",
                                  "campaign_file", "guardrail_defaults", "provenance", "workspace_schema",
                                  "dm_handoff", "draft_handoff", "sheet_export", "resume"])
def test_golden_files_are_committed(name):
    assert (GOLDEN / f"{name}.json").exists()


# --- 11. an operator's own agent command is used as written; today's built-in call is pinned -----------
def test_golden_agent_command(tmp_path, monkeypatch):
    from leadforge.agent_runner import resolve_command
    from leadforge.config import load_config

    monkeypatch.chdir(tmp_path)
    cfg = load_config(tmp_path)
    own = ["my-wrapper.cmd", "--flag", "value with spaces"]
    monkeypatch.setattr(cfg.agent, "command", own)
    assert resolve_command(cfg) == own  # verbatim: nothing added, nothing removed

    monkeypatch.setattr(cfg.agent, "command", None)
    monkeypatch.setattr("shutil.which", lambda _: "CLAUDE")
    # C1 changes this call on purpose (tools off); that change must be listed in its slice.
    _check("autopilot_builtin_command", {"argv": resolve_command(cfg), "isolate": cfg.agent.isolate})


# --- 1. the campaign file: its fields, "country required", and the hash that ignores caps ---------------
def _schema_shape(schema: dict) -> dict:
    """Field names and the required list of every object in a JSON schema (not types or descriptions)."""
    defs = {"ICP": schema, **schema.get("$defs", {})}
    return {name: {"fields": sorted(d.get("properties", {})), "required": sorted(d.get("required", []))}
            for name, d in sorted(defs.items()) if d.get("type") == "object"}


def test_golden_campaign_file(sample_icp):
    from pydantic import ValidationError

    from leadforge.models import ICP, Answers

    base = sample_icp.icp_hash()
    capped = sample_icp.model_copy(update={"caps": sample_icp.caps.model_copy(update={"max_leads": 9999}),
                                          "notes": "raised the cap"})
    moved = sample_icp.model_validate({**sample_icp.model_dump(mode="json"),
                                       "target": {**sample_icp.target.model_dump(mode="json"),
                                                  "geography": {"areas": ["Leeds"], "country": "GB"}}})
    assert capped.icp_hash() == base  # caps and notes are not part of the campaign's identity
    assert moved.icp_hash() != base
    no_country = sample_icp.model_dump(mode="json")
    del no_country["target"]["geography"]["country"]
    with pytest.raises(ValidationError, match="country"):
        ICP.model_validate(no_country)
    assert Answers.model_json_schema()["properties"] == ICP.model_json_schema()["properties"]
    _check("campaign_file", {"shape": _schema_shape(ICP.model_json_schema()), "sample_hash": base})


# --- 6. the guardrails that exist: their defaults ---------------------------------------------------------
def test_golden_guardrail_defaults():
    from leadforge.config import Config
    from leadforge.models import Caps
    from leadforge.util import HostThrottle

    cfg = Config()
    out = cfg.outreach
    _check("guardrail_defaults", {
        "politeness": {"delay_s": cfg.politeness.delay_s, "user_agent": cfg.politeness.user_agent},
        "throttle": {"jitter": HostThrottle(1.0).jitter},
        "caps": Caps().model_dump(),
        "outreach": {"armed": out.armed, "transport": out.transport,
                     "bounce_rate_pause": out.bounce_rate_pause, "complaint_rate_pause": out.complaint_rate_pause,
                     "require_email_confirmation": out.require_email_confirmation},
    })


# --- 7. where every fact came from: the provenance records and their tables --------------------------------
def _fresh_tables(tmp_path: Path) -> dict:
    from leadforge import db

    conn = db.connect(tmp_path / "fresh.sqlite3")
    names = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
    tables = {n: [r[1] for r in conn.execute(f"PRAGMA table_info('{n}')")] for n in names}
    conn.close()
    return tables


def test_golden_provenance(tmp_path):
    from leadforge.models import EnrichmentObservation, Evidence

    tables = _fresh_tables(tmp_path)
    _check("provenance", {
        "Evidence": sorted(Evidence.model_fields),
        "EnrichmentObservation": sorted(EnrichmentObservation.model_fields),
        "tables": {n: cols for n, cols in tables.items() if n in ("evidence", "enrichment_observations")},
    })


# --- 10. a workspace made by the current version still opens ------------------------------------------------
SAVED_WORKSPACE = GOLDEN / "workspace_current.sqlite3"


def test_golden_saved_workspace_opens(tmp_path):
    """`workspace_current.sqlite3` was made by this version (schema 7) with one made-up business in it. A
    new version that cannot open it breaks every user's workspace. Re-make it only together with a
    schema change that the slice lists."""
    import shutil

    from leadforge import db

    copy = tmp_path / "db.sqlite3"
    shutil.copyfile(SAVED_WORKSPACE, copy)
    conn = db.connect(copy)  # refuses any other schema_version
    row = conn.execute("SELECT name, website FROM businesses WHERE id='biz_golden'").fetchone()
    assert tuple(row) == ("Golden Example Plumbing", "https://plumbing.example")
    conn.close()
    _check("workspace_schema", _fresh_tables(tmp_path))


# --- 3. the hand-off files: a dm batch, the label lines `dm apply` accepts, a draft packet, the gate ------------
# Every value below is made up (.example domains, invented names). The CLI verb that reads labels back is
# `dm apply` (there is no `dm import`).
def _dm_workspace(conn):
    from leadforge import db
    from leadforge.models import Business, Person

    rid = db.create_run(conn, "icp.yaml", "h")
    for bid, name, reviews in (("biz_dm_a", "Example Plumbing Co", 30), ("biz_dm_b", "Sample Heating Ltd", 20),
                               ("biz_dm_c", "Demo Drains", 10)):
        db.upsert_business(conn, Business(id=bid, run_id=rid, name=name, category="plumber", source="gosom",
                                          dedupe_key=f"dk-{bid}", review_count=reviews))
    db.add_person(conn, Person(business_id="biz_dm_a", name="Alex Example", title="Owner",
                               snippet="Alex Example founded the firm.", origin="heuristic"))
    db.add_person(conn, Person(business_id="biz_dm_a", name="Sam Sample", title="Engineer",
                               snippet="Sam Sample fitted our boiler.", origin="heuristic"))
    db.add_person(conn, Person(business_id="biz_dm_b", name="Jo Placeholder", title="Director",
                               snippet="Jo Placeholder, director.", origin="registry", labeled_by="registry"))
    db.add_person(conn, Person(business_id="biz_dm_c", name="Pat Fictional", title="Apprentice",
                               snippet="Pat Fictional answered the phone.", origin="gbp", labeled_by="gbp"))
    conn.commit()
    return rid


def test_golden_dm_handoff(conn, sample_icp, tmp_path):
    import typer.main

    from leadforge import db
    from leadforge.cli import app
    from leadforge.enrich.dm import apply_labels, export_batch
    from leadforge.util import InputError

    _dm_workspace(conn)
    ndjson, tsv = tmp_path / "dm_batch.ndjson", tmp_path / "dm_batch.tsv"
    first = export_batch(conn, sample_icp, ndjson, max_biz=2)
    export_batch(conn, sample_icp, tsv, max_biz=60, tsv=True)
    batch = [json.loads(ln) for ln in ndjson.read_text(encoding="utf-8").splitlines()]
    tsv_rows = [ln.split("\t") for ln in tsv.read_text(encoding="utf-8").splitlines()]

    labels = tmp_path / "dm_labels.ndjson"  # the canonical NDJSON line, the documented TSV line, a reject, a skip
    labels.write_text(json.dumps({"biz": "biz_dm_a", "pick": 0, "confidence": 0.9}) + "\n"
                      + "biz_dm_b\t0\t0.8\tManaging Director\n"
                      + json.dumps({"biz": "biz_dm_c", "pick": -1}) + "\n"
                      + json.dumps({"biz": "biz_dm_a"}) + "\n", encoding="utf-8")
    counts = apply_labels(conn, labels)
    people = [{k: p[k] for k in ("business_id", "name", "title", "is_dm", "dm_confidence", "labeled_by")}
              for b in ("biz_dm_a", "biz_dm_b", "biz_dm_c") for p in db.people_for(conn, b)]
    bad = tmp_path / "bad.ndjson"
    bad.write_text("not a label line\n", encoding="utf-8")
    with pytest.raises(InputError, match="bad label line"):
        apply_labels(conn, bad)
    after = export_batch(conn, sample_icp, tmp_path / "empty.ndjson")

    dm = typer.main.get_command(app).commands["dm"]
    _check("dm_handoff", {
        "cli": {name: sorted(o for p in cmd.params for o in getattr(p, "opts", []))
                for name, cmd in sorted(dm.commands.items())},
        "batch_returns": list(first),
        "batch_lines": batch,
        "tsv_rows": tsv_rows,
        "apply_counts": counts,
        "people_after_apply": people,
        "batch_after_apply": list(after),
        "empty_batch_text": (tmp_path / "empty.ndjson").read_text(encoding="utf-8"),
    })


def _norm_at(obj):
    """Fact timestamps (`at`) are provenance, not contract: replaced so the golden never holds a clock."""
    if isinstance(obj, dict):
        return {k: ("<at>" if k == "at" else _norm_at(v)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_norm_at(v) for v in obj]
    return obj


def test_golden_draft_packet_and_gate(cfg, conn, tmp_path):
    from leadforge import db
    from leadforge.draft import service
    from leadforge.draft.gate import check_draft
    from leadforge.draft.template import template_draft
    from leadforge.models import ICP, Business, Score, ScoreFactor

    icp = ICP.model_validate({
        "campaign": "golden-draft",
        "offer": {"what": "website refresh", "value_prop": "more bookings", "sender": "Example Sender"},
        "target": {"categories": ["plumber"], "geography": {"areas": ["Nottingham"], "country": "GB"}},
        "compliance": {"region_profile": "uk"},
    })
    rid = db.create_run(conn, "icp.yaml", "h")
    db.upsert_business(conn, Business(
        id="biz_draft", name="Example Plumbing Co", category="Plumber", address_city="Nottingham",
        website="https://plumbing-co.example", rating=4.6, review_count=120, source="gosom",
        dedupe_key="dk-biz-draft",
        enrich={"crawled_at": "2026-01-01T00:00:00Z", "pages": 1, "signals": {"careers": True}}))
    db.save_score(conn, Score(business_id="biz_draft", run_id=rid, total=85, tier="A",
                              factors=[ScoreFactor(factor="x", group="fit", weight=1, score=1, points=1, why="w")]))
    conn.commit()
    ids = service.ensure_targets(conn, rid, {"A"}, "golden-draft")
    lines, counts = service.build_packets(conn, cfg, icp, ids, "gainlev_leadgen")
    path = tmp_path / "packets.ndjson"
    path.write_text("\n".join(json.dumps(ln) for ln in lines) + "\n", encoding="utf-8")
    packet = service.load_packets(path)[ids[0]]
    assert packet == lines[1]["packet"]

    clean = template_draft(packet)
    invented_fact = {"subject": "Quick note for Example Plumbing Co",
                     "observation": "Noticed Example Plumbing Co has online booking.", "used_fact": "booking"}
    invented_number = {"subject": "Quick note for Example Plumbing Co",
                       "observation": "Noticed Example Plumbing Co has 5.0 stars (300 reviews).",
                       "used_fact": "rating"}
    gate = {name: check_draft(packet, d) for name, d in
            (("template", clean), ("invented_fact", invented_fact), ("invented_number", invented_number))}
    applied = service.apply_drafts(conn, cfg, {ids[0]: packet},
                                   [{"target": ids[0], **clean}, {"target": ids[0], **invented_fact}],
                                   author="agent")
    stored = [dict(r) for r in conn.execute(
        "SELECT step, state, used_fact, author FROM messages WHERE target_id=? ORDER BY step", (ids[0],))]
    _check("draft_handoff", {
        "header": lines[0],
        "line_keys": sorted(lines[1]),
        "line": _norm_at({k: v for k, v in lines[1].items() if k != "target"}),
        "build_counts": counts,
        "template_draft": clean,
        "gate": gate,
        "apply_counts": applied,
        "stored_messages": stored,
    })


# --- 4. the sheet: four tabs, no empty cell, the CSV mirror, report.json ------------------------------------
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}(?:[T ][0-9:.]+Z?)?")


def test_golden_sheet_export(cfg, conn):
    import csv

    from openpyxl import load_workbook

    from leadforge import db
    from leadforge.export import export_run
    from leadforge.models import ICP, Business, Contact, Person, Score, ScoreFactor

    icp = ICP.model_validate({"campaign": "golden-sheet", "offer": {"what": "website refresh"},
                              "target": {"categories": ["plumber"],
                                         "geography": {"areas": ["Nottingham"], "country": "GB"}}})
    rid = db.create_run(conn, "icp.yaml", "h")
    db.upsert_business(conn, Business(id="full", name="Example Plumbing Co", source="gosom", category="Plumber",
                                      website="https://plumbing-co.example", phone_e164="+441154960100",
                                      address_city="Nottingham", rating=4.6, review_count=120,
                                      dedupe_key="dk-full"))
    db.upsert_business(conn, Business(id="bare", name="Sample Heating Ltd", source="gosom", dedupe_key="dk-bare"))
    db.add_person(conn, Person(business_id="full", name="Alex Example", title="Owner", labeled_by="agent",
                               is_dm=1, dm_confidence=0.9))
    db.add_contact(conn, Contact(business_id="full", kind="email", value="alex@plumbing-co.example",
                                 label="personal", tier="valid", affinity="own_domain"))
    for bid, total, tier in (("full", 80, "A"), ("bare", 40, "C")):
        db.save_score(conn, Score(business_id=bid, run_id=rid, total=total, tier=tier,
                                  factors=[ScoreFactor(factor="x", group="fit", weight=1, score=1, points=1,
                                                       why="w")]))
    conn.commit()
    arts = [Path(a) for a in export_run(conn, icp, rid, cfg.exports_dir, ["xlsx", "csv"], cfg=cfg)]
    assert all(a.parent == cfg.exports_dir / rid for a in arts)

    wb = load_workbook(next(a for a in arts if a.suffix == ".xlsx"))
    leads = [[c.value for c in row] for row in wb["Leads"].iter_rows()]
    empty = [(r, c) for r, row in enumerate(leads) for c, v in enumerate(row) if v is None or str(v).strip() == ""]
    assert not empty, f"empty Leads cells at {empty[:5]}"
    with open(next(a for a in arts if a.suffix == ".csv"), encoding="utf-8-sig", newline="") as fh:
        csv_rows = list(csv.reader(fh))
    assert csv_rows == [[str(v) for v in row] for row in leads]  # the CSV mirrors the Leads tab cell for cell
    bare = dict(zip(leads[0], leads[-1], strict=True))
    assert bare["Business"] == "Sample Heating Ltd"
    report = json.loads(next(a for a in arts if a.name == "report.json").read_text(encoding="utf-8"))
    assert report.pop("run") == rid and _DATE.fullmatch(report.pop("generated"))
    _check("sheet_export", {
        "artifacts": [a.name for a in arts],
        "tabs": wb.sheetnames,
        "csv_header": csv_rows[0],
        "bare_row": {k: _DATE.sub("<date>", str(v)) for k, v in bare.items()},
        "report_keys": sorted([*report, "run", "generated"]),
        "report": report,
    })


# --- 5. runs that resume: a re-started run continues where it stopped and duplicates nothing ---------------------
@pytest.fixture
def offline_pipeline(monkeypatch):
    """Discovery, crawl, registry and email checks replaced with made-up, offline answers; calls counted."""
    from leadforge.enrich.crawler import CrawlResult, Page, SiteCrawler
    from leadforge.models import RawListing
    from leadforge.util import now_iso

    calls = {"fetch": 0, "crawl": 0}

    def fetch(self, query, limit=None):
        calls["fetch"] += 1
        return [
            RawListing(provider="gosom", fetched_at=now_iso(), data={
                "title": "Example Plumbing Co", "category": "plumber", "address": "1 Example Street, Nottingham",
                "complete_address": {"street": "1 Example Street", "city": "Nottingham", "postal_code": "NG1 1AA",
                                     "country": "United Kingdom"},
                "phone": "0115 496 0100", "web_site": "https://plumbing-co.example",
                "review_rating": "4.6", "review_count": "120", "place_id": "PID_GOLDEN_A"}),
            RawListing(provider="gosom", fetched_at=now_iso(), data={
                "title": "Sample Heating Ltd", "category": "plumber", "address": "2 Sample Road, Nottingham",
                "phone": "0115 496 0200", "review_rating": "4.1", "review_count": "15",
                "place_id": "PID_GOLDEN_B"}),
        ]

    def crawl(self, website, business_domain=None):
        calls["crawl"] += 1
        if "plumbing-co.example" in website:
            text = "Owner Alex Example founded the firm in 2010. Contact alex@plumbing-co.example"
            html = f"<html><body>{text} <a href='mailto:alex@plumbing-co.example'>email</a></body></html>"
            return CrawlResult(ok=True, pages=[Page(website, html, text)],
                               signals={"https": True, "stale_site": False, "booking_hint": False})
        return CrawlResult(ok=False, error="unreachable")

    monkeypatch.setattr("leadforge.pipeline.ensure_ready", lambda cfg: None)
    monkeypatch.setattr("leadforge.providers.gosom.GosomProvider.available", lambda self: (True, "offline"))
    monkeypatch.setattr("leadforge.providers.gosom.GosomProvider.fetch", fetch)
    monkeypatch.setattr(SiteCrawler, "crawl", crawl)
    monkeypatch.setattr("leadforge.providers.registry.get_registries", lambda cfg: [])
    monkeypatch.setattr("leadforge.enrich.runner.validate_email",
                        lambda email, label, cfg: ("valid" if label == "personal" else "role", {}))
    return calls


def test_golden_resume(cfg, offline_pipeline, tmp_path):
    import yaml

    from leadforge import db
    from leadforge.enrich.dm import apply_labels
    from leadforge.models import ICP
    from leadforge.pipeline import run_pipeline

    icp = ICP.model_validate({"campaign": "golden-resume", "offer": {"what": "website refresh"},
                              "target": {"categories": ["plumber"],
                                         "geography": {"areas": ["Nottingham"], "country": "GB"}},
                              "decision_maker": {"titles_priority": ["Owner", "Director"]}})
    icp_path = tmp_path / "icp.yaml"
    icp_path.write_text(yaml.safe_dump(icp.model_dump(mode="json")), encoding="utf-8")
    first_run: list[str] = []

    def snap(r: dict) -> dict:
        conn = db.connect(cfg.db_path)

        def one(sql: str) -> int:
            return conn.execute(sql).fetchone()[0]

        first_run[:1] = first_run[:1] or [r["run"]]
        out = {"stage": r["stage"], "same_run": r["run"] == first_run[0], "counts": r["counts"],
               "runs": one("SELECT COUNT(*) FROM runs"), "businesses": one("SELECT COUNT(*) FROM businesses"),
               "people": one("SELECT COUNT(*) FROM people"), "contacts": one("SELECT COUNT(*) FROM contacts"),
               "scores": one("SELECT COUNT(*) FROM scores"),
               "queries": {s: n for s, n in conn.execute(
                   "SELECT status, COUNT(*) FROM queries GROUP BY status ORDER BY status")},
               "calls": dict(offline_pipeline)}
        conn.close()
        return out

    steps = {"1_first_run": snap(run_pipeline(cfg, icp, icp_path, autopilot=False))}
    steps["2_resume_while_waiting_for_labels"] = snap(run_pipeline(cfg, icp, icp_path, resume=True, autopilot=False))
    conn = db.connect(cfg.db_path)
    db.set_stage(conn, first_run[0], "enriching")  # the process died mid-enrich
    conn.close()
    steps["3_resume_after_kill_mid_enrich"] = snap(run_pipeline(cfg, icp, icp_path, resume=True, autopilot=False))
    conn = db.connect(cfg.db_path)
    biz = db.dm_pending(conn, 10)[0]["id"]
    labels = tmp_path / "dm_labels.ndjson"
    labels.write_text(json.dumps({"biz": biz, "pick": 0, "confidence": 0.9}) + "\n", encoding="utf-8")
    apply_labels(conn, labels)
    conn.close()
    resumed = run_pipeline(cfg, icp, icp_path, resume=True, autopilot=False)
    resumed["counts"] = sorted(resumed["counts"])  # export digest counts: their keys are the contract here
    steps["4_resume_after_dm_apply"] = snap(resumed)
    steps["5_resume_when_already_exported"] = snap(run_pipeline(cfg, icp, icp_path, resume=True, autopilot=False))
    _check("resume", steps)
