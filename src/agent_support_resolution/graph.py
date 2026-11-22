"""The resolution workflow as an explicit LangGraph state machine.

    intake -> classify -> retrieve_kb -> draft -> policy_check
        -> confidence_gate -> auto_resolve -> send -> audit
                           -> human_review -> send -> audit
                                           -> audit (rejected)

Why LangGraph: the workflow is a state machine with a human-approval
interrupt. LangGraph's checkpointed graph pauses at ``interrupt()``,
persists state per ticket (thread), and resumes exactly where it stopped
when a reviewer decides — the production pattern for human-in-the-loop
automation, not a hand-rolled callback.

Every node appends to the audit log as it runs. Nothing reaches ``send``
without passing policy + the confidence gate, or a named human's
approval. Sending itself is simulated (see ``outbox.py``).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import TypedDict

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from . import tools
from .audit import AuditLog
from .classifier import detect_pii
from .confidence import AUTO_RESOLVE_THRESHOLD
from .drafting import get_drafter
from .kb import KnowledgeBase
from .models import (
    Classification,
    PipelineError,
    PolicyDecision,
    PolicyDecisionType,
    RetrievedArticle,
    ReviewAction,
    ReviewDecision,
    ReviewError,
    ReviewItem,
    Route,
    Ticket,
)
from .outbox import Outbox
from .policy import check_policy
from .review import ReviewQueue


class ResolutionState(TypedDict, total=False):
    ticket: dict
    pii_detected: dict  # PII shapes found in the ORIGINAL ticket at intake
    classification: dict | None
    retrieved: list[dict]
    draft_text: str | None
    policy: dict | None
    confidence: dict | None
    route: str | None
    review: dict | None
    final_text: str | None
    sent_by: str | None
    status: str
    error: dict | None


def _ticket(state: ResolutionState) -> Ticket:
    return Ticket(**state["ticket"])


def build_graph(*, kb, drafter, audit: AuditLog, queue: ReviewQueue,
                outbox: Outbox, checkpointer, threshold: float):
    """Compile the resolution graph around injected services."""

    def intake(state: ResolutionState) -> dict:
        ticket = _ticket(state)
        # Detect PII on the ORIGINAL text first (the flag must survive
        # redaction), then redact before anything else touches the text.
        pii = detect_pii(f"{ticket.subject} {ticket.body}")
        redacted = ticket.model_copy(update={
            "subject": tools.redact_pii(tools.RedactPIIInput(text=ticket.subject)).redacted_text,
            "body": tools.redact_pii(tools.RedactPIIInput(text=ticket.body)).redacted_text,
        })
        audit.record(ticket.ticket_id, "ticket_received", "intake", {
            "customer_id": ticket.customer_id, "channel": ticket.channel,
            "subject": redacted.subject,
            "pii_detected": [k for k, v in pii.items() if v],
        })
        return {"ticket": redacted.model_dump(), "pii_detected": pii,
                "status": "in_progress"}

    def classify(state: ResolutionState) -> dict:
        ticket = _ticket(state)
        out = tools.classify_ticket(tools.ClassifyTicketInput(ticket=ticket))
        cls = out.classification
        # The classifier saw redacted text; restore the intake PII finding.
        if any((state.get("pii_detected") or {}).values()) and not cls.contains_pii:
            flags = list(cls.risk_flags)
            if "pii_in_ticket" not in flags:
                flags.append("pii_in_ticket")
            cls = cls.model_copy(update={"contains_pii": True, "risk_flags": flags})
        audit.record(ticket.ticket_id, "classified", "classify",
                     cls.model_dump(mode="json"))
        return {"classification": cls.model_dump(mode="json")}

    def retrieve_kb(state: ResolutionState) -> dict:
        ticket = _ticket(state)
        query = f"{ticket.subject} {ticket.body}"
        out = tools.search_kb(tools.SearchKBInput(query=query, top_k=3), kb)
        audit.record(ticket.ticket_id, "kb_retrieved", "retrieve_kb", {
            "articles": [{"id": a.article_id, "score": a.score} for a in out.articles],
        })
        return {"retrieved": [a.model_dump() for a in out.articles]}

    def draft(state: ResolutionState) -> dict:
        ticket = _ticket(state)
        cls = Classification(**state["classification"])
        retrieved = [RetrievedArticle(**a) for a in state["retrieved"]]
        text = drafter.draft(ticket, cls, retrieved)
        audit.record(ticket.ticket_id, "draft_created", "draft",
                     {"chars": len(text), "drafter": type(drafter).__name__})
        return {"draft_text": text}

    def policy_check(state: ResolutionState) -> dict:
        ticket = _ticket(state)
        cls = Classification(**state["classification"])
        retrieved = [RetrievedArticle(**a) for a in state["retrieved"]]
        out = tools.check_policy(tools.CheckPolicyInput(
            draft_text=state["draft_text"] or "", ticket=ticket,
            classification=cls, retrieved=retrieved,
        ))
        decision = out.decision
        audit.record(ticket.ticket_id, "policy_checked", "policy_check", {
            "decision": decision.decision.value,
            "violations": [v.model_dump(mode="json") for v in decision.violations],
        })
        update: dict = {"policy": decision.model_dump(mode="json")}
        if decision.decision == PolicyDecisionType.BLOCK:
            # Unsafe draft: discard it. A human writes from scratch.
            update["draft_text"] = None
        return update

    def confidence_gate(state: ResolutionState) -> dict:
        ticket = _ticket(state)
        cls = Classification(**state["classification"])
        retrieved = [RetrievedArticle(**a) for a in state["retrieved"]]
        policy = PolicyDecision(**state["policy"])
        out = tools.score_confidence(tools.ScoreConfidenceInput(
            classification=cls, retrieved=retrieved, policy_decision=policy,
        ))
        # score_confidence uses the module threshold; re-route on ours.
        conf = out.confidence
        route = (Route.AUTO_RESOLVE if conf.score >= threshold
                 and policy.decision == PolicyDecisionType.ALLOW
                 else Route.HUMAN_REVIEW)
        conf = conf.model_copy(update={"route": route})
        audit.record(ticket.ticket_id, "confidence_scored", "confidence_gate", {
            "score": conf.score, "route": route.value, "reasons": conf.reasons,
        })
        return {"confidence": conf.model_dump(mode="json"), "route": route.value}

    def route_after_gate(state: ResolutionState) -> str:
        return "auto_resolve" if state.get("route") == Route.AUTO_RESOLVE.value else "human_review"

    def auto_resolve(state: ResolutionState) -> dict:
        ticket = _ticket(state)
        audit.record(ticket.ticket_id, "auto_resolved", "auto_resolve",
                     {"confidence": (state.get("confidence") or {}).get("score")})
        return {"final_text": state["draft_text"], "sent_by": "auto"}

    def human_review(state: ResolutionState) -> dict:
        ticket = _ticket(state)
        cls = Classification(**state["classification"])
        retrieved = [RetrievedArticle(**a) for a in state["retrieved"]]
        policy = PolicyDecision(**state["policy"])
        conf = state.get("confidence") or {}
        reasons = list(conf.get("reasons", []))
        if policy.violations:
            reasons += [f"policy:{v.rule_id} ({v.severity.value})" for v in policy.violations]

        queue.add(ReviewItem(ticket_id=ticket.ticket_id,
                             draft_text=state.get("draft_text"), reasons=reasons))
        if not any(e.event_type == "review_requested"
                   for e in audit.events_for(ticket.ticket_id)):
            audit.record(ticket.ticket_id, "review_requested", "human_review",
                         {"reasons": reasons})

        message = "Awaiting human decision (approve / edit / reject)."
        while True:
            decision = interrupt({
                "ticket_id": ticket.ticket_id,
                "draft_text": state.get("draft_text"),
                "reasons": reasons,
                "policy_decision": policy.decision.value,
                "confidence": conf.get("score"),
                "message": message,
            })
            try:
                review = ReviewDecision(**decision)
            except Exception as exc:  # malformed resume payload
                message = f"Invalid decision payload: {exc}"
                continue

            if review.action == ReviewAction.REJECT:
                queue.mark_decided(ticket.ticket_id, "rejected", review.reviewer)
                audit.record(ticket.ticket_id, "review_decision", "human_review",
                             {"action": "reject", "reviewer": review.reviewer,
                              "reason": review.reason})
                return {"status": "rejected", "final_text": None,
                        "review": review.model_dump(mode="json")}

            if review.action == ReviewAction.APPROVE:
                if not state.get("draft_text"):
                    message = ("No draft to approve (policy hard-blocked it). "
                               "Edit with replacement text, or reject.")
                    continue
                final_text = state["draft_text"]
                status = "approved"
            else:  # EDIT
                if not review.edited_text or not review.edited_text.strip():
                    message = "Edit requires replacement text."
                    continue
                edited_policy = check_policy(review.edited_text, ticket, cls, retrieved)
                audit.record(ticket.ticket_id, "policy_checked", "human_review", {
                    "decision": edited_policy.decision.value, "on": "edited_text",
                    "violations": [v.model_dump(mode="json") for v in edited_policy.violations],
                })
                if edited_policy.decision == PolicyDecisionType.BLOCK:
                    message = ("Edited text still hard-violates policy: "
                               + ", ".join(v.rule_id for v in edited_policy.violations)
                               + ". Fix it or reject.")
                    continue
                final_text = review.edited_text
                status = "edited"

            queue.mark_decided(ticket.ticket_id, status, review.reviewer)
            audit.record(ticket.ticket_id, "review_decision", "human_review",
                         {"action": review.action.value, "reviewer": review.reviewer})
            return {"final_text": final_text, "sent_by": review.reviewer,
                    "review": review.model_dump(mode="json")}

    def route_after_review(state: ResolutionState) -> str:
        return "audit" if state.get("status") == "rejected" else "send"

    def send(state: ResolutionState) -> dict:
        ticket = _ticket(state)
        record = outbox.send(ticket.ticket_id, ticket.customer_id,
                             state["final_text"] or "", state.get("sent_by") or "auto")
        audit.record(ticket.ticket_id, "sent", "send",
                     {"sent_by": record["sent_by"], "simulated": True})
        return {"status": "sent"}

    def audit_node(state: ResolutionState) -> dict:
        ticket = _ticket(state)
        final_status = state.get("status") or "sent"
        audit.record(ticket.ticket_id, "completed", "audit", {
            "final_status": final_status,
            "route": state.get("route"),
            "sent_by": state.get("sent_by"),
        })
        return {"status": final_status}

    graph = StateGraph(ResolutionState)
    graph.add_node("intake", intake)
    graph.add_node("classify", classify)
    graph.add_node("retrieve_kb", retrieve_kb)
    graph.add_node("draft", draft)
    graph.add_node("policy_check", policy_check)
    graph.add_node("confidence_gate", confidence_gate)
    graph.add_node("auto_resolve", auto_resolve)
    graph.add_node("human_review", human_review)
    graph.add_node("send", send)
    graph.add_node("audit", audit_node)

    graph.add_edge(START, "intake")
    graph.add_edge("intake", "classify")
    graph.add_edge("classify", "retrieve_kb")
    graph.add_edge("retrieve_kb", "draft")
    graph.add_edge("draft", "policy_check")
    graph.add_edge("policy_check", "confidence_gate")
    graph.add_conditional_edges("confidence_gate", route_after_gate,
                                {"auto_resolve": "auto_resolve",
                                 "human_review": "human_review"})
    graph.add_edge("auto_resolve", "send")
    graph.add_conditional_edges("human_review", route_after_review,
                                {"send": "send", "audit": "audit"})
    graph.add_edge("send", "audit")
    graph.add_edge("audit", END)
    return graph.compile(checkpointer=checkpointer)


class SupportPipeline:
    """The support-resolution agent: submit tickets, work the review queue, inspect the audit.

    The agent loop is the LangGraph state machine built by
    ``build_graph()`` above:

        intake -> classify -> retrieve_kb -> draft -> policy_check
            -> confidence_gate -> auto_resolve -> send -> audit
                               -> human_review -> send -> audit
                                               -> audit (rejected)

    ``submit()`` runs a ticket until it is sent, rejected, or paused at
    the human-review interrupt; ``approve()`` / ``edit()`` / ``reject()``
    resume it. ``workdir`` holds the audit log, outbox, review DB, and
    (optionally) the SQLite checkpointer. ``live=True`` swaps the mock
    drafter for Gemini (system prompt in ``prompts.py``); everything
    else — classification, retrieval, policy, confidence gate — is
    identical deterministic code.
    """

    def __init__(self, workdir: str | Path, *, live: bool = False,
                 checkpointer: str = "memory",
                 threshold: float = AUTO_RESOLVE_THRESHOLD,
                 kb: KnowledgeBase | None = None, drafter=None):
        self.workdir = Path(workdir)
        self.workdir.mkdir(parents=True, exist_ok=True)
        self.kb = kb or KnowledgeBase()
        self.drafter = drafter if drafter is not None else get_drafter(live=live)
        self.audit = AuditLog(self.workdir / "audit.jsonl")
        self.outbox = Outbox(self.workdir / "outbox.jsonl")
        self.queue = ReviewQueue(self.workdir / "review.db")
        if checkpointer == "sqlite":
            from langgraph.checkpoint.sqlite import SqliteSaver
            conn = sqlite3.connect(str(self.workdir / "checkpoints.db"),
                                   check_same_thread=False)
            saver = SqliteSaver(conn)
        else:
            saver = MemorySaver()
        self.graph = build_graph(kb=self.kb, drafter=self.drafter,
                                 audit=self.audit, queue=self.queue,
                                 outbox=self.outbox, checkpointer=saver,
                                 threshold=threshold)

    # -- submission -----------------------------------------------------------

    def submit(self, ticket: Ticket | dict) -> dict:
        """Run a ticket until it is sent, rejected, or paused for review."""
        try:
            ticket_obj = ticket if isinstance(ticket, Ticket) else Ticket(**ticket)
        except Exception as exc:
            err = PipelineError(f"Invalid ticket: {exc}", code="ticket_validation_error")
            return {"status": "error", "error": err.to_dict()}
        config = {"configurable": {"thread_id": ticket_obj.ticket_id}}
        try:
            result = self.graph.invoke(
                {"ticket": ticket_obj.model_dump(), "status": "received"}, config)
        except PipelineError as exc:
            return {"status": "error", "error": exc.to_dict()}
        return self._summarize(ticket_obj.ticket_id, result, config)

    # -- human review ---------------------------------------------------------

    def pending_reviews(self) -> list[ReviewItem]:
        return self.queue.list_pending()

    def approve(self, ticket_id: str, reviewer: str) -> dict:
        return self._decide(ticket_id, ReviewDecision(
            action=ReviewAction.APPROVE, reviewer=reviewer))

    def edit(self, ticket_id: str, new_text: str, reviewer: str) -> dict:
        return self._decide(ticket_id, ReviewDecision(
            action=ReviewAction.EDIT, reviewer=reviewer, edited_text=new_text))

    def reject(self, ticket_id: str, reviewer: str, reason: str = "") -> dict:
        return self._decide(ticket_id, ReviewDecision(
            action=ReviewAction.REJECT, reviewer=reviewer, reason=reason))

    def _decide(self, ticket_id: str, decision: ReviewDecision) -> dict:
        item = self.queue.get(ticket_id)
        if item is None or item.status != "pending":
            raise ReviewError(
                f"Ticket {ticket_id} is not pending review "
                f"(status: {item.status if item else 'unknown'}).")
        config = {"configurable": {"thread_id": ticket_id}}
        result = self.graph.invoke(Command(resume=decision.model_dump(mode="json")), config)
        return self._summarize(ticket_id, result, config)

    # -- inspection -----------------------------------------------------------

    def audit_trail(self, ticket_id: str):
        return self.audit.events_for(ticket_id)

    def outbox_records(self) -> list[dict]:
        return self.outbox.records()

    # -- helpers --------------------------------------------------------------

    def _summarize(self, ticket_id: str, result: dict, config: dict) -> dict:
        interrupts = result.get("__interrupt__") if isinstance(result, dict) else None
        state = self.graph.get_state(config)
        paused = bool(interrupts) or bool(state.next)
        values = state.values or result
        status = "pending_review" if paused else values.get("status", "unknown")
        summary = {
            "ticket_id": ticket_id,
            "status": status,
            "route": values.get("route"),
            "confidence": (values.get("confidence") or {}).get("score"),
            "policy_decision": (values.get("policy") or {}).get("decision"),
            "sent_by": values.get("sent_by"),
            "final_text": values.get("final_text"),
        }
        if interrupts:
            summary["interrupt"] = interrupts[0].value if hasattr(interrupts[0], "value") else interrupts[0]
        return summary
