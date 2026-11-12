"""L9 item 2 (C2): the registry keys come from the environment or the OS keyring only, never from leadforge.yaml.
A key in the file is refused with a message that names the setting, never the value. The keyring is always the
fake from tests/conftest.py (or a fake module below): the real keyring of the machine is never read or written."""

from __future__ import annotations

import sys
import types

import pytest
from typer.testing import CliRunner

from leadforge.cli import app
from leadforge.config import KEY_SETTINGS, KeyInConfigFile, key_env_name, load_config
from leadforge.config import _keyring_get as REAL_KEYRING_GET  # taken before the autouse fake replaces it

FAKE = "-".join(["FAKE", "registry", "planted", "for", "the", "scan", "not", "real"])


def _out(res) -> str:
    return (res.output or "") + (getattr(res, "stderr", "") or "")


@pytest.mark.parametrize("name", KEY_SETTINGS)
def test_a_key_in_the_file_is_refused_by_name_never_by_value(tmp_path, monkeypatch, name):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "leadforge.yaml").write_text(f"registry:\n  {name}: {FAKE}\n", encoding="utf-8")
    with pytest.raises(KeyInConfigFile) as e:
        load_config(tmp_path)
    assert f"registry.{name}" in str(e.value) and key_env_name(name) in str(e.value)
    assert FAKE not in str(e.value)
    res = CliRunner().invoke(app, ["status"])  # every command reports it, whole message, no value
    assert res.exit_code != 0
    assert f"registry.{name} must not be in leadforge.yaml" in _out(res) and key_env_name(name) in _out(res)
    assert FAKE not in _out(res)


def test_an_empty_key_in_the_file_is_still_accepted(tmp_path):
    (tmp_path / "leadforge.yaml").write_text('registry:\n  companies_house_key: ""\n', encoding="utf-8")
    assert load_config(tmp_path).registry.companies_house_key == ""


def test_keys_come_from_the_environment_as_written(tmp_path, monkeypatch):
    monkeypatch.setenv(key_env_name("companies_house_key"), FAKE)
    monkeypatch.setenv(key_env_name("opencorporates_token"), "0123")  # YAML would read this as the number 83
    cfg = load_config(tmp_path)
    assert cfg.registry.companies_house_key == FAKE
    assert cfg.registry.opencorporates_token == "0123"
    assert cfg._key_sources == {"companies_house_key": "environment", "opencorporates_token": "environment"}


def test_keys_come_from_the_keyring_when_the_environment_has_none(tmp_path, monkeypatch, keyring_fake):
    keyring_fake["registry.opencorporates_token"] = FAKE
    keyring_fake["registry.companies_house_key"] = "from-the-keyring"
    monkeypatch.setenv(key_env_name("companies_house_key"), "from-the-environment")
    cfg = load_config(tmp_path)
    assert cfg.registry.opencorporates_token == FAKE
    assert cfg.registry.companies_house_key == "from-the-environment"  # the environment wins
    assert cfg._key_sources == {"companies_house_key": "environment", "opencorporates_token": "OS keyring"}
    (tmp_path / "leadforge.yaml").write_text("registry:\n  keyring: false\n", encoding="utf-8")
    assert load_config(tmp_path).registry.opencorporates_token == ""  # switched off: not looked at


def test_the_keyring_lookup_without_the_package_and_with_a_broken_backend(monkeypatch, caplog):
    monkeypatch.setitem(sys.modules, "keyring", None)  # `import keyring` raises ImportError
    assert REAL_KEYRING_GET("companies_house_key") is None
    asked = []

    def get_password(service, name):
        asked.append((service, name))
        return FAKE

    monkeypatch.setitem(sys.modules, "keyring", types.SimpleNamespace(get_password=get_password))
    assert REAL_KEYRING_GET("companies_house_key") == FAKE
    assert asked == [("leadforge", "registry.companies_house_key")]

    def broken(service, name):
        raise RuntimeError("no backend")

    monkeypatch.setitem(sys.modules, "keyring", types.SimpleNamespace(get_password=broken))
    assert REAL_KEYRING_GET("opencorporates_token") is None
    assert "OS keyring not readable for registry.opencorporates_token: RuntimeError" in caplog.text


def test_config_set_refuses_a_key_and_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    for args in (["config", "set", "registry.companies_house_key", FAKE],
                 ["config", "set", "registry", "{opencorporates_token: " + FAKE + "}"]):
        res = runner.invoke(app, args)
        assert res.exit_code == 2, _out(res)
        assert "must not be in leadforge.yaml" in _out(res) and FAKE not in _out(res)
    assert not (tmp_path / "leadforge.yaml").exists()
    res = runner.invoke(app, ["config", "set", "registry.companies_house_key", ""])  # clearing one is allowed
    assert res.exit_code == 0, _out(res)


def test_config_get_says_where_a_key_is_from_never_the_value(tmp_path, monkeypatch, keyring_fake):
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    res = runner.invoke(app, ["config", "get", "registry.companies_house_key"])
    assert res.exit_code == 0 and "not set" in _out(res) and key_env_name("companies_house_key") in _out(res)
    monkeypatch.setenv(key_env_name("companies_house_key"), FAKE)
    keyring_fake["registry.opencorporates_token"] = FAKE
    res = runner.invoke(app, ["config", "get", "registry.companies_house_key"])
    assert "from the environment" in _out(res) and FAKE not in _out(res)
    res = runner.invoke(app, ["config", "get", "registry.opencorporates_token"])
    assert "from the OS keyring" in _out(res) and FAKE not in _out(res)
