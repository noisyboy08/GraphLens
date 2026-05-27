"""Token accounting helpers."""

from __future__ import annotations

import re
from pathlib import Path

TOKEN_RE = re.compile(r"\w+|[^\w\s]", re.UNICODE)


class TokenCounter:
    """Count source tokens with a tokenizer fallback chain."""

    def __init__(self) -> None:
        self._encoding = self._load_tiktoken()

    def count_text(self, text: str) -> int:
        """Return token count for text."""

        if self._encoding is not None:
            return len(self._encoding.encode(text))
        return len(TOKEN_RE.findall(text))

    def count_file(self, path: str | Path) -> int:
        """Return token count for a text file."""

        text = Path(path).read_text(encoding="utf-8", errors="ignore")
        return self.count_text(text)

    def count_files(self, root: str | Path, paths: list[str]) -> int:
        """Return total token count for paths under a root."""

        total = 0
        root_path = Path(root)
        for path in paths:
            if path.startswith("<external>"):
                continue
            target = root_path / path
            if target.exists() and target.is_file():
                total += self.count_file(target)
        return total

    def _load_tiktoken(self) -> object | None:
        try:
            import tiktoken

            return tiktoken.get_encoding("cl100k_base")
        except Exception:
            return None
