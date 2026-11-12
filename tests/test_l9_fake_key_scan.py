"""L9 item 6 (C2): the fake-key scan. A fake key is planted in every key setting (Companies House key through the
environment, OpenCorporates token through the fake keyring, a key inside `agent.command`'s arguments, and a key
written in leadforge.yaml), then EVERY command of the CLI is run and its output, every log record, every file the
workspace got and every error is scanned: no fake key appears anywhere. Outside connections and outside programs are
refused for the whole test (nothing reaches the network; no browser, no scraper binary, no real `claude`).

The full pipeline with a real key in use (intake, plan, run, discover, byol import, status, export) is scanned by the
fake campaign (scripts/e2e_fake_campaign.py), which plants its own keys and scans every step's output."""

from __future__ import annotations

import json
import socket
import subprocess
import sys
from pathlib import Path

import typer
from typer.testing import CliRunner

from leadforge import db
from leadforge.cli import app
from leadforge.config import key_env_name, load_config

_PIECES = ["planted", "for", "the", "scan", "not", "real"]
FAKE_CH = "-".join(["FAKE", "ch", *_PIECES])        # environment
FAKE_OC = "-".join(["FAKE", "oc", *_PIECES])        # OS keyring (the fake)
FAKE_AGENT = "-".join(["FAKE", "agent", *_PIECES])  # an argument of agent.command
FAKE_FILE = "-".join(["FAKE", "file", *_PIECES])    # written in leadforge.yaml (refused)
FAKES = {"Companies House key": FAKE_CH, "OpenCorporates token": FAKE_OC, "agent.command argument": FAKE_AGENT,
         "key in leadforge.yaml": FAKE_FILE}

# commands that are not run here, and why (the test fails when one of these names stops existing)
NOT_RUN = {
    ("dashboard",): "serves pages until stopped",
    ("watch",): "follows a live run until stopped",
}
FAIL_AGENT = """\
import sys
sys.stderr.write("cannot use " + " ".join(sys.argv[1:]) + "\\n")
sys.exit(2)
"""
GB_ANSWERS = """campaign: t
offer:
  what: Web redesign
target:
  categories: [accounting firm]
  geography:
    areas: [Leeds]
    country: GB
"""


def _leaf_commands() -> list[tuple[str, ...]]:
    out: list[tuple[str, ...]] = []

    def walk(cmd, path: tuple[str, ...]) -> None:
        if getattr(cmd, "commands", None):  # a group (typer ships its own click)
            for name, sub in cmd.commands.items():
                walk(sub, (*path, name))
        else:
            out.append(path)

    walk(typer.main.get_command(app), ())
    return sorted(out)


def _guard(monkeypatch, agent_script: Path) -> list[str]:
    refused: list[str] = []
    real_connect, real_popen_init = socket.socket.connect, subprocess.Popen.__init__

    def connect(self, address):
        if isinstance(address, tuple) and address[0] in ("127.0.0.1", "::1", "localhost"):
            return real_connect(self, address)
        refused.append(f"connect {address!r}")
        raise ConnectionRefusedError("refused by the fake-key scan")

    def getaddrinfo(host, *a, **k):
        refused.append(f"dns {host!r}")
        raise socket.gaierror(socket.EAI_NONAME, "refused by the fake-key scan")

    def popen_init(self, args, *a, **k):
        argv = [str(x) for x in (args if isinstance(args, (list, tuple)) else [args])]
        if argv[:2] == [sys.executable, str(agent_script)] or (len(argv) > 1 and argv[0] == "taskkill"):
            return real_popen_init(self, args, *a, **k)
        refused.append(f"program {Path(argv[0]).name}")
        raise FileNotFoundError("refused by the fake-key scan")

    monkeypatch.setattr(socket.socket, "connect", connect)
    monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)
    monkeypatch.setattr(subprocess.Popen, "__init__", popen_init)
    return refused


def _hits(text: str) -> list[str]:
    return [label for label, fake in FAKES.items() if fake in text]


def test_no_planted_key_in_any_output_log_file_or_error(tmp_path, monkeypatch, keyring_fake, caplog):
    import logging

    from tests.test_dm_auto_label import _seed_business

    caplog.set_level(logging.DEBUG)
    monkeypatch.chdir(tmp_path)
    agent_script = tmp_path / "fake_agent.py"
    agent_script.write_text(FAIL_AGENT, encoding="utf-8")
    refused = _guard(monkeypatch, agent_script)
    monkeypatch.setenv(key_env_name("companies_house_key"), FAKE_CH)
    keyring_fake["registry.opencorporates_token"] = FAKE_OC
    base_yaml = ("agent:\n  command: " + json.dumps([sys.executable, str(agent_script), "--api-key=" + FAKE_AGENT])
                 + "\nregistry:\n  opencorporates_enabled: true\nexport:\n  auto_open: false\nprogress_window: false\n")
    (tmp_path / "leadforge.yaml").write_text(base_yaml, encoding="utf-8")
    (tmp_path / "answers.yaml").write_text(GB_ANSWERS, encoding="utf-8")
    runner = CliRunner()
    texts: list[tuple[str, str]] = []

    def run(args: list[str]) -> None:
        res = runner.invoke(app, args)
        exc = "" if res.exception is None or isinstance(res.exception, SystemExit) else repr(res.exception)
        texts.append((" ".join(args), (res.output or "") + exc))

    leaves = _leaf_commands()
    assert set(NOT_RUN) <= set(leaves), "a command named in NOT_RUN is gone: update the list"
    for path in leaves:  # every command, as a user would first try it
        if path not in NOT_RUN:
            run([*path])
            run(["--json", *path])
    for args in (["config", "get", "registry.companies_house_key"], ["config", "get", "registry.opencorporates_token"],
                 ["config", "get", "registry"], ["config", "get", "agent"], ["config", "get", "agent.command"],
                 ["config", "set", "registry.companies_house_key", FAKE_FILE],
                 ["config", "set", "registry", "{opencorporates_token: " + FAKE_FILE + "}"],
                 ["intake", "--answers", "answers.yaml"], ["plan", "--icp", "icp.yaml"], ["doctor", "--json"],
                 ["status"], ["enrich", "--stage", "registry"], ["run", "--icp", "icp.yaml"]):
        run(args)

    # the agent call fails through the real labeling path: AgentFailed is logged with its traceback at debug level
    from leadforge import agent_runner
    from leadforge.enrich import dm
    from leadforge.intake import load_icp
    cfg = load_config(tmp_path)
    conn = db.connect(cfg.db_path)
    _seed_business(conn, "biz_a", [("Jane Smith", "Owner", "...")])
    out = dm.auto_label(conn, load_icp(Path("icp.yaml")), cfg,
                        runner=agent_runner.make_ndjson_runner(cfg, dm.LABEL_INSTRUCTIONS))
    assert out["agent_failures"] == 1  # the planted argument really went through a failed call

    # an old workspace with a key written in the file: every command refuses it by name
    (tmp_path / "leadforge.yaml").write_text(
        base_yaml.replace("registry:\n", "registry:\n  companies_house_key: " + FAKE_FILE + "\n"), encoding="utf-8")
    for path in leaves:
        if path not in NOT_RUN:
            run([*path])
    assert any("must not be in leadforge.yaml" in t for _, t in texts)

    files = [p for p in tmp_path.rglob("*") if p.is_file() and p.name not in ("leadforge.yaml", "fake_agent.py")]
    found = [f"{cmd}: {_hits(t)}" for cmd, t in texts if _hits(t)]
    found += [f"log record: {_hits(caplog.text)}"] if _hits(caplog.text) else []
    found += [f"{p.relative_to(tmp_path)}: {_hits(p.read_text(encoding='utf-8', errors='replace'))}"
              for p in files if _hits(p.read_text(encoding="utf-8", errors="replace"))]
    assert found == [], found
    assert len(texts) > 2 * (len(leaves) - len(NOT_RUN)), len(texts)
    print(f"fake-key scan: {len(texts)} command runs, {len(files)} files, {len(caplog.records)} log records; "
          f"refused by the guard: {sorted(set(refused))}")
