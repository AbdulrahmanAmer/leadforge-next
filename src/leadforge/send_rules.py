"""Send rules by country (C13): which countries the tool will e-mail into, and on what footing.

Pure functions, no I/O. `compliance.email_eligibility` calls `check`, so the sheet, the score, the draft packet, `outreach plan` and the live
re-check in `outreach send` all see the same answer. A rule can only make a lead less sendable than the address rules alone, never more.
A practical posture, not legal advice (docs/07-compliance.md).

    US  opt-out model (CAN-SPAM): a business address may be mailed, with identity and an opt-out.
    GB  corporate subscribers may be mailed (PECR); a sole trader or partnership needs consent.
    DE  consent before any commercial e-mail (UWG section 7).

Every other country, and an unreadable or empty one, has no rule: no send. The tool records no consent, so a "consent" outcome is not sendable either.
"""

from __future__ import annotations

RULES = {"US": "opt_out", "GB": "corporate_subscriber", "DE": "consent"}

REASON_UNKNOWN = "country_unknown"
REASON_NO_RULE = "country_no_rule"
REASON_CONSENT = "consent_required"


def country_code(raw: str | None) -> str:
    """ISO-2 of an `address_country` value ('GB', 'United Kingdom', 'uk', 'Germany'...), or '' when empty or not a country the tool can read."""
    from leadforge.normalize import COUNTRY_TO_REGION

    s = (raw or "").strip()
    if not s:
        return ""
    known = COUNTRY_TO_REGION.get(s.casefold())
    if known:
        return known
    return s.upper() if len(s) == 2 and s.isalpha() else ""


def check(country_raw: str | None, *, unmatched_entity: bool = False) -> dict:
    """-> {"country", "rule", "outcome": "ok" | "consent" | "no_send", "reason"}.

    `unmatched_entity`: the registry was asked and found no company (a likely sole trader or partnership)."""
    code = country_code(country_raw)
    if not code:
        return {"country": "", "rule": "", "outcome": "no_send", "reason": REASON_UNKNOWN}
    rule = RULES.get(code, "")
    if not rule:
        return {"country": code, "rule": "", "outcome": "no_send", "reason": REASON_NO_RULE}
    if rule == "consent" or (rule == "corporate_subscriber" and unmatched_entity):
        return {"country": code, "rule": rule, "outcome": "consent", "reason": REASON_CONSENT}
    return {"country": code, "rule": rule, "outcome": "ok", "reason": ""}
