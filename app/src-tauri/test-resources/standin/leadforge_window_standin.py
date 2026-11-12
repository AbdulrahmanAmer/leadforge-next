"""STAND-IN ENGINE for the window's 21 commands. Made-up data only. NOT the engine; NOT shipped once the real
`leadforge window <name>` commands exist (switch: `STAND_IN = false` in app/src-tauri/src/engine.rs; see
docs/slices/L11-window.md).

Started exactly like the real engine will be, apart from the entry: the same interpreter and flags
(`python -X utf8 -I`), then `window <name>`; the arguments object as ONE JSON document on stdin; ONE JSON document
on stdout and exit 0, or on an error a non-zero exit and `{"kind","message","details","next"}` on stdout; logs on
stderr only. `run_start` writes the run handle `{"runId": ...}` as its first line, then one RunEvent per line.

The values come from app/ui/src/engine.mock.ts: invented businesses, `.example` domains, Ofcom's drama number ranges.
State between calls lives in `standin-state.json` in the working folder (the app's own workspace folder).
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

STATE = Path("standin-state.json")
STOP_FLAG = Path("standin-stop.flag")
STATE_VERSION = 2  # 2: the seam decisions of 2026-11-12 (offer, sicCodes, sources, nullable fields, no theme or accent)
UNNAMED_RUN = "unnamed-run"  # the campaign name that makes a run answer with the engine's "unknown" fields (as in engine.mock.ts)
EXIT = {"failed": 1, "usage": 2, "environment": 3, "input": 4, "source": 5, "keyring": 1, "missing": 1}
STAGES = ["discover", "enrich", "label", "score", "draft", "export"]

BUSINESSES = [
    ("Harbourside Motors", "harbourside-motors.example", "Bristol"),
    ("Clifton Down Garage", "cliftondowngarage.example", "Bristol"),
    ("Redcliffe MOT Centre", "redcliffe-mot.example", "Bristol"),
    ("Avon Gorge Autos", "avongorgeautos.example", "Bristol"),
    ("Bedminster Tyre and Test", "bedminstertest.example", "Bristol"),
    ("Kingswood Service Station", "kingswood-service.example", "Kingswood"),
    ("Fishponds Road Garage", "fishpondsroad.example", "Bristol"),
    ("Portway Vehicle Care", "portwayvehicle.example", "Avonmouth"),
    ("Stokes Croft Auto Repair", "stokescroftauto.example", "Bristol"),
    ("Severn View Motor Works", "severnview-motors.example", "Thornbury"),
]
NAMES = [
    ("Priya Nair", "Owner"), ("Tomasz Zielinski", "Workshop manager"), ("Aoife Brennan", "Director"),
    ("Daniel Okafor", "Service manager"), ("Megan Hartley", "Owner"), ("Yusuf Demir", "General manager"),
    ("Rhys Calloway", "Director"), ("Hannah Whitcombe", "Office manager"), ("Luca Marchetti", "Owner"),
    ("Sofia Lindqvist", "Service manager"), ("Callum Ferreira", "Director"), ("Nadia Rahman", "General manager"),
]
STAGE_SUMMARY = {
    "discover": "212 businesses from 48 searches",
    "enrich": "204 websites read, 8 refused and left alone",
    "label": "151 businesses with a named decision maker",
    "score": "38 strong, 97 fair, 77 weak",
    "draft": "131 draft notes for the sheet",
    "export": "Sheet written: 212 rows",
}


class Refused(Exception):
    def __init__(self, kind: str, message: str, details: list[str] | None = None, next_: str | None = None):
        super().__init__(message)
        self.doc = {"kind": kind, "message": message, "details": details or [], "next": next_}


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def people() -> list[dict]:
    out = []
    for i, (name, role) in enumerate(NAMES):
        business, domain, _town = BUSINESSES[i % len(BUSINESSES)]
        first = name.split(" ")[0].lower()
        phone = (f"0117 496 0{100 + i * 37:03d}" if i % 3 == 0 else
                 f"01632 960{100 + i * 53:03d}" if i % 3 == 1 else f"07700 900{100 + i * 41:03d}")
        out.append({
            "id": f"p{i + 1}", "name": name, "role": role, "business": business, "domain": domain,
            "email": f"{first}@{domain}" if i % 5 != 3 else None,
            "phone": phone if i % 4 != 2 else None,
            # the last two people carry the engine's "not recorded": one lacks the page, the last lacks all three
            "source": None if i >= 10 else f"{domain}/{['contact', 'about-us', 'our-team', 'contact-us'][i % 4]}",
            "foundAt": None if i == 11 else f"2026-{'11' if i < 7 else '09'}-{(3 + i if i < 7 else 14 + i - 7):02d}",
            "campaign": None if i == 11 else "bristol-mot-garages" if i < 7 else "bath-tyre-fitters",
            "suppressed": i == 9,
        })
    return out


def sheet(run_id: str, leads: int, written_at: str) -> dict:
    d = f"leadforge_data\\exports\\{run_id}"
    return {
        "runId": run_id, "writtenAt": written_at, "leads": leads,
        "tabs": [{"name": "Leads", "rows": leads}, {"name": "Drafts", "rows": round(leads * 0.62)},
                 {"name": "Summary", "rows": 14}, {"name": "About", "rows": 9}],
        "files": [{"kind": "xlsx", "path": f"{d}\\leads.xlsx"}, {"kind": "csv", "path": f"{d}\\leads.csv"},
                  {"kind": "report", "path": f"{d}\\report.json"}],
        "highlights": ["No online booking on the site, phone only", "Site last changed more than two years ago",
                       "Owner named on the contact page"],
    }


def campaigns() -> list[dict]:
    return [
        {"runId": "r-20261103-a41c", "name": "bristol-mot-garages", "kinds": ["MOT garage"], "places": ["Bristol"],
         "source": "dvsa", "state": "finished", "stage": "export", "startedAt": "2026-11-03T09:12:00Z",
         "keptUntil": "2027-11-03", "businesses": 212, "withEmail": 164, "withPhone": 201,
         "tiers": {"a": 38, "b": 97, "c": 77}, "sheet": sheet("r-20261103-a41c", 212, "2026-11-03T09:58:00Z")},
        {"runId": "r-20261028-77be", "name": "somerset-plumbing-firms", "kinds": ["Plumbing and heating"],
         "places": ["Taunton", "Yeovil"], "source": "companies_house", "state": "stopped", "stage": "enrich",
         "startedAt": "2026-10-28T14:40:00Z", "keptUntil": "2027-10-28", "businesses": 96, "withEmail": 31,
         "withPhone": 58, "tiers": {"a": 0, "b": 0, "c": 0}, "sheet": None},
        {"runId": "r-20260914-0d3f", "name": "bath-tyre-fitters", "kinds": ["Tyre fitter"], "places": ["Bath"],
         "source": "dvsa", "state": "finished", "stage": "export", "startedAt": "2026-09-14T11:05:00Z",
         "keptUntil": "2027-09-14", "businesses": 64, "withEmail": 47, "withPhone": 60,
         "tiers": {"a": 9, "b": 31, "c": 24}, "sheet": sheet("r-20260914-0d3f", 64, "2026-09-14T11:31:00Z")},
        # every nullable field null: the engine has no name, register or deletion day for this run
        {"runId": "r-20260802-3c1a", "name": None, "kinds": ["Roofing contractor"], "places": ["Exeter"],
         "source": None, "state": "finished", "stage": "export", "startedAt": "2026-08-02T08:20:00Z",
         "keptUntil": None, "businesses": 41, "withEmail": 22, "withPhone": 38, "tiers": {"a": 4, "b": 19, "c": 18},
         "sheet": sheet("r-20260802-3c1a", 41, "2026-08-02T08:44:00Z")},
    ]


def settings_default() -> dict:
    return {"workspace": "D:\\Leads\\west-country", "sheetFormats": ["xlsx", "csv"], "openSheetWhenDone": True,
            "sources": ["dvsa", "companies_house"]}


def settings_doc(s: dict) -> dict:
    """Exactly the engine's Settings fields. A state file from an older stand-in may hold more (theme, accent): never passed on."""
    st = {**settings_default(), **(s.get("settings") or {})}
    return {k: st[k] for k in settings_default()}


def shown(status: dict, unknown: bool) -> dict:
    """A run status as the engine sends it when it does not know: campaign, done and the clean-up counts null."""
    out = {**status, "counts": dict(status["counts"])}
    if unknown:
        out.update(campaign=None, done=None)
        out["counts"].update(purged=None, expiringIn30Days=None)
    return out


def load() -> dict:
    for _ in range(20):  # a run's process may be replacing the file this moment
        try:
            if STATE.exists():
                old = json.loads(STATE.read_text(encoding="utf-8"))
                if old.get("v") == STATE_VERSION:  # a file from an older stand-in has the old shapes: start again
                    return old
            break
        except (OSError, json.JSONDecodeError):
            time.sleep(0.05)
    return {
        "people": people(), "campaigns": campaigns(), "suppressed": 23, "months": 12, "expired": 14, "total": 372,
        "settings": settings_default(),
        "keys": {"companies_house_key": {"name": "companies_house_key", "saved": True, "savedAt": "2026-11-03T08:50:00Z"},
                 "opencorporates_token": {"name": "opencorporates_token", "saved": False, "savedAt": None}},
        "run": None, "v": STATE_VERSION,
    }


def save(state: dict) -> None:
    tmp = STATE.with_suffix(f".{id(state)}.tmp")
    tmp.write_text(json.dumps(state), encoding="utf-8")
    for _ in range(20):
        try:
            tmp.replace(STATE)
            return
        except OSError:
            time.sleep(0.05)
    tmp.unlink(missing_ok=True)


def purge_state(s: dict, state: str, deleted: int) -> dict:
    return {"state": state, "months": s["months"], "total": s["total"], "expired": s["expired"],
            "expiringIn30Days": 9, "deleted": deleted, "armed": True, "suppressed": s["suppressed"]}


def emit(doc: dict) -> None:
    sys.stdout.write(json.dumps(doc) + "\n")
    sys.stdout.flush()


def run_start(s: dict, a: dict) -> None:
    args = a.get("args") or {}
    campaign = str(args.get("campaign") or "").strip()
    if not campaign:
        raise Refused("input", "The engine could not start the run.", ["no campaign named"], "Check the plan first.")
    run_id = "r-20261112-5e90"
    status = {"runId": run_id, "campaign": campaign, "state": "running", "stage": "discover", "done": 0, "total": None,
              "etaSeconds": None, "counts": {"businesses": 0, "contacts": 0, "purged": 4, "expiringIn30Days": 9},
              "startedAt": now(), "reason": None}
    unknown = campaign == UNNAMED_RUN
    s["run"] = shown(status, unknown)
    save(s)
    STOP_FLAG.unlink(missing_ok=True)
    emit({"runId": run_id})
    emit({"type": "notice", "text": "Clean-up before the run: 4 businesses past the 12-month limit were deleted. "
                                    "9 more expire in the next 30 days.", "at": now()})
    steps = [("discover", 48, 6), ("enrich", 212, 12), ("label", 204, 34), ("score", 212, 53), ("draft", 131, 44),
             ("export", 3, 1)]
    for stage, total, step in steps:
        done, i = 0, 0
        while done <= total:
            if STOP_FLAG.exists():
                STOP_FLAG.unlink(missing_ok=True)
                status["state"] = "stopped"
                s["run"] = shown(status, unknown)
                save(s)
                emit({"type": "stopped", "status": shown(status, unknown)})
                return
            status.update(stage=stage, done=done, total=total)
            status["etaSeconds"] = None if stage == "export" else round((total - done) * 0.6)
            if stage == "discover":
                status["counts"]["businesses"] = round(done / 48 * 212)
            if stage == "enrich":
                status["counts"]["contacts"] = round(done / 212 * 318)
            b = BUSINESSES[i % len(BUSINESSES)]
            emit({"type": "progress", "stage": stage, "done": done, "total": total,
                  "message": f"{b[1]}: {['1 email, 1 phone', '1 phone', '2 emails, 1 phone'][i % 3]}",
                  "etaSeconds": status["etaSeconds"], "at": now()})
            s["run"] = shown(status, unknown)
            save(s)
            time.sleep(0.25)
            done = total + 1 if done == total else min(total, done + step)
            i += 1
        emit({"type": "stage-done", "stage": stage, "summary": STAGE_SUMMARY[stage], "at": now()})
    status["state"] = "finished"
    s["run"] = shown(status, unknown)
    s["campaigns"].insert(0, {"runId": run_id, "name": campaign, "kinds": ["MOT garage"], "places": ["Bristol"],
                              "source": "dvsa", "state": "finished", "stage": "export", "startedAt": status["startedAt"],
                              "keptUntil": "2027-11-12", "businesses": 212, "withEmail": 164, "withPhone": 201,
                              "tiers": {"a": 38, "b": 97, "c": 77}, "sheet": sheet(run_id, 212, now())})
    save(s)
    emit({"type": "finished", "status": shown(status, unknown)})


def answer(name: str, s: dict, a: dict):  # noqa: C901 - one branch per command, on purpose
    if name == "campaign_create":
        d = a.get("draft") or {}
        problems = []
        if not any(str(k).strip() for k in d.get("kinds") or []):
            problems.append("target.categories: at least one kind of business")
        if not any(str(p).strip() for p in d.get("places") or []):
            problems.append("target.geography.areas: at least one place")
        if not str(d.get("country") or "").strip():
            problems.append("target.geography.country: country is required")
        if not (isinstance(d.get("maxLeads"), (int, float)) and d["maxLeads"] >= 1):
            problems.append("caps.max_leads: must be 1 or more")
        # the three refusals of the seam decisions: each names its field. A missing `offer` key is refused like a blank one.
        if not str(d.get("offer") or "").strip():
            problems.append("offer: say in a line or two what you offer these businesses")
        if d.get("source") == "companies_house" and not any(str(c).strip() for c in d.get("sicCodes") or []):
            problems.append("sicCodes: at least one SIC code is needed for Companies House")
        configured = s.get("configured") or settings_doc(s)["sources"]
        if d.get("source") not in configured:
            raise Refused("input", "The campaign is not complete.",
                          [*problems, f"source: {d.get('source')} is not switched on"],
                          f"this workspace is configured for {', '.join(configured) or 'no register'}")
        if problems:
            raise Refused("input", "The campaign is not complete.", problems,
                          "Fill in the marked fields and check the plan again.")
        searches = len(d["kinds"]) * len(d["places"]) * 12
        est = min(int(d["maxLeads"]), searches * 9)
        slug = "".join(c if c.isalnum() else "-" for c in f"{d['places'][0]}-{d['kinds'][0]}s".lower()).strip("-")
        return {"campaign": slug, "searches": searches, "estimatedBusinesses": est, "estimatedSites": round(est * 0.92),
                "estimatedMinutes": max(4, round(est * 0.21)),
                "warnings": [f"The plan can find more than {d['maxLeads']} businesses; the run stops at {d['maxLeads']}."]
                if est == d["maxLeads"] else [], "retentionMonths": s["months"]}
    if name == "run_stop":
        run = s.get("run")
        if not run or run.get("runId") != a.get("runId") or run.get("state") != "running":
            raise Refused("input", "There is no run to stop.", ["No engine process is running for this workspace."])
        STOP_FLAG.write_text("stop", encoding="utf-8")
        return {**run, "state": "stopped"}
    if name == "run_status":
        run = s.get("run")
        return run if run and (not a.get("runId") or run.get("runId") == a.get("runId")) else None
    if name == "campaigns_list":
        return s["campaigns"]
    if name == "sheet_export":
        c = next((c for c in s["campaigns"] if c["runId"] == a.get("runId")), None)
        if not c:
            raise Refused("input", "The sheet was not written.", ["no run found"], "Run the campaign first.")
        c["sheet"] = sheet(c["runId"], c["businesses"], now())
        return c["sheet"]
    if name == "sheet_open":
        if "\\exports\\" not in str(a.get("path") or ""):
            raise Refused("usage", "That file is not a sheet of this workspace.",
                          ["Only files in the exports folder can be opened."])
        return None
    if name == "people_list":
        q = a.get("query") or {}
        term = str(q.get("search") or "").strip().lower()
        everyone = s["people"]
        hit = [p for p in everyone if not term or any(term in str(p.get(k) or "").lower()
                                                       for k in ("name", "email", "domain", "business", "phone"))]
        return {"people": hit[: int(q.get("limit") or 50)], "total": len(everyone), "matching": len(hit)}
    if name == "person_forget":
        v = str(a.get("value") or "").strip().lower()
        if not v:
            raise Refused("usage", "Nothing was changed.", ["Give an email address, a domain or a name."],
                          "nothing was changed")
        kind = "email" if "@" in v else "domain" if "." in v and " " not in v else "name"
        field = {"email": "email", "domain": "domain", "name": "name"}[kind]
        gone = [p for p in s["people"] if str(p.get(field) or "").lower() == v]
        s["people"] = [p for p in s["people"] if p not in gone]
        s["suppressed"] += 1
        return {"kind": kind, "value": str(a.get("value")).strip(), "rows": len(gone) * 7,
                "filesRemoved": 2 if gone else 0, "filesEdited": 3 if gone else 0,
                "warnings": ["Sheets already handed out, or written outside this folder, cannot be reached from here."]}
    if name == "address_suppress":
        v = str(a.get("value") or "").strip().lower()
        if not v:
            raise Refused("usage", "The address was not added.", ["empty value: nothing to suppress"])
        kind = a.get("kind") or ("email" if "@" in v else "domain")
        for p in s["people"]:
            if str(p.get("email" if kind == "email" else "domain") or "").lower() == v:
                p["suppressed"] = True
        s["suppressed"] += 1
        return {"kind": kind, "value": str(a.get("value")).strip(), "suppressed": s["suppressed"]}
    if name == "purge_report":
        return purge_state(s, "report", 0)
    if name == "purge_apply":
        deleted = s["expired"]
        s["total"] -= deleted
        s["expired"] = 0
        return purge_state(s, "purged", deleted)
    if name == "purge_everything":
        if a.get("confirm") is not True:
            raise Refused("usage", "Nothing was deleted.", ["The window did not confirm."])
        s.update(people=[], campaigns=[], total=0, expired=0)
        return {"filesRemoved": 1846}
    if name == "retention_get":
        return {"months": s["months"], "min": 1, "max": 12}
    if name == "retention_set":
        m = a.get("months")
        if not isinstance(m, int) or isinstance(m, bool) or not 1 <= m <= 12:
            raise Refused("usage", "The retention period was not changed.",
                          ["invalid value for retention.months: ValidationError"], "Choose 1 to 12 months.")
        s["months"] = m
        return {"months": m, "min": 1, "max": 12}
    if name == "keys_list":
        return list(s["keys"].values())
    if name == "key_save":
        key = a.get("name")
        if key not in s["keys"]:
            raise Refused("usage", "The key was not saved.", ["There is no such key."])
        if not str(a.get("value") or "").strip():
            raise Refused("usage", "The key was not saved.", ["The key is empty."])
        # the value is dropped here on purpose: the stand-in keeps nothing, returns nothing, logs nothing
        s["keys"][key] = {"name": key, "saved": True, "savedAt": now()}
        return s["keys"][key]
    if name == "key_remove":
        key = a.get("name")
        if key not in s["keys"]:
            raise Refused("usage", "The key was not removed.", ["There is no such key."])
        s["keys"][key] = {"name": key, "saved": False, "savedAt": None}
        return s["keys"][key]
    if name == "settings_get":
        return settings_doc(s)
    if name == "settings_set":
        patch = a.get("patch") or {}
        if "sheetFormats" in patch and not patch["sheetFormats"]:
            raise Refused("usage", "The setting was not saved.", ["Keep at least one sheet format."])
        # only the two settings a window may change: any other key (theme, accent, workspace, an unknown one) refuses the whole patch
        foreign = [str(k) for k in patch if k not in ("sheetFormats", "openSheetWhenDone")]
        if foreign:
            raise Refused("usage", "The setting was not saved.",
                          [f"{k}: the engine has no such setting" for k in foreign], "nothing was changed")
        st = settings_doc(s)
        st.update({k: patch[k] for k in ("sheetFormats", "openSheetWhenDone") if k in patch})
        s["settings"] = st
        return settings_doc(s)
    if name == "about":
        try:
            from leadforge import __version__ as engine_version
        except Exception:  # noqa: BLE001 - the stand-in still answers without the engine
            engine_version = "unknown"
        return {"engineVersion": engine_version, "licence": "MIT", "licences": [
            {"name": "React", "version": "19.3.1", "licence": "MIT", "notice": "Copyright (c) Meta Platforms, Inc. and affiliates."},
            {"name": "Tauri", "version": "2.x", "licence": "Apache-2.0 OR MIT", "notice": "Copyright (c) The Tauri Programme within The Commons Conservancy."},
            {"name": "Python", "version": "3.12", "licence": "PSF-2.0", "notice": "Copyright (c) Python Software Foundation."},
        ]}
    raise Refused("missing", "The engine has no command for this yet.", [f"window {name}"])


COMMANDS = {
    "campaign_create", "run_start", "run_stop", "run_status", "campaigns_list", "sheet_export", "sheet_open",
    "people_list", "person_forget", "address_suppress", "purge_report", "purge_apply", "purge_everything",
    "retention_get", "retention_set", "keys_list", "key_save", "key_remove", "settings_get", "settings_set", "about",
}


def main(argv: list[str]) -> int:
    if len(argv) != 2 or argv[0] != "window" or argv[1] not in COMMANDS:
        emit({"kind": "usage", "message": "The stand-in answers `window <name>` only.", "details": [], "next": None})
        return 2
    name = argv[1]
    print(f"stand-in: window {name}", file=sys.stderr)  # the command's name only, never its arguments
    try:
        raw = sys.stdin.read()
        a = json.loads(raw) if raw.strip() else {}
        if not isinstance(a, dict):
            raise Refused("usage", "The arguments are not an object.")
        s = load()
        if name == "run_start":
            run_start(s, a)
            return 0
        result = answer(name, s, a)
        save(s)
        emit(result) if result is not None else sys.stdout.write("null\n")
        return 0
    except Refused as r:
        emit(r.doc)
        return EXIT.get(r.doc["kind"], 1)
    except json.JSONDecodeError:
        emit({"kind": "usage", "message": "The arguments are not one JSON document.", "details": [], "next": None})
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
