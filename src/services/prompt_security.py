"""
Prompt Security service: lightweight, deterministic prompt-injection detection and sanitization.

Responsibilities:
- Heuristic detection of common injection patterns
- Risk scoring and decisioning (allow/sanitize/block)
- Safe sanitization that removes/neutralizes injection directives

Design goals:
- Simple, explicit control flow (no recursion, bounded loops)
- Deterministic behavior with predictable outcomes
- No external calls; fast (< 1ms typical)
"""

import re
from dataclasses import dataclass
from typing import Dict, Any, List, Optional, Tuple

from src.utils.input_sanitization import InputSanitizer
from src.services.prompt_patterns import get_prompt_pattern_db
from src.services.trust_manager import get_trust_manager
from src.services.ai_injection_detector import AIInjectionDetector


@dataclass
class PromptSecurityConfig:
    """Configuration for prompt injection detection thresholds and allowlists."""
    block_threshold: int = 80
    sanitize_threshold: int = 40
    max_input_length: int = 10000
    # Allowlisted user_ids or explicit patterns that skip blocking (still audited)
    allowed_user_ids: Optional[List[int]] = None
    allowed_patterns: Optional[List[re.Pattern]] = None


class PromptSecurity:
    """
    Provide prompt injection detection and sanitization for user-supplied text.
    """

    # Patterns are provided by PromptPatternDB; kept here for clarity of access
    _PATTERNS: List[Tuple[str, re.Pattern, int]] = []

    # Neutralization substitutions (ordered, bounded)
    _NEUTRALIZE_SUBS: List[Tuple[re.Pattern, str]] = [
        (re.compile(r"\b(ignore|disregard|forget)\b", re.IGNORECASE), "[redacted]")
    ]

    def __init__(self, config: Optional[PromptSecurityConfig] = None):
        self.config = config or PromptSecurityConfig()
        self._ai_detector: Optional[AIInjectionDetector] = None

    async def analyze_text_async(self, text: str, *, user_key: Optional[str] = None) -> Dict[str, Any]:
        """
        Analyze text for prompt injection signals.

        Returns dict with: { risk_score, matches: [(name, span)], action: 'allow'|'sanitize'|'block' }
        """
        if not isinstance(text, str):
            return {"risk_score": 100, "matches": [("non_string", (0, 0))], "action": "block"}

        if len(text) > self.config.max_input_length:
            return {"risk_score": 100, "matches": [("too_long", (0, 0))], "action": "block"}

        # Lazy load patterns from DB to allow version updates without restart
        if not self._PATTERNS:
            db = get_prompt_pattern_db()
            self._PATTERNS = db.get_patterns()

        total_score = 0
        matches: List[Tuple[str, Tuple[int, int]]] = []

        for name, pattern, weight in self._PATTERNS:
            m = pattern.search(text)
            if m:
                total_score += weight
                matches.append((name, (m.start(), m.end())))
                # Bound the number of patterns considered
                if len(matches) >= 10:
                    break

        # Additional signals from generic sanitizer (dangerous patterns)
        dangerous = InputSanitizer.detect_dangerous_patterns(text)
        if dangerous:
            # Each dangerous indicator adds small weight; cap additions
            add = min(len(dangerous) * 5, 20)
            total_score += add
            matches.append(("dangerous_patterns", (0, 0)))

        # Trust-based threshold adjustment
        block_threshold = self.config.block_threshold
        sanitize_threshold = self.config.sanitize_threshold
        if user_key:
            tm = get_trust_manager()
            adjust = await tm.get_threshold_adjustment(user_key)
            block_threshold = max(0, block_threshold + adjust)
            sanitize_threshold = max(0, sanitize_threshold + adjust)

        # Optional AI-based refinement (only if heuristics are close to thresholds)
        if (total_score >= sanitize_threshold - 5) and (total_score < block_threshold + 5):
            # Lazy init detector
            if self._ai_detector is None:
                self._ai_detector = AIInjectionDetector(model_tier="flash")
            ai_score = await self._ai_detector.score(text)
            # Blend: take max to be conservative
            total_score = max(total_score, ai_score)

        if total_score >= block_threshold:
            action = "block"
        elif total_score >= sanitize_threshold:
            action = "sanitize"
        else:
            action = "allow"

        return {"risk_score": total_score, "matches": matches, "action": action}

    def sanitize_text(self, text: str) -> str:
        """
        Sanitize text by:
        - Running security checks (length, XSS/SQL patterns)
        - Neutralizing strong instruction override verbs
        - HTML-escaping
        """
        # Primary sanitation with strict checks
        sanitized = InputSanitizer.sanitize_with_security_checks(
            text,
            max_length=self.config.max_input_length,
            allowed_pattern=None,
            check_dangerous=True,
            check_sql_injection=True,
        )

        # Targeted neutralization of directive verbs
        for pattern, replacement in self._NEUTRALIZE_SUBS:
            sanitized = pattern.sub(replacement, sanitized)

        return sanitized


_prompt_security_singleton: Optional[PromptSecurity] = None


def get_prompt_security() -> PromptSecurity:
    """Global singleton accessor to avoid repeated instantiation."""
    global _prompt_security_singleton
    if _prompt_security_singleton is None:
        _prompt_security_singleton = PromptSecurity()
    return _prompt_security_singleton


