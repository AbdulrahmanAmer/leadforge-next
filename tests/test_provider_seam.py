"""C17 (slice L8): the public engine has no Maps code. Extra providers come only through the entry-point seam.

Pass lines these tests hold:
  * asking for a provider that no add-on provides prints "not available" and starts no browser or process;
  * an add-on that is installed is found through the seam (a made-up one here, no private code needed);
  * an add-on that fails to load never takes the engine down;
  * with only registers configured the plan holds no text-search queries.
Nothing here opens a socket or a browser."""
from __future__ import annotations

import json
import subprocess
import sys
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from leadforge.cli import app
from leadforge.grid import build_plan
from leadforge.providers import base as pbase
from leadforge.util import ProviderFailed

# the user-facing key of the private add-on's provider; only the NAME is public, no code behind it
ASKED = "maps"


def _answers(tmp_path):
    (tmp_path / "answers.yaml").write_text(
        "campaign: t\noffer:\n  what: Web redesign\n"
        "target:\n  categories: [auto repair shop]\n"
        "  geography:\n    country: GB\n    areas: ['Bristol']\n", encoding="utf-8")


def _no_start(monkeypatch):
    """Every way to start a browser or a helper process records itself and fails loudly."""
    started: list[str] = []

    def _boom(name):
        def _raise(*a, **k):
            started.append(name)
            raise AssertionError(f"something was started: {name}")
        return _raise

    monkeypatch.setattr(subprocess.Popen, "__init__", _boom("Popen"))
    monkeypatch.setattr(subprocess, "run", _boom("subprocess.run"))
    for mod in ("playwright", "playwright.sync_api", "crawl4ai"):
        monkeypatch.setitem(sys.modules, mod, None)  # `import playwright` now raises ImportError
    return started


def test_asking_for_maps_without_the_add_on_says_not_available_and_starts_nothing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _answers(tmp_path)
    runner = CliRunner()
    assert runner.invoke(app, ["--json", "intake", "--answers", "answers.yaml"]).exit_code == 0
    monkeypatch.setattr("leadforge.pipeline.ensure_ready", lambda cfg: None)
    monkeypatch.setattr(pbase, "_load_addons", lambda: None)  # this test venv may hold the private add-on: leave it out
    started = _no_start(monkeypatch)

    res = runner.invoke(app, ["--json", "discover", "--icp", "icp.yaml", "--provider", ASKED])

    assert started == [], f"a process or browser was started: {started}"
    assert res.exit_code != 0
    assert "not available" in res.output, res.output[-600:]
    line = next(ln for ln in res.output.splitlines() if ln.startswith("LF_DIGEST "))
    assert json.loads(line[len("LF_DIGEST "):])["ok"] is False


def test_get_chain_names_the_provider_that_is_not_available(cfg, monkeypatch):
    monkeypatch.setattr(pbase, "_load_addons", lambda: None)
    cfg.discovery.providers = [ASKED]
    with pytest.raises(ProviderFailed, match=f"provider '{ASKED}' is not available"):
        pbase.get_chain(cfg)


def _fake_entry_point(name, hook):
    def load():
        if isinstance(hook, Exception):
            raise hook
        return hook
    return SimpleNamespace(name=name, load=load)


def test_an_installed_add_on_is_found_through_the_seam(cfg, monkeypatch):
    class AddonProvider(pbase.DiscoveryProvider):
        name = "made_up_addon"

        def available(self):
            return True, "ok"

        def fetch(self, query, limit=None):
            return []

    monkeypatch.setattr(pbase, "PROVIDERS", dict(pbase.PROVIDERS))  # register() writes into a copy; undone after
    monkeypatch.setattr("importlib.metadata.entry_points",
                        lambda group=None: [_fake_entry_point("made_up", lambda: pbase.register(AddonProvider))]
                        if group == pbase.ENTRY_POINT_GROUP else [])
    cfg.discovery.providers = ["made_up_addon"]

    chain = pbase.get_chain(cfg)

    assert [p.name for p in chain] == ["made_up_addon"]


def test_an_add_on_that_fails_to_load_never_takes_the_engine_down(cfg, monkeypatch):
    monkeypatch.setattr("importlib.metadata.entry_points",
                        lambda group=None: [_fake_entry_point("broken", RuntimeError("boom"))])
    cfg.discovery.providers = ["dvsa"]

    chain = pbase.get_chain(cfg)  # the built-in register still loads

    assert [p.name for p in chain] == ["dvsa"]


def test_registers_only_plan_has_no_text_search_queries(cfg, sample_icp, monkeypatch):
    monkeypatch.delenv("LEADFORGE_DISCOVERY__PROVIDERS", raising=False)  # the suite's made-up default off
    cfg.discovery.providers = ["dvsa"]
    cfg.discovery.grid_mode = "off"
    qs = build_plan(sample_icp, cfg)
    assert qs and all(q.provider == "dvsa" for q in qs)


def test_the_public_default_chain_is_the_register():
    from leadforge.config import Config

    assert Config().discovery.providers == ["dvsa"]
