"""Slice keyring-lock: requirements-keyring.lock carries the `keyring` extra on top of requirements.lock.

The window's bundle installs both with `pip install --require-hashes --only-binary :all:`. Offline: the lock pins `keyring` at
pyproject's version, every pin has a hash, nothing in it differs from requirements.lock, and every package uv.lock reaches from
`keyring` is pinned in one of the two files. The real install of both files runs in CI (the `fake campaign` jobs)."""
import re
import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MAIN = REPO / "requirements.lock"
EXTRA = REPO / "requirements-keyring.lock"


def _pins(text: str) -> dict[str, tuple[str, set[str]]]:
    """name -> (version, hashes) of a pip requirements file in uv export's layout."""
    out: dict[str, tuple[str, set[str]]] = {}
    for block in re.split(r"\n(?=[A-Za-z0-9])", text):
        m = re.match(r"([A-Za-z0-9_.\-]+)==([^\s;\\]+)", block)
        if m:
            out[m.group(1).lower()] = (m.group(2), set(re.findall(r"--hash=(sha256:[0-9a-f]{64})", block)))
    return out


def test_keyring_lock_pins_the_extra_with_hashes_and_agrees_with_the_main_lock():
    extra, main = _pins(EXTRA.read_text(encoding="utf-8")), _pins(MAIN.read_text(encoding="utf-8"))
    pin = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))["project"]["optional-dependencies"]["keyring"]
    assert len(pin) == 1 and re.fullmatch(r"keyring==\S+", pin[0]), f"the extra is not one exact pin: {pin}"
    assert "keyring" in extra and f"keyring=={extra['keyring'][0]}" == pin[0], f"lock {extra.get('keyring')}, pyproject {pin}"
    for name, (version, hashes) in extra.items():
        assert hashes, f"{name}=={version} has no hash"
        assert name not in main or main[name][0] == version, f"{name}: keyring lock {version}, requirements.lock {main[name][0]}"


def test_keyring_lock_holds_the_whole_closure_from_uv_lock():
    held = _pins(EXTRA.read_text(encoding="utf-8")) | _pins(MAIN.read_text(encoding="utf-8"))
    uv = {p["name"]: p for p in tomllib.loads((REPO / "uv.lock").read_text(encoding="utf-8"))["package"]}
    todo, seen = ["keyring"], set()
    while todo:
        name = todo.pop()
        if name in seen:
            continue
        seen.add(name)
        assert name in held, f"{name} (reached from keyring in uv.lock) is in neither lock"
        assert held[name][0] == uv[name]["version"], f"{name}: lock {held[name][0]}, uv.lock {uv[name]['version']}"
        todo += [d["name"] for d in uv[name].get("dependencies", [])]
