"""The window's key commands go through this one small adapter (slice L11a, on L9's keyring).

L9 keeps the registry keys in the OS keyring under service `config.KEYRING_SERVICE`, entry `registry.<key name>`, and the
engine reads them with `config._keyring_get`. The adapter reads through that same function, so the window shows exactly what
the engine will read, and writes and deletes through the `keyring` package under the same service and entry. A key's value
goes to the backend and nowhere else: it is never returned, printed or logged. The backend is handed in (tests use a fake;
the real one is the `keyring` package, L9's optional extra, loaded only here).
"""

from __future__ import annotations

from typing import Protocol

from leadforge import config

KEY_NAMES = config.KEY_SETTINGS   # ("companies_house_key", "opencorporates_token"): engine.ts KeyName


class KeyringMissing(Exception):  # noqa: N818 — the window's error kind `environment`
    """The `keyring` package (L9's extra `keyring`) is not installed on this computer."""


class Backend(Protocol):
    """What the adapter needs from a keyring to change it: two calls of the `keyring` package."""

    def set_password(self, service: str, username: str, password: str) -> None: ...
    def delete_password(self, service: str, username: str) -> None: ...


def default_backend() -> Backend:
    try:
        import keyring
    except ImportError as e:
        raise KeyringMissing("the keyring package is not installed") from e
    return keyring


def entry(name: str) -> str:
    """L9's entry name for a registry key (config.key_refusal names the same one)."""
    return f"registry.{name}"


class Keys:
    def __init__(self, backend: Backend):
        self._backend = backend

    @staticmethod
    def status(name: str) -> dict:
        saved = bool((config._keyring_get(name) or "").strip())   # L9's own read: what a run will find
        # savedAt: the keyring keeps no date (KeyStatus.savedAt may be null)
        return {"name": name, "saved": saved, "savedAt": None}

    def list(self) -> list[dict]:
        return [self.status(n) for n in KEY_NAMES]

    def save(self, name: str, value: str) -> dict:
        self._backend.set_password(config.KEYRING_SERVICE, entry(name), value)
        return self.status(name)

    def remove(self, name: str) -> dict:
        if config._keyring_get(name):
            self._backend.delete_password(config.KEYRING_SERVICE, entry(name))
        return self.status(name)


def make_keys() -> Keys:
    """The adapter the window uses. Raises KeyringMissing without the keyring package."""
    return Keys(default_backend())
