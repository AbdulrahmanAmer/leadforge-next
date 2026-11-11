"""C2 (slice L2): `config` never prints a key value. A fake key is planted; no output contains it."""

from __future__ import annotations

from typer.testing import CliRunner

from leadforge.cli import app

FAKE = "FAKE-KEY-0123456789abcdef-not-real"


def _out(res) -> str:
    return (res.output or "") + (getattr(res, "stderr", "") or "")


def test_config_set_and_get_never_print_a_key(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    for key in ("registry.companies_house_key", "registry.opencorporates_token"):
        res = runner.invoke(app, ["config", "set", key, FAKE])
        assert res.exit_code == 0, _out(res)
        assert FAKE not in _out(res)
        assert "hidden" in _out(res)
        res = runner.invoke(app, ["config", "get", key])
        assert res.exit_code == 0, _out(res)
        assert FAKE not in _out(res)
    # the value is still written: the command works, it only stops echoing it
    assert FAKE in (tmp_path / "leadforge.yaml").read_text(encoding="utf-8")


def test_config_still_prints_ordinary_values(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    res = CliRunner().invoke(app, ["config", "get", "agent.model"])
    assert res.exit_code == 0
    assert "hidden" not in _out(res)
