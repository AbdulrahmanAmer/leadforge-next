"""`leadforge window <name>` (slice L11a): the 21 commands, their shapes, the seam's rules.

Everything here is invented: `.example` domains, phone numbers from the Ofcom drama ranges, no request leaves the machine
(the geocoder is refused, the planned area has a fixed box). `run_start` runs against a stand-in pipeline that only reports
progress. Goldens: tests/golden/window/<name>.json; re-record a deliberate change with LF_UPDATE_GOLDEN=1.
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
import os
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml

from leadforge import db, util
from leadforge import window as win
from leadforge.window import commands, keys

GOLDEN = Path(__file__).parent / "golden" / "window"
RID = "run_20261101_090000_ab12"
CAMPAIGN = "bristol-mot-garage"
NOW = datetime(2026, 11, 12, 10, 0, 0, tzinfo=UTC)

# ------------------------------------------------------------------ the types of app/ui/src/engine.ts, field for field
S, N, B, NULL = "string", "number", "boolean", "null"
STAGE = {"discover", "enrich", "label", "score", "draft", "export"}
STATE = {"running", "finished", "stopped", "failed"}
# engine.ts ErrorKind on origin/slice/L11-window, copied: the kinds the screens know
SEVEN = {"failed", "usage", "environment", "input", "source", "keyring", "missing"}


def gap(t):
    """A field the engine cannot supply yet: null allowed (each one is listed in the slice file's seam changes)."""
    return (NULL, t)


TYPES = {
    "CampaignPlan": {"campaign": S, "searches": N, "estimatedBusinesses": N, "estimatedSites": N, "estimatedMinutes": N,
                     "warnings": [S], "retentionMonths": N},
    "RunCounts": {"businesses": N, "contacts": N, "purged": gap(N), "expiringIn30Days": gap(N)},
    "RunStatus": {"runId": S, "campaign": gap(S), "state": STATE, "stage": STAGE, "done": gap(N), "total": (NULL, N),
                  "etaSeconds": (NULL, N), "counts": "RunCounts", "startedAt": S, "reason": (NULL, S)},
    "RunHandle": {"runId": S},
    "SheetFile": {"kind": {"xlsx", "csv", "report"}, "path": S},
    "Sheet": {"runId": S, "writtenAt": S, "leads": N, "tabs": [{"name": S, "rows": N}], "files": ["SheetFile"], "highlights": [S]},
    "Campaign": {"runId": S, "name": gap(S), "kinds": [S], "places": [S], "source": gap({"dvsa", "companies_house"}),
                 "state": STATE, "stage": STAGE, "startedAt": S, "keptUntil": gap(S), "businesses": N, "withEmail": N,
                 "withPhone": N, "tiers": {"a": N, "b": N, "c": N}, "sheet": (NULL, "Sheet")},
    "Person": {"id": S, "name": S, "role": S, "business": S, "domain": S, "email": (NULL, S), "phone": (NULL, S),
               "source": gap(S), "foundAt": gap(S), "campaign": gap(S), "suppressed": B},
    "PeoplePage": {"people": ["Person"], "total": N, "matching": N},
    "ForgetResult": {"kind": {"email", "domain", "name"}, "value": S, "rows": N, "filesRemoved": N, "filesEdited": N, "warnings": [S]},
    "SuppressResult": {"kind": {"email", "domain"}, "value": S, "suppressed": N},
    "PurgeReport": {"state": {"report", "armed", "purged", "no_workspace"}, "months": N, "total": N, "expired": N,
                    "expiringIn30Days": N, "deleted": N, "armed": B, "suppressed": N},
    "PurgeEverythingResult": {"filesRemoved": N},
    "Retention": {"months": N, "min": N, "max": N},
    "KeyStatus": {"name": {"companies_house_key", "opencorporates_token"}, "saved": B, "savedAt": (NULL, S)},
    "Settings": {"theme": {"light", "dark", "system"}, "accent": {"cobalt", "brass", "celadon", "ember"}, "workspace": S,
                 "sheetFormats": [{"xlsx", "csv"}], "openSheetWhenDone": B},
    "Licence": {"name": S, "version": S, "licence": S, "notice": S},
    "About": {"windowVersion": gap(S), "engineVersion": S, "licence": S, "licences": ["Licence"]},
    "Error": {"kind": SEVEN, "message": S, "details": [S], "next": (NULL, S)},
}
RESULT = {
    "campaign_create": "CampaignPlan", "run_stop": "RunStatus", "run_status": (NULL, "RunStatus"), "campaigns_list": ["Campaign"],
    "sheet_export": "Sheet", "sheet_open": NULL, "people_list": "PeoplePage", "person_forget": "ForgetResult",
    "address_suppress": "SuppressResult", "purge_report": "PurgeReport", "purge_apply": "PurgeReport",
    "purge_everything": "PurgeEverythingResult", "retention_get": "Retention", "retention_set": "Retention",
    "keys_list": ["KeyStatus"], "key_save": "KeyStatus", "key_remove": "KeyStatus", "settings_get": "Settings",
    "settings_set": "Settings", "about": "About",
}
EVENT = {
    "progress": {"type": S, "stage": STAGE, "done": N, "total": (NULL, N), "message": S, "etaSeconds": (NULL, N), "at": S},
    "stage-done": {"type": S, "stage": STAGE, "summary": S, "at": S},
    "notice": {"type": S, "text": S, "at": S},
    "finished": {"type": S, "status": "RunStatus"},
    "stopped": {"type": S, "status": "RunStatus"},
    "failed": {"type": S, "status": "RunStatus", "error": {"kind": SEVEN, "message": S, "details": [S]}},
}


def conforms(value, t, where="$") -> list[str]:
    """Every way `value` differs from type `t`: exactly the fields of an object, no more, no fewer, each of the right kind."""
    if isinstance(t, tuple):
        errs = [conforms(value, x, where) for x in t]
        return [] if any(not e for e in errs) else [f"{where}: none of {t} ({errs})"]
    if isinstance(t, set):
        return [] if value in t else [f"{where}: {value!r} not one of {sorted(t)}"]
    if isinstance(t, list):
        if not isinstance(value, list):
            return [f"{where}: not a list"]
        return [e for i, v in enumerate(value) for e in conforms(v, t[0], f"{where}[{i}]")]
    if isinstance(t, dict):
        if not isinstance(value, dict):
            return [f"{where}: not an object"]
        if set(value) != set(t):
            return [f"{where}: fields {sorted(value)} != {sorted(t)}"]
        return [e for k in t for e in conforms(value[k], t[k], f"{where}.{k}")]
    if t in TYPES:
        return conforms(value, TYPES[t], where)
    ok = {S: isinstance(value, str), N: isinstance(value, (int, float)) and not isinstance(value, bool),
          B: isinstance(value, bool), NULL: value is None}[t]
    return [] if ok else [f"{where}: {value!r} is not {t}"]


# ------------------------------------------------------------------ an invented workspace
class FakeKeyring:
    def __init__(self, fail_with: str | None = None):
        self.entries: dict[tuple[str, str], str] = {}
        self.fail_with = fail_with

    def get_password(self, service, username):
        return self.entries.get((service, username))

    def set_password(self, service, username, password):
        if self.fail_with:
            raise RuntimeError(f"{self.fail_with} {password}")   # a backend that quotes what it was given
        self.entries[(service, username)] = password

    def delete_password(self, service, username):
        del self.entries[(service, username)]


@pytest.fixture
def ws(tmp_path, monkeypatch):
    """A workspace with one finished run of an invented campaign: two businesses, two people, a score each."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(util, "utcnow", lambda: NOW)

    def refuse(*a, **k):
        raise AssertionError("a test tried to reach the geocoder")

    monkeypatch.setattr("leadforge.grid.httpx.get", refuse)
    (tmp_path / "leadforge.yaml").write_text(yaml.safe_dump({"discovery": {"area_bbox": {"Bristol": [-2.65, 51.42, -2.52, 51.50]}}}),
                                             encoding="utf-8")
    from leadforge.models import ICP

    icp = ICP.model_validate({"campaign": CAMPAIGN, "offer": {"what": "Online booking for garages"},
                              "target": {"categories": ["MOT garage"], "geography": {"areas": ["Bristol"], "country": "GB", "grid": "off"}},
                              "qualify": {"soft": ["website_missing", "stale_site"]}})
    cdir = tmp_path / "campaigns" / CAMPAIGN
    cdir.mkdir(parents=True)
    (cdir / "icp.yaml").write_text(yaml.safe_dump(icp.model_dump(mode="json"), sort_keys=True), encoding="utf-8")
    (cdir / "window.json").write_text(json.dumps({"kinds": ["MOT garage"], "places": ["Bristol"], "source": "dvsa"}), encoding="utf-8")
    (tmp_path / "leadforge_data").mkdir()
    conn = db.connect(tmp_path / "leadforge_data" / "db.sqlite3")
    conn.execute("INSERT INTO runs(id,icp_path,icp_hash,stage,started_at,stats_json) VALUES(?,?,?,?,?,?)",
                 (RID, f"campaigns/{CAMPAIGN}/icp.yaml", icp.icp_hash(), "exported", "2026-11-01T09:00:00Z", '{"leads": 2}'))
    rows = [("b1", "Harbourside Motors", "harbourside-motors.example", "+441632960101"),
            ("b2", "Clifton Down Garage", "cliftondowngarage.example", None)]
    for bid, name, domain, phone in rows:
        conn.execute("INSERT INTO businesses(id,place_id,name,name_norm,website,domain,phone_e164,address_city,address_country,"
                     "first_run_id,last_seen_at,dedupe_key) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                     (bid, "place-" + bid, name, name.lower(), f"https://{domain}/", domain, phone, "Bristol", "GB", RID,
                      "2026-11-01T09:10:00Z", "key-" + bid))
        conn.execute("INSERT INTO scores(business_id,run_id,total,tier,factors_json,need_hooks_json,scored_at) VALUES(?,?,?,?,?,?,?)",
                     (bid, RID, 80 if bid == "b1" else 55, "A" if bid == "b1" else "B", "{}", '["no online booking"]',
                      "2026-11-01T09:20:00Z"))
    conn.execute("INSERT INTO contacts(business_id,kind,value) VALUES('b1','email','office@harbourside-motors.example')")
    conn.execute("INSERT INTO contacts(business_id,kind,value) VALUES('b2','email','hello@cliftondowngarage.example')")
    conn.execute("INSERT INTO people(business_id,name,title,source_url) VALUES('b1','Priya Nair','Owner',"
                 "'https://harbourside-motors.example/contact')")
    conn.execute("INSERT INTO people(business_id,name,title,source_url) VALUES('b2','Tomasz Zielinski','Workshop manager','')")
    conn.execute("INSERT INTO enrichment_observations(business_id,field,value_json,source,source_url,observed_at,person_name) "
                 "VALUES('b1','email','\"priya@harbourside-motors.example\"','public_site','https://harbourside-motors.example/contact',"
                 "'2026-11-01T09:10:00Z','Priya Nair')")
    conn.commit()
    conn.close()
    exports = tmp_path / "leadforge_data" / "exports" / RID
    exports.mkdir(parents=True)
    (exports / f"{CAMPAIGN}.csv").write_text("Business\nHarbourside Motors\n", encoding="utf-8")
    yield tmp_path
    logging.getLogger("leadforge").handlers.clear()   # the workspace log file belongs to this tmp folder only
    for h in list(logging.getLogger().handlers):
        if getattr(h, "_leadforge_window", False):
            logging.getLogger().removeHandler(h)


def call(name: str, args, argv_extra: tuple = ()) -> tuple[int, str]:
    out = io.StringIO()
    code = win.main([name, *argv_extra], stdin=io.StringIO(args if isinstance(args, str) else json.dumps(args)), stdout=out)
    return code, out.getvalue()


def one_doc(text: str):
    assert text.endswith("\n") and text.count("\n") == 1, f"stdout is not one JSON document: {text[:300]!r}"
    return json.loads(text)


def tree_hashes(root: Path) -> dict[str, str]:
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(root.rglob("*")) if p.is_file()}


def normalize(doc, ws: Path):
    text = json.dumps(doc, ensure_ascii=False)
    for form in {str(ws.resolve()), str(ws)}:
        for spelled in (json.dumps(form)[1:-1], json.dumps(form.replace("\\", "/"))[1:-1]):
            text = text.replace(spelled, "<ws>")
    doc = json.loads(text.replace("\\\\", "/"))

    def walk(v):
        if isinstance(v, dict):
            return {k: ("<time>" if k in ("at", "writtenAt") else "<n chars>" if k == "notice" else walk(x)) for k, x in v.items()}
        if isinstance(v, list):
            return [walk(x) for x in v]
        return v
    return walk(doc)


def check_golden(name: str, actual) -> None:
    path = GOLDEN / f"{name}.json"
    text = json.dumps(actual, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    if os.environ.get("LF_UPDATE_GOLDEN") == "1":
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
        return
    assert path.exists(), f"golden {path.name} missing: record it with LF_UPDATE_GOLDEN=1"
    assert actual == json.loads(path.read_text(encoding="utf-8")), f"window command {name} changed its output"


def fake_pipeline(monkeypatch, *, stop_after: int | None = None, stages=(("discover", 3), ("enrich", 2))):
    """Stands in for pipeline.run_pipeline: reports progress the way the engine does (and prints and logs, as a library may)."""
    from leadforge import pipeline

    def run(cfg, icp, icp_path, resume=False, **kw):
        print("LF_PROGRESS a line the engine prints")
        logging.getLogger("leadforge.enrich").warning("a library log line")
        sent = 0
        for stage, n in stages:
            for i in range(n):
                if stop_after is not None and sent == stop_after:
                    rid = db.latest_run(db.connect(cfg.db_path))["id"]
                    code, out = call("run_stop", {"runId": rid})
                    assert code == 0, out
                util.emit_progress(stage, i + 1, n, f"{stage} {i + 1}")
                sent += 1
        return {"ok": True, "run": None, "stage": "exported", "counts": {}, "warnings": [], "artifacts": [], "next": None}

    monkeypatch.setattr(pipeline, "run_pipeline", run)


# ------------------------------------------------------------------ one golden and one shape check per command
ARGS = {
    "campaign_create": {"draft": {"kinds": ["MOT garage"], "places": ["Bristol"], "country": "GB", "source": "dvsa", "maxLeads": 50}},
    "run_stop": {"runId": RID}, "run_status": {"runId": None}, "campaigns_list": {}, "sheet_export": {"runId": RID},
    "sheet_open": {"path": f"leadforge_data/exports/{RID}/{CAMPAIGN}.csv"}, "people_list": {"query": {"search": "", "limit": 50}},
    "person_forget": {"value": "priya@harbourside-motors.example"},
    "address_suppress": {"value": "hello@cliftondowngarage.example", "kind": None},
    "purge_report": {}, "purge_apply": {}, "purge_everything": {"confirm": True}, "retention_get": {}, "retention_set": {"months": 6},
    "keys_list": {}, "key_save": {"name": "companies_house_key", "value": "fixture-value"}, "key_remove": {"name": "companies_house_key"},
    "settings_get": {}, "settings_set": {"patch": {"sheetFormats": ["xlsx"], "openSheetWhenDone": False}}, "about": {},
}


def test_the_seam_names_exactly_the_21():
    assert set(win.NAMES) == set(RESULT) | {"run_start"} and len(win.NAMES) == 21
    assert not any(w in n for n in win.NAMES for w in ("send", "outreach", "mail"))   # C14: no sending from the window


@pytest.mark.parametrize("name", sorted(RESULT))
def test_command_golden_and_shape(ws, monkeypatch, name):
    fake = FakeKeyring()
    fake.entries[("leadforge", "registry.opencorporates_token")] = "fixture-token"
    monkeypatch.setattr(keys, "make_keys", lambda: keys.Keys(fake, "leadforge"))
    opened = []
    monkeypatch.setattr(commands, "_default_opener", opened.append)
    if name == "run_stop":   # a run the window started, still going (this test process stands in for it)
        conn = db.connect(ws / "leadforge_data" / "db.sqlite3")
        db.set_run_meta(conn, RID, window_pid=os.getpid(), window_state="running")
        conn.execute("UPDATE runs SET stage='enriching' WHERE id=?", (RID,))
        conn.commit()
    code, out = call(name, ARGS[name])
    doc = one_doc(out)
    assert code == 0, doc
    assert conforms(doc, RESULT[name]) == []
    if name == "sheet_open":
        assert [p.name for p in opened] == [f"{CAMPAIGN}.csv"]
    check_golden(name, normalize(doc, ws))


def test_run_start_streams_events_and_finishes(ws, monkeypatch, capsys):
    fake_pipeline(monkeypatch)
    code, out = call("run_start", {"args": {"campaign": CAMPAIGN, "resume": False}})
    lines = [json.loads(ln) for ln in out.splitlines()]
    assert code == 0
    assert conforms(lines[0], "RunHandle") == []
    for ev in lines[1:]:
        assert conforms(ev, EVENT[ev["type"]]) == [], ev
    assert lines[-1]["type"] == "finished" and lines[-1]["status"]["state"] == "finished"
    assert "LF_PROGRESS a line the engine prints" in capsys.readouterr().err   # the engine's own output went to stderr
    check_golden("run_start", [{**normalize(e, ws), **({"runId": "<new run>"} if "runId" in e else {})} if e.get("type") != "finished"
                               else {"type": "finished", "status": {**normalize(e["status"], ws), "runId": "<new run>",
                                                                    "startedAt": "<time>"}} for e in lines])


# ------------------------------------------------------------------ the seam's rules
def test_stdout_is_one_json_document_even_when_the_engine_prints_and_logs(ws, monkeypatch, capsys):
    """Every command, through the real sys.stdout: whatever the engine prints or logs reaches stderr only."""
    real = win.read_arguments

    def noisy(stdin):   # every command passes here, inside the seam
        print("LF_DIGEST {\"ok\": true}")
        logging.getLogger("leadforge").warning("a library log line")
        return real(stdin)

    monkeypatch.setattr(win, "read_arguments", noisy)
    monkeypatch.setattr(keys, "make_keys", lambda: keys.Keys(FakeKeyring(), "leadforge"))
    fake_pipeline(monkeypatch)
    for name in [*sorted(RESULT), "run_start"]:
        args = ARGS.get(name, {"args": {"campaign": CAMPAIGN, "resume": False}})
        code = win.main([name], stdin=io.StringIO(json.dumps(args)))
        cap = capsys.readouterr()
        if name == "run_start":
            assert all(json.loads(ln) for ln in cap.out.splitlines()) and code == 0
        else:
            one_doc(cap.out)
        assert "LF_DIGEST" not in cap.out and "LF_DIGEST" in cap.err and "a library log line" in cap.err, name
    code = win.main(["retention_set"], stdin=io.StringIO('{"months": 40}'))   # an error document, same discipline
    cap = capsys.readouterr()
    assert code == 2 and conforms(one_doc(cap.out), "Error") == [] and "LF_DIGEST" in cap.err


def test_an_argument_in_argv_is_refused(ws):
    before = tree_hashes(ws)
    code, out = call("person_forget", {"value": "priya@harbourside-motors.example"}, argv_extra=("--value", "x"))
    doc = one_doc(out)
    assert code == 2 and doc["kind"] == "usage" and conforms(doc, "Error") == []
    assert tree_hashes(ws) == before


def test_purge_everything_without_confirm_true_deletes_nothing(ws):
    before = tree_hashes(ws)
    for args in ({}, {"confirm": "true"}, {"confirm": 1}, {"confirm": False}):
        code, out = call("purge_everything", args)
        assert code == 2 and one_doc(out)["kind"] == "usage", args
    assert tree_hashes(ws) == before


def test_person_forget_dry_run_changes_no_byte(ws):
    before = tree_hashes(ws)
    code, out = call("person_forget", {"value": "Harbourside Motors", "dry_run": True})
    doc = one_doc(out)
    assert code == 0 and conforms(doc, "ForgetResult") == []
    assert doc["rows"] > 0 and doc["filesRemoved"] == 1   # it found what it would delete: rows and the sheet that holds the name
    assert tree_hashes(ws) == before


@pytest.mark.parametrize("case", ["outside", "dotdot", "link"])
def test_sheet_open_refuses_what_is_not_in_exports(ws, monkeypatch, case):
    opened = []
    monkeypatch.setattr(commands, "_default_opener", opened.append)
    outside = ws / "elsewhere.xlsx"
    outside.write_bytes(b"not a sheet of this workspace")
    if case == "outside":
        path = str(outside)
    elif case == "dotdot":
        path = f"leadforge_data/exports/{RID}/../../db.sqlite3"
    else:
        link = ws / "leadforge_data" / "exports" / RID / "looks-inside.xlsx"
        try:
            link.symlink_to(outside)
        except OSError:
            pytest.skip("this account cannot make a symbolic link (Windows without the privilege): not run here")
        path = f"leadforge_data/exports/{RID}/looks-inside.xlsx"
    code, out = call("sheet_open", {"path": path})
    assert code == 2 and one_doc(out)["kind"] == "usage"
    assert opened == []


def test_a_planted_key_appears_in_no_output_and_no_log(ws, monkeypatch, capsys):
    planted = "".join(["lf", "PLANTED", "k3y", str(31337 * 7)])   # built at run time, never written in the source
    fake = FakeKeyring()
    monkeypatch.setattr(keys, "make_keys", lambda: keys.Keys(fake, "leadforge"))
    seen = []
    for name, args in (("key_save", {"name": "companies_house_key", "value": planted}), ("keys_list", {}),
                       ("key_remove", {"name": "companies_house_key"})):
        code = win.main([name], stdin=io.StringIO(json.dumps(args)))
        cap = capsys.readouterr()
        seen += [cap.out, cap.err]
        assert code == 0, cap.out
    assert fake.entries == {}   # saved, then removed
    failing = FakeKeyring(fail_with="backend refused")   # a backend whose error quotes the value
    monkeypatch.setattr(keys, "make_keys", lambda: keys.Keys(failing, "leadforge"))
    code = win.main(["key_save"], stdin=io.StringIO(json.dumps({"name": "companies_house_key", "value": planted})))
    cap = capsys.readouterr()
    seen += [cap.out, cap.err]
    assert code == 1
    logs = ws / "leadforge_data" / "logs"
    seen += [p.read_text(encoding="utf-8", errors="replace") for p in logs.rglob("*")] if logs.is_dir() else []
    assert not any(planted in s for s in seen)


def test_key_commands_without_l9_answer_keyring(ws):
    code, out = call("keys_list", {})
    doc = one_doc(out)
    assert code == 1 and doc["kind"] == "keyring" and "L9" in doc["next"]


def test_run_stop_stops_between_businesses_and_keeps_the_place(ws, monkeypatch):
    fake_pipeline(monkeypatch, stop_after=2)
    code, out = call("run_start", {"args": {"campaign": CAMPAIGN, "resume": False}})
    lines = [json.loads(ln) for ln in out.splitlines()]
    progress = [e for e in lines if e.get("type") == "progress"]
    assert code == 0 and lines[-1]["type"] == "stopped" and lines[-1]["status"]["state"] == "stopped"
    assert len(progress) == 2   # nothing reported after the stop
    assert not (ws / "leadforge_data" / "window-run.stop").exists()
    code, out = call("run_status", {"runId": lines[0]["runId"]})
    assert one_doc(out)["state"] == "stopped"


def test_licence_notices_are_not_older_than_the_lock():
    import importlib.util

    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("make_licence_notices", root / "scripts" / "make_licence_notices.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    lock = (root / "requirements.lock").read_text(encoding="utf-8")
    notices = json.loads((root / "src" / "leadforge" / "data" / "licences.json").read_text(encoding="utf-8"))
    assert notices["lock_sha256"] == mod.lock_hash(lock), "licences.json is older than requirements.lock: run scripts/make_licence_notices.py"
    assert [(p["name"], p["version"]) for p in notices["packages"]] == mod.locked(lock)


def test_read_commands_answer_while_a_run_holds_the_database(ws, monkeypatch):
    """On Windows a running run's locks refuse the copy db.readonly_view makes of a busy database (seen in the loopback proof:
    run_stop answered PermissionError). The read commands then read the live database instead; the dry run of forget says so."""
    from contextlib import contextmanager

    @contextmanager
    def refused(path):
        raise PermissionError(13, "Permission denied")
        yield

    monkeypatch.setattr(db, "readonly_view", refused)
    code, out = call("run_status", {"runId": RID})
    assert code == 0 and one_doc(out)["runId"] == RID
    code, out = call("person_forget", {"value": "Harbourside Motors", "dry_run": True})
    doc = one_doc(out)
    assert code == 4 and doc["kind"] == "input" and "running run" in doc["details"][0]


# ------------------------------------------------------------------ Build 2: matching the window core (slice/L11-window)
# The object `app/ui/src/engine.tauri.ts` passes to `invoke` for each command, copied as data (the core drops `events` from
# run_start's and sends `{}` for a call without arguments). The values are invented.
def screen_args(ws: Path) -> dict:
    sheet = str((ws / "leadforge_data" / "exports" / RID / f"{CAMPAIGN}.csv").resolve())   # Sheet.files[].path, as the engine gave it
    return {
        "campaign_create": {"draft": {"kinds": ["MOT garage"], "places": ["Bristol"], "country": "GB", "source": "dvsa", "maxLeads": 50}},
        "run_start": {"args": {"campaign": CAMPAIGN, "resume": False}},
        "run_stop": {"runId": RID}, "run_status": {"runId": None}, "campaigns_list": {}, "sheet_export": {"runId": RID},
        "sheet_open": {"path": sheet}, "people_list": {"query": {"search": "priya", "limit": 50}},
        "person_forget": {"value": "priya@harbourside-motors.example"},
        "address_suppress": {"value": "hello@cliftondowngarage.example", "kind": None},
        "purge_report": {}, "purge_apply": {}, "purge_everything": {"confirm": True}, "retention_get": {}, "retention_set": {"months": 6},
        "keys_list": {}, "key_save": {"name": "companies_house_key", "value": "fixture-value"}, "key_remove": {"name": "companies_house_key"},
        "settings_get": {}, "settings_set": {"patch": {"theme": "dark", "accent": "brass", "sheetFormats": ["xlsx", "csv"],
                                                       "openSheetWhenDone": True}},
        "about": {},
    }


@pytest.mark.parametrize("name", win.NAMES)
def test_each_command_answers_what_the_screens_send(ws, monkeypatch, name):
    monkeypatch.setattr(keys, "make_keys", lambda: keys.Keys(FakeKeyring(), "leadforge"))
    opened = []
    monkeypatch.setattr(commands, "_default_opener", opened.append)
    fake_pipeline(monkeypatch)
    if name == "run_stop":
        conn = db.connect(ws / "leadforge_data" / "db.sqlite3")
        db.set_run_meta(conn, RID, window_pid=os.getpid(), window_state="running")
        conn.commit()
    code, out = call(name, screen_args(ws)[name])
    docs = [json.loads(ln) for ln in out.splitlines()]
    assert code == 0 and docs and not (isinstance(docs[0], dict) and "kind" in docs[0] and "message" in docs[0]), docs[:1]
    if name == "run_start":
        assert conforms(docs[0], "RunHandle") == [] and docs[-1]["type"] == "finished"
    else:
        assert len(docs) == 1 and conforms(docs[0], RESULT[name]) == []
    if name == "sheet_open":
        assert docs == [None] and [p.name for p in opened] == [f"{CAMPAIGN}.csv"]
    if name == "settings_set":
        code, out = call("settings_get", {})
        assert (one_doc(out)["theme"], one_doc(out)["accent"]) == ("dark", "brass")


def test_the_error_kinds_are_the_seven_the_screens_know():
    import re

    from leadforge.util import EnvError, InputError, LeadForgeError, ProviderFailed

    src = Path(win.__file__).parent
    emitted = set(win.EXIT_CODES) | set(win.KINDS)
    for p in src.glob("*.py"):
        text = p.read_text(encoding="utf-8")
        emitted |= set(re.findall(r'WindowError\(\s*"(\w+)"', text))
        emitted |= set(re.findall(r'"kind": "(\w+)", "message"', text))
    emitted |= {win.from_engine(cls("x"), "m").kind for cls in (LeadForgeError, EnvError, InputError, ProviderFailed)}
    assert emitted == SEVEN, f"a kind the screens do not know: {sorted(emitted - SEVEN)}"
    assert set(win.EXIT_CODES) == SEVEN


def test_arguments_over_1_mib_are_refused_with_input(ws):
    code, out = call("about", json.dumps({"x": "a" * (1024 * 1024)}))
    doc = one_doc(out)
    assert code == 4 and doc["kind"] == "input"


def test_no_run_start_line_exceeds_64_kib(ws, monkeypatch):
    from leadforge import pipeline

    def run(cfg, icp, icp_path, resume=False, **kw):
        util.emit_progress("enrich", 1, 2, "x" * 1_000_000)
        raise util.InputError("\n".join(["y" * 200_000] * 8))

    monkeypatch.setattr(pipeline, "run_pipeline", run)
    code, out = call("run_start", screen_args(ws)["run_start"])
    lines = out.splitlines()
    assert all(len(ln.encode("utf-8")) < 64 * 1024 for ln in lines), max(len(ln) for ln in lines)
    events = [json.loads(ln) for ln in lines]
    progress = [e for e in events if e.get("type") == "progress"]
    assert progress and len(progress[0]["message"]) <= 120   # the engine's own cut (util.emit_progress)
    assert events[-1]["type"] == "failed" and events[-1]["error"]["details"][0].endswith("[cut]")
    assert conforms(events[-1], EVENT["failed"]) == []


def test_a_start_refused_before_a_run_exists_is_one_error_document(ws):
    code, out = call("run_start", {"args": {"campaign": "no-such-campaign", "resume": False}})
    doc = one_doc(out)
    assert code == 4 and doc["kind"] == "input" and "runId" not in doc


@pytest.mark.parametrize("way", ["engine_error", "exception", "interrupt", "planning", "end_bookkeeping"])
def test_run_start_ends_with_an_end_event_on_every_way_out(ws, monkeypatch, way):
    import sqlite3

    from leadforge import pipeline
    from leadforge.window import run as wrun

    fake_pipeline(monkeypatch)
    if way in ("engine_error", "exception", "interrupt"):
        error = {"engine_error": util.ProviderFailed("the register did not answer"), "exception": RuntimeError("boom"),
                 "interrupt": KeyboardInterrupt()}[way]

        def run(*a, **k):
            util.emit_progress("discover", 1, 3, "one")
            raise error
        monkeypatch.setattr(pipeline, "run_pipeline", run)
    elif way == "planning":
        def plan(*a, **k):
            raise RuntimeError("plan failed")
        monkeypatch.setattr(pipeline, "_plan_into_db", plan)
    else:
        real = db.set_run_meta

        def locked(conn, run_id, **kw):
            if kw.get("window_state") in ("finished", "stopped", "failed"):
                raise sqlite3.OperationalError("database is locked")
            return real(conn, run_id, **kw)
        monkeypatch.setattr(wrun.db, "set_run_meta", locked)
    code, out = call("run_start", screen_args(ws)["run_start"])
    events = [json.loads(ln) for ln in out.splitlines()]
    assert conforms(events[0], "RunHandle") == []
    end = events[-1]
    assert end["type"] in ("finished", "stopped", "failed") and conforms(end, EVENT[end["type"]]) == [], end
    assert end["status"]["runId"] == events[0]["runId"]
    assert end["type"] == ("finished" if way == "end_bookkeeping" else "failed")
    assert code == {"engine_error": 5, "end_bookkeeping": 0}.get(way, 1)


# A second engine process for the two tests below: the real `leadforge window run_start`, its pipeline replaced by one that
# reports a business every 0.2 s and writes the database each time (as enrich does). Nothing leaves the machine.
RUNNER = """
import sys, time
from leadforge import db, pipeline, util
import leadforge.grid
def refuse(*a, **k):
    raise AssertionError("the runner tried to reach the geocoder")
leadforge.grid.httpx.get = refuse
def run(cfg, icp, icp_path, resume=False, **kw):
    conn = db.connect(cfg.db_path)
    rid = db.latest_run(conn)["id"]
    n = int(sys.argv[1])
    for i in range(n):
        util.emit_progress("enrich", i + 1, n, f"business {i + 1}")
        db.set_run_meta(conn, rid, runner_tick=i)
        time.sleep(0.2)
    return {"ok": True, "run": None, "stage": "exported", "counts": {}, "warnings": [], "artifacts": [], "next": None}
pipeline.run_pipeline = run
from leadforge import window
sys.exit(window.main(["run_start"]))
"""


def engine_process(ws: Path, *argv: str, script: bool = False):
    import subprocess
    import sys

    cmd = ([sys.executable, "-X", "utf8", str(ws / "runner.py"), *argv] if script else
           [sys.executable, "-X", "utf8", "-m", "leadforge", "window", *argv])
    return subprocess.Popen(cmd, cwd=ws, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, encoding="utf-8")


def start_runner(ws: Path, n: int):
    (ws / "runner.py").write_text(RUNNER, encoding="utf-8")
    p = engine_process(ws, str(n), script=True)
    p.stdin.write(json.dumps(screen_args(ws)["run_start"]))
    p.stdin.close()
    handle = json.loads(p.stdout.readline())
    while json.loads(p.stdout.readline()).get("type") != "progress":
        pass
    return p, handle["runId"]


def ask(ws: Path, name: str, args: dict, timeout: float) -> tuple[int, dict, str, float]:
    import time

    t0 = time.monotonic()
    p = engine_process(ws, name)
    out, err = p.communicate(json.dumps(args), timeout=timeout)
    return p.returncode, json.loads(out), err, time.monotonic() - t0


def test_after_the_run_process_is_ended_from_outside_status_is_not_running(ws):
    p, rid = start_runner(ws, 300)
    p.kill()   # as the core ends an engine past its time: no line can be written now
    p.communicate(timeout=30)
    code, out = call("run_status", {"runId": rid})
    doc = one_doc(out)
    assert code == 0 and doc["state"] == "failed" and doc["reason"], doc


def test_run_stop_from_a_second_process_ends_the_run_within_10_s_and_status_answers_beside_it(ws):
    import time

    p, rid = start_runner(ws, 300)
    try:
        for _ in range(3):   # run_status beside the run while it writes the database
            code, doc, err, secs = ask(ws, "run_status", {"runId": rid}, 30)
            assert code == 0 and doc["state"] == "running" and secs < 30, (doc, err[-500:])
            assert "locked" not in err.lower()
        asked_at = time.monotonic()
        code, doc, err, _ = ask(ws, "run_stop", {"runId": rid}, 30)
        stopped_at = time.monotonic()
        assert code == 0 and doc["runId"] == rid, (doc, err[-500:])
        rest, run_err = p.communicate(timeout=10)
        ended_at = time.monotonic()
        took = ended_at - stopped_at
    finally:
        if p.poll() is None:
            p.kill()
            p.communicate()
    last = json.loads(rest.splitlines()[-1])
    print(f"run_stop answered to the run's end: {took:.2f} s; run_stop started to the run's end: {ended_at - asked_at:.2f} s")
    assert took < 10 and p.returncode == 0 and last["type"] == "stopped", (took, last, run_err[-500:])
    assert "locked" not in run_err.lower()
    assert not (ws / "leadforge_data" / "window-run.stop").exists()
    code, doc, err, _ = ask(ws, "run_status", {"runId": rid}, 30)
    assert code == 0 and doc["state"] == "stopped"
