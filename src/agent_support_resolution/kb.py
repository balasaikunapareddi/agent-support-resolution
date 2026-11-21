"""Knowledge base + local TF-IDF retrieval.

The KB is a bundled set of synthetic support articles. Retrieval is a
pure-Python TF-IDF cosine search — deterministic, offline, no embeddings
service. In production this layer swaps for a vector store; the interface
(``search(query, top_k) -> list[RetrievedArticle]``) stays the same.
"""

from __future__ import annotations

import math
import re
from collections import Counter

from .models import Category, KBArticle, RetrievedArticle

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_STOPWORDS = {
    "the", "a", "an", "and", "or", "to", "of", "in", "on", "for", "is", "are",
    "my", "i", "me", "you", "your", "it", "this", "that", "how", "can", "do",
    "does", "what", "when", "where", "with", "please", "hi", "hello",
}


def _stem(token: str) -> str:
    # Minimal plural stemming so "refunds"/"refund", "items"/"item" match.
    if len(token) > 3 and token.endswith("s") and not token.endswith("ss"):
        return token[:-1]
    return token


def _tokens(text: str) -> list[str]:
    return [_stem(t) for t in _TOKEN_RE.findall(text.lower()) if t not in _STOPWORDS]


ARTICLES: list[KBArticle] = [
    KBArticle(
        article_id="KB-001", title="Resetting your password", category=Category.ACCOUNT,
        keywords=["forgot password", "reset password", "can't log in", "locked out", "sign in"],
        body="To reset your password, go to the sign-in page and choose 'Forgot password'. "
             "We email you a reset link that expires in 30 minutes. If the email does not "
             "arrive, check your spam folder. Passwords must be at least 10 characters.",
    ),
    KBArticle(
        article_id="KB-002", title="Refund policy", category=Category.REFUND,
        keywords=["refund", "money back", "charged twice", "duplicate charge", "reimburse",
                  "refund amount", "process my refund"],
        body="Refunds are available within 30 days of delivery for unused items. Refunds of "
             "$50 or less are approved automatically and issued to the original payment "
             "method within 5 business days. Refunds above $50 require review by a support "
             "specialist before they can be issued.",
    ),
    KBArticle(
        article_id="KB-003", title="Shipping times and costs", category=Category.SHIPPING,
        keywords=["shipping time", "how long shipping", "delivery time", "express shipping",
                  "shipping cost", "when will it arrive"],
        body="Standard shipping takes 3-5 business days and is free on orders over $35. "
             "Express shipping takes 1-2 business days and costs $9.99. Orders placed "
             "before 2pm local time ship the same business day.",
    ),
    KBArticle(
        article_id="KB-004", title="Tracking your order", category=Category.SHIPPING,
        keywords=["track my order", "tracking number", "where is my order", "package status",
                  "order status", "track package"],
        body="Once your order ships, we email you a tracking number. You can also find it "
             "under Account > Orders. Tracking updates can take up to 24 hours to appear "
             "after the shipping confirmation email.",
    ),
    KBArticle(
        article_id="KB-005", title="Warranty coverage", category=Category.ORDER,
        keywords=["warranty", "warranty claim", "stopped working", "defect", "broken after",
                  "covered by warranty"],
        body="Electronics include a 1-year limited warranty covering manufacturing defects. "
             "To start a warranty claim, contact support with your order number and a "
             "description of the defect. Accidental damage is not covered.",
    ),
    KBArticle(
        article_id="KB-006", title="Cancelling a subscription", category=Category.BILLING,
        keywords=["cancel subscription", "cancel my subscription", "stop billing",
                  "unsubscribe", "cancel membership"],
        body="You can cancel your subscription anytime under Account > Subscriptions. "
             "Cancellation takes effect at the end of the current billing period, and "
             "you keep access until then. We do not charge cancellation fees.",
    ),
    KBArticle(
        article_id="KB-007", title="Billing cycle and invoices", category=Category.BILLING,
        keywords=["billing", "invoice", "card declined", "payment failed", "charged",
                  "billing status", "billing cycle", "payment method"],
        body="Subscriptions bill on the same day each month. Invoices are available under "
             "Account > Billing and are emailed after each successful payment. Failed "
             "payments are retried after 3 days.",
    ),
    KBArticle(
        article_id="KB-008", title="Changing your shipping address", category=Category.ACCOUNT,
        keywords=["change address", "shipping address", "new address", "wrong address"],
        body="You can change the shipping address on an order within 1 hour of placing it "
             "under Account > Orders. After that, contact support and we will try to "
             "update it before the order ships.",
    ),
    KBArticle(
        article_id="KB-009", title="Deleting your account", category=Category.ACCOUNT,
        keywords=["delete account", "close account", "delete my data", "remove account"],
        body="To delete your account, go to Account > Privacy > Delete account. Deletion "
             "is permanent after a 14-day grace period. Order history required for tax "
             "records is retained as required by law.",
    ),
    KBArticle(
        article_id="KB-010", title="Your privacy and other customers' data", category=Category.PRIVACY,
        keywords=["another customer", "other customer", "someone else", "their email",
                  "their order", "privacy", "share data"],
        body="We never share one customer's personal data with another customer. Support "
             "agents can only discuss your own account, orders, and contact details with "
             "you. Requests for another customer's information are always declined.",
    ),
    KBArticle(
        article_id="KB-011", title="Damaged or defective items", category=Category.ORDER,
        keywords=["damaged", "arrived damaged", "cracked", "broken item", "defective",
                  "damaged item", "replacement"],
        body="If an item arrives damaged or defective, contact support within 14 days with "
             "a photo. We will send a replacement at no charge or refund you, your choice. "
             "You do not need to return the damaged item.",
    ),
    KBArticle(
        article_id="KB-012", title="Gift cards", category=Category.PRODUCT,
        keywords=["gift card", "gift card balance", "redeem gift card"],
        body="Gift cards are delivered by email within 1 hour and never expire. Balances "
             "can be checked under Account > Gift Cards. Gift cards cannot be redeemed "
             "for cash except where required by law.",
    ),
    KBArticle(
        article_id="KB-013", title="Loyalty points", category=Category.PRODUCT,
        keywords=["loyalty points", "points balance", "redeem points", "earn points"],
        body="You earn 1 loyalty point per $1 spent. Points can be redeemed at checkout: "
             "100 points = $1. Points expire after 12 months of account inactivity.",
    ),
    KBArticle(
        article_id="KB-014", title="International shipping", category=Category.SHIPPING,
        keywords=["international shipping", "ship to canada", "ship to uk", "ship to eu",
                  "duties", "customs"],
        body="We ship to Canada, the UK, and the EU. International delivery takes 7-14 "
             "business days. Duties and taxes are calculated at checkout; there are no "
             "additional charges on delivery.",
    ),
    KBArticle(
        article_id="KB-015", title="Returns window", category=Category.ORDER,
        keywords=["return item", "return window", "send back", "return label", "returns"],
        body="You can return most items within 30 days of delivery for a full refund. "
             "Start a return under Account > Orders > Return. We email a prepaid return "
             "label; refunds are issued when the carrier scans the package.",
    ),
]


class KnowledgeBase:
    """TF-IDF index over the bundled articles."""

    def __init__(self, articles: list[KBArticle] | None = None):
        self.articles = articles if articles is not None else ARTICLES
        # Title and keyword tokens are weighted (repeated) — in a real KB
        # they are the strongest relevance signal.
        self._doc_tokens: list[list[str]] = [
            _tokens(a.title) * 3 + _tokens(" ".join(a.keywords)) * 2 + _tokens(a.body)
            for a in self.articles
        ]
        n = len(self.articles)
        df: Counter[str] = Counter()
        for toks in self._doc_tokens:
            df.update(set(toks))
        self._idf = {t: math.log((n + 1) / (c + 1)) + 1.0 for t, c in df.items()}
        self._doc_vecs = [self._vectorize(toks) for toks in self._doc_tokens]

    def _vectorize(self, toks: list[str]) -> dict[str, float]:
        tf = Counter(toks)
        vec = {t: (1 + math.log(c)) * self._idf.get(t, 1.0) for t, c in tf.items()}
        norm = math.sqrt(sum(v * v for v in vec.values())) or 1.0
        return {t: v / norm for t, v in vec.items()}

    def search(self, query: str, top_k: int = 3) -> list[RetrievedArticle]:
        qvec = self._vectorize(_tokens(query))
        scored: list[RetrievedArticle] = []
        for article, dvec in zip(self.articles, self._doc_vecs):
            score = sum(w * dvec.get(t, 0.0) for t, w in qvec.items())
            scored.append(RetrievedArticle(
                article_id=article.article_id, title=article.title,
                body=article.body, score=round(score, 4),
            ))
        scored.sort(key=lambda r: (-r.score, r.article_id))
        return scored[:top_k]
