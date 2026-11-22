"""The support-resolution agent: gated ticket resolution, end to end.

This module is the agent's front door. The agent is ``SupportPipeline``
(defined in ``graph.py`` as a LangGraph state machine):

    intake -> classify -> retrieve_kb -> draft -> policy_check
        -> confidence_gate -> auto_resolve -> send -> audit
                           -> human_review -> send -> audit
                                           -> audit (rejected)

- **intake** redacts PII before anything else touches the ticket.
- **classify** / **retrieve_kb** / **policy_check** / **confidence_gate**
  call the typed tools in ``tools.py``; every routing rule lives in code
  (``classifier.py``, ``kb.py``, ``policy.py``, ``confidence.py``).
- **draft** uses the drafter in ``drafting.py``. In live mode the model
  is driven by the system prompt in ``prompts.py`` (behavior only); the
  drafter never decides what gets sent.
- **human_review** pauses the graph at a checkpointed ``interrupt()``
  until a named reviewer approves, edits, or rejects.

Nothing reaches ``send`` without passing policy + the confidence gate,
or a human's approval. Every node appends to the audit log
(``audit.py``); sending is simulated via ``outbox.py``.

Usage::

    pipeline = SupportPipeline(workdir)          # mock mode
    result = pipeline.submit(ticket)             # sent or pending review
    pipeline.approve(ticket_id, reviewer="sam")  # resume a paused ticket
"""

from .graph import SupportPipeline

__all__ = ["SupportPipeline"]
