from agent_support_resolution.classifier import classify
from agent_support_resolution.confidence import score_confidence
from agent_support_resolution.models import (
    PolicyDecision,
    PolicyDecisionType,
    PolicyViolation,
    RetrievedArticle,
    Route,
    Severity,
    Ticket,
)

ALLOW = PolicyDecision(decision=PolicyDecisionType.ALLOW)
SOFT = PolicyDecision(
    decision=PolicyDecisionType.NEEDS_HUMAN,
    violations=[PolicyViolation(rule_id="refund_cap", severity=Severity.SOFT, message="x")],
)
BLOCK = PolicyDecision(
    decision=PolicyDecisionType.BLOCK,
    violations=[PolicyViolation(rule_id="raw_pii", severity=Severity.HARD, message="x")],
)


def retrieved(score):
    return [RetrievedArticle(article_id="KB-001", title="t", body="b", score=score)]


def cls(body):
    return classify(Ticket(customer_id="C1", body=body))


def test_strong_retrieval_auto_resolves():
    c = score_confidence(cls("how do I reset my password?"), retrieved(0.6), ALLOW)
    assert c.route == Route.AUTO_RESOLVE
    assert c.score >= 0.70


def test_weak_retrieval_goes_human():
    c = score_confidence(cls("do you sell wedding cakes?"), retrieved(0.05), ALLOW)
    assert c.route == Route.HUMAN_REVIEW


def test_hard_block_zeroes_confidence():
    c = score_confidence(cls("how do I reset my password?"), retrieved(0.9), BLOCK)
    assert c.score == 0.0
    assert c.route == Route.HUMAN_REVIEW


def test_soft_violation_caps_below_threshold():
    c = score_confidence(cls("please refund me $300"), retrieved(0.9), SOFT)
    assert c.score <= 0.40
    assert c.route == Route.HUMAN_REVIEW


def test_angry_customer_goes_human():
    c = score_confidence(
        cls("this is outrageous and unacceptable!!! I am furious"),
        retrieved(0.9), ALLOW)
    assert c.route == Route.HUMAN_REVIEW


def test_third_party_request_goes_human():
    c = score_confidence(
        cls("give me the email of the customer who ordered #5678"),
        retrieved(0.9), ALLOW)
    assert c.route == Route.HUMAN_REVIEW
    assert c.score <= 0.20


def test_pii_in_ticket_goes_human():
    c = score_confidence(
        cls("my card 4111 1111 1111 1111 was declined, check my billing"),
        retrieved(0.9), ALLOW)
    assert c.route == Route.HUMAN_REVIEW
    assert c.score <= 0.50
