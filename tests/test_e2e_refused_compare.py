"""G2 compares WHICH outside calls the fake campaign refused (kind, host, port, caller), not how often a resolver retried one."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("e2e_fake_campaign", ROOT / "scripts" / "e2e_fake_campaign.py")
e2e = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(e2e)


def entry(host, kind="sendto", port=53, caller="dns"):
    return {"kind": kind, "host": host, "port": port, "caller": caller}


def refused_of(entries):
    data = {"steps": [], "tabs": {}, "csv": {}, "report": None, "refused": entries, "requests": []}
    return e2e.normalized(data, "/ws")["refused"]


BASE = [entry("1.1.1.1"), entry("8.8.8.8"), entry("10.0.0.1")]


def test_one_more_retry_of_a_known_call_changes_nothing():
    assert refused_of(BASE) == refused_of(BASE + [entry("1.1.1.1")] * 9 + [entry("8.8.8.8")])


def test_a_new_host_port_or_kind_is_a_different_result():
    base = refused_of(BASE)
    assert refused_of(BASE + [entry("203.0.113.5", kind="connect", port=443)]) != base  # an outside host that was not refused before
    assert refused_of(BASE + [entry("1.1.1.1", port=443)]) != base            # same host, other port
    assert refused_of(BASE + [entry("1.1.1.1", kind="connect")]) != base      # same host, other kind
    assert refused_of(BASE + [entry("1.1.1.1", caller="http")]) != base       # same call, other caller


def test_a_saved_call_that_no_longer_happens_is_a_different_result():
    assert refused_of([entry("8.8.8.8"), entry("10.0.0.1")]) != refused_of(BASE)


def test_the_saved_result_equals_any_retry_count():
    saved = json.loads((ROOT / "tests" / "fixtures" / "e2e" / "expected.json").read_text(encoding="utf-8"))["refused"]
    for n in (1, 10, 15):
        got = refused_of([entry("1.1.1.1")] * n + [entry("8.8.8.8")] * n + [entry("10.0.0.1")])
        assert got == saved
