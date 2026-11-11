"""C3 (slice L2): `python install.py` installs the CLI's dependencies from the hashed lock, like the plugin
launcher; the package itself adds nothing unchecked (--no-deps, --no-build-isolation)."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def test_install_py_installs_from_the_hashed_lock(monkeypatch, capsys):
    spec = importlib.util.spec_from_file_location("lf_install", REPO / "install.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    calls: list[list[str]] = []

    def fake_run(argv, *a, **k):
        calls.append([str(x) for x in argv])
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.setattr(mod.subprocess, "run", fake_run)
    monkeypatch.setattr(sys, "argv", ["install.py", "--targets", "none-such"])
    assert mod.main() == 0
    pips = [c for c in calls if c[1:4] == ["-m", "pip", "install"]]
    assert pips, f"no pip install ran: {calls}"
    assert "--require-hashes" in pips[0] and str(REPO / "requirements.lock") in pips[0], pips[0]
    assert all("--require-hashes" in c or "--no-deps" in c for c in pips), f"an install without the lock: {pips}"
