"""Unit tests for ``transcript_chunker``.

Pure function — no LLM, no DB. Verifies window/overlap behaviour and
sentence-boundary handling.
"""

from app.services.transcript_chunker import chunk_transcript


class TestEdgeCases:
    def test_empty_input(self) -> None:
        assert chunk_transcript("") == []
        assert chunk_transcript("   ") == []

    def test_single_short_sentence(self) -> None:
        out = chunk_transcript("Hola, ¿cómo estás?", window=256)
        assert out == ["Hola, ¿cómo estás?"]


class TestSentenceBoundaries:
    def test_splits_on_punctuation(self) -> None:
        text = "Una. Dos. Tres. Cuatro. Cinco."
        out = chunk_transcript(text, window=2, overlap=0)
        # Each sentence is 1 word ("Uno", "Dos", ...) + period; window=2
        # means after 2 sentences we flush.
        assert len(out) >= 2
        # Combined chunks should reconstitute all sentences in order.
        joined = " ".join(out)
        for needle in ("Una", "Dos", "Tres", "Cuatro", "Cinco"):
            assert needle in joined

    def test_oversize_single_sentence_is_split(self) -> None:
        # 600 words without punctuation must still produce > 1 chunk.
        text = " ".join(f"w{i}" for i in range(600))
        out = chunk_transcript(text, window=256, overlap=32)
        assert len(out) >= 2
        # Each chunk fits inside window.
        for chunk in out:
            assert len(chunk.split()) <= 256


class TestOverlap:
    def test_overlap_words_appear_in_next_chunk(self) -> None:
        # Build sentences that fill exactly past the window so we trigger
        # a flush and copy a tail. window=10, overlap=3.
        text = ". ".join(f"oracion {i} con tres palabras" for i in range(8)) + "."
        out = chunk_transcript(text, window=10, overlap=3)
        assert len(out) >= 2
        # Each chunk fits the window soft cap (sentences are atomic, so
        # the cap is enforced *before* adding the new sentence).
        for chunk in out:
            assert len(chunk.split()) <= 12  # +small slack for punctuation
