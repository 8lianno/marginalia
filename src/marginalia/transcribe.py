from __future__ import annotations

import os
from pathlib import Path

# Default Whisper model — runs on Apple GPU via MLX
_DEFAULT_MODEL = "mlx-community/whisper-base-mlx"


def transcribe_local(
    audio_path: Path,
    on_heartbeat: callable | None = None,
) -> str:
    """Transcribe an audio file using MLX-Whisper on Apple Silicon GPU.

    Args:
        audio_path: Path to the audio file (WAV, etc.).
        on_heartbeat: Optional callback (unused — mlx-whisper is fast enough
                      that heartbeat pacing is unnecessary).

    Returns:
        The transcript text.
    """
    import mlx_whisper

    result = mlx_whisper.transcribe(
        str(audio_path),
        path_or_hf_repo=_DEFAULT_MODEL,
        fp16=True,
    )
    return result["text"].strip()


def transcribe_local_segments(
    audio_path: Path,
    on_heartbeat: callable | None = None,
) -> list:
    """Transcribe locally and return segment-level timestamps.

    Returns a list of `marginalia.youtube.Segment` (start, duration, text) so
    the notes-mode pipeline can treat local videos and YouTube videos
    uniformly. Keeps `transcribe_local` intact for transcript mode.
    """
    import mlx_whisper

    from marginalia.youtube import Segment

    result = mlx_whisper.transcribe(
        str(audio_path),
        path_or_hf_repo=_DEFAULT_MODEL,
        fp16=True,
    )

    segments_raw = result.get("segments") or []
    segments: list[Segment] = []
    for seg in segments_raw:
        start = float(seg.get("start", 0.0))
        end = float(seg.get("end", start))
        text = str(seg.get("text", "")).strip()
        if not text:
            continue
        segments.append(Segment(start=start, duration=max(0.0, end - start), text=text))
    return segments


# --- Brief mode: LLM summarization ---

# Model context limits (tokens). Conservative at 80% to leave room for output.
MODEL_CONTEXT_LIMITS: dict[str, int] = {
    "gemini-2.0-flash": 1_000_000,
    "gemini-2.5-flash": 1_000_000,
    "gemini-2.0-pro": 2_000_000,
}
SAFE_CONTEXT_RATIO = 0.80
CHARS_PER_TOKEN_ESTIMATE = 4  # rough average for English text


def _estimate_tokens(text: str) -> int:
    """Rough token count estimate from character length."""
    return len(text) // CHARS_PER_TOKEN_ESTIMATE


def check_transcript_length(transcript: str, prompt: str, model: str) -> None:
    """Raise if the transcript + prompt would exceed the model's safe context limit."""
    total_chars = len(transcript) + len(prompt) + 200  # 200 for framing
    estimated_tokens = total_chars // CHARS_PER_TOKEN_ESTIMATE
    limit = MODEL_CONTEXT_LIMITS.get(model)
    if limit is None:
        return  # Unknown model — let the API reject if needed
    safe_limit = int(limit * SAFE_CONTEXT_RATIO)
    if estimated_tokens > safe_limit:
        raise RuntimeError(
            f"Transcript too long for {model} context window "
            f"(~{estimated_tokens:,} tokens, limit ~{safe_limit:,}). "
            f"Chunking will be added in a future version."
        )


def preflight_check(model: str) -> None:
    """Verify API key and model reachability with a minimal request."""
    from google import genai
    from google.genai import types

    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY environment variable is not set")

    client = genai.Client(api_key=api_key)
    try:
        client.models.generate_content(
            model=model,
            contents=[types.Content(parts=[types.Part.from_text(text="ping")])],
        )
    except Exception as e:
        error_str = str(e).lower()
        if "api key" in error_str or "401" in error_str or "403" in error_str:
            raise RuntimeError(f"API key invalid or unauthorized for model {model}") from None
        if "not found" in error_str or "404" in error_str:
            raise RuntimeError(f"Model '{model}' is not available") from None
        raise RuntimeError(f"Preflight check failed: {e}") from None


def summarize_transcript(
    transcript: str,
    prompt: str,
    model: str,
) -> tuple[str, int | None, int | None, float | None]:
    """Send a transcript to an LLM for structured brief generation.

    Returns (text, input_tokens, output_tokens, cost_usd).
    """
    from google import genai
    from google.genai import types

    # Guard against transcripts that exceed model context
    check_transcript_length(transcript, prompt, model)

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY environment variable is not set")
    client = genai.Client(api_key=api_key)

    full_prompt = f"{prompt}\n\n---\n\nTRANSCRIPT:\n{transcript}"

    response = client.models.generate_content(
        model=model,
        contents=[types.Content(parts=[types.Part.from_text(text=full_prompt)])],
    )

    text = response.text or ""
    input_tokens = None
    output_tokens = None
    if response.usage_metadata:
        input_tokens = response.usage_metadata.prompt_token_count
        output_tokens = response.usage_metadata.candidates_token_count

    # Estimate cost from tokens (Gemini 2.0 Flash: $0.10/1M input, $0.40/1M output)
    cost = 0.0
    if input_tokens:
        cost += input_tokens * 0.10 / 1_000_000
    if output_tokens:
        cost += output_tokens * 0.40 / 1_000_000

    return text, input_tokens, output_tokens, round(cost, 6)
