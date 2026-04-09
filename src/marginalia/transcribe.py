from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

# Path to the Swift helper source and compiled binary
_SWIFT_SRC = Path(__file__).parent / "swift" / "transcribe.swift"
_BINARY_DIR = Path(__file__).parent / "swift"
_BINARY_NAME = "transcribe_helper"

# Known error prefixes from the Swift helper for structured error messages
_ERROR_MESSAGES = {
    "SPEECH_LOCALE_UNAVAILABLE": "Speech recognizer not available for en-US locale.",
    "SPEECH_NOT_AVAILABLE": (
        "On-device speech recognition is not available.\n"
        "  Fix: System Settings > Privacy & Security > Speech Recognition — enable access.\n"
        "  Also: System Settings > General > Keyboard > Dictation — enable on-device."
    ),
    "SPEECH_MODEL_NOT_DOWNLOADED": (
        "On-device speech model is not downloaded.\n"
        "  Fix: System Settings > General > Keyboard > Dictation — enable 'On-Device Dictation'."
    ),
    "SPEECH_PERMISSION_DENIED": (
        "Speech recognition permission denied.\n"
        "  Fix: System Settings > Privacy & Security > Speech Recognition — grant access."
    ),
    "RECOGNITION_FAILED": "Apple Speech recognition failed during processing.",
}


def _binary_path() -> Path:
    return _BINARY_DIR / _BINARY_NAME


def _ensure_binary() -> Path:
    """Compile the Swift helper if the binary doesn't exist or is older than source."""
    binary = _binary_path()
    if binary.exists() and binary.stat().st_mtime >= _SWIFT_SRC.stat().st_mtime:
        return binary

    # Check swiftc is available
    if not shutil.which("swiftc"):
        raise RuntimeError(
            "swiftc not found. Install Xcode Command Line Tools: run `xcode-select --install`"
        )

    print("  Compiling Apple Speech helper...", file=sys.stderr)
    try:
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
            text=True,
        )
    except subprocess.CalledProcessError as e:
        stderr = e.stderr.strip() if e.stderr else "unknown error"
        raise RuntimeError(
            f"Swift helper compilation failed:\n{stderr}\n\n"
            f"Ensure Xcode Command Line Tools are installed: `xcode-select --install`"
        ) from None

    return binary


def transcribe_local(
    audio_path: Path,
    on_heartbeat: callable | None = None,
) -> str:
    """Transcribe a WAV file using the Apple Speech Swift helper.

    The Swift helper emits "." lines as heartbeats during transcription
    and a final "TRANSCRIPT: <text>" line when done.  We stream stdout
    line-by-line via Popen so the caller can update a progress bar in
    real time.

    Args:
        audio_path: Path to the WAV file.
        on_heartbeat: Optional callback invoked on each heartbeat (no args).

    Returns:
        The transcript text.
    """
    binary = _ensure_binary()
    proc = subprocess.Popen(
        [str(binary), str(audio_path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    transcript = ""
    try:
        for line in proc.stdout:
            line = line.rstrip("\n")
            if line == ".":
                if on_heartbeat:
                    on_heartbeat()
            elif line.startswith("TRANSCRIPT: "):
                transcript = line[len("TRANSCRIPT: "):]
            # Ignore any other lines
    except Exception:
        proc.kill()
        raise

    proc.wait()

    if proc.returncode != 0:
        error = (proc.stderr.read() if proc.stderr else "").strip() or "Unknown transcription error"
        friendly = _parse_helper_error(error)
        raise RuntimeError(friendly)

    return transcript


def _parse_helper_error(raw_error: str) -> str:
    """Map Swift helper error codes to user-friendly messages."""
    for prefix, message in _ERROR_MESSAGES.items():
        if prefix in raw_error:
            return message
    return f"Apple Speech transcription failed: {raw_error}"


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
