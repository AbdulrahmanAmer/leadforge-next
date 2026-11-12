"""The window's run commands against the fake campaign's loopback world (slice L11a).

    python scripts/e2e_window_run.py --out <folder>

Uses scripts/e2e_fake_campaign.py's world (invented sites, registers and Maps listings on 127.0.0.1) and its child
harness (every non-loopback connection or lookup refused and logged). In child processes, as the window's shell would:
`window run_start` (fresh), `window run_stop` while it runs, `window run_status`, `window run_start` with resume until
it finishes, then `window campaigns_list`, `window sheet_export`, `window people_list`. PASS when every stdout line is
JSON, the first run ends `stopped` and keeps its place, the resumed one ends `finished`, and no outside attempt was made.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import e2e_fake_campaign as fake  # noqa: E402

CAMPAIGN = "bristol-garages-fixture"


def window(py: str, ws: Path, env: dict, name: str, args: dict, timeout: int = 120) -> tuple[int, str, str]:
    p = subprocess.run([py, "-m", "leadforge", "window", name], cwd=ws, env=env, input=json.dumps(args), capture_output=True,
                       encoding="utf-8", errors="replace", timeout=timeout)
    return p.returncode, p.stdout, p.stderr


def stream_run(py: str, ws: Path, env: dict, resume: bool, stop_after_enrich: int | None, log: Path) -> tuple[int, list[dict], list[str]]:
    """run_start in a child; with `stop_after_enrich`, run_stop from a second child once that many enrich events arrived."""
    p = subprocess.Popen([py, "-m", "leadforge", "window", "run_start"], cwd=ws, env=env, stdin=subprocess.PIPE,
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding="utf-8", errors="replace")
    p.stdin.write(json.dumps({"args": {"campaign": CAMPAIGN, "resume": resume}}))
    p.stdin.close()
    err: list[str] = []
    t = threading.Thread(target=lambda: err.extend(p.stderr), daemon=True)
    t.start()
    lines, raw, enrich_seen, stopper = [], [], 0, None
    stopped_at, arrived = None, []
    for line in p.stdout:
        raw.append(line)
        arrived.append(time.monotonic())
        doc = json.loads(line)   # a line that is not JSON fails the proof here
        lines.append(doc)
        if stop_after_enrich is not None and len(lines) == 1:
            # started now, released later: on a loaded machine a fresh interpreter takes seconds to start, and the stop
            # must reach the run while it is still visiting businesses. The child waits for its arguments on stdin.
            stopper = subprocess.Popen([py, "-m", "leadforge", "window", "run_stop"], cwd=ws, env=env, stdin=subprocess.PIPE,
                                       stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, encoding="utf-8", errors="replace")
        if doc.get("type") == "progress" and doc["stage"] == "enrich":
            enrich_seen += 1
            if stopper is not None and stopper.returncode is None and enrich_seen == stop_after_enrich:
                so, _ = stopper.communicate(json.dumps({"runId": lines[0]["runId"]}), timeout=120)
                stopped_at = time.monotonic()
                print(f"  run_stop exit={stopper.returncode} {so.strip()[:200]}", flush=True)
    code = p.wait(timeout=600)
    ended_at = time.monotonic()
    t.join(timeout=10)
    if stopped_at is not None:
        print(f"  run_stop answered to the run's end: {ended_at - stopped_at:.2f} s", flush=True)
    gaps = [b - a for a, b in zip(arrived[1:-1], arrived[2:], strict=True)]
    if gaps:
        print(f"  longest wait between two stream lines (two checks of the stop flag): {max(gaps):.2f} s", flush=True)
    log.write_text("".join(raw) + "\n--- stderr ---\n" + "".join(err), encoding="utf-8")
    return code, lines, err


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--python", default=sys.executable)
    a = ap.parse_args()
    out = Path(a.out).resolve()
    shutil.rmtree(out, ignore_errors=True)
    ws = out / "ws"
    ws.mkdir(parents=True)
    srv = fake.start_world(out / "requests.log")
    try:
        env = fake.child_env(ws, out / "guard.log")
        (ws / "leadforge.yaml").write_text(fake.CONFIG_YAML, encoding="utf-8", newline="\n")
        cdir = ws / "campaigns" / CAMPAIGN
        cdir.mkdir(parents=True)
        shutil.copyfile(fake.FIX / "answers.yaml", cdir / "answers.yaml")
        subprocess.run([a.python, "-m", "leadforge", "--json", "intake", "--answers", str(cdir / "answers.yaml"), "--out",
                        str(cdir / "icp.yaml")], cwd=ws, env=env, check=True, capture_output=True, timeout=120)
        checks: list[tuple[str, bool, str]] = []

        code, first, _ = stream_run(a.python, ws, env, False, 2, out / "run1.log")
        end = first[-1] if first else {}
        checks.append(("first run ends stopped", code == 0 and end.get("type") == "stopped", f"exit {code}, last {json.dumps(end)[:300]}"))
        rid = first[0]["runId"] if first else ""
        code, st, _ = window(a.python, ws, env, "run_status", {"runId": rid})
        status = json.loads(st) if code == 0 else {}
        checks.append(("run_status says stopped, stage kept", status.get("state") == "stopped" and status.get("stage") == "enrich", st.strip()[:300]))
        checks.append(("no stop flag left", not (ws / "leadforge_data" / "window-run.stop").exists(), ""))

        code, second, _ = stream_run(a.python, ws, env, True, None, out / "run2.log")
        end = second[-1] if second else {}
        checks.append(("resumed run ends finished, same run", code == 0 and end.get("type") == "finished"
                       and second[0]["runId"] == rid, f"exit {code}, last {json.dumps(end)[:300]}"))
        for name, args in (("campaigns_list", {}), ("sheet_export", {"runId": rid}), ("people_list", {"query": {"search": "", "limit": 5}})):
            code, so, _ = window(a.python, ws, env, name, args)
            ok = code == 0 and so.count("\n") == 1
            checks.append((f"{name} answers one JSON document", ok, so.strip()[:300]))
            (out / f"{name}.json").write_text(so, encoding="utf-8")
        # every outside attempt was refused by the guard; the rule is the fake campaign's: none outside its known set
        known = {tuple(x) for x in json.loads(fake.GOLDEN.read_text(encoding="utf-8"))["refused"]}
        got = {tuple(x) for x in fake.normalized({"steps": [], "refused": fake.read_jsonl(out / "guard.log"), "requests": []}, str(ws))["refused"]}
        checks.append(("no outside attempt beyond the fake campaign's known set", got <= known, json.dumps(sorted(got - known))[:300]))
    finally:
        srv.shutdown()
    for label, ok, detail in checks:
        print(f"{'PASS' if ok else 'FAIL'}  {label}  {detail}")
    passed = all(ok for _, ok, _ in checks)
    print("E2E WINDOW RUN " + ("PASS" if passed else "FAIL"))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
