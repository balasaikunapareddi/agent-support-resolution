"""Production-grade support-resolution agent (LangGraph, mock-first).

Classify -> retrieve -> draft -> policy-as-code check -> confidence gate
-> human approval for anything risky -> simulated send, with a full
audit trail. No API key or network needed in mock mode.
"""

from .graph import SupportPipeline
from .models import Ticket

__all__ = ["SupportPipeline", "Ticket"]
__version__ = "0.1.0"
