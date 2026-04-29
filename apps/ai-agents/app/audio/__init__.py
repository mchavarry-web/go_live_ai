"""Audio training pipeline.

Phase 1 modules:
    transcription -- provider abstraction (default: OpenAI gpt-4o-mini-transcribe)

Phase 2 will add:
    voice_print   -- Resemblyzer embeddings for speaker identification
    speaker_id    -- cosine-match diarized turns against enrolled embedding
    diarization   -- pyannote.audio speaker turn segmentation
"""
