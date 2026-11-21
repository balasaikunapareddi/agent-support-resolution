"""Every policy rule gets a violating case and a passing case."""

from agent_support_resolution.classifier import classify
from agent_support_resolution.models import (
    PolicyDecisionType,
    RetrievedArticle,
    Severity,
    Ticket,
)
from agent_support_resolution.policy import check_policy, redact_pii

GROUNDED = [RetrievedArticle(article_id="KB-002", title="Refund policy", body="...", score=0.6)]
UNGROUNDED = [RetrievedArticle(article_id="KB-001", title="x", body="...", score=0.01)]


def ticket(body="Please refund me $25", email="me@example.com"):
    return Ticket(customer_id="C1", customer_email=email, body=body)


def decide(draft, t=None, retrieved=GROUNDED):
    t = t or ticket()
    return check_policy(draft, t, classify(t), retrieved)


# --- refund_cap ---------------------------------------------------------------


def test_refund_over_cap_needs_human():
    d = decide("We've issued your refund of $329.99 to your card.")
    assert d.decision == PolicyDecisionType.NEEDS_HUMAN
    assert [v.rule_id for v in d.violations] == ["refund_cap"]
    assert d.violations[0].severity == Severity.SOFT


def test_refund_under_cap_allowed():
    d = decide("We've issued your refund of $25.00 to your card.")
    assert d.decision == PolicyDecisionType.ALLOW


def test_refund_exactly_at_cap_allowed():
    d = decide("Your refund of $50.00 is on its way.")
    assert d.decision == PolicyDecisionType.ALLOW


# --- third_party_pii ----------------------------------------------------------


def test_other_customers_email_blocks():
    d = decide("The other customer's email is stranger@example.com.")
    assert d.decision == PolicyDecisionType.BLOCK
    assert d.violations[0].rule_id == "third_party_pii"
    assert d.violations[0].severity == Severity.HARD


def test_own_email_allowed():
    d = decide("We've sent the details to me@example.com.")
    assert d.decision == PolicyDecisionType.ALLOW


# --- raw_pii ------------------------------------------------------------------


def test_card_number_blocks():
    d = decide("Your card 4111 1111 1111 1111 was charged.")
    assert d.decision == PolicyDecisionType.BLOCK
    assert any(v.rule_id == "raw_pii" for v in d.violations)


def test_ssn_blocks():
    d = decide("Your SSN on file is 123-45-6789.")
    assert d.decision == PolicyDecisionType.BLOCK


# --- unsupported_claims -------------------------------------------------------


def test_guarantee_claim_needs_human():
    d = decide("We guarantee a full refund guaranteed, no questions asked!")
    assert d.decision == PolicyDecisionType.NEEDS_HUMAN
    assert any(v.rule_id == "unsupported_claim" for v in d.violations)


def test_plain_claim_allowed():
    d = decide("Refunds are available within 30 days of delivery.")
    assert d.decision == PolicyDecisionType.ALLOW


# --- tone ---------------------------------------------------------------------


def test_dismissive_tone_needs_human():
    d = decide("Calm down, that's not our problem.")
    assert d.decision == PolicyDecisionType.NEEDS_HUMAN
    assert any(v.rule_id == "tone" for v in d.violations)


def test_courteous_tone_allowed():
    d = decide("I'm sorry for the trouble — let me look into that for you.")
    assert d.decision == PolicyDecisionType.ALLOW


# --- kb_grounding -------------------------------------------------------------


def test_ungrounded_draft_needs_human():
    d = decide("Here is an answer I made up.", retrieved=UNGROUNDED)
    assert d.decision == PolicyDecisionType.NEEDS_HUMAN
    assert any(v.rule_id == "kb_grounding" for v in d.violations)


def test_no_retrieval_needs_human():
    d = decide("Here is an answer.", retrieved=[])
    assert d.decision == PolicyDecisionType.NEEDS_HUMAN


# --- redaction ----------------------------------------------------------------


def test_redact_pii_masks_everything():
    text = ("mail a@b.com, call 555-013-4477, card 4111 1111 1111 1111, "
            "ssn 123-45-6789")
    out = redact_pii(text)
    for raw in ("a@b.com", "555-013-4477", "4111", "123-45-6789"):
        assert raw not in out
    assert "[EMAIL REDACTED]" in out
    assert "[CARD REDACTED]" in out


def test_redact_leaves_plain_text_alone():
    assert redact_pii("Where is my order?") == "Where is my order?"
