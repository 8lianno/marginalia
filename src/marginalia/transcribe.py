from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

# Path to the Swift helper source and compiled binary
_SWIFT_SRC = Path(__file__).parent / "swift" / "transcribe.swift"
_BINARY_DIR = Path(__file__).parent / "swift"
_BINARY_NAME = "transcribe_helper"


def _binary_path() -> Path:
    return _BINARY_DIR / _BINARY_NAME


def _ensure_binary() -> Path:
    """Compile the Swift helper if the binary doesn't exist or is older than source."""
    binary = _binary_path()
    if binary.exists() and binary.stat().st_mtime >= _SWIFT_SRC.stat().st_mtime:
        return binary
    print("  Compiling Apple Speech helper...", file=sys.stderr)
    subprocess.run(
        [
            "swiftc",
            "-O",
            "-o", str(binary),
            str(_SWIFT_SRC),
            "-framework", "Speech",
        ],
        check=True,
        capture_output=True,
    )
    return binary


def transcribe_local(audio_path: Path) -> str:
    """Transcribe a WAV file using the Apple Speech Swift helper. Returns transcript text."""
    binary = _ensure_binary()
    result = subprocess.run(
        [str(binary), str(audio_path)],
        capture_output=True,
        text=True,
        timeout=3600,  # 1 hour max for very long audio
    )
    if result.returncode != 0:
        error = result.stderr.strip() or "Unknown transcription error"
        raise RuntimeError(f"Apple Speech transcription failed: {error}")
    return result.stdout.strip()


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

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

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
