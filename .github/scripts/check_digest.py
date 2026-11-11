#!/usr/bin/env python3
"""Agent contract smoke: `leadforge --json version` and `--json status` each print exactly one LF_DIGEST line."""

from __future__ import annotations

import subprocess
import sys
import tempfile

failures = []
with tempfile.TemporaryDirectory() as tmp:
    for cmd in (["--json", "version"], ["--json", "status"]):
        out = subprocess.run(
            [sys.executable, "-m", "leadforge", *cmd], capture_output=True, text=True, cwd=tmp, check=False
        ).stdout
        n = sum(1 for line in out.splitlines() if line.startswith("LF_DIGEST "))
        print(f"leadforge {' '.join(cmd)}: {n} LF_DIGEST line(s)")
        if n != 1:
            failures.append(cmd)
sys.exit(1 if failures else 0)
