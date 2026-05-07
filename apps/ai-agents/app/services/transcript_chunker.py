"""Pure-function transcript chunker.

Splits a transcript string into ~256-word windows with ~32-word overlap.
We approximate "tokens" with words to avoid pulling in tiktoken — the
actual embedding cost is computed by OpenAI server-side anyway and the
window length only needs to be in the right ballpark.

Sentence-aware: when possible, windows end on a sentence boundary so the
embedding captures a coherent thought rather than a torn-mid-clause fragment.
"""

from __future__ import annotations

import re

# Soft target window length in words. ~256 ≈ ~340 OpenAI tokens, well
# below the 8k embedding-model max and small enough to be retrievable
# without hauling a paragraph of tangential context.
DEFAULT_WINDOW_WORDS = 256
DEFAULT_OVERLAP_WORDS = 32

_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?¡¿…])\s+")


def chunk_transcript(
    transcript: str,
    *,
    window: int = DEFAULT_WINDOW_WORDS,
    overlap: int = DEFAULT_OVERLAP_WORDS,
) -> list[str]:
    """Split ``transcript`` into overlapping word-windows.

    The transcript is first split on sentence boundaries; sentences are
    then accumulated until the running word count crosses ``window``.
    Overlap is applied by re-emitting the trailing ``overlap`` words at
    the start of the next window.

    Args:
        transcript: Raw transcript text.
        window: Soft target word count per window (default 256).
        overlap: Word overlap between consecutive windows (default 32).

    Returns:
        List of window strings. Empty when input is empty/whitespace.
    """
    text = (transcript or "").strip()
    if not text:
        return []
    if window <= 0:
        return [text]
    overlap = max(0, min(overlap, max(0, window - 1)))

    sentences = [s.strip() for s in _SENTENCE_BOUNDARY.split(text) if s.strip()]
    if not sentences:
        sentences = [text]

    chunks: list[str] = []
    current_words: list[str] = []
    for sentence in sentences:
        words = sentence.split()
        if not words:
            continue
        # If a single sentence is itself bigger than the window — usually
        # only happens with punctuation-free transcripts — slice it up
        # raw so we still produce useful chunks instead of one giant blob.
        if len(words) > window:
            if current_words:
                chunks.append(" ".join(current_words).strip())
                current_words = []
            step = max(1, window - overlap)
            for start in range(0, len(words), step):
                window_slice = words[start:start + window]
                if not window_slice:
                    break
                chunks.append(" ".join(window_slice).strip())
                if start + window >= len(words):
                    break
            continue
        if current_words and len(current_words) + len(words) > window:
            chunks.append(" ".join(current_words).strip())
            tail = current_words[-overlap:] if overlap else []
            current_words = list(tail)
        current_words.extend(words)
    if current_words:
        chunks.append(" ".join(current_words).strip())
    return [c for c in chunks if c]
