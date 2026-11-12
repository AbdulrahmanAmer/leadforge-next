"""The window's fake campaign against the same campaign through the command line (slice L11, 2026-11-12). Test scaffolding.

    python compare_campaign.py --window-ws <ws> --window-exports <snapshot of ws/leadforge_data/exports> --cli <folder>

Takes the campaign the window made (`campaigns/<name>/icp.yaml` in the window's workspace), runs it through the command line
(`run --icp`, then `export --icp --format xlsx,csv`) in a FRESH workspace under --cli with the same fakes and harness as
scripts/e2e_fake_campaign.py (its child environment, its CONFIG_YAML), and compares with that script's own reading and
normalizing: the sheet's tabs, the csv files and report.json; then the engine's digest of the command-line run against the
window run's status. Prints one line per compared part and PASS or FAIL.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))
import e2e_fake_campaign as fake  # noqa: E402


def exports_of(folder: Path, ws: str) -> dict:
    """fake.read_exports on an exports folder (a snapshot or the live one), normalized the script's way."""
    tmp_ws = folder.parent.parent if folder.name == "exports" else None
    if tmp_ws is not None and (tmp_ws / "leadforge_data" / "exports") == folder:
        data = fake.read_exports(tmp_ws)
    else:   # a snapshot: give read_exports a workspace shape around it
        shim = folder.parent / "_shim"
        shutil.rmtree(shim, ignore_errors=True)
        (shim / "leadforge_data").mkdir(parents=True)
        shutil.copytree(folder, shim / "leadforge_data" / "exports")
        data = fake.read_exports(shim)
        shutil.rmtree(shim, ignore_errors=True)
    data.pop("files", None)
    return fake.one_separator(fake._walk(data, ws))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--window-ws", required=True)
    ap.add_argument("--window-exports", required=True)
    ap.add_argument("--window-status", required=True, help="the window run's RunStatus (JSON file)")
    ap.add_argument("--cli", required=True)
    ap.add_argument("--python", default=sys.executable)
    a = ap.parse_args()
    wws = Path(a.window_ws)
    icps = sorted(wws.glob("campaigns/*/icp.yaml"))
    if len(icps) != 1:
        print(f"FAIL: expected one campaign in the window's workspace, found {[str(p) for p in icps]}")
        return 1
    name = icps[0].parent.name
    out = Path(a.cli)
    ws = out / "ws"
    if ws.exists():
        print(f"FAIL: {ws} exists; give a fresh folder")
        return 2
    cdir = ws / "campaigns" / name
    cdir.mkdir(parents=True)
    for f in ("answers.yaml", "icp.yaml", "window.json"):
        if (icps[0].parent / f).exists():
            shutil.copyfile(icps[0].parent / f, cdir / f)
    (ws / "leadforge.yaml").write_text(fake.CONFIG_YAML, encoding="utf-8", newline="\n")
    env = fake.child_env(ws, out / "guard.log")
    srv = fake.start_world(out / "requests.log")
    digests = {}
    try:
        for step, argv in (("run", ["run", "--icp", str(cdir / "icp.yaml")]),
                           ("export", ["export", "--icp", str(cdir / "icp.yaml"), "--format", "xlsx,csv"])):
            p = subprocess.run([a.python, "-m", "leadforge", "--json", *argv], cwd=ws, env=env, capture_output=True,
                               encoding="utf-8", errors="replace", timeout=900, stdin=subprocess.DEVNULL)
            (out / f"{step}.log").write_text(p.stdout + p.stderr, encoding="utf-8")
            digests[step] = fake.digest_of(p.stdout + p.stderr)
            print(f"cli {step}: exit {p.returncode}; digest counts {json.dumps((digests[step] or {}).get('counts'))[:400]}")
    finally:
        srv.shutdown()
        srv.server_close()
    win = exports_of(Path(a.window_exports), str(wws))
    cli = exports_of(ws / "leadforge_data" / "exports", str(ws))
    ok = True
    for part in ("tabs", "csv", "report"):
        same = win.get(part) == cli.get(part)
        ok &= same
        size = len(json.dumps(cli.get(part)))
        print(f"{'EQUAL' if same else 'DIFFERENT'}  {part} ({size} characters normalized)")
        if not same:
            for line in fake.leaf_diffs(cli.get(part), win.get(part), part)[:20]:
                print("   cli vs window: " + line)
    # the engine's digest of the command-line run against the window run's own status
    status = json.loads(Path(a.window_status).read_text(encoding="utf-8"))
    counts = (digests.get("run") or {}).get("counts") or {}
    # the run's digest names the businesses of the sheet `leads`; the window's RunStatus names them `businesses`
    pairs = [("businesses (window) = leads (digest)", status["counts"]["businesses"], counts.get("leads")),
             ("stage", status["stage"], "export" if (digests.get("run") or {}).get("ok") else None)]
    for label, w, c in pairs:
        same = w == c
        ok &= same
        print(f"{'EQUAL' if same else 'DIFFERENT'}  {label}: window {w!r}, command line {c!r}")
    # and against the repository's own saved result: the parts the window's campaign shares with it
    golden = fake.one_separator(json.loads(fake.GOLDEN.read_text(encoding="utf-8")))
    for part in ("tabs", "csv", "report"):
        print(f"expected.json {part}: {'equal' if golden.get(part) == win.get(part) else 'not equal'} to the window's "
              "(expected.json is the CLI campaign WITH byol import and a resume: not the same campaign)")
    print("CAMPAIGN COMPARE " + ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
