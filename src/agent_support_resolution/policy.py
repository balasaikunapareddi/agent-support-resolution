"""Policy-as-code: the rules a draft must pass before it can be sent.

Every rule is explicit, named, and individually testable. The drafter
(mock or LLM) proposes text; this module disposes. Two severities:

- ``hard``: the draft is unsafe (leaks PII, promises what we cannot).
  The draft is discarded and a human writes from scratch.
- ``soft``: the draft may be fine but needs a human decision (large
  refund, ungrounded claim, tone). The draft is kept for review.

Also here: PII redaction for inbound ticket text, so raw emails / phone
numbers / card numbers never reach the drafter, the audit log, or the
outbox.
"""

from __future__ import annotations

import re

from .classifier import _AMOUNT_RE, _CARD_RE, _EMAIL_RE, _PHONE_RE, _SSN_RE
from .models import (
    Classification,
    PolicyDecision,
    PolicyDecisionType,
    PolicyViolation,
    RetrievedArticle,
    Severity,
    Ticket,
)

# --- configuration (the "policy" knobs a real team would tune) ---------------

REFUND_AUTO_CAP_USD = 50.0      # KB-002: above this, a specialist must approve
MIN_GROUNDING_SCORE = 0.05      # a draft needs at least one relevant KB article

# Claims the KB never authorizes. If a draft says these, it is inventing policy.
UNSUPPORTED_CLAIM_MARKERS = (
    "guaranteed", "100%", "free forever", "lifetime warranty", "no questions asked",
    "we promise", "always refund", "full refund guaranteed", "risk-free",
)

# Dismissive phrasing that must never reach a customer.
TONE_MARKERS = (
    "calm down", "not our problem", "as i already said", "you should have",
    "that's your fault", "obviously", "per my last email",
)

_REFUND_PROMISE_RE = re.compile(
    r"(refund|credit|reimburse)[^.]{0,60}?\$\s?(\d{1,3}(?:,\d{3})*(?:\.\d{2})?|\d+(?:\.\d{2})?)"
    r"|\$\s?(\d{1,3}(?:,\d{3})*(?:\.\d{2})?|\d+(?:\.\d{2})?)[^.]{0,40}?(refund|credit|reimburse)",
    re.IGNORECASE,
)


# --- PII redaction -----------------------------------------------------------


def redact_pii(text: str) -> str:
    """Mask emails, phone numbers, card numbers, and SSNs in free text."""
    text = _EMAIL_RE.sub("[EMAIL REDACTED]", text)
    text = _SSN_RE.sub("[SSN REDACTED]", text)
    text = _CARD_RE.sub("[CARD REDACTED]", text)
    text = _PHONE_RE.sub("[PHONE REDACTED]", text)
    return text


def _find_emails(text: str) -> list[str]:
    # The regex can swallow a sentence-ending period ("me@example.com.");
    # strip trailing punctuation so address comparison is exact.
    return [e.rstrip(".,;:)") for e in _EMAIL_RE.findall(text)]


# --- individual rules --------------------------------------------------------


def rule_refund_cap(draft: str, ticket: Ticket, cls: Classification) -> PolicyViolation | None:
    """A draft may not promise a refund above the auto-approval cap."""
    promised: list[float] = []
    for m in _REFUND_PROMISE_RE.finditer(draft):
        for g in m.groups():
            if g and g[0].isdigit():
                promised.append(float(g.replace(",", "")))
    # Fall back: refund-category draft mentioning any amount above the cap.
    if not promised and cls.category.value == "refund":
        promised = [float(a.replace(",", "")) for a in _AMOUNT_RE.findall(draft)]
    over = [a for a in promised if a > REFUND_AUTO_CAP_USD]
    if over:
        return PolicyViolation(
            rule_id="refund_cap", severity=Severity.SOFT,
            message=f"Draft promises a refund of ${max(over):,.2f}, above the "
                    f"${REFUND_AUTO_CAP_USD:,.0f} auto-approval cap (KB-002).",
            evidence=f"${max(over):,.2f}",
        )
    return None


def rule_third_party_pii(draft: str, ticket: Ticket, cls: Classification) -> PolicyViolation | None:
    """A draft may not contain an email address that is not the customer's own."""
    own = ticket.customer_email.lower()
    for email in _find_emails(draft):
        if email.lower() != own:
            return PolicyViolation(
                rule_id="third_party_pii", severity=Severity.HARD,
                message="Draft contains an email address that does not belong "
                        "to the ticket's customer.",
                evidence=email,
            )
    return None


def rule_raw_pii(draft: str, ticket: Ticket, cls: Classification) -> PolicyViolation | None:
    """A draft may not contain raw card numbers or SSNs, ever."""
    if _CARD_RE.search(draft) or _SSN_RE.search(draft):
        return PolicyViolation(
            rule_id="raw_pii", severity=Severity.HARD,
            message="Draft contains a raw card number or SSN.",
            evidence="[pattern matched]",
        )
    return None


def rule_unsupported_claims(draft: str, ticket: Ticket, cls: Classification) -> PolicyViolation | None:
    """A draft may not make claims the knowledge base does not authorize."""
    lowered = draft.lower()
    for marker in UNSUPPORTED_CLAIM_MARKERS:
        if marker in lowered:
            return PolicyViolation(
                rule_id="unsupported_claim", severity=Severity.SOFT,
                message=f"Draft makes an unsupported claim ('{marker}') that no "
                        "KB article authorizes.",
                evidence=marker,
            )
    return None


def rule_tone(draft: str, ticket: Ticket, cls: Classification) -> PolicyViolation | None:
    """A draft may not use dismissive language."""
    lowered = draft.lower()
    for marker in TONE_MARKERS:
        if marker in lowered:
            return PolicyViolation(
                rule_id="tone", severity=Severity.SOFT,
                message=f"Draft uses dismissive language ('{marker}').",
                evidence=marker,
            )
    return None


def rule_kb_grounding(
    draft: str, ticket: Ticket, cls: Classification, retrieved: list[RetrievedArticle]
) -> PolicyViolation | None:
    """A substantive draft needs at least one relevant KB article behind it."""
    top = retrieved[0].score if retrieved else 0.0
    if top < MIN_GROUNDING_SCORE:
        return PolicyViolation(
            rule_id="kb_grounding", severity=Severity.SOFT,
            message=f"No KB article is relevant enough to ground this draft "
                    f"(top score {top:.3f} < {MIN_GROUNDING_SCORE}).",
            evidence=f"top_score={top:.3f}",
        )
    return None


RULES = (rule_refund_cap, rule_third_party_pii, rule_raw_pii,
         rule_unsupported_claims, rule_tone)


def check_policy(
    draft: str,
    ticket: Ticket,
    classification: Classification,
    retrieved: list[RetrievedArticle],
) -> PolicyDecision:
    """Run every rule; hard violations block, soft ones need a human."""
    violations: list[PolicyViolation] = []
    for rule in RULES:
        v = rule(draft, ticket, classification)
        if v:
            violations.append(v)
    v = rule_kb_grounding(draft, ticket, classification, retrieved)
    if v:
        violations.append(v)

    if any(v.severity == Severity.HARD for v in violations):
        decision = PolicyDecisionType.BLOCK
    elif violations:
        decision = PolicyDecisionType.NEEDS_HUMAN
    else:
        decision = PolicyDecisionType.ALLOW
    return PolicyDecision(decision=decision, violations=violations)
