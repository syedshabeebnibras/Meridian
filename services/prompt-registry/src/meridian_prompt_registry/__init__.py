"""Meridian prompt registry.

Postgres-backed store for versioned, immutable prompt templates with
separate activation rows (Section 19 D3). Rollback is a row-level flip, not
a code deploy.
"""

from meridian_prompt_registry.registry import (
    ActiveTemplateNotFoundError,
    NoPriorActivationError,
    PromptRegistry,
    PromptVersionNotFoundError,
)

__all__ = [
    "ActiveTemplateNotFoundError",
    "NoPriorActivationError",
    "PromptRegistry",
    "PromptVersionNotFoundError",
]
