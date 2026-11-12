"""L6 item 4: `purge` and its protections (C5). Every business and person here is invented.

Time is a value handed in (`NOW`, or `leadforge.util.utcnow` patched): no test sleeps and none reads the real date.
"""
import hashlib
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from leadforge import db
from leadforge.cli import app
from leadforge.config import load_config
from leadforge.retention import add_months, purge

NOW = datetime(2026, 11, 12, 9, 0, tzinfo=UTC)
RUNS = {"r_old": "2025-10-01T08:00:00Z",    # 13 months before NOW: past the limit
        "r_soon": "2025-12-01T08:00:00Z",   # 11.4 months: due on 2026-12-01, inside the next 30 days
        "r_mid": "2025-12-15T08:00:00Z",    # 10.9 months: due on 2026-12-15, outside the next 30 days
        "r_new": "2026-10-20T08:00:00Z"}


def digest_of(output: str) -> dict:
    return json.loads([ln for ln in output.splitlines() if ln.startswith("LF_DIGEST ")][-1][len("LF_DIGEST "):])


def snapshot(root: Path) -> dict[str, str]:
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file()}


def make_workspace(ws: Path) -> Path:
    """10 businesses: A and C first found in r_old (C was refreshed yesterday), D has no first_run_id (= the workspace's
    first run, r_old), B in r_mid, E in r_soon, five in r_new. Each of A, B, C carries a contact, a person and evidence."""
    data = ws / "leadforge_data"
    data.mkdir(parents=True, exist_ok=True)
    conn = db.connect(data / "db.sqlite3")
    for rid, started in RUNS.items():
        conn.execute("INSERT INTO runs(id,started_at,stage) VALUES(?,?,'exported')", (rid, started))
    rows = [("A", "r_old", "2025-10-01T08:00:00Z"), ("B", "r_mid", "2026-11-11T08:00:00Z"),
            ("C", "r_old", "2026-11-11T08:00:00Z"), ("D", None, "2026-11-11T08:00:00Z"), ("E", "r_soon", "2026-11-11T08:00:00Z")]
    rows += [(f"N{i}", "r_new", "2026-10-20T08:00:00Z") for i in range(5)]
    for bid, run, seen in rows:
        conn.execute("INSERT INTO businesses(id,name,name_norm,dedupe_key,first_run_id,last_seen_at) VALUES(?,?,?,?,?,?)",
                     (bid, f"Invented {bid} Works", f"invented {bid.lower()} works", f"k_{bid}", run, seen))
        conn.execute("INSERT INTO contacts(business_id,kind,value) VALUES(?,?,?)", (bid, "email", f"{bid.lower()}@works-{bid.lower()}.example"))
        conn.execute("INSERT INTO people(business_id,name) VALUES(?,?)", (bid, f"Person {bid}"))
        conn.execute("INSERT INTO evidence(business_id,fact) VALUES(?,?)", (bid, "fact"))
    conn.execute("INSERT INTO outreach_targets(business_id,campaign,state) VALUES('A','c','drafted')")
    tid = conn.execute("SELECT id FROM outreach_targets").fetchone()[0]
    conn.execute("INSERT INTO messages(target_id,subject,body_text) VALUES(?,?,?)", (tid, "s", "body"))
    conn.commit()
    conn.close()
    return data / "db.sqlite3"


def ids(path: Path) -> set[str]:
    c = sqlite3.connect(path)
    try:
        return {r[0] for r in c.execute("SELECT id FROM businesses")}
    finally:
        c.close()


def count(path: Path, table: str, where: str = "1") -> int:
    c = sqlite3.connect(path)
    try:
        return c.execute(f"SELECT COUNT(*) FROM {table} WHERE {where}").fetchone()[0]
    finally:
        c.close()


ALL = {"A", "B", "C", "D", "E"} | {f"N{i}" for i in range(5)}


def test_first_run_only_reports_then_13_months_go_11_stay_refresh_does_not_renew(tmp_path):
    path = make_workspace(tmp_path)
    cfg = load_config(tmp_path)
    first = purge(cfg, NOW, "auto")
    assert first["state"] == "armed" and first["deleted"] == 0 and first["expired"] == 3   # A, C, D would go
    assert ids(path) == ALL and count(path, "contacts") == 10          # the first run deleted nothing
    second = purge(cfg, NOW, "auto")
    assert second["state"] == "purged" and second["deleted"] == 3
    assert ids(path) == ALL - {"A", "C", "D"}                           # A 13 months, C refreshed but still old, D empty = first run
    assert "B" in ids(path) and "E" in ids(path)                        # 11 months stay
    for table in ("contacts", "people", "evidence"):                    # everything attached went with them
        assert count(path, table, "business_id IN ('A','C','D')") == 0
        assert count(path, table, "business_id IN ('B','E','N0')") == 3
    assert count(path, "outreach_targets") == 0 and count(path, "messages") == 0


def test_every_run_reports_what_expires_in_30_days(tmp_path, monkeypatch, capsys):
    make_workspace(tmp_path)
    cfg = load_config(tmp_path)
    purge(cfg, NOW, "auto")                                              # arm
    from leadforge import cli
    monkeypatch.setattr("leadforge.util.utcnow", lambda: NOW)
    monkeypatch.chdir(tmp_path)
    counts = cli._start_of_run_purge(cfg)
    assert counts == {"purged": 3, "expiring_30d": 1}                    # only E is due within 30 days (B is due in 33)
    assert "1 records expire in the next 30 days" in capsys.readouterr().err
    assert purge(cfg, NOW, "report")["expiring_30d"] == 1


def test_a_clock_a_year_ahead_deletes_nothing_and_stops(tmp_path, monkeypatch):
    path = make_workspace(tmp_path)
    cfg = load_config(tmp_path)
    purge(cfg, NOW, "auto")                                              # arm
    (tmp_path / "icp.yaml").write_text(yaml.safe_dump({"campaign": "c"}), encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("leadforge.util.utcnow", lambda: datetime(2027, 11, 12, tzinfo=UTC))
    monkeypatch.setattr("leadforge.intake.load_icp", lambda p: object())
    before = snapshot(tmp_path)
    res = CliRunner().invoke(app, ["run"])
    assert res.exit_code == 4, res.output
    d = digest_of(res.output)
    assert d["ok"] is False and "purge --apply" in d["next"]
    assert ids(path) == ALL                                              # nothing deleted
    assert {k: v for k, v in snapshot(tmp_path).items() if not k.endswith(("-wal", "-shm", ".sqlite3"))} == \
           {k: v for k, v in before.items() if not k.endswith(("-wal", "-shm", ".sqlite3"))}
    # the explicit command is what deletes more than half
    res = CliRunner().invoke(app, ["purge", "--apply"])
    assert res.exit_code == 0 and ids(path) == set()


def test_run_digest_carries_the_purge_numbers(tmp_path, monkeypatch):
    make_workspace(tmp_path)
    cfg = load_config(tmp_path)
    purge(cfg, NOW, "auto")
    (tmp_path / "icp.yaml").write_text("x", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("leadforge.util.utcnow", lambda: NOW)
    monkeypatch.setattr("leadforge.intake.load_icp", lambda p: object())
    monkeypatch.setattr("leadforge.pipeline.run_pipeline", lambda *a, **k: {
        "ok": True, "run": "r", "stage": "exported", "counts": {}, "warnings": [], "next": None})
    res = CliRunner().invoke(app, ["run"])
    assert res.exit_code == 0, res.output
    assert digest_of(res.output)["counts"]["expiring_30d"] == 1


def test_a_detached_run_makes_one_retention_pass_not_two(tmp_path, monkeypatch):
    """`run --detach` (the skill's way to start a run) makes the pass in the parent; the child it starts runs `run` again
    and must not make a second one, or the first run after the upgrade would arm and then delete seconds later."""
    from leadforge import cli

    path = make_workspace(tmp_path)
    (tmp_path / "icp.yaml").write_text("x", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("leadforge.util.utcnow", lambda: NOW)
    monkeypatch.setattr("leadforge.intake.load_icp", lambda p: object())
    monkeypatch.setattr("leadforge.pipeline.ensure_run", lambda *a, **k: "r_new")
    monkeypatch.setattr("leadforge.pipeline.run_pipeline", lambda *a, **k: {
        "ok": True, "run": "r_new", "stage": "exported", "counts": {}, "warnings": [], "next": None})
    spawned = []
    monkeypatch.setattr(cli, "_spawn_detached", lambda cmd, log, cwd: spawned.append(cmd) or 4242)
    parent = CliRunner().invoke(app, ["run", "--detach"])
    assert parent.exit_code == 0, parent.output
    assert ids(path) == ALL and digest_of(parent.output)["counts"]["purged"] == 0     # the first pass only arms
    child = CliRunner().invoke(app, spawned[0][3:])     # the child's own arguments, run in this process
    assert child.exit_code == 0, child.output
    assert ids(path) == ALL                                              # and the child deleted nothing either
    assert digest_of(child.output)["counts"].get("purged") is None


def test_a_half_upgraded_workspace_stops_the_command(tmp_path, monkeypatch):
    path = make_workspace(tmp_path)
    c = sqlite3.connect(path)
    c.execute("ALTER TABLE businesses DROP COLUMN first_run_id")         # a table of the old shape: this version expects the column
    c.commit()
    c.close()
    before = snapshot(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("leadforge.util.utcnow", lambda: NOW)
    for argv in (["purge", "--apply"], ["purge"]):
        res = CliRunner().invoke(app, argv)
        assert res.exit_code == 4, (argv, res.output)
        assert "half upgraded" in digest_of(res.output)["warnings"][0]
    assert snapshot(tmp_path) == before                                  # nothing deleted, nothing written
    # a marker nobody can read is a half-finished upgrade too
    path2 = make_workspace(tmp_path / "second")
    c = sqlite3.connect(path2)
    c.execute("INSERT INTO meta(key,value) VALUES('retention_armed_at','not a date')")
    c.commit()
    c.close()
    with pytest.raises(Exception, match="half upgraded"):
        purge(load_config(tmp_path / "second"), NOW, "apply")
    assert ids(path2) == ALL


def test_old_schema_workspace_is_refused_by_purge_and_unchanged(tmp_path, monkeypatch):
    path = make_workspace(tmp_path)
    c = sqlite3.connect(path)
    c.execute("UPDATE meta SET value='4' WHERE key='schema_version'")
    c.commit()
    c.close()
    before = snapshot(tmp_path)
    monkeypatch.chdir(tmp_path)
    res = CliRunner().invoke(app, ["purge", "--apply"])
    assert res.exit_code == 4 and "older LeadForge" in digest_of(res.output)["warnings"][0]
    assert snapshot(tmp_path) == before


def test_everything_wipes_a_workspace_of_any_age_without_opening_the_database(tmp_path, monkeypatch):
    path = make_workspace(tmp_path)
    c = sqlite3.connect(path)
    c.execute("UPDATE meta SET value='4' WHERE key='schema_version'")
    c.commit()
    c.close()
    data = tmp_path / "leadforge_data"
    (data / "bin").mkdir()
    (data / "bin" / "helper.txt").write_text("kept", encoding="utf-8")
    (data / ".doctor_ok.json").write_text("{}", encoding="utf-8")
    (data / "cache").mkdir()
    (data / "cache" / "gosom_x.json").write_text("{}", encoding="utf-8")
    (tmp_path / "dm_batch.ndjson").write_text("{}\n", encoding="utf-8")
    (tmp_path / "leadforge.yaml").write_text("retention:\n  months: 6\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    def opened(*a, **k):
        raise AssertionError("purge --everything opened the database")
    monkeypatch.setattr(db, "connect", opened)
    monkeypatch.setattr(sqlite3, "connect", opened)

    refused = CliRunner().invoke(app, ["purge", "--everything"])
    assert refused.exit_code == 2 and path.exists()                      # no --yes: nothing happens
    res = CliRunner().invoke(app, ["purge", "--everything", "--yes"])
    assert res.exit_code == 0, res.output
    left = {p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*") if p.is_file()}
    assert left == {"leadforge_data/bin/helper.txt", "leadforge_data/.doctor_ok.json", "leadforge.yaml"}
    assert not (data / "cache").exists()                                 # emptied folders go too
    assert digest_of(res.output)["counts"]["files_removed"] == 3        # db, cache file, dm_batch


def test_the_period_can_be_shortened_never_lengthened(tmp_path):
    make_workspace(tmp_path)
    (tmp_path / "leadforge.yaml").write_text("retention:\n  months: 6\n", encoding="utf-8")
    cfg = load_config(tmp_path)
    assert purge(cfg, NOW, "report")["expired"] == 5                     # A, B, C, D, E are all older than 6 months; the five new ones are not
    (tmp_path / "leadforge.yaml").write_text("retention:\n  months: 24\n", encoding="utf-8")
    with pytest.raises(Exception, match="less than or equal to 12"):
        load_config(tmp_path)


def bare(ws: Path, started: list[str], first_runs: list[str | None]) -> Path:
    data = ws / "leadforge_data"
    data.mkdir(parents=True)
    conn = db.connect(data / "db.sqlite3")
    for i, s in enumerate(started):
        conn.execute("INSERT INTO runs(id,started_at,stage) VALUES(?,?,'exported')", (f"r{i}", s))
    for i, run in enumerate(first_runs):
        conn.execute("INSERT INTO businesses(id,name,name_norm,dedupe_key,first_run_id) VALUES(?,?,?,?,?)",
                     (f"b{i}", f"B{i}", f"b{i}", f"k{i}", run))
    conn.commit()
    conn.close()
    return data / "db.sqlite3"


def test_the_day_of_expiry_and_the_30_day_edge_are_inclusive(tmp_path):
    # due exactly now: expired. due exactly now + 30 days: counts as expiring. one second later: neither.
    bare(tmp_path, ["2025-11-12T09:00:00Z", "2025-12-12T09:00:00Z", "2025-12-12T09:00:01Z"], ["r0", "r1", "r2"] + ["r2"] * 6)
    cfg = load_config(tmp_path)
    res = purge(cfg, NOW, "report")
    assert res["expired"] == 1 and res["expiring_30d"] == 1 and res["total"] == 9


def test_exactly_half_may_go_automatically_more_than_half_may_not(tmp_path):
    path = bare(tmp_path, ["2025-01-01T00:00:00Z", "2026-11-01T00:00:00Z"], ["r0", "r0", "r1", "r1"])
    cfg = load_config(tmp_path)
    assert purge(cfg, NOW, "auto")["state"] == "armed"
    assert purge(cfg, NOW, "auto")["state"] == "purged" and ids(path) == {"b2", "b3"}      # 2 of 4
    path2 = bare(tmp_path / "w2", ["2025-01-01T00:00:00Z", "2026-11-01T00:00:00Z"], ["r0", "r0", "r0", "r1"])
    cfg2 = load_config(tmp_path / "w2")
    purge(cfg2, NOW, "auto")
    assert purge(cfg2, NOW, "auto")["state"] == "stopped_over_half" and len(ids(path2)) == 4  # 3 of 4


def test_a_workspace_with_no_run_has_no_age_and_nothing_expires(tmp_path):
    path = bare(tmp_path, [], [None, None])
    cfg = load_config(tmp_path)
    purge(cfg, NOW, "auto")
    res = purge(cfg, NOW, "auto")
    assert res["state"] == "nothing" and res["expired"] == 0 and ids(path) == {"b0", "b1"}


def test_marker_flag_and_no_workspace(tmp_path):
    assert purge(load_config(tmp_path / "empty"), NOW, "auto") == {"state": "no_workspace", "deleted": 0, "expiring_30d": 0, "months": 12}
    bare(tmp_path, ["2026-11-01T00:00:00Z"], ["r0"])
    cfg = load_config(tmp_path)
    assert purge(cfg, NOW, "report")["armed"] is False      # a report never arms
    assert purge(cfg, NOW, "auto")["state"] == "armed"
    assert purge(cfg, NOW, "report")["armed"] is True


def test_month_arithmetic_clamps_the_day():
    assert add_months(datetime(2025, 1, 15, tzinfo=UTC), 12) == datetime(2026, 1, 15, tzinfo=UTC)
    assert add_months(datetime(2025, 1, 31, tzinfo=UTC), 1) == datetime(2025, 2, 28, tzinfo=UTC)
    assert add_months(datetime(2024, 2, 29, tzinfo=UTC), 12) == datetime(2025, 2, 28, tzinfo=UTC)
    assert add_months(datetime(2025, 10, 1, tzinfo=UTC), 12) == datetime(2026, 10, 1, tzinfo=UTC)
