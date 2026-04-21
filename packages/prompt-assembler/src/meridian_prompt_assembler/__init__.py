"""Meridian prompt assembler.

Takes a PromptTemplate from the registry plus a runtime AssemblyContext
(retrieved docs, history, few-shot examples, user query, vars) and produces
an AssembledPrompt that matches the ModelRequest shape. Enforces the token
budget and truncation priority from Section 6.
"""

from meridian_prompt_assembler.assembler import (
    AssembledMessage,
    AssembledPrompt,
    Assembler,
    AssemblyContext,
    FewShotExample,
    TruncationEvent,
)
from meridian_prompt_assembler.tokens import TokenCounter, TokenCounterProtocol

__all__ = [
    "AssembledMessage",
    "AssembledPrompt",
    "Assembler",
    "AssemblyContext",
    "FewShotExample",
    "TokenCounter",
    "TokenCounterProtocol",
    "TruncationEvent",
]
