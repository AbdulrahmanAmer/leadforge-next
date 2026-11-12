"""The repository's loopback fakes for the REAL engine started by the window's core (slice L11, 2026-11-12). Test scaffolding:
never bundled, never read by the core.

The core starts the engine isolated (`python -X utf8 -I`, the environment cleared to a short list), so the fake campaign's
harness (tests/fixtures/e2e/harness/sitecustomize.py: every non-loopback connection refused, the invented *.example sites
resolved to 127.0.0.1, the `fixture_list` provider) cannot arrive by PYTHONPATH. Instead:
  * `prepare` writes the workspace's own files: leadforge.yaml (the fake campaign's CONFIG_YAML: dvsa and the Companies House
    lookup on 127.0.0.1, keyring off) and `.lf-e2e-harness.json` (the harness's settings);
  * `loader on` puts a two-file loader into the DEV venv's site-packages (`-I` still reads `.pth` files there); the loader does
    nothing unless the engine's working folder holds `.lf-e2e-harness.json`; `loader off` removes both files. The bundled
    engine cannot load it: its `python312._pth` has no `import site`;
  * `serve` runs the fake world (the e2e script's own server) until a stop file appears or a bound passes.

    python fake_world.py prepare --ws <dir> --out <dir>
    python fake_world.py loader on|off --venv <dir>
    python fake_world.py serve --out <dir> --stop <file> --bound <seconds>
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))
import e2e_fake_campaign as fake  # noqa: E402

MARKER = ".lf-e2e-harness.json"
PTH = "lf_e2e_harness_loader.pth"
MOD = "lf_e2e_harness_loader.py"
LOADER = f'''"""Fake-campaign harness loader (LeadForge window tests, packaging/fake_world.py). Inert unless the working folder holds
{MARKER}. Removed by `fake_world.py loader off`."""
import importlib.util, json, os
_p = os.path.join(os.getcwd(), "{MARKER}")
if os.path.isfile(_p):
    with open(_p, encoding="utf-8") as _f:
        _cfg = json.load(_f)
    os.environ.update(_cfg["env"])
    _spec = importlib.util.spec_from_file_location("lf_e2e_sitecustomize", _cfg["harness"])
    _m = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_m)
'''


def site_packages(venv: Path) -> Path:
    sp = venv / "Lib" / "site-packages"
    if not sp.is_dir():
        raise SystemExit(f"no site-packages in {venv}")
    return sp


def prepare(ws: Path, out: Path, registers_only: bool = False) -> None:
    ws.mkdir(parents=True, exist_ok=True)
    out.mkdir(parents=True, exist_ok=True)
    config = fake.CONFIG_YAML
    if registers_only:   # no `fixture_list`: that provider exists only inside the harness, which a bundled engine never loads
        config = config.replace("providers: [fixture_list, dvsa]", "providers: [dvsa]")
        assert "fixture_list" not in config
    (ws / "leadforge.yaml").write_text(config, encoding="utf-8", newline="\n")
    env = {"LF_GUARD_LOG": str(out / "guard.log"), "LF_GUARD_HOSTS": ",".join(fake.HOSTS),
           "LF_FAKE_LISTINGS": str(fake.FIX / "listings.json"),
           # the fixture key of the fake Companies House (made up, in the public repository); the workspace reads no keyring
           "LEADFORGE_REGISTRY__COMPANIES_HOUSE_KEY": fake.CH["key"], "PYTHONUTF8": "1"}
    (ws / MARKER).write_text(json.dumps({"env": env, "harness": str(fake.HARNESS / "sitecustomize.py")}), encoding="utf-8")
    print(f"prepared {ws}")


def loader(on: bool, venv: Path) -> None:
    sp = site_packages(venv)
    if on:
        (sp / MOD).write_text(LOADER, encoding="utf-8", newline="\n")
        (sp / PTH).write_text("import lf_e2e_harness_loader\n", encoding="utf-8", newline="\n")
    else:
        for name in (PTH, MOD):
            (sp / name).unlink(missing_ok=True)
        for c in (sp / "__pycache__").glob("lf_e2e_harness_loader*") if (sp / "__pycache__").is_dir() else []:
            c.unlink(missing_ok=True)
    left = [n for n in (PTH, MOD) if (sp / n).exists()]
    print(f"loader {'on' if on else 'off'}: files present {left}")


def serve(out: Path, stop: Path, bound: float) -> None:
    out.mkdir(parents=True, exist_ok=True)
    srv = fake.start_world(out / "requests.log")
    print(f"fake world on 127.0.0.1:{fake.WORLD['port']}", flush=True)
    t0 = time.monotonic()
    try:
        while not stop.exists() and time.monotonic() - t0 < bound:
            time.sleep(0.3)
    finally:
        srv.shutdown()
        srv.server_close()
    print(f"fake world stopped after {time.monotonic() - t0:.0f} s ({'stop file' if stop.exists() else 'bound'})", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("--ws", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--registers-only", action="store_true")
    p = sub.add_parser("loader")
    p.add_argument("state", choices=("on", "off"))
    p.add_argument("--venv", required=True)
    p = sub.add_parser("serve")
    p.add_argument("--out", required=True)
    p.add_argument("--stop", required=True)
    p.add_argument("--bound", type=float, default=900)
    a = ap.parse_args()
    if a.cmd == "prepare":
        prepare(Path(a.ws), Path(a.out), a.registers_only)
    elif a.cmd == "loader":
        loader(a.state == "on", Path(a.venv))
    else:
        serve(Path(a.out), Path(a.stop), a.bound)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
