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


def test_config_never_prints_a_key_through_its_parent_or_a_proxy_address(tmp_path, monkeypatch):
    """A key is also hidden when the command names the section that holds it, when a whole section is
    set at once (also as unparseable YAML), and when it sits in a proxy address as user:password."""
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    proxy = f"http://user:{FAKE}@upstream.example:8080"
    calls = [
        ["config", "set", "registry.companies_house_key", FAKE],
        ["config", "get", "registry"],
        ["config", "set", "registry", "{opencorporates_token: " + FAKE + "}"],
        ["config", "get", "registry"],
        ["config", "set", "registry", "{opencorporates_token: " + FAKE],
        ["config", "set", "discovery.upstreams", f"['{proxy}']"],
        ["config", "get", "discovery.upstreams"],
        ["config", "get", "discovery"],
    ]
    for args in calls:
        res = runner.invoke(app, args)
        assert FAKE not in _out(res), f"{' '.join(args[:3])} printed the key: {_out(res)}"
    res = runner.invoke(app, ["config", "get", "registry"])
    assert "opencorporates_token" in _out(res) and "hidden" in _out(res)
    assert "upstream.example:8080" in _out(runner.invoke(app, ["config", "get", "discovery.upstreams"]))


def test_config_hides_every_shape_of_proxy_password_and_plural_key_names(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    addresses = [f"http://user:{FAKE}@x@upstream.example:8080", f"user:{FAKE}@upstream.example:8080",
               f"http://user:{FAKE.replace('-', '/')}@upstream.example:8080"]
    res = runner.invoke(app, ["config", "set", "discovery.upstreams", str(addresses)])
    assert res.exit_code == 0, _out(res)
    out = _out(runner.invoke(app, ["config", "get", "discovery"]))
    assert "upstream.example:8080" in out
    for secret in (FAKE, FAKE.replace("-", "/"), "not-real", "not/real"):
        assert secret not in out, out
    (tmp_path / "leadforge.yaml").write_text(f"registry:\n  extra_tokens: [{FAKE}]\n", encoding="utf-8")
    out = _out(runner.invoke(app, ["config", "get", "registry"]))
    assert FAKE not in out, out
