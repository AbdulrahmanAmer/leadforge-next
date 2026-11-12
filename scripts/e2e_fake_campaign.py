"""Fake-campaign end-to-end proof: one invented campaign through the CLI with every outside call refused.

    python scripts/e2e_fake_campaign.py                 # run with THIS interpreter's leadforge, compare with the saved result
    python scripts/e2e_fake_campaign.py --update-golden # (re)save the result as tests/fixtures/e2e/expected.json
    python scripts/e2e_fake_campaign.py --python <py> --label old --out <dir> --no-golden   # run another install, keep its output
    python scripts/e2e_fake_campaign.py --probe         # only prove the guard refuses an outside address

What it does: starts a loopback web server that plays invented business sites and an invented DVSA register
(fixtures under tests/fixtures/e2e), writes a fresh workspace, and runs the same CLI commands as a user would
(intake, plan, run, discover, byol import, run --resume, status, export) in child processes whose PYTHONPATH carries
tests/fixtures/e2e/harness/sitecustomize.py: every non-loopback connection or lookup is refused and logged, the
Maps scraper binary is replaced by a fixture-fed stand-in, the agent call is switched off, provider keys are removed.
Result: PASS when the normalized result equals expected.json AND no refused attempt other than the known set happened.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "tests" / "fixtures" / "e2e"
HARNESS = FIX / "harness"
GOLDEN = FIX / "expected.json"
WORLD = json.loads((FIX / "world.json").read_text(encoding="utf-8"))
HOSTS = [s["host"] for s in WORLD["sites"]]
SECRETISH = re.compile(r"KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|AUTH|ANTHROPIC|OPENAI|GITHUB|^GH_|PROXY", re.I)
PUBLIC_RESOLVERS = {"8.8.8.8", "1.1.1.1"}
KEEP_ENV = ("SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC", "PATHEXT", "PATH", "TEMP", "TMP", "PROCESSOR_ARCHITECTURE", "NUMBER_OF_PROCESSORS", "OS")

CONFIG_YAML = f"""discovery:
  providers: [gosom, dvsa]
  dvsa:
    url: http://127.0.0.1:{WORLD['port']}/dvsa/active-mot-stations.csv
politeness:
  delay_s: 0.2
  workers: 4
enrich:
  ner: false
agent:
  command: []
social:
  enabled: false
export:
  auto_open: false
progress_window: false
"""


# ----------------------------------------------------------------------------- the fake world
class World(BaseHTTPRequestHandler):
    log_path: Path
    protocol_version = "HTTP/1.0"

    def log_message(self, *a):  # silence default stderr logging
        pass

    def _send(self, code, body=b"", ctype="text/html; charset=utf-8", extra=()):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in extra:
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def do_GET(self):  # noqa: N802
        host = (self.headers.get("Host") or "").split(":")[0].lower()
        path = self.path.split("?")[0]
        mode = next((s["mode"] for s in WORLD["sites"] if s["host"] == host), None)
        status = 404
        try:
            if path == "/dvsa/active-mot-stations.csv":
                status = 200
                return self._send(200, (FIX / "dvsa_register.csv").read_bytes(), "text/csv")
            if mode is None or mode == "not_found":
                return self._send(404, b"not found")
            if mode == "slow" and path != "/robots.txt":
                time.sleep(WORLD["slow_seconds"])
            site = FIX / "sites" / host
            if mode == "redirect_disallowed" and path == "/":
                status = 302
                return self._send(302, b"", extra=[("Location", (site / "_redirect_target").read_text(encoding="utf-8").strip())])
            rel = "index.html" if path == "/" else path.lstrip("/")
            cand = [site / rel, site / (rel + ".html")]
            for c in cand:
                if c.is_file() and site in c.resolve().parents:
                    status = 200
                    return self._send(200, c.read_bytes(), "text/plain" if c.suffix == ".txt" else "text/html; charset=utf-8")
            return self._send(404, b"not found")
        finally:
            with self.log_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps({"host": host, "path": path, "status": status, "ua": self.headers.get("User-Agent", "")}) + "\n")


def start_world(log_path: Path) -> ThreadingHTTPServer:
    handler = type("H", (World,), {"log_path": log_path})
    srv = ThreadingHTTPServer(("127.0.0.1", WORLD["port"]), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


# ----------------------------------------------------------------------------- running the CLI
def child_env(ws: Path, guard_log: Path) -> dict:
    env = {k: v for k, v in os.environ.items() if k.upper() in KEEP_ENV and not SECRETISH.search(k)}
    home = ws / "_home"
    home.mkdir(parents=True, exist_ok=True)
    env.update({
        "PYTHONPATH": str(HARNESS), "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8", "COLUMNS": "200", "NO_COLOR": "1",
        "HOME": str(home), "USERPROFILE": str(home), "APPDATA": str(home / "AppData"), "LOCALAPPDATA": str(home / "Local"),
        "LF_GUARD_LOG": str(guard_log), "LF_GUARD_HOSTS": ",".join(HOSTS), "LF_FAKE_MAPS": str(FIX / "maps_listings.json"),
    })
    return env


def digest_of(text: str):
    last = None
    for line in text.splitlines():
        if line.startswith("LF_DIGEST "):
            try:
                last = json.loads(line[len("LF_DIGEST "):])
            except json.JSONDecodeError:
                last = {"unparseable": line[:200]}
    return last


def run_campaign(py: str, ws: Path, out: Path) -> dict:
    guard_log = out / "guard.log"
    env = child_env(ws, guard_log)
    steps: list[dict] = []
    ws.mkdir(parents=True, exist_ok=True)
    (ws / "leadforge.yaml").write_text(CONFIG_YAML, encoding="utf-8", newline="\n")
    shutil.copyfile(FIX / "answers.yaml", ws / "answers.yaml")
    shutil.copyfile(FIX / "user_list.csv", ws / "user_list.csv")

    def step(name: str, argv: list[str], timeout=600):
        t0 = time.time()
        try:
            p = subprocess.run([py, *argv], cwd=ws, env=env, capture_output=True, encoding="utf-8", errors="replace",
                               timeout=timeout, stdin=subprocess.DEVNULL)
            text, code = (p.stdout or "") + (p.stderr or ""), p.returncode
        except subprocess.TimeoutExpired as e:
            text, code = f"TIMEOUT after {timeout}s\n{(e.stdout or b'')!s}", 124
        (out / f"{len(steps):02d}-{name}.log").write_text(text, encoding="utf-8")
        d = digest_of(text)
        steps.append({"step": name, "argv": argv, "exit": code, "digest": d, "seconds": round(time.time() - t0, 1)})
        print(f"  [{len(steps):02d}] {name:<14} exit={code} {json.dumps(d)[:160] if d else '(no LF_DIGEST)'}", flush=True)

    m = ["-m", "leadforge"]
    step("intake", [*m, "intake", "--answers", "answers.yaml"])
    step("plan", [*m, "plan", "--icp", "icp.yaml"])
    step("run-unstamped", [*m, "run", "--icp", "icp.yaml"], timeout=300)
    stamp = ("import json,time;from leadforge import GOSOM_VERSION;from pathlib import Path;"
             "p=Path('leadforge_data');p.mkdir(exist_ok=True);"
             "(p/'.doctor_ok.json').write_text(json.dumps({'at':'harness','t':time.time(),'gosom':GOSOM_VERSION}))")
    step("env-stamp", ["-c", stamp])
    step("discover", [*m, "discover", "--icp", "icp.yaml"])
    step("byol-preview", [*m, "byol", "import", "--in", "user_list.csv"])
    step("byol-apply", [*m, "byol", "import", "--in", "user_list.csv", "--apply"])
    step("run-resume", [*m, "run", "--icp", "icp.yaml", "--resume"])
    step("status", [*m, "status"])
    step("export", [*m, "export", "--icp", "icp.yaml", "--format", "xlsx,csv"])
    return {"steps": steps, "ws": str(ws)}


# ----------------------------------------------------------------------------- reading the result
def read_exports(ws: Path) -> dict:
    from openpyxl import load_workbook

    res: dict = {"tabs": {}, "csv": {}, "report": None, "files": []}
    exp = ws / "leadforge_data" / "exports"
    for f in sorted(exp.rglob("*")) if exp.exists() else []:
        if not f.is_file():
            continue
        res["files"].append(f.relative_to(exp).as_posix())
        if f.suffix == ".xlsx":
            wb = load_workbook(f, data_only=True)
            for ws_ in wb.worksheets:
                rows = [["" if c is None else str(c) for c in r] for r in ws_.iter_rows(values_only=True)]
                res["tabs"][ws_.title] = rows
        elif f.suffix == ".csv":
            res["csv"][f.name] = list(csv.reader(io.StringIO(f.read_text(encoding="utf-8-sig"))))
        elif f.name == "report.json":
            res["report"] = json.loads(f.read_text(encoding="utf-8"))
    return res


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def collect(py: str, label: str, out: Path) -> dict:
    guard = read_jsonl(out / "guard.log")
    reqs = read_jsonl(out / "requests.log")
    camp = json.loads((out / "campaign.json").read_text(encoding="utf-8"))
    ws = Path(camp["ws"])
    data = {"label": label, "steps": camp["steps"], **read_exports(ws), "refused": guard, "requests": reqs}
    (out / "result.raw.json").write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    return data


# ----------------------------------------------------------------------------- normalizing + golden
_NORMS = [
    (re.compile(r"\d{4}-\d\d-\d\d[T ]\d\d:\d\d:\d\d(\.\d+)?(Z|[+-]\d\d:?\d\d)?"), "<TS>"),
    (re.compile(r"\d{4}-\d\d-\d\d"), "<DATE>"),
    (re.compile(r"run_\d{8}_\d+_[0-9a-f]+"), "<RUN>"),
]


def _ws_forms(ws: str) -> list[str]:
    """The workspace path as a child may print it: as given, with / separators, and resolved (Windows hands out the
    8.3 short temp name, RUNNER~1, while the child prints the long one). Longest first."""
    forms = {ws, os.path.realpath(ws)}
    forms |= {f.replace("\\", "/") for f in forms}
    return sorted(forms, key=len, reverse=True)


def norm_str(s: str, ws: str) -> str:
    for w in _ws_forms(ws):
        s = s.replace(w, "<WS>")
    for rx, rep in _NORMS:
        s = rx.sub(rep, s)
    return s


def _walk(o, ws: str):
    if isinstance(o, str):
        return norm_str(o, ws)
    if isinstance(o, list):
        return [_walk(x, ws) for x in o]
    if isinstance(o, dict):
        return {norm_str(k, ws): _walk(v, ws) for k, v in o.items()}
    return o


def one_separator(o):
    """Compare across systems: a path is written with backslash on Windows and / elsewhere (applied to both sides of a compare)."""
    if isinstance(o, str):
        return o.replace("\\", "/")
    if isinstance(o, list):
        return [one_separator(x) for x in o]
    if isinstance(o, dict):
        return {one_separator(k): one_separator(v) for k, v in o.items()}
    return o


def normalized(data: dict, ws: str) -> dict:
    """Drop what must differ between runs (clock, run id, paths, timings, process ids)."""
    d = _walk({k: v for k, v in data.items() if k not in ("label", "files")}, ws)
    for s in d["steps"]:
        s.pop("seconds", None)
    # a DNS packet to the machine's own resolvers (read from the OS) differs per machine in address and number: keep
    # that it happened, once; packets to leadforge's fixed fallbacks (enrich/validate.py get_resolver) keep their count
    refused = [[r["kind"], r["host"], r["port"] or 0, r["caller"]] for r in data["refused"]]
    own = [x for x in refused if x[0] == "sendto" and x[2] == 53 and x[1] not in PUBLIC_RESOLVERS]
    other = [x for x in refused if x not in own]
    d["refused"] = sorted(other + [list(t) for t in {("sendto", "<system resolver>", 53, x[3]) for x in own}])
    # request log: order depends on thread timing -> compare as a sorted multiset without the user agent
    d["requests"] = sorted(f'{r["host"]} {r["path"]} {r["status"]}' for r in data["requests"])
    return d


def leaf_diffs(exp, got, path: str = "", out: list | None = None) -> list[str]:
    """Where two results differ, one short line per leaf (lists of different length: entries only on one side)."""
    out = [] if out is None else out
    if isinstance(exp, dict) and isinstance(got, dict):
        for k in sorted(set(exp) | set(got)):
            if k not in exp or k not in got:
                out.append(f"{path}.{k}: only in {'expected' if k in exp else 'got'}")
            else:
                leaf_diffs(exp[k], got[k], f"{path}.{k}", out)
    elif isinstance(exp, list) and isinstance(got, list):
        if len(exp) == len(got):
            for i, (x, y) in enumerate(zip(exp, got)):
                leaf_diffs(x, y, f"{path}[{i}]", out)
        else:
            ex, go = [json.dumps(x, sort_keys=True) for x in exp], [json.dumps(x, sort_keys=True) for x in got]
            out.append(f"{path}: expected {len(exp)} entries, got {len(go)}")
            out += [f"{path}: only in expected: {x[:200]}" for x in ex if x not in go]
            out += [f"{path}: only in got: {x[:200]}" for x in go if x not in ex]
    elif exp != got:
        out.append(f"{path}: expected {json.dumps(exp)[:200]} got {json.dumps(got)[:200]}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--python", default=sys.executable, help="interpreter of the leadforge install to run")
    ap.add_argument("--label", default="new")
    ap.add_argument("--out", help="output folder (must not hold an earlier run); default: a temp folder")
    ap.add_argument("--update-golden", action="store_true")
    ap.add_argument("--no-golden", action="store_true", help="run and save, do not compare")
    ap.add_argument("--probe", action="store_true", help="only prove the guard refuses an outside address")
    a = ap.parse_args()

    out = Path(a.out) if a.out else Path(tempfile.mkdtemp(prefix=f"lf-e2e-{a.label}-"))
    if a.probe:
        out.mkdir(parents=True, exist_ok=True)
        log = out / "probe.guard.log"
        env = child_env(out, log)
        p = subprocess.run([a.python, str(HARNESS / "probe.py")], env=env, capture_output=True, encoding="utf-8", timeout=60)
        print(p.stdout + p.stderr)
        print("guard log:\n" + (log.read_text(encoding="utf-8") if log.exists() else "(empty)"))
        entries = read_jsonl(log)
        refused = {r["kind"] for r in entries}
        # the OS refuses TCP to a closed loopback port by itself, so the guard's own log is the evidence for port 53
        dns_local = {r["kind"] for r in entries if r["host"] == "127.0.0.53" and r["port"] == 53}
        ok = p.returncode == 0 and {"connect", "dns", "sendto"} <= refused and {"connect", "sendto"} <= dns_local
        print("PROBE", "PASS" if ok else "FAIL")
        return 0 if ok else 1
    ws = out / "ws"
    if ws.exists():
        print(f"FAIL: {ws} already exists; pass a fresh --out", file=sys.stderr)
        return 2
    out.mkdir(parents=True, exist_ok=True)
    srv = start_world(out / "requests.log")
    try:
        print(f"[{a.label}] campaign in {ws}")
        camp = run_campaign(a.python, ws, out)
    finally:
        srv.shutdown()
    (out / "campaign.json").write_text(json.dumps(camp, indent=1), encoding="utf-8")
    data = collect(a.python, a.label, out)
    norm = normalized(data, str(ws))
    (out / "result.json").write_text(json.dumps(norm, indent=1, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    if a.no_golden:
        print(f"saved {out / 'result.json'}")
        return 0
    if a.update_golden:
        GOLDEN.write_text(json.dumps(norm, indent=1, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
        print(f"golden saved: {GOLDEN}")
        return 0
    exp = one_separator(json.loads(GOLDEN.read_text(encoding="utf-8")))
    got = one_separator(json.loads(json.dumps(norm, sort_keys=True)))
    if got == exp:
        print(f"PASS - result equals tests/fixtures/e2e/expected.json ({len(norm['refused'])} refused-call entries, as saved)")
        return 0
    diffs = [k for k in sorted(set(exp) | set(got)) if exp.get(k) != got.get(k)]
    print(f"FAIL - differs from expected.json in: {', '.join(diffs)}  (full result: {out / 'result.json'})")
    lines = leaf_diffs(exp, got)
    for line in lines[:30]:
        print("  " + line)
    if len(lines) > 30:
        print(f"  ... {len(lines) - 30} more")
    return 1


if __name__ == "__main__":
    sys.exit(main())
