import sqlite3

import pytest

from leadforge import db
from leadforge.config import load_config


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return load_config(tmp_path)


@pytest.fixture
def conn(cfg) -> sqlite3.Connection:
    return db.connect(cfg.db_path)


@pytest.fixture
def sample_icp():
    from leadforge.models import ICP

    return ICP.model_validate({
        "campaign": "test-campaign",
        "offer": {"what": "Website redesign", "value_prop": "more jobs"},
        "target": {"categories": ["auto repair shop"],
                   "geography": {"areas": ["Houston, TX"], "country": "US"},
                   "size": {"min_reviews": 10}},
        "qualify": {"hard": ["no_phone"], "soft": ["website_missing", "stale_site"]},
        "decision_maker": {"titles_priority": ["Owner", "General Manager"]},
    })


@pytest.fixture(autouse=True)
def _no_ui(monkeypatch):
    """Tests must never pop Excel or console windows (auto-open features, v0.1.3)."""
    monkeypatch.setenv("LEADFORGE_NO_UI", "1")

@pytest.fixture(autouse=True)
def _no_real_ner_model(monkeypatch, request):
    """Layer 3: enrichment starts a NER worker process that loads real GLiNER (~25 s) when gliner is
    installed. Plumbing tests must not pay that (it tripled suite time); the env var also reaches the
    `python -m leadforge` subprocesses. NER-worker tests inject a fake model, and gpu-marked tests load the
    real one, so both opt out."""
    if request.node.get_closest_marker("gpu") or request.node.fspath.basename == "test_ner_worker.py":
        return
    monkeypatch.setenv("LEADFORGE_NO_NER_MODEL", "1")


@pytest.fixture(autouse=True)
def _never_autodetect_claude(monkeypatch):
    """v0.4: `agent_runner.resolve_command` auto-detects `claude` on PATH. A test that reaches the
    autopilot labeling/drafting stages without patching the runner would otherwise shell out to the
    operator's real Claude Code (it happened in the 2026-09-03 full-suite run). Explicit
    `agent.command` lists (the fake scripts in test_agent_runner.py) still work."""
    import leadforge.agent_runner as _ar
    monkeypatch.setattr(_ar.shutil, "which", lambda *a, **k: None)


@pytest.fixture(autouse=True)
def _never_the_real_keyring(monkeypatch):
    """L9 (C2): the registry keys may come from the OS keyring. No test ever reads or writes the real one: the
    lookup is replaced by a fake that holds nothing (a test fills `keyring_fake` to plant a key), the switch is off
    for `python -m leadforge` children, and the operator's own keys in the environment never reach a test."""
    import leadforge.config as _cfg
    store: dict[str, str] = {}
    monkeypatch.setattr(_cfg, "_keyring_get", lambda name: store.get(f"registry.{name}"))
    monkeypatch.setenv("LEADFORGE_REGISTRY__KEYRING", "false")
    for name in _cfg.KEY_SETTINGS:
        monkeypatch.delenv(_cfg.key_env_name(name), raising=False)
    return store


@pytest.fixture
def keyring_fake(_never_the_real_keyring, monkeypatch):
    """The fake keyring's store, with the keyring lookup switched on for this test (in this process only)."""
    monkeypatch.delenv("LEADFORGE_REGISTRY__KEYRING", raising=False)
    return _never_the_real_keyring
