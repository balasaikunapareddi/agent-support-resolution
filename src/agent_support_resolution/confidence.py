"""Confidence scoring and the auto-resolve gate.

Confidence is computed from facts the pipeline already has — retrieval
quality, policy outcome, category risk, sentiment — never from the
drafter's self-assessment. Anything below the threshold, any policy
violation, and any high-risk flag routes to a human. The gate is the
product: it is what makes auto-resolution safe enough to ship.
"""

from __future__ import annotations

from .models import (
    Classification,
    ConfidenceScore,
    PolicyDecision,
    PolicyDecisionType,
    RetrievedArticle,
    Route,
    Sentiment,
)

AUTO_RESOLVE_THRESHOLD = 0.70

# Categories where a wrong auto-reply is expensive even when grounded.
_RISK_PENALTY = {
    "privacy": 0.45,
    "refund": 0.15,
    "billing": 0.10,
    "other": 0.30,
}


def score_confidence(
    classification: Classification,
    retrieved: list[RetrievedArticle],
    policy: PolicyDecision,
    threshold: float = AUTO_RESOLVE_THRESHOLD,
) -> ConfidenceScore:
    reasons: list[str] = []

    # Hard policy block: confidence is zero, no debate.
    if policy.decision == PolicyDecisionType.BLOCK:
        return ConfidenceScore(
            score=0.0, route=Route.HUMAN_REVIEW,
            reasons=["policy hard-block: " + ", ".join(v.rule_id for v in policy.violations)],
        )

    # Retrieval quality is the base signal (cosine score of the best article).
    top = retrieved[0].score if retrieved else 0.0
    score = min(1.0, top * 1.8)  # good TF-IDF matches land ~0.45-0.70 raw
    reasons.append(f"retrieval top score {top:.3f}")

    # Soft policy violations cap confidence below the threshold.
    if policy.decision == PolicyDecisionType.NEEDS_HUMAN:
        score = min(score, 0.40)
        reasons.append("soft policy violations: "
                       + ", ".join(v.rule_id for v in policy.violations))

    penalty = _RISK_PENALTY.get(classification.category.value, 0.0)
    if penalty:
        score -= penalty
        reasons.append(f"category risk penalty -{penalty:.2f} ({classification.category.value})")

    if classification.sentiment == Sentiment.ANGRY:
        score = min(score, 0.35)
        reasons.append("angry customer: human should reply")
    elif classification.sentiment == Sentiment.FRUSTRATED:
        score -= 0.10
        reasons.append("frustrated customer: -0.10")

    if classification.asks_third_party_data:
        score = min(score, 0.20)
        reasons.append("ticket asks for another customer's data")

    if classification.contains_pii:
        # The customer pasted secrets into the ticket; a human should
        # confirm nothing sensitive is echoed back.
        score = min(score, 0.50)
        reasons.append("ticket contained raw PII (redacted at intake)")

    score = max(0.0, min(1.0, round(score, 3)))
    route = Route.AUTO_RESOLVE if score >= threshold else Route.HUMAN_REVIEW
    reasons.append(f"score {score:.3f} vs threshold {threshold:.2f} -> {route.value}")
    return ConfidenceScore(score=score, route=route, reasons=reasons)
