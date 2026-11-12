"""L9 item 3 (C2): an operator's own `agent.command` may carry a key in its arguments. No `AgentFailed` message, and
no traceback of one, holds an argument's text: not for a non-zero exit (also when the program echoes its arguments
on stderr), an empty stdout, a timeout, or a program that cannot start."""

from __future__ import annotations

import sys
import traceback

import pytest

from leadforge import agent_runner

FAKE = "-".join(["FAKE", "agent", "planted", "for", "the", "scan", "not", "real"])

ECHO_AND_FAIL = """\
import sys
sys.stderr.write("usage error, I was given: " + " ".join(sys.argv[1:]) + " and " + sys.argv[1].split("=", 1)[1] + "\\n")
sys.exit(3)
"""
EMPTY = "import sys\nsys.exit(0)\n"
SLEEP = "import time\ntime.sleep(5)\n"


def _fail_text(cfg, tmp_path, body: str | None, timeout_s: int | None = None) -> str:
    if body is None:
        cfg.agent.command = [str(tmp_path / "no-such-program.exe"), "--api-key=" + FAKE, FAKE]
    else:
        script = tmp_path / "fake_agent.py"
        script.write_text(body, encoding="utf-8")
        cfg.agent.command = [sys.executable, str(script), "--api-key=" + FAKE, FAKE]
    with pytest.raises(agent_runner.AgentFailed) as e:
        agent_runner.run_agent(cfg, "prompt", timeout_s=timeout_s)
    return str(e.value) + "\n" + "".join(traceback.format_exception(e.value))


@pytest.mark.parametrize("case", ["exit", "empty", "timeout", "cannot start"])
def test_agent_failed_never_holds_an_argument(cfg, tmp_path, case):
    body, timeout_s = {"exit": (ECHO_AND_FAIL, None), "empty": (EMPTY, None), "timeout": (SLEEP, 1),
                       "cannot start": (None, None)}[case]
    text = _fail_text(cfg, tmp_path, body, timeout_s)
    assert FAKE not in text, text
    assert "<3 arguments hidden>" in text or "<2 arguments hidden>" in text  # the program is named, the count shown
    if case == "exit":
        assert "usage error, I was given: <argument hidden> <argument hidden> and <argument hidden>" in text
