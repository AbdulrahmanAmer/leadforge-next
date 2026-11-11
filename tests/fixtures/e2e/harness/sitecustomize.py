"""Socket guard + fixture-fed discovery stand-in for the fake-campaign proof (scripts/e2e_fake_campaign.py).

Loaded by Python at start-up because this folder is on PYTHONPATH of every campaign process.
  * Every connection and every name lookup that is not loopback is refused and appended to the file named by
    LF_GUARD_LOG (one JSON object per line: kind, host, port, caller, leadforge frame).
  * Names listed in LF_GUARD_HOSTS (comma list, the invented *.example sites) resolve to 127.0.0.1 inside this
    process only - the guard is the resolver for the fixture world; no real lookup happens.
  * The pinned Maps scraper binary is never used: if LF_FAKE_MAPS names a gosom-shaped JSON file, the `gosom`
    provider is replaced by a subclass that reads that file through the real GosomProvider._parse.
Nothing here ships; it is test scaffolding and is only found when a harness puts it on PYTHONPATH.
"""
from __future__ import annotations

import ipaddress
import json
import os
import socket
import sys
import time

_LOG = os.environ.get("LF_GUARD_LOG")
_FAKE_HOSTS = {h.strip().lower() for h in os.environ.get("LF_GUARD_HOSTS", "").split(",") if h.strip()}
_real_getaddrinfo = socket.getaddrinfo
_real_gethostbyname = socket.gethostbyname
_real_gethostbyname_ex = socket.gethostbyname_ex
_real_connect = socket.socket.connect
_real_connect_ex = socket.socket.connect_ex
_real_sendto = socket.socket.sendto


def _is_loopback_ip(host) -> bool:
    try:
        return ipaddress.ip_address(str(host).split("%")[0]).is_loopback
    except ValueError:
        return False


def _callers() -> tuple[str, str]:
    """(first non-stdlib package on the stack, first leadforge frame) - best effort, never raises."""
    pkg, lf = "", ""
    try:
        f = sys._getframe(2)
        while f is not None:
            name = f.f_globals.get("__name__", "")
            top = name.split(".")[0]
            if not lf and top == "leadforge":
                lf = f"{name}:{f.f_lineno}"
            if not pkg and top not in ("socket", "ssl", "encodings", "sitecustomize", "_socket", "http", "urllib", "selectors",
                                        "threading", "concurrent", "asyncio"):
                pkg = top
            if pkg and lf:
                break
            f = f.f_back
    except Exception:  # noqa: BLE001
        pass
    return pkg, lf


def _refuse(kind: str, host, port, exc: Exception):
    pkg, lf = _callers()
    if _LOG:
        try:
            with open(_LOG, "a", encoding="utf-8") as fh:
                fh.write(json.dumps({"t": round(time.time(), 3), "pid": os.getpid(), "kind": kind, "host": str(host),
                                     "port": port, "caller": pkg, "leadforge": lf}) + "\n")
        except OSError:
            pass
    raise exc


def _addr(address):
    if isinstance(address, tuple) and address:
        return address[0], (address[1] if len(address) > 1 else None)
    return address, None


def getaddrinfo(host, port, *a, **k):
    h = host.decode() if isinstance(host, bytes) else host
    if h is None or (isinstance(h, str) and (h.lower() == "localhost" or _is_loopback_ip(h))):
        return _real_getaddrinfo(host, port, *a, **k)
    if isinstance(h, str) and h.lower() in _FAKE_HOSTS:
        return _real_getaddrinfo("127.0.0.1", port, *a, **k)
    _refuse("dns", h, port, socket.gaierror(socket.EAI_NONAME, "LF_GUARD: name lookup refused (not loopback)"))


def gethostbyname(host):
    if host.lower() in _FAKE_HOSTS:
        return "127.0.0.1"
    if host.lower() == "localhost" or _is_loopback_ip(host):
        return _real_gethostbyname(host)
    _refuse("dns", host, None, socket.gaierror(socket.EAI_NONAME, "LF_GUARD: name lookup refused (not loopback)"))


def gethostbyname_ex(host):
    if host.lower() in _FAKE_HOSTS:
        return (host, [], ["127.0.0.1"])
    if host.lower() == "localhost" or _is_loopback_ip(host):
        return _real_gethostbyname_ex(host)
    _refuse("dns", host, None, socket.gaierror(socket.EAI_NONAME, "LF_GUARD: name lookup refused (not loopback)"))


def _guard_addr_call(real, kind):
    def wrapper(self, address, *a):
        if self.family in (socket.AF_INET, socket.AF_INET6):
            host, port = _addr(address)
            if not _is_loopback_ip(host):
                _refuse(kind, host, port, ConnectionRefusedError(f"LF_GUARD: {kind} to {host}:{port} refused (not loopback)"))
        return real(self, address, *a)
    return wrapper


def _guard_sendto(self, data, *args):
    address = args[-1] if args else None
    if self.family in (socket.AF_INET, socket.AF_INET6) and address is not None:
        host, port = _addr(address)
        if not _is_loopback_ip(host):
            _refuse("sendto", host, port, ConnectionRefusedError(f"LF_GUARD: sendto {host}:{port} refused (not loopback)"))
    return _real_sendto(self, data, *args)


socket.getaddrinfo = getaddrinfo
socket.gethostbyname = gethostbyname
socket.gethostbyname_ex = gethostbyname_ex
socket.socket.connect = _guard_addr_call(_real_connect, "connect")
socket.socket.connect_ex = _guard_addr_call(_real_connect_ex, "connect_ex")
socket.socket.sendto = _guard_sendto


def _install_fake_maps(path: str) -> None:
    try:
        from leadforge.providers import base as _base
        from leadforge.providers import gosom as _gosom
    except Exception:  # noqa: BLE001 - leadforge not importable in this process (pip etc.): nothing to replace
        return
    from pathlib import Path

    class FixtureGosom(_gosom.GosomProvider):
        def available(self):
            return True, "fixture-fed stand-in (no binary)"

        def fetch(self, query, limit=None):
            area = (query.area or "").casefold()
            rows = [r for r in self._parse(Path(path))
                    if area and area in str(r.data.get("address", "")).casefold()]
            return rows[:limit] if limit else rows

    _base.PROVIDERS["gosom"] = FixtureGosom


if os.environ.get("LF_FAKE_MAPS"):
    _install_fake_maps(os.environ["LF_FAKE_MAPS"])
