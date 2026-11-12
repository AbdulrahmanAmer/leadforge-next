"""Provider abstraction (U3.1).

Contract:
- available() -> (bool, reason): cheap capability probe; never raises.
- fetch(query, limit) -> list[RawListing]: blocking; raises ProviderDegraded for recoverable trouble
  (captcha/cooldown/empty-after-retry) and ProviderFailed only when the provider is unusable outright.
Providers NEVER write to the DB — the discover stage normalizes + upserts (separation keeps dedupe in one place).
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from leadforge.config import Config
from leadforge.grid import PlannedQuery
from leadforge.models import RawListing
from leadforge.util import ProviderFailed


class DiscoveryProvider(ABC):
    name: str = "base"
    supports_tiles: bool = False  # True only when fetch() actually constrains search to query.tile

    def __init__(self, cfg: Config):
        self.cfg = cfg

    @abstractmethod
    def available(self) -> tuple[bool, str]: ...

    @abstractmethod
    def fetch(self, query: PlannedQuery, limit: int | None = None) -> list[RawListing]: ...


PROVIDERS: dict[str, type[DiscoveryProvider]] = {}

# The field names normalize understands for any provider; a provider's own map is merged over this one.
DEFAULT_FIELD_MAP: dict[str, list[str]] = {
    "name": ["title"],
    "category": ["category"],
    "categories": ["categories"],
    "address": ["address"],
    "complete_address": ["complete_address"],  # dict: street/borough/city/postal_code/state/country
    "phone": ["phone"],
    "website": ["web_site", "website"],
    "rating": ["review_rating", "rating"],
    "review_count": ["review_count", "reviews"],
    "lat": ["latitude"],
    "lng": ["longitude"],
    "place_id": ["place_id"],
    "cid": ["cid"],
    "hours": ["open_hours"],
    "maps_url": ["link", "url"],
    # business-profile fields a listing source may carry: about's "Planning" group has the appointment policy,
    # order_online is booking links, status/owner/description are self-explanatory, reviews carries owner
    # replies + credited names as evidence.
    "about": ["about"],
    "order_online": ["order_online"],
    "status": ["status"],
    "owner": ["owner"],
    "description": ["description"],
    "reviews": ["user_reviews_extended", "user_reviews"],
}

# v0.3: every provider registers its own raw-field map so normalize.to_business can dispatch on
# RawListing.provider instead of assuming one source's field names.
FIELD_MAPS: dict[str, dict[str, list[str]]] = {}


def register(cls: type[DiscoveryProvider]) -> type[DiscoveryProvider]:
    PROVIDERS[cls.name] = cls
    fmap = getattr(cls, "FIELD_MAP", None)
    if isinstance(fmap, dict):
        FIELD_MAPS[cls.name] = fmap
    return cls


def register_field_map(name: str, fmap: dict[str, list[str]]) -> None:
    FIELD_MAPS[name] = fmap


def get_field_map(name: str) -> dict[str, list[str]] | None:
    if name not in FIELD_MAPS:
        _import_builtins()
    return FIELD_MAPS.get(name)


ENTRY_POINT_GROUP = "leadforge.providers"


def _load_addons() -> None:
    """The provider seam. Every installed package that declares an entry point in the group
    `leadforge.providers` is called once; it registers its providers with @register / register_field_map.
    Never fatal: an add-on that fails to load is logged and left out, the engine carries on without it."""
    from importlib.metadata import entry_points

    from leadforge.util import LOG

    try:
        eps = entry_points(group=ENTRY_POINT_GROUP)
    except Exception:  # noqa: BLE001 — a broken metadata directory must not take discovery down
        return
    for ep in eps:
        try:
            hook = ep.load()
            if callable(hook):
                hook()
        except Exception as e:  # noqa: BLE001
            LOG.warning("provider add-on '%s' did not load: %s", ep.name, type(e).__name__)


def _import_builtins() -> None:
    """Import the built-in providers so their @register / field maps run (each import is optional so a
    half-built provider module never takes the others down), then let installed add-ons register theirs."""
    import importlib

    for mod in ("dvsa", "companies_house"):
        try:
            importlib.import_module(f"leadforge.providers.{mod}")
        except ImportError:
            continue
    _load_addons()


def get_chain(cfg: Config, only: str | None = None) -> list[DiscoveryProvider]:
    # imports here so registration happens on demand without import cycles
    _import_builtins()

    names = [only] if only else cfg.discovery.providers
    chain: list[DiscoveryProvider] = []
    for name in names:
        cls = PROVIDERS.get(name)
        if cls is None:
            raise ProviderFailed(
                f"provider '{name}' is not available: it is not built in and no installed add-on provides it "
                f"(available: {sorted(PROVIDERS)})")
        chain.append(cls(cfg))
    if not chain:
        raise ProviderFailed("no discovery providers configured")
    return chain
