"""A made-up discovery provider for tests: the public engine ships no text-search provider of its own.

Tests that drive discover through the pipeline or the CLI patch `available` and `fetch` of this class, the way
they used to patch a real engine. conftest.py points the default provider chain at it (env override), so the
tests need no leadforge.yaml. Nothing here runs a process, opens a browser or touches the network.
"""
from __future__ import annotations

from leadforge.grid import PlannedQuery
from leadforge.models import RawListing
from leadforge.providers.base import DiscoveryProvider, register

NAME = "fakelist"


@register
class FakeProvider(DiscoveryProvider):
    name = NAME
    supports_tiles = True

    def available(self) -> tuple[bool, str]:
        return True, "made-up provider"

    def fetch(self, query: PlannedQuery, limit: int | None = None) -> list[RawListing]:
        return []
