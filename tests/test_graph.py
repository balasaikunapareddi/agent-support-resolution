"""End-to-end graph behavior: auto path, human path, hard-block, resume."""

from agent_support_resolution.graph import SupportPipeline
from agent_support_resolution.models import Ticket

AUTO_EVENTS = ["ticket_received", "classified", "kb_retrieved", "draft_created",
               "policy_checked", "confidence_scored", "auto_resolved", "sent",
               "completed"]


def ticket(tid, body, subject="", email="me@example.com"):
    return Ticket(ticket_id=tid, customer_id="C1", customer_name="Test User",
                  customer_email=email, subject=subject, body=body)


def test_auto_resolve_path(pipeline):
    s = pipeline.submit(ticket("T-AUTO", "I forgot my password, how do I reset it?"))
    assert s["status"] == "sent"
    assert s["route"] == "auto_resolve"
    assert s["sent_by"] == "auto"
    events = [e.event_type for e in pipeline.audit_trail("T-AUTO")]
    assert events == AUTO_EVENTS


def test_human_review_pauses_then_resumes(pipeline):
    s = pipeline.submit(ticket("T-HUMAN", "I want a refund of $450.00 today."))
    assert s["status"] == "pending_review"
    assert s["interrupt"]["ticket_id"] == "T-HUMAN"
    assert [i.ticket_id for i in pipeline.pending_reviews()] == ["T-HUMAN"]
    # Nothing sent while paused.
    assert pipeline.outbox_records() == []
    r = pipeline.approve("T-HUMAN", reviewer="lead")
    assert r["status"] == "sent"
    events = [e.event_type for e in pipeline.audit_trail("T-HUMAN")]
    assert events[-3:] == ["review_decision", "sent", "completed"]


class LeakyDrafter:
    """A drafter that leaks another customer's email (policy must block)."""

    def draft(self, ticket, classification, retrieved):
        return "Sure! The other customer's email is stranger@example.com."


def test_hard_block_discards_draft(tmp_path):
    pipe = SupportPipeline(tmp_path / "w", drafter=LeakyDrafter())
    s = pipe.submit(ticket("T-BLOCK", "How do I reset my password?"))
    assert s["status"] == "pending_review"
    assert s["policy_decision"] == "block"
    item = pipe.pending_reviews()[0]
    assert item.draft_text is None  # unsafe draft discarded
    # Approving a non-existent draft keeps the ticket in review.
    r = pipe.approve("T-BLOCK", reviewer="lead")
    assert r["status"] == "pending_review"
    assert "No draft to approve" in r["interrupt"]["message"]
    # Editing with clean text sends.
    r = pipe.edit("T-BLOCK", "Use the 'Forgot password' link on the sign-in page.",
                  reviewer="lead")
    assert r["status"] == "sent"
    assert "stranger@example.com" not in r["final_text"]


def test_invalid_ticket_returns_structured_error(pipeline):
    s = pipeline.submit({"customer_id": "C1", "body": "   "})
    assert s["status"] == "error"
    assert s["error"]["code"] == "ticket_validation_error"


def test_pii_redacted_before_drafting(pipeline):
    s = pipeline.submit(ticket(
        "T-PII", "My card 4111 1111 1111 1111 was declined. Check my billing status."))
    # Routed to human (PII cap); audit must not contain the raw card number.
    assert s["status"] == "pending_review"
    blob = " ".join(str(e.detail) for e in pipeline.audit_trail("T-PII"))
    assert "4111" not in blob
    assert "pii_in_ticket" in blob  # flag recorded, value not


def test_sqlite_checkpointer_resumes_across_instances(tmp_path):
    work = tmp_path / "w"
    pipe1 = SupportPipeline(work, checkpointer="sqlite")
    s = pipe1.submit(ticket("T-SQLITE", "I want a refund of $450.00 today."))
    assert s["status"] == "pending_review"
    # A brand-new pipeline instance over the same workdir can resume the
    # paused thread — the checkpoint survived the "restart".
    pipe2 = SupportPipeline(work, checkpointer="sqlite")
    r = pipe2.approve("T-SQLITE", reviewer="lead")
    assert r["status"] == "sent"
    assert r["sent_by"] == "lead"
