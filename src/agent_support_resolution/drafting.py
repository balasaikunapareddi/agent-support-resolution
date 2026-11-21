"""Draft generation: deterministic mock drafter + optional live LLM drafter.

The mock drafter composes a reply from the top KB article. It is
deliberately a little naive in one realistic way: for refund tickets it
templates the customer's requested amount into a confirmation sentence —
exactly what a careless auto-reply bot does — so the policy gate has
something real to catch. Everything else is grounded in the article text.

The live drafter calls Gemini via langchain-google-genai with the system
prompt from ``prompts.py``. It is only constructed when explicitly
requested (``live=True``) and needs ``GEMINI_API_KEY``; the model defaults
to ``gemini-3.5-flash-lite`` and is overridable via ``GEMINI_MODEL``.
Either way, the draft then faces the same policy check and confidence
gate — the drafter never decides what gets sent.
"""

from __future__ import annotations

import os

from .models import Classification, LiveModeError, RetrievedArticle, Ticket
from .prompts import DRAFT_USER_TEMPLATE, SYSTEM_PROMPT

DEFAULT_LIVE_MODEL = "gemini-3.5-flash-lite"


def _greeting(ticket: Ticket) -> str:
    name = ticket.customer_name.strip()
    return f"Hi {name}," if name else "Hi there,"


class MockDrafter:
    """Deterministic, offline drafter grounded in the top KB article."""

    def draft(
        self,
        ticket: Ticket,
        classification: Classification,
        retrieved: list[RetrievedArticle],
    ) -> str:
        top = retrieved[0] if retrieved else None
        lines = [_greeting(ticket), ""]
        if classification.asks_third_party_data:
            lines.append(
                "Thanks for reaching out. I can only discuss your own account, "
                "orders, and contact details with you — I'm not able to share "
                "another customer's information."
            )
        elif top is not None and top.score > 0:
            lines.append("Thanks for reaching out. Here's what I found:")
            lines.append("")
            lines.append(top.body)
            if classification.category.value == "refund" and classification.refund_amount_usd:
                # Naive-bot behavior the policy gate exists to catch.
                lines.append("")
                lines.append(
                    f"We've issued your refund of ${classification.refund_amount_usd:,.2f} "
                    "to your original payment method."
                )
        else:
            lines.append(
                "Thanks for reaching out. I couldn't find an answer in our help "
                "center for this one, so I've passed your ticket to a specialist "
                "who will follow up."
            )
        lines += ["", "Best regards,", "Support Team"]
        return "\n".join(lines)


class LiveDrafter:
    """Gemini-backed drafter (needs the ``live`` extra + GEMINI_API_KEY)."""

    def __init__(self, model: str | None = None):
        if not os.environ.get("GEMINI_API_KEY"):
            raise LiveModeError(
                "Live mode needs GEMINI_API_KEY in the environment. "
                "Mock mode (the default) needs no key and no network."
            )
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
        except ImportError as exc:
            raise LiveModeError(
                "Live mode needs langchain-google-genai: "
                "pip install 'agent-support-resolution[live]'"
            ) from exc
        self._model = ChatGoogleGenerativeAI(
            model=model or os.environ.get("GEMINI_MODEL", DEFAULT_LIVE_MODEL),
            temperature=0,
        )

    def draft(
        self,
        ticket: Ticket,
        classification: Classification,
        retrieved: list[RetrievedArticle],
    ) -> str:
        excerpts = "\n\n".join(
            f"[{a.article_id}] {a.title}\n{a.body}" for a in retrieved
        ) or "(no relevant articles found)"
        user = DRAFT_USER_TEMPLATE.format(
            subject=ticket.subject, body=ticket.body, kb_excerpts=excerpts
        )
        reply = self._model.invoke([("system", SYSTEM_PROMPT), ("human", user)])
        return str(reply.content).strip()


def get_drafter(live: bool = False):
    """Mock by default; live only when explicitly requested."""
    return LiveDrafter() if live else MockDrafter()
