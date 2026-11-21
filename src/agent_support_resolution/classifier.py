"""Deterministic ticket classification.

No model calls: keyword rules, amount extraction, and risk-flag detection
in plain code, so routing decisions are reproducible and testable. The
classifier's job is to surface risk early — refund amounts, third-party
data requests, PII in the ticket, angry tone — so downstream gates can act
on facts, not vibes.
"""

from __future__ import annotations

import re

from .models import Category, Classification, Sentiment, Ticket

# Ordered: first match wins. Privacy/refund checks run before generic ones.
_CATEGORY_RULES: list[tuple[Category, tuple[str, ...]]] = [
    (Category.PRIVACY, ("another customer", "other customer", "someone else's", "their email",
                        "their address", "their order", "who ordered", "privacy", "delete my data")),
    (Category.REFUND, ("refund", "money back", "chargeback", "reimburse")),
    (Category.ACCOUNT, ("password", "log in", "login", "sign in", "account", "email address",
                        "change my email", "delete my account", "two-factor", "2fa")),
    (Category.BILLING, ("bill", "billing", "charge", "invoice", "payment", "subscription",
                        "cancel my subscription", "renew", "price")),
    (Category.SHIPPING, ("shipping", "delivery", "deliver", "arrive", "tracking", "track my",
                         "where is my order", "package")),
    (Category.ORDER, ("order", "damaged", "broken", "wrong item", "missing item", "return",
                      "exchange", "warranty")),
    (Category.PRODUCT, ("how do i", "how to", "feature", "does it", "compatible", "gift card",
                        "loyalty", "points")),
]

_INTENT_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("password_reset", ("password", "reset")),
    ("refund_request", ("refund", "money back")),
    ("order_tracking", ("tracking", "where is my order", "track my")),
    ("cancel_subscription", ("cancel",)),
    ("third_party_data_request", ("another customer", "other customer", "who ordered",
                                  "someone else's", "their email", "their address")),
    ("damaged_item", ("damaged", "broken", "arrived damaged")),
    ("address_change", ("change my address", "new address", "shipping address")),
    ("warranty_claim", ("warranty",)),
    ("billing_question", ("bill", "billing", "invoice", "charge")),
    ("shipping_question", ("shipping", "delivery", "arrive")),
    ("account_question", ("account", "email address", "delete my account")),
]

_ANGRY_MARKERS = (
    "furious", "outrageous", "unacceptable", "ridiculous", "worst", "terrible",
    "scam", "fraud", "sue", "lawyer", "never again", "disgusted", "incompetent",
)
_FRUSTRATED_MARKERS = (
    "frustrated", "annoying", "still waiting", "third time", "again?", "fed up",
    "disappointed", "not happy", "useless",
)

_THIRD_PARTY_MARKERS = (
    "another customer", "other customer", "someone else's", "who ordered",
    "their email", "their address", "their phone", "their order",
    "the customer who", "give me the email", "give me their",
)

_AMOUNT_RE = re.compile(r"\$\s?(\d{1,3}(?:,\d{3})*(?:\.\d{2})?|\d+(?:\.\d{2})?)")
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
_PHONE_RE = re.compile(r"\b(?:\+?1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)\d{3}[-.\s]?\d{4}\b")
_CARD_RE = re.compile(r"\b(?:\d[ -]*?){13,16}\b")
_SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")


def _contains_any(text: str, markers: tuple[str, ...]) -> bool:
    return any(m in text for m in markers)


def extract_refund_amount(text: str) -> float | None:
    """Largest dollar amount mentioned in a refund-context ticket."""
    amounts = [float(a.replace(",", "")) for a in _AMOUNT_RE.findall(text)]
    return max(amounts) if amounts else None


def detect_pii(text: str) -> dict[str, bool]:
    """Which PII shapes appear in the text (used for flags + redaction)."""
    return {
        "email": bool(_EMAIL_RE.search(text)),
        "phone": bool(_PHONE_RE.search(text)),
        "card": bool(_CARD_RE.search(text)),
        "ssn": bool(_SSN_RE.search(text)),
    }


def classify(ticket: Ticket) -> Classification:
    text = f"{ticket.subject} {ticket.body}".lower()

    category = Category.OTHER
    for cat, markers in _CATEGORY_RULES:
        if _contains_any(text, markers):
            category = cat
            break

    intent = "general_question"
    for name, markers in _INTENT_RULES:
        if _contains_any(text, markers):
            intent = name
            break

    # Shouting (mostly-caps body) also counts as angry.
    letters = [c for c in ticket.body if c.isalpha()]
    shouting = bool(letters) and sum(c.isupper() for c in letters) / len(letters) > 0.6
    if _contains_any(text, _ANGRY_MARKERS) or shouting or text.count("!") >= 3:
        sentiment = Sentiment.ANGRY
    elif _contains_any(text, _FRUSTRATED_MARKERS):
        sentiment = Sentiment.FRUSTRATED
    else:
        sentiment = Sentiment.CALM

    refund_amount = extract_refund_amount(text) if category == Category.REFUND else None
    asks_third_party = _contains_any(text, _THIRD_PARTY_MARKERS)
    pii = detect_pii(ticket.body)
    contains_pii = any(pii.values())

    risk_flags: list[str] = []
    if asks_third_party:
        risk_flags.append("third_party_data_request")
    if contains_pii:
        risk_flags.append("pii_in_ticket")
    if sentiment == Sentiment.ANGRY:
        risk_flags.append("angry_customer")
    if refund_amount is not None and refund_amount > 50:
        risk_flags.append("large_refund")
    if category == Category.OTHER:
        risk_flags.append("unclassified")

    return Classification(
        category=category,
        intent=intent,
        sentiment=sentiment,
        refund_amount_usd=refund_amount,
        asks_third_party_data=asks_third_party,
        contains_pii=contains_pii,
        risk_flags=risk_flags,
    )
