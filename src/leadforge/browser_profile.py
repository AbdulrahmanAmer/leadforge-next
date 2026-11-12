"""The one place a browser profile folder is made (L7, ADOPT risk 15).

Starting Chrome or Edge on a brand-new profile folder makes one failed Windows logon on a machine whose account has
a password; ten in a short window lock the account (found on the owner's other laptop, 2026-11-11). Every browser
this product starts therefore takes its folder from `prepare_profile`, which seeds a new folder with the recipe
below BEFORE the folder is handed out, and reuses a folder that exists. `tests/test_browser_profile.py` fails when
a start in `src/leadforge` does not call it.

The recipe is the one the owner's setup uses (its ARCHITECTURE 8.5, tried there on Chrome 157 and Edge 156):
`Local State` = {"password_manager": {"os_password_blank": false, "os_password_last_changed": "<N>"}} with
N = (Unix milliseconds + 11644473600000) x 1000, as a string. Here only the file is proven; its effect on a
machine with a password is not (this one has none).
"""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

LOCAL_STATE = "Local State"
_WINDOWS_EPOCH_OFFSET_MS = 11_644_473_600_000  # 1601-01-01 to 1970-01-01, in milliseconds


def local_state_text(now_ms: int | None = None) -> str:
    ms = int(time.time() * 1000) if now_ms is None else now_ms
    changed = str((ms + _WINDOWS_EPOCH_OFFSET_MS) * 1000)
    return json.dumps({"password_manager": {"os_password_blank": False, "os_password_last_changed": changed}})


_slots_lock = threading.Lock()
_slots_busy: dict[str, set[int]] = {}


def take_slot(kind: str) -> int:
    """The lowest free slot number of `kind`: a browser keeps its profile folder locked, so each live browser of a
    kind gets its own folder (`<kind>-<slot>`), and the same folders are used again on the next start."""
    with _slots_lock:
        busy = _slots_busy.setdefault(kind, set())
        slot = next(i for i in range(len(busy) + 1) if i not in busy)
        busy.add(slot)
        return slot


def free_slot(kind: str, slot: int) -> None:
    with _slots_lock:
        _slots_busy.get(kind, set()).discard(slot)


def prepare_profile(root: Path, name: str, now_ms: int | None = None) -> Path:
    """-> the profile folder `root/name`. A new (or empty) folder holds the seeded `Local State` when this returns;
    a folder with anything in it is reused as it is. `name` is one plain folder name, never a path."""
    if not name or name in {".", ".."} or Path(name).name != name or "\\" in name or "/" in name:
        raise ValueError(f"a browser profile name is one plain folder name, got {name!r}")
    folder = Path(root) / name
    folder.mkdir(parents=True, exist_ok=True)
    if not any(folder.iterdir()):
        tmp = folder / (LOCAL_STATE + ".tmp")
        tmp.write_text(local_state_text(now_ms), encoding="utf-8")
        os.replace(tmp, folder / LOCAL_STATE)  # the file appears whole or not at all
    return folder
