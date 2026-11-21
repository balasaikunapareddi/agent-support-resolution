"""Typed tools: the service boundary the graph nodes call.

Each tool has pydantic input/output schemas, so the same functions can be
exposed to a live LLM agent (function calling) without change. The graph
calls them directly — deterministic code does the work, the model (in
live mode) only drafts text.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from . import classifier as _classifier
from . import confidence as _confidence
from . import policy as _policy
from .kb import KnowledgeBase
from .models import (
    Classification,
    ConfidenceScore,
    PolicyDecision,
    RetrievedArticle,
    Ticket,
)

# --- classify_ticket ---------------------------------------------------------


class ClassifyTicketInput(BaseModel):
    ticket: Ticket


class ClassifyTicketOutput(BaseModel):
    classification: Classification


def classify_ticket(inp: ClassifyTicketInput) -> ClassifyTicketOutput:
    return ClassifyTicketOutput(classification=_classifier.classify(inp.ticket))


# --- search_kb ---------------------------------------------------------------


class SearchKBInput(BaseModel):
    query: str
    top_k: int = Field(default=3, ge=1, le=10)


class SearchKBOutput(BaseModel):
    articles: list[RetrievedArticle]


def search_kb(inp: SearchKBInput, kb: KnowledgeBase) -> SearchKBOutput:
    return SearchKBOutput(articles=kb.search(inp.query, top_k=inp.top_k))


# --- check_policy ------------------------------------------------------------


class CheckPolicyInput(BaseModel):
    draft_text: str
    ticket: Ticket
    classification: Classification
    retrieved: list[RetrievedArticle]


class CheckPolicyOutput(BaseModel):
    decision: PolicyDecision


def check_policy(inp: CheckPolicyInput) -> CheckPolicyOutput:
    return CheckPolicyOutput(
        decision=_policy.check_policy(
            inp.draft_text, inp.ticket, inp.classification, inp.retrieved
        )
    )


# --- score_confidence --------------------------------------------------------


class ScoreConfidenceInput(BaseModel):
    classification: Classification
    retrieved: list[RetrievedArticle]
    policy_decision: PolicyDecision


class ScoreConfidenceOutput(BaseModel):
    confidence: ConfidenceScore


def score_confidence(inp: ScoreConfidenceInput) -> ScoreConfidenceOutput:
    return ScoreConfidenceOutput(
        confidence=_confidence.score_confidence(
            inp.classification, inp.retrieved, inp.policy_decision
        )
    )


# --- redact_pii --------------------------------------------------------------


class RedactPIIInput(BaseModel):
    text: str


class RedactPIIOutput(BaseModel):
    redacted_text: str


def redact_pii(inp: RedactPIIInput) -> RedactPIIOutput:
    return RedactPIIOutput(redacted_text=_policy.redact_pii(inp.text))
