"""L9 item 4 (C1 carried over from L2): on Windows `claude` is often npm's `claude.cmd` shim, so LeadForge's argv goes
through cmd.exe and `%*` before the program sees it. The empty argument after `--tools` must survive that, or the call
would run with tools. A FAKE shim (npm's own layout; its last line starts an interpreter with a script and `%*`)
records the argv it was given; the recorded argv must equal the golden. The real `claude` is never started."""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

import pytest

from leadforge import agent_runner

REAL_WHICH = shutil.which  # taken before tests/conftest.py's autouse fixture hides `claude`
GOLDEN = Path(__file__).parent / "golden" / "autopilot_builtin_command.json"

# npm's cmd-shim for a bin, with node's path and the package's cli.js swapped for this Python and the recorder
SHIM = """@ECHO off
GOTO start
:find_dp0
SET dp0=%~dp0
EXIT /b
:start
SETLOCAL
CALL :find_dp0
SET "_prog={python}"
endLocal & goto #_undefined_# 2>NUL || title %COMSPEC% & "%_prog%"  "%dp0%\\record_argv.py" %*
"""
RECORDER = """import json, sys
from pathlib import Path
Path(__file__).with_name("argv.json").write_text(json.dumps(sys.argv[1:]), encoding="utf-8")
print('{"ok": true}')
"""


@pytest.mark.skipif(os.name != "nt", reason="a .cmd shim exists only on Windows")
def test_empty_tools_argument_survives_an_npm_claude_cmd_shim(cfg, tmp_path, monkeypatch):
    shim_dir = tmp_path / "npm"
    shim_dir.mkdir()
    (shim_dir / "claude.cmd").write_text(SHIM.format(python=sys.executable), encoding="utf-8", newline="\r\n")
    (shim_dir / "record_argv.py").write_text(RECORDER, encoding="utf-8")
    monkeypatch.setenv("PATH", str(shim_dir))
    monkeypatch.setattr(agent_runner.shutil, "which", REAL_WHICH)
    cmd = agent_runner.resolve_command(cfg)
    assert cmd is not None and Path(cmd[0]).name.lower() == "claude.cmd"  # the shim is what LeadForge picked
    assert agent_runner.run_agent(cfg, "hello").strip() == '{"ok": true}'
    recorded = json.loads((shim_dir / "argv.json").read_text(encoding="utf-8"))
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))["argv"][1:]
    assert recorded == golden
    assert recorded[recorded.index("--tools") + 1] == ""
