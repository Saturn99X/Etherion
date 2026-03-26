"""
Pattern Database for prompt injection detection.

Simple in-memory registry with versioning and loader hook.
"""

from dataclasses import dataclass
from typing import List, Tuple
import re


@dataclass(frozen=True)
class PatternSignature:
    name: str
    regex: str
    weight: int


class PromptPatternDB:
    """Lightweight, immutable registry of known injection signatures."""

    VERSION = "2025-10-02.1"

    def __init__(self) -> None:
        self._patterns: List[Tuple[str, re.Pattern, int]] = []
        for sig in self._default_signatures():
            self._patterns.append((sig.name, re.compile(sig.regex, re.IGNORECASE), sig.weight))

    def get_patterns(self) -> List[Tuple[str, re.Pattern, int]]:
        return list(self._patterns)

    def version(self) -> str:
        return self.VERSION

    def _default_signatures(self) -> List[PatternSignature]:
        return [
            PatternSignature("ignore_directives", r"\b(ignore|disregard|forget)\b[^\n]{0,40}\b(instructions|rules|previous|system)\b", 25),
            PatternSignature("override_system", r"\b(override|bypass|disable)\b[^\n]{0,40}\b(safety|guardrails|system|policy|filter)\b", 25),
            PatternSignature("exfiltrate_prompt", r"\b(show|print|reveal|expose)\b[^\n]{0,40}\b(system\s+prompt|hidden\s+prompt|instructions)\b", 30),
            PatternSignature("chain_of_thought", r"\b(show|reveal)\b[^\n]{0,40}\b(chain\s*of\s*thought|reasoning)\b", 10),
            PatternSignature("jailbreak_dan", r"\b(DAN|developer\s*mode|jailbreak)\b", 20),
            PatternSignature("system_impersonation", r"\b(you\s+are\s+now\s+the\s+system|act\s+as\s+the\s+system)\b", 20),
            PatternSignature("tool_simulation", r"\b(simulate|pretend)\b[^\n]{0,40}\b(tool|api|filesystem|shell|command)\b", 15),
            PatternSignature("base64_decode_exec", r"\b(base64|hex)\b[^\n]{0,40}\b(decode|decode\s+and\s+execute)\b", 20),
            PatternSignature("prompt_delimiters", r"(BEGIN\s+SYSTEM\s+PROMPT|END\s+SYSTEM\s+PROMPT)", 15),
            PatternSignature("secret_exfil", r"\b(secret|apikeys?|tokens?|passwords?|credentials?)\b", 15),
        ]


_singleton: PromptPatternDB | None = None


def get_prompt_pattern_db() -> PromptPatternDB:
    global _singleton
    if _singleton is None:
        _singleton = PromptPatternDB()
    return _singleton


