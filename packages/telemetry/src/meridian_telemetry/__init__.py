"""Telemetry helpers — OTel setup and GenAI semantic convention constants.

Implementation lives in Phase 6 (Observability & Ops Hardening). This module
only defines the attribute keys so the rest of the codebase can already emit
spans against a stable schema.
"""

from meridian_telemetry.semconv import GenAIAttr, MeridianAttr

__all__ = ["GenAIAttr", "MeridianAttr"]
