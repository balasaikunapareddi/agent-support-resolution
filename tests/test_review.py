import pytest

from agent_support_resolution.models import ReviewError, ReviewItem, Ticket
from agent_support_resolution.review import ReviewQueue


def pending_ticket(tid="T-REV-1"):
    # Large refund: policy soft-violation -> human review with a draft.
    return Ticket(ticket_id=tid, customer_id="C1", customer_name="David Kim",
                  customer_email="david@example.com", subject="Refund for the TV",
                  body="I want a full refund of $329.99. Please process the refund today.")


# --- queue unit behavior ------------------------------------------------------


def test_queue_add_get_pending(tmp_path):
    q = ReviewQueue(tmp_path / "review.db")
    q.add(ReviewItem(ticket_id="T1", draft_text="hi", reasons=["r1"]))
    assert q.get("T1").draft_text == "hi"
    assert [i.ticket_id for i in q.list_pending()] == ["T1"]


def test_queue_mark_decided(tmp_path):
    q = ReviewQueue(tmp_path / "review.db")
    q.add(ReviewItem(ticket_id="T1", draft_text="hi"))
    item = q.mark_decided("T1", "approved", "sam")
    assert item.status == "approved"
    assert item.decided_by == "sam"
    assert q.list_pending() == []


def test_queue_double_decide_raises(tmp_path):
    q = ReviewQueue(tmp_path / "review.db")
    q.add(ReviewItem(ticket_id="T1"))
    q.mark_decided("T1", "rejected", "sam")
    with pytest.raises(ReviewError):
        q.mark_decided("T1", "approved", "sam")


def test_queue_unknown_ticket_raises(tmp_path):
    q = ReviewQueue(tmp_path / "review.db")
    with pytest.raises(ReviewError):
        q.mark_decided("nope", "approved", "sam")


# --- pipeline approve / edit / reject -----------------------------------------


def test_approve_sends_draft(pipeline):
    s = pipeline.submit(pending_ticket())
    assert s["status"] == "pending_review"
    r = pipeline.approve("T-REV-1", reviewer="sam.lead")
    assert r["status"] == "sent"
    assert r["sent_by"] == "sam.lead"
    records = pipeline.outbox_records()
    assert len(records) == 1 and records[0]["sent_by"] == "sam.lead"
    assert pipeline.pending_reviews() == []


def test_edit_sends_edited_text(pipeline):
    pipeline.submit(pending_ticket())
    edited = "Hi David, a specialist will review your refund request within one business day."
    r = pipeline.edit("T-REV-1", edited, reviewer="sam.lead")
    assert r["status"] == "sent"
    assert r["final_text"] == edited
    assert pipeline.outbox_records()[0]["text"] == edited


def test_edit_with_hard_violation_stays_pending(pipeline):
    pipeline.submit(pending_ticket())
    bad = "Sure, the other customer's email is stranger@example.com."
    r = pipeline.edit("T-REV-1", bad, reviewer="sam.lead")
    assert r["status"] == "pending_review"
    assert "hard-violates" in r["interrupt"]["message"]
    assert pipeline.outbox_records() == []
    # A clean edit afterwards still works.
    r2 = pipeline.edit("T-REV-1", "A specialist will review this.", reviewer="sam.lead")
    assert r2["status"] == "sent"


def test_reject_sends_nothing(pipeline):
    pipeline.submit(pending_ticket())
    r = pipeline.reject("T-REV-1", reviewer="sam.lead", reason="duplicate ticket")
    assert r["status"] == "rejected"
    assert pipeline.outbox_records() == []
    assert pipeline.pending_reviews() == []
    events = [e.event_type for e in pipeline.audit_trail("T-REV-1")]
    assert "review_decision" in events and "sent" not in events


def test_decide_unknown_ticket_raises(pipeline):
    with pytest.raises(ReviewError):
        pipeline.approve("T-NOPE", reviewer="sam")


def test_decide_twice_raises(pipeline):
    pipeline.submit(pending_ticket())
    pipeline.approve("T-REV-1", reviewer="sam")
    with pytest.raises(ReviewError):
        pipeline.approve("T-REV-1", reviewer="sam")
