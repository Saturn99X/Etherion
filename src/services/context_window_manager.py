from __future__ import annotations

from functools import lru_cache
from typing import List, Dict, Any, Tuple

try:
    import tiktoken
except Exception:  # pragma: no cover
    tiktoken = None


class ContextWindowManager:
    """
    Simple policy functions to manage chat history and retrieved docs within token budgets.
    This is a lightweight, explicit controller to be used before prompt assembly.
    """

    def __init__(self, max_prompt_tokens: int, reserve_for_output: int = 1024) -> None:
        if max_prompt_tokens <= 0:
            raise ValueError("max_prompt_tokens must be positive")
        if reserve_for_output < 0:
            raise ValueError("reserve_for_output cannot be negative")
        self.max_prompt_tokens = max_prompt_tokens
        self.reserve_for_output = reserve_for_output

    @staticmethod
    @lru_cache(maxsize=1)
    def _encoder():
        if tiktoken is None:
            raise RuntimeError("tiktoken is required for token budgeting")
        return tiktoken.get_encoding("cl100k_base")

    def _count_tokens(self, text: str) -> int:
        if not text:
            return 0
        enc = self._encoder()
        return len(enc.encode(text))

    def _truncate_to_tokens(self, text: str, max_tokens: int) -> str:
        if not text or max_tokens <= 0:
            return ""
        enc = self._encoder()
        toks = enc.encode(text)
        if len(toks) <= max_tokens:
            return text
        return enc.decode(toks[:max_tokens])

    def trim_history_window(self, messages: List[Dict[str, str]], budget: int) -> List[Dict[str, str]]:
        """Keep only most recent turns that fit into budget.
        messages is a list of {role, content}.
        """
        kept: List[Dict[str, str]] = []
        running = 0
        for m in reversed(messages):
            t = self._count_tokens(m.get("content", ""))
            if running + t > budget:
                break
            kept.append(m)
            running += t
        return list(reversed(kept))

    def compress_docs(self, docs: List[str], budget: int) -> List[str]:
        """Truncate documents to fit token budget by head truncation."""
        kept: List[str] = []
        running = 0
        for d in docs:
            t = self._count_tokens(d)
            if running + t <= budget:
                kept.append(d)
                running += t
            else:
                # Truncate to remaining budget
                remain = max(0, budget - running)
                if remain > 0:
                    kept.append(self._truncate_to_tokens(d, remain))
                    running = budget
                break
        return kept

    def allocate_budgets(
        self,
        system_tokens: int,
        input_tokens: int,
        history: List[Dict[str, str]],
        retrieved_docs: List[str],
    ) -> Tuple[List[Dict[str, str]], List[str]]:
        """Compute budgets and return trimmed history and compressed docs.
        The order of application: prioritize KB docs, then history; web docs should be pre-filtered.
        """
        total_budget = self.max_prompt_tokens - self.reserve_for_output
        if total_budget <= 0:
            return [], []

        remaining = max(0, total_budget - system_tokens - input_tokens)
        if remaining <= 0:
            return [], []

        # Split remaining: 60% retrieved docs, 40% history by default
        docs_budget = int(remaining * 0.6)
        hist_budget = remaining - docs_budget

        trimmed_docs = self.compress_docs(retrieved_docs, docs_budget)
        trimmed_hist = self.trim_history_window(history, hist_budget)
        return trimmed_hist, trimmed_docs


