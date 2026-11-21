"""Domain models and structured errors.

Pydantic models are the typed boundary of the system: tickets come in as
``Ticket`` objects, every stage produces a typed result, and failures are
structured (``PipelineError``) rather than bare exceptions or free text.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field, field_validator


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


# --- structured errors -------------------------------------------------------


class PipelineError(Exception):
    """Base error carrying a machine-readable code."""

    code = "pipeline_error"

    def __init__(self, message: str, *, code: str | None = None, detail: dict | None = None):
        super().__init__(message)
        self.message = message
        if code:
            self.code = code
        self.detail = detail or {}

    def to_dict(self) -> dict:
        return {"code": self.code, "message": self.message, "detail": self.detail}


class TicketValidationError(PipelineError):
    code = "ticket_validation_error"


class PolicyBlockError(PipelineError):
    code = "policy_block"


class ReviewError(PipelineError):
    code = "review_error"


class LiveModeError(PipelineError):
    code = "live_mode_unavailable"


# --- tickets -----------------------------------------------------------------


class Ticket(BaseModel):
    """An inbound support ticket."""

    ticket_id: str = Field(default_factory=lambda: new_id("TKT"))
    customer_id: str
    customer_name: str = ""
    customer_email: str = ""
    subject: str = ""
    body: str
    channel: str = "email"
    created_at: str = Field(default_factory=utc_now_iso)

    @field_validator("body")
    @classmethod
    def _body_nonempty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("ticket body must not be empty")
        return v

    @field_validator("customer_id")
    @classmethod
    def _customer_id_nonempty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("customer_id must not be empty")
        return v


class Category(str, Enum):
    ACCOUNT = "account"
    BILLING = "billing"
    ORDER = "order"
    REFUND = "refund"
    SHIPPING = "shipping"
    PRODUCT = "product"
    PRIVACY = "privacy"
    OTHER = "other"


class Sentiment(str, Enum):
    CALM = "calm"
    FRUSTRATED = "frustrated"
    ANGRY = "angry"


class Classification(BaseModel):
    category: Category
    intent: str
    sentiment: Sentiment = Sentiment.CALM
    refund_amount_usd: float | None = None
    asks_third_party_data: bool = False
    contains_pii: bool = False
    risk_flags: list[str] = Field(default_factory=list)


# --- knowledge base ----------------------------------------------------------


class KBArticle(BaseModel):
    article_id: str
    title: str
    body: str
    category: Category = Category.OTHER
    keywords: list[str] = Field(default_factory=list)  # customer phrasings, like real KB tags


class RetrievedArticle(BaseModel):
    article_id: str
    title: str
    body: str
    score: float


# --- policy ------------------------------------------------------------------


class Severity(str, Enum):
    SOFT = "soft"  # needs a human, draft is kept for review
    HARD = "hard"  # draft is unsafe; discard it, human writes from scratch


class PolicyViolation(BaseModel):
    rule_id: str
    severity: Severity
    message: str
    evidence: str = ""


class PolicyDecisionType(str, Enum):
    ALLOW = "allow"
    NEEDS_HUMAN = "needs_human"
    BLOCK = "block"


class PolicyDecision(BaseModel):
    decision: PolicyDecisionType
    violations: list[PolicyViolation] = Field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.decision == PolicyDecisionType.ALLOW


# --- confidence / routing ----------------------------------------------------


class Route(str, Enum):
    AUTO_RESOLVE = "auto_resolve"
    HUMAN_REVIEW = "human_review"


class ConfidenceScore(BaseModel):
    score: float  # 0..1
    route: Route
    reasons: list[str] = Field(default_factory=list)


# --- human review ------------------------------------------------------------


class ReviewAction(str, Enum):
    APPROVE = "approve"
    EDIT = "edit"
    REJECT = "reject"


class ReviewDecision(BaseModel):
    action: ReviewAction
    reviewer: str
    edited_text: str | None = None
    reason: str = ""


class ReviewItem(BaseModel):
    ticket_id: str
    status: str = "pending"  # pending | approved | edited | rejected
    draft_text: str | None = None
    reasons: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=utc_now_iso)
    decided_by: str | None = None
    decided_at: str | None = None


# --- audit -------------------------------------------------------------------


class AuditEvent(BaseModel):
    ts: str = Field(default_factory=utc_now_iso)
    ticket_id: str
    event_type: str
    node: str
    detail: dict = Field(default_factory=dict)
