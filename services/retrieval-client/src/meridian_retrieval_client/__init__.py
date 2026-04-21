"""Meridian retrieval client.

Two implementations of the RetrievalClient Protocol:
  - MockRetrievalClient  — fixture-backed, used in tests + dev (Phase 3)
  - HttpRetrievalClient  — calls the Data Platform team's RAG API (Phase 4)

ThresholdingClient is a composable wrapper that filters below a minimum
relevance score, per Section 7 §Confidence checks and escalation logic.
"""

from meridian_retrieval_client.http import HttpRetrievalClient, RetrievalConfig
from meridian_retrieval_client.mock import MockRetrievalClient
from meridian_retrieval_client.protocols import RetrievalClient
from meridian_retrieval_client.threshold import ThresholdingClient

__all__ = [
    "HttpRetrievalClient",
    "MockRetrievalClient",
    "RetrievalClient",
    "RetrievalConfig",
    "ThresholdingClient",
]
