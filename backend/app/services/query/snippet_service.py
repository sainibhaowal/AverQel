from __future__ import annotations

import re


class SnippetService:
    """Utilities for cleaning and compacting text snippets for UI display."""

    _CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
    _WHITESPACE_RE = re.compile(r"\s+")
    _SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
    _MULTI_DOTS_RE = re.compile(r"\.{4,}")
    _MULTI_SPACES_BEFORE_PUNCT_RE = re.compile(r"\s+([,.;:!?])")

    @classmethod
    def normalize(cls, text: str) -> str:
        """Normalize raw text into a clean single-line snippet-safe form."""
        if not text:
            return ""

        cleaned = text.replace("\ufffd", " ")
        cleaned = cls._CONTROL_CHARS_RE.sub("", cleaned)
        cleaned = cls._WHITESPACE_RE.sub(" ", cleaned).strip()
        cleaned = cls._MULTI_DOTS_RE.sub("...", cleaned)
        cleaned = cls._MULTI_SPACES_BEFORE_PUNCT_RE.sub(r"\1", cleaned)
        return cleaned

    @classmethod
    def truncate(cls, text: str, max_chars: int) -> str:
        """Hard truncate text with ellipsis."""
        if max_chars <= 0:
            raise ValueError("max_chars must be a positive integer")

        if len(text) <= max_chars:
            return text

        if max_chars <= 3:
            return text[:max_chars]

        return text[:max_chars].rstrip() + "..."

    @classmethod
    def clean(cls, text: str, max_chars: int = 240) -> str:
        """
        Clean text and trim it to a readable snippet, preferring whole sentences
        when possible.
        """
        if max_chars <= 0:
            raise ValueError("max_chars must be a positive integer")

        cleaned = cls.normalize(text)
        if not cleaned:
            return ""

        if len(cleaned) <= max_chars:
            return cleaned

        sentences = cls._SENTENCE_SPLIT_RE.split(cleaned)
        result: list[str] = []
        current_len = 0

        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue

            extra = len(sentence) if not result else len(sentence) + 1
            if current_len + extra <= max_chars:
                result.append(sentence)
                current_len += extra
            else:
                break

        if result:
            final_text = " ".join(result).strip()
            if final_text:
                return final_text

        return cls.truncate(cleaned, max_chars)
