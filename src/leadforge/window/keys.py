"""The window's key commands go through this one small adapter (slice L11a).

Keys in the OS keyring are slice L9, which is not in this branch's base. The adapter uses L9's keyring service when
`leadforge.config` has it (`KEYRING_SERVICE`), and answers `not_available` when it does not. The entry names are L9's:
`registry.<key name>` under that service. A key's value goes to the backend and nowhere else: it is never returned,
printed or logged. The backend is handed in (tests use a fake; the real one is the `keyring` package, loaded only here).
"""

from __future__ import annotations

from typing import Protocol

KEY_NAMES = ("companies_house_key", "opencorporates_token")


class KeysNotAvailable(Exception):  # noqa: N818 — the window's error kind `not_available`
    """No keyring for the window: L9 is not in this build, or the `keyring` package is not installed."""


class Backend(Protocol):
    """What the adapter needs from a keyring: the three calls of the `keyring` package."""

    def get_password(self, service: str, username: str) -> str | None: ...
    def set_password(self, service: str, username: str, password: str) -> None: ...
    def delete_password(self, service: str, username: str) -> None: ...


def l9_service() -> str | None:
    """L9's keyring service name, or None while L9 is not in this build."""
    from leadforge import config

    return getattr(config, "KEYRING_SERVICE", None)


def default_backend() -> Backend:
    try:
        import keyring
    except ImportError as e:
        raise KeysNotAvailable("the keyring package is not installed") from e
    return keyring


class Keys:
    def __init__(self, backend: Backend, service: str):
        self._backend = backend
        self._service = service

    @staticmethod
    def _entry(name: str) -> str:
        return f"registry.{name}"

    def status(self, name: str) -> dict:
        saved = bool(self._backend.get_password(self._service, self._entry(name)))
        # savedAt: the keyring keeps no date (gap, see the slice file)
        return {"name": name, "saved": saved, "savedAt": None}

    def list(self) -> list[dict]:
        return [self.status(n) for n in KEY_NAMES]

    def save(self, name: str, value: str) -> dict:
        self._backend.set_password(self._service, self._entry(name), value)
        return self.status(name)

    def remove(self, name: str) -> dict:
        if self._backend.get_password(self._service, self._entry(name)):
            self._backend.delete_password(self._service, self._entry(name))
        return self.status(name)


def make_keys() -> Keys:
    """The adapter the window uses. Raises KeysNotAvailable until L9 is in (and without the keyring package)."""
    service = l9_service()
    if service is None:
        raise KeysNotAvailable("this engine reads its keys from leadforge.yaml; keys in the OS keyring come with slice L9")
    return Keys(default_backend(), service)
