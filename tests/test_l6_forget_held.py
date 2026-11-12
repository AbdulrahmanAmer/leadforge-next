"""L6 build 2, item 2: `forget` never says it forgot while a file still holds the value. Every person here is invented.

A detached run keeps its log open; on Windows such a file cannot be replaced. Either the file is scrubbed in spite of that, or the
command names the file and exits non-zero.
"""
import json
import subprocess
import sys

from typer.testing import CliRunner

from leadforge import retention
from leadforge.cli import app
from tests.test_l6_forget import BYSTANDER_LINE, EMAIL, NAME, TARGET_LINE, _w, plant

HOLDER = ("import sys; f = open(sys.argv[1], 'a', encoding='utf-8'); print('held', flush=True); sys.stdin.readline(); f.close()")


def digest_of(output: str) -> dict:
    return json.loads([ln for ln in output.splitlines() if ln.startswith("LF_DIGEST ")][-1][len("LF_DIGEST "):])


def test_a_log_held_open_by_another_process_is_scrubbed_or_named(tmp_path, monkeypatch):
    plant(tmp_path)
    log = _w(tmp_path / "leadforge_data" / "logs" / "run_x.detach.log", f"INFO a {TARGET_LINE}\nINFO b {BYSTANDER_LINE}\n")
    holder = subprocess.Popen([sys.executable, "-c", HOLDER, str(log)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    try:
        assert holder.stdout.readline().strip() == "held"      # the second process now holds the file open
        monkeypatch.chdir(tmp_path)
        res = CliRunner().invoke(app, ["forget", EMAIL])
    finally:
        holder.stdin.write("\n")
        holder.stdin.flush()
        holder.wait(timeout=30)
    after = log.read_bytes().decode("utf-8")
    assert EMAIL not in res.output and NAME not in res.output
    if res.exit_code == 0:                                      # then it must really be scrubbed, and the bystander's line kept
        assert EMAIL not in after and BYSTANDER_LINE in after, after
    else:                                                       # or the command says which file still holds the value
        assert res.exit_code == 4 and "run_x.detach.log" in res.output, res.output


def test_a_file_that_can_be_neither_replaced_nor_rewritten_is_named_and_the_exit_is_not_zero(tmp_path, monkeypatch):
    plant(tmp_path)
    log = _w(tmp_path / "leadforge_data" / "logs" / "run_x.detach.log", f"INFO a {TARGET_LINE}\nINFO b {BYSTANDER_LINE}\n")

    def refuse(*a, **k):
        raise PermissionError("held open by another program")

    monkeypatch.setattr(retention.os, "replace", refuse)
    monkeypatch.setattr(retention, "_rewrite_in_place", refuse)
    monkeypatch.chdir(tmp_path)
    res = CliRunner().invoke(app, ["forget", EMAIL])
    assert res.exit_code == 4, res.output
    d = digest_of(res.output)
    assert d["ok"] is False and "leadforge_data/logs/run_x.detach.log" in " ".join(d["warnings"] + d["artifacts"]).replace("\\", "/")
    assert EMAIL not in res.output and NAME not in res.output and "forgot that" not in res.output
    assert EMAIL in log.read_bytes().decode("utf-8")           # it really is still there: the command did not lie about it
    assert d["counts"]["rows"] > 0                              # the database part was done and is reported
    monkeypatch.undo()
    monkeypatch.chdir(tmp_path)
    again = CliRunner().invoke(app, ["forget", EMAIL])          # repeatable: with the file free again it finishes
    assert again.exit_code == 0 and EMAIL not in log.read_bytes().decode("utf-8")
