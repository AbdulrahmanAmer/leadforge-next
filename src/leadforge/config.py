"""Layered configuration (U0.3).

Order: built-in defaults -> ./leadforge.yaml (workspace) -> env LEADFORGE_SECTION__KEY.
All runtime state lives under `data_dir` (default ./leadforge_data). Nothing here performs network I/O.
The registry keys (KEY_SETTINGS) are the exception (L9, C2): never from leadforge.yaml (refused there), only from the
environment or the OS keyring.
"""

from __future__ import annotations

import ipaddress
import logging
import os
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit

import yaml
from pydantic import BaseModel, Field, field_validator

CH_BASE_DEFAULT = "https://api.company-information.service.gov.uk"
KEY_SETTINGS = ("companies_house_key", "opencorporates_token")  # in the `registry` section
KEYRING_SERVICE = "leadforge"


def key_env_name(name: str) -> str:
    return f"LEADFORGE_REGISTRY__{name.upper()}"


def key_refusal(name: str) -> str:
    """Why a key in leadforge.yaml is refused and where it goes instead. Names the setting, never the value."""
    return (f"registry.{name} must not be in leadforge.yaml: keys are read only from the environment variable "
            f"{key_env_name(name)} or the OS keyring (service '{KEYRING_SERVICE}', name 'registry.{name}', e.g. "
            f"`keyring set {KEYRING_SERVICE} registry.{name}`); remove it from leadforge.yaml")


class KeyInConfigFile(ValueError):
    """A registry key written in leadforge.yaml (L9, C2)."""


def _keyring_get(name: str) -> str | None:
    """The OS keyring's entry for registry.<name>, or None. The `keyring` package is optional (extra `keyring`);
    without it the environment still works. tests/conftest.py replaces this function, so no test reads a real keyring."""
    try:
        import keyring
    except ImportError:
        return None
    try:
        return keyring.get_password(KEYRING_SERVICE, f"registry.{name}")
    except Exception as e:  # noqa: BLE001 — a broken backend counts as "not set", with a warning (no value)
        logging.getLogger("leadforge").warning("OS keyring not readable for registry.%s: %s", name, type(e).__name__)
        return None


class DvsaCfg(BaseModel):
    """DVSA 'Active MOT test stations' register (gov.uk, OGL, refreshed quarterly) - v0.3 provider `dvsa`."""

    url: str = "https://assets.publishing.service.gov.uk/media/69a0638bc497bac082bc7741/active-mot-stations.csv"
    refresh_days: int = 90


class CompaniesHouseDiscoveryCfg(BaseModel):
    """Companies House advanced search as a discovery provider (company mode, v0.3)."""

    page_size: int = 100
    max_hits_per_shard: int = 9000  # the API stops paging at 10k; a bigger shard must be split
    exclude_sic: list[str] = Field(default_factory=lambda: ["82200"])  # call centres = competitors (owner decision 7)


class MapsListCfg(BaseModel):
    """Native list-first Google Maps provider (`maps_list`, speed unit) — docs/09, ADR-014.

    Measured 2026-09-02 (probe_list2.py, plain Playwright, no stealth): one persistent browser,
    ~120 cards per search in 25-28s once the browser is up (13s page load + ~15s scrolling);
    phone on 119-120/120 cards, website on 83-91/120. Defaults below are set from that probe.
    """

    max_cards: int = 130            # Google Maps list caps out ~120/search server-side regardless
    search_delay_s: float = 4.0     # politeness gap between searches in one browser; +/-30% jitter applied
    max_searches_per_hour: int = 120  # token-bucket cap per provider instance
    visit_details: bool = False     # opt-in place-page visit for full address/hours/plus-code on NEW cards only
    detail_tabs: int = 3            # pages of the same context cycled (round-robin) for detail visits
    delay_s: float = 1.5            # politeness gap between detail-page navigations; +/-30% jitter applied


class DiscoveryCfg(BaseModel):
    providers: list[str] = Field(default_factory=lambda: ["gosom"])  # + "dvsa" | "companies_house" per campaign
    grid_mode: str = "off"  # off | auto — keep off until gosom grid flags are live-verified (U8.2)
    grid_cell_km: float = 3.0
    depth: int = 10
    concurrency: int = 2
    lang: str = "en"
    timeout_min: int = 30
    stall_s: float = 180.0  # kill gosom when results stop growing this long (v1.17.4 hangs after finishing)
    proxies: list[str] = Field(default_factory=list)
    email_crawl: bool = False
    # v0.3 coverage: explicit [minLng, minLat, maxLng, maxLat] per area label bypasses the geocoder
    area_bbox: dict[str, list[float]] = Field(default_factory=dict)
    subdivide_at: int = 100        # a tiled query returning >= this many listings is split into 4 child tiles
    max_subdivisions: int = 2
    subdivide_min_new: int = 3     # ...but only when the saturated tile itself added >= this many NEW businesses
                                   # (live 2026-09-03: saturated children of well-covered tiles yielded ~0.6 each; 0 = always)
    est_min_per_query: float = 2.0         # measured 2026-08-31: 1.7 min untiled
    est_min_per_tiled_query: float = 4.0   # measured 2026-08-31: 3.5-4.7 min tiled
    dvsa: DvsaCfg = Field(default_factory=DvsaCfg)
    companies_house: CompaniesHouseDiscoveryCfg = Field(default_factory=CompaniesHouseDiscoveryCfg)
    maps_list: MapsListCfg = Field(default_factory=MapsListCfg)
    # speed unit: fan discover queries across N provider-chain instances (each its own browser/subprocess
    # pool); ==1 keeps the original strictly-serial loop. See pipeline.run_discover.
    parallel_queries: int = 1


class CrawlCfg(BaseModel):
    pages_per_site: int = 6
    headed_browser: bool = False  # browser-escalation runs VISIBLY (debug aid; real-browser rendering, no stealth flags)
    stale_after_years: int = 2  # copyright year older than this many years back => stale_site signal
    # v0.3 speed unit (2026-09-02): the home page is the ONLY fetch that gates whether a site is
    # crawled at all, so it keeps the longer timeout; secondary/candidate pages (about, team, contact,
    # sitemap probe...) get the shorter page_timeout_s — a dead or slow secondary page used to cost the
    # full 15s EACH, and a 6-page site chained that into minutes. site_budget_s caps the whole crawl()
    # call's wall clock (home fetch + every secondary page) so one slow-but-alive site can never eat
    # more than its share of a batch — once exceeded, crawl() stops fetching further pages and returns
    # what it already collected (still ok=True if the home page loaded; signals["budget_exhausted"]=True).
    timeout_s: float = 10.0          # was 15.0 — home page fetch only now
    page_timeout_s: float = 6.0      # secondary/candidate page + sitemap-probe fetch timeout
    site_budget_s: float = 45.0      # per-site wall-clock budget across the whole crawl() call
    max_text_bytes: int = 400_000


class PolitenessCfg(BaseModel):
    delay_s: float = 2.0
    # v0.3 speed unit (2026-09-02): was 4. HostThrottle (util.py) serializes every request to a given
    # host to one-in-flight with >= delay_s (+-30% jitter) between them, regardless of `workers` — this
    # knob only controls how many DIFFERENT hosts run concurrently. Measured on a 20-site sample
    # (scratchpad/speed/enrich/result_A.json vs result_B.json): raising workers alone (4 -> 16) did NOT
    # improve throughput because the slow tail (403/Cloudflare blocks, dead hosts, the browser-render
    # semaphore) dominated — see crawl.site_budget_s / crawl.page_timeout_s / enrich.browser_concurrency,
    # which is what actually lets more workers help. 12 is the number those fixes are measured against;
    # per-host pacing is unchanged at any worker count.
    # 2026-09-24 (Layer 3): with NER moved to its own GPU/CPU worker process the crawl threads are pure I/O;
    # same 200 sites from identical DB copies: 12 workers 22.9 sites/min, 24 workers 26.3 (one run each —
    # network variance applies). Per-host pacing is unchanged, so 24 costs no site anything extra.
    workers: int = 24
    user_agent: str = "LeadForgeBot/0.1 (internal lead research)"


class ValidationCfg(BaseModel):
    dns_timeout_s: float = 5.0
    staleness_days: int = 90
    # opt-in: propose a LIKELY address for a known decision maker when the domain's own naming
    # convention is demonstrated by an email already found there. Public evidence + MX only —
    # never SMTP/RCPT probing (icm/SCOPE.md #5). Exported in its own column, never as a found email.
    infer_emails: bool = False
    # v0.3 (owner decision 5): which freemail addresses count as the business's own -
    # linked (local part matches the business or a known person), any, none (own-domain only)
    freemail_policy: str = "linked"


class EnrichCfg(BaseModel):
    """v0.3 speed unit (2026-09-02): browser-escalation throughput, overlapped stages, DNS pooling.
    None of this touches politeness — HostThrottle's per-host delay/single-flight is unaffected; these
    knobs only change how many DIFFERENT hosts/domains/lookups run at once and how the 'all' stage
    sequence is scheduled."""

    browser_concurrency: int = 4     # was a hardcoded threading.Semaphore(2) in browser.py
    rendered_pages_per_site: int = 2  # was the hardcoded MAX_RENDERED_PAGES_PER_SITE = 3
    render_timeout_s: float = 20.0    # the rendered fetch's own timeout (was borrowing crawl.timeout_s,
                                       # which just dropped to 10s — nowhere near enough for a real render)
    overlap_stages: bool = True       # stage='all' interleaves registry(backlog)+validate with the crawl;
                                       # `enrich --stage <one>` is never affected by this (single-stage
                                       # runs always use the original serial per-stage functions)
    dns_workers: int = 8              # MX-lookup thread pool size for validate_emails_parallel
    # v0.4.1: GLiNER people extraction runs on the CPU inside every crawl worker; unbounded, 12 workers x
    # torch's default 8 intra-op threads oversubscribed an 8-core box (live 2026-09-03: 2.7 cores of NER,
    # crawl at 5.7 sites/min vs 26 measured without contention). ner=false selects the heuristic extractor.
    ner: bool = True
    ner_parallel: int = 2             # inferences in flight at once (a semaphore across the crawl workers)
    ner_threads: int = 2              # torch intra-op threads per inference
    # Layer 3 (throughput, 2026-09-24): GLiNER now runs in ONE separate model-worker process instead of
    # inside the crawl ThreadPoolExecutor, so crawl threads never block on torch. ner_parallel/ner_threads
    # above still bound the legacy in-thread path used as the worker's own fallback when it fails to start.
    ner_device: Literal["auto", "cpu", "cuda"] = "auto"  # auto = cuda when torch.cuda.is_available()
    ner_batch: int = 8                # max requests the worker groups into one GLiNER call
    ner_batch_wait_ms: float = 25.0   # max time the worker waits to fill a batch before running it short
    # Layer 6 (skill v2, `plan` digest): enrichment time estimate alongside the existing discovery
    # estimate. Measured this machine, 24 crawl workers + GPU NER (docs/UPGRADE-PLAN.md Layer 3):
    # ~26 sites/min; ~64% of discovered businesses have a website (docs/UPGRADE-PLAN.md "Where we are").
    # Both are configurable per-machine/per-campaign, not hardcoded into the estimate math.
    est_website_share: float = 0.64        # measured 2026-09-24: 64% of discovered businesses have a website
    est_crawl_rate_per_min: float = 25.0   # measured ~26 sites/min (24 workers, GPU NER); default rounds down
    ner_timeout_s: float = 30.0       # per-request timeout incl. queue wait (CPU: ~0.8 s/page x 12 crawl threads); on expiry -> heuristics

    @field_validator("ner_device", mode="before")
    @classmethod
    def _normalize_ner_device(cls, v: Any) -> Any:
        # yaml/env values arrive as arbitrary strings ("Auto", "CUDA", ...); normalize case so the
        # Literal validator (which is case-sensitive) doesn't reject a value spelled differently
        # than the three canonical ones — pydantic still rejects anything that isn't one of them.
        if isinstance(v, str):
            return v.strip().lower()
        return v


class RegistryCfg(BaseModel):
    # the two keys are filled by load_config from the environment or the OS keyring, never from leadforge.yaml
    companies_house_key: str = ""
    # Every request to this address carries companies_house_key (basic auth), so only the default or a loopback address
    # (a local stand-in server) is accepted; DVSA's url takes any host because it sends no secret.
    companies_house_url: str = CH_BASE_DEFAULT
    opencorporates_token: str = ""
    # L9 (C2): OpenCorporates documents its token only as a query parameter, so it would travel in the web address;
    # off unless the operator accepts that.
    opencorporates_enabled: bool = False
    keyring: bool = True               # L9: look in the OS keyring when the environment has no key
    min_name_similarity: float = 0.45  # v0.3: a registry hit must also resemble the business name
    active_only: bool = True           # v0.3: dissolved/liquidated companies are never matched

    @field_validator("companies_house_url", mode="before")
    @classmethod
    def _companies_house_url_is_default_or_loopback(cls, v: Any) -> Any:
        if not isinstance(v, str):
            return v  # pydantic rejects a non-string itself
        url = v.strip().rstrip("/") or CH_BASE_DEFAULT
        if url == CH_BASE_DEFAULT:
            return url
        parts = urlsplit(url)
        try:
            host = parts.hostname
            parts.port  # noqa: B018 - raises ValueError on a bad port
        except ValueError as e:
            raise ValueError(f"registry.companies_house_url is not a valid address: {e}") from e
        loopback = False
        if host:
            try:
                loopback = ipaddress.ip_address(host).is_loopback
            except ValueError:
                loopback = host.lower() == "localhost"
        if (parts.scheme not in ("http", "https") or not loopback or parts.username is not None
                or parts.password is not None or parts.query or parts.fragment):
            raise ValueError(
                "registry.companies_house_url must be the default (" + CH_BASE_DEFAULT + ") or an http(s) address on this "
                "machine (localhost or a loopback IP, no credentials, query or fragment): the Companies House key is sent "
                "with every request to it")
        return url


class OutreachCfg(BaseModel):
    """v0.3 sending layer (ADR-011/012). Nothing sends unless `armed` is true AND `--live` AND `--i-am` agree."""

    armed: bool = False
    transport: str = "file"            # file (dry-run .eml) | smtp | <registered adapter>
    require_corporate: bool = False    # owner decision 5: plausibility-linked freemail is mailable by default
    require_email_confirmation: bool = False  # provider/delivery/reply/operator confirmation; never SMTP probing
    send_window: str = "09:00-17:00"   # local time of `timezone`
    timezone: str = "Europe/London"
    follow_up_days: int = 5
    bounce_rate_pause: float = 0.03    # hard bounces over the last 100 live sends
    complaint_rate_pause: float = 0.001
    inbox_dir: str = "inbox"           # webhook spool + IMAP dumps under data_dir; never printed
    outbox_dir: str = "outbox"


class DraftCfg(BaseModel):
    """v0.3 agent drafting (in-harness by default: the CLI emits packets, the agent writes the two slots)."""

    packet_max_tokens: int = 350
    name_policy: str = "gated"         # gated | never | always (owner decision 6)
    max_observation_words: int = 45
    max_subject_chars: int = 60
    # v0.4 autopilot (ADR-015): draft during `run` itself, no separate export/apply round-trip.
    auto: bool = True                       # draft during `run` (autopilot)
    auto_purpose: str = "client_campaign"   # one of draft.skeletons.PURPOSES; neutral default (Layer 6) —
                                             # "gainlev_leadgen" is GainLev's own branded skeleton, not
                                             # a sensible default for other users; set explicitly to use it
    auto_tiers: list[str] = Field(default_factory=lambda: ["A", "B"])
    auto_max: int = 500                     # targets drafted per run
    template_fallback: bool = True
    retries: int = 1                   # re-ask the runner once for drafts the gate rejected, with the reasons          # deterministic template drafts when no runner is available


class AgentCfg(BaseModel):
    """v0.4 headless agent runner (ADR-015): the operator's own Claude Code in print mode. No API key."""

    command: list[str] | None = None   # None = auto-detect `claude` on PATH; [] = disabled (deterministic fallbacks only)
    model: str = "sonnet"              # used only for the auto-detected command
    timeout_s: int = 900               # per invocation
    batch: int = 40                    # items per invocation
    max_batches: int = 50              # hard stop per stage per run
    # v0.4 Layer 2 (ADR-015 follow-up): isolation + timeout + concurrency for the auto-detected
    # `claude` invocation. Only apply to the auto-detected command — an explicit `agent.command`
    # override is used verbatim (the operator's own flags), never mutated.
    isolate: bool = True               # append --strict-mcp-config + --settings '{"disableAllHooks":true}'
    max_concurrent: int = 2            # process-level cap on simultaneous `claude` invocations


class PipelineCfg(BaseModel):
    autopilot: bool = True             # run continues through labeling -> score -> draft -> export without pausing


class SocialCfg(BaseModel):
    """Social/video presence signals (U4.8, providers/social.py).

    On by default — is_available() still gates on the tooling actually answering, so absence
    degrades silently. Public, logged-out, business-owned profiles only — never LinkedIn, never
    cookie/session auth (see icm/SCOPE.md and the provider module docstring).
    """

    enabled: bool = True  # auto: is_available() still gates on the agent-reach CLI actually answering
    networks: list[str] = Field(default_factory=lambda: ["youtube"])  # only youtube has a real logged-out backend today
    max_networks: int = 3
    stale_months: int = 6
    timeout_s: float = 30.0
    max_calls_per_min: int = 20


class ExportCfg(BaseModel):
    formats: list[str] = Field(default_factory=lambda: ["xlsx", "csv"])
    auto_open: bool = True  # open the finished XLSX with the OS default app (skipped in CI)


class Config(BaseModel):
    data_dir: str = "leadforge_data"
    default_region: str = "US"
    progress_window: bool = True  # headless runs pop a console with the live bar (Windows; skipped in CI)
    discovery: DiscoveryCfg = Field(default_factory=DiscoveryCfg)
    crawl: CrawlCfg = Field(default_factory=CrawlCfg)
    politeness: PolitenessCfg = Field(default_factory=PolitenessCfg)
    enrich: EnrichCfg = Field(default_factory=EnrichCfg)
    validation: ValidationCfg = Field(default_factory=ValidationCfg)
    registry: RegistryCfg = Field(default_factory=RegistryCfg)
    social: SocialCfg = Field(default_factory=SocialCfg)
    export: ExportCfg = Field(default_factory=ExportCfg)
    outreach: OutreachCfg = Field(default_factory=OutreachCfg)
    draft: DraftCfg = Field(default_factory=DraftCfg)
    agent: AgentCfg = Field(default_factory=AgentCfg)
    pipeline: PipelineCfg = Field(default_factory=PipelineCfg)

    _workspace: Path = Path(".")
    _key_sources: dict[str, str] = {}  # registry key name -> "environment" | "OS keyring" (set keys only)

    # --- path helpers (create-on-demand) -------------------------------------------------
    @property
    def workspace(self) -> Path:
        return self._workspace

    def _dir(self, *parts: str) -> Path:
        p = (self._workspace / self.data_dir).joinpath(*parts)
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def data_path(self) -> Path:
        return self._dir()

    @property
    def bin_dir(self) -> Path:
        return self._dir("bin")

    @property
    def cache_dir(self) -> Path:
        return self._dir("cache")

    @property
    def exports_dir(self) -> Path:
        return self._dir("exports")

    @property
    def logs_dir(self) -> Path:
        return self._dir("logs")

    @property
    def db_path(self) -> Path:
        return self._dir() / "db.sqlite3"


def _deep_merge(base: dict[str, Any], over: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _env_overrides(prefix: str = "LEADFORGE_") -> dict[str, Any]:
    """LEADFORGE_DISCOVERY__DEPTH=5 -> {"discovery": {"depth": 5}} (values parsed as YAML scalars)."""
    out: dict[str, Any] = {}
    for key, val in os.environ.items():
        if not key.startswith(prefix):
            continue
        path = key[len(prefix):].lower().split("__")
        node = out
        for part in path[:-1]:
            node = node.setdefault(part, {})
        try:
            node[path[-1]] = yaml.safe_load(val)
        except yaml.YAMLError:
            node[path[-1]] = val
    return out


def load_config(workspace: Path | str = ".", data_dir_override: str | None = None) -> Config:
    workspace = Path(workspace)
    merged: dict[str, Any] = {}
    cfg_file = workspace / "leadforge.yaml"
    if cfg_file.is_file():
        loaded = yaml.safe_load(cfg_file.read_text(encoding="utf-8")) or {}
        if not isinstance(loaded, dict):
            raise ValueError(f"{cfg_file} must contain a YAML mapping")
        registry = loaded.get("registry")
        for name in KEY_SETTINGS:
            if isinstance(registry, dict) and registry.get(name) not in (None, ""):
                raise KeyInConfigFile(key_refusal(name))
        merged = _deep_merge(merged, loaded)
    env = _env_overrides()
    if isinstance(env.get("registry"), dict):
        for name in KEY_SETTINGS:
            env["registry"].pop(name, None)  # read below as written, not parsed as YAML
    merged = _deep_merge(merged, env)
    if data_dir_override:
        merged["data_dir"] = data_dir_override
    cfg = Config.model_validate(merged)
    cfg._workspace = workspace
    sources: dict[str, str] = {}
    for name in KEY_SETTINGS:
        value, source = os.environ.get(key_env_name(name), "").strip(), "environment"
        if not value and cfg.registry.keyring:
            value, source = (_keyring_get(name) or "").strip(), "OS keyring"
        setattr(cfg.registry, name, value)
        if value:
            sources[name] = source
    cfg._key_sources = sources
    return cfg
