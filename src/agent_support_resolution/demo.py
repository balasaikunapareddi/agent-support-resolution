"""One-command demo: the gated pipeline end to end.

    python -m agent_support_resolution.demo

1. Runs the bundled ticket set through the graph.
2. Shows what auto-resolved vs what the gate queued for a human.
3. Works the review queue: approve one, edit one, reject one.
4. Prints the audit trail for the large-refund ticket.
5. Runs the eval set and prints the summary.

Runs fully offline in mock mode (default). Set GEMINI_API_KEY and pass
--live for real Gemini drafting; the gates are identical either way.
Sending is simulated (outbox log) — no real email leaves this process.
"""

from __future__ import annotations

import sys
import tempfile

from .data import TICKETS
from .evals import run_evals
from .graph import SupportPipeline


def _short(text: str | None, n: int = 110) -> str:
    if not text:
        return "(none)"
    flat = " ".join(text.split())
    return flat if len(flat) <= n else flat[: n - 1] + "…"


def run_demo(live: bool = False) -> SupportPipeline:
    workdir = tempfile.mkdtemp(prefix="support-resolution-demo-")
    pipe = SupportPipeline(workdir, live=live)

    print("== Support resolution pipeline demo ==")
    print(f"Workdir: {workdir}  (audit.jsonl, outbox.jsonl, review.db)\n")

    print("-- Step 1: run the ticket set through the graph --")
    for ticket in TICKETS:
        s = pipe.submit(ticket)
        conf = f"{s['confidence']:.2f}" if s["confidence"] is not None else "  - "
        print(f"  {ticket.ticket_id}  [{s['status']:<14}] conf={conf}  "
              f"policy={s['policy_decision']}  {ticket.subject}")

    print("\n-- Step 2: the human review queue --")
    for item in pipe.pending_reviews():
        print(f"  {item.ticket_id}: {_short(item.draft_text, 80)}")
        print(f"      reasons: {'; '.join(item.reasons[:3])}")

    print("\n-- Step 3: work the queue (approve / edit / reject) --")
    r = pipe.approve("TKT-1005", reviewer="sam.lead")
    print(f"  approve TKT-1005 (PII-bait decline) -> {r['status']}, sent_by={r['sent_by']}")

    edited = (
        "Hi David,\n\nThanks for reaching out. Refunds above $50 need a quick "
        "review by a support specialist before they can be issued (that's our "
        "standard policy). I've flagged your $329.99 request for that review "
        "and you'll hear back within one business day.\n\nBest regards,\nSupport Team"
    )
    r = pipe.edit("TKT-1004", edited, reviewer="sam.lead")
    print(f"  edit    TKT-1004 (large refund)     -> {r['status']}, sent_by={r['sent_by']}")
    print(f"      sent text starts: {_short(r['final_text'], 90)}")

    r = pipe.reject("TKT-1007", reviewer="sam.lead",
                    reason="Out of scope for support; routed to sales.")
    print(f"  reject  TKT-1007 (wedding cakes)    -> {r['status']}")

    print("\n-- Step 4: audit trail for TKT-1004 (every decision, on record) --")
    for e in pipe.audit_trail("TKT-1004"):
        print(f"  {e.ts}  {e.node:<16} {e.event_type}")

    print("\n-- Step 5: evals --")
    results = run_evals(SupportPipeline(tempfile.mkdtemp(prefix="support-evals-")))
    passed = sum(r.passed for r in results)
    for r in results:
        if not r.passed:
            print(f"  [FAIL] {r.name}: {'; '.join(r.failures)}")
    print(f"  {passed}/{len(results)} eval cases passed "
          "(routing, auto-resolve safety, audit completeness, redaction).")

    sent = pipe.outbox_records()
    print(f"\nOutbox: {len(sent)} simulated sends "
          f"({sum(1 for s in sent if s['sent_by'] == 'auto')} auto, "
          f"{sum(1 for s in sent if s['sent_by'] != 'auto')} human-approved).")
    print("Note: sending is simulated — see outbox.jsonl in the workdir.")
    return pipe


def main() -> int:
    run_demo(live="--live" in sys.argv)
    return 0


if __name__ == "__main__":
    sys.exit(main())
