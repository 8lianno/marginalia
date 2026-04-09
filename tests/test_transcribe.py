from pathlib import Path

import pytest

from marginalia.transcribe import _parse_helper_error, check_transcript_length, transcribe_local


def test_parse_speech_locale_error():
    msg = _parse_helper_error("Error: SPEECH_LOCALE_UNAVAILABLE: blah")
    assert "not available" in msg


def test_parse_speech_not_available_error():
    msg = _parse_helper_error("Error: SPEECH_NOT_AVAILABLE: blah")
    assert "System Settings" in msg


def test_parse_speech_model_not_downloaded():
    msg = _parse_helper_error("Error: SPEECH_MODEL_NOT_DOWNLOADED: blah")
    assert "not downloaded" in msg


def test_parse_speech_permission_denied():
    msg = _parse_helper_error("Error: SPEECH_PERMISSION_DENIED: blah")
    assert "permission denied" in msg


def test_parse_unknown_error():
    msg = _parse_helper_error("Error: something weird happened")
    assert "Apple Speech transcription failed" in msg


def test_check_transcript_length_within_limit():
    # Short transcript — should not raise
    check_transcript_length("Hello world", "Summarize this", "gemini-2.0-flash")


def test_check_transcript_length_exceeds_limit():
    # Create a transcript that would exceed the limit
    # gemini-2.0-flash has 1M token limit, 80% safe = 800K tokens
    # At 4 chars/token, that's 3.2M chars
    huge_transcript = "word " * 1_000_000  # 5M chars ~ 1.25M tokens
    with pytest.raises(RuntimeError, match="too long"):
        check_transcript_length(huge_transcript, "Summarize", "gemini-2.0-flash")


def test_check_transcript_length_unknown_model():
    # Unknown model — should not raise (let the API handle it)
    huge_transcript = "word " * 1_000_000
    check_transcript_length(huge_transcript, "Summarize", "unknown-model-xyz")


def test_transcribe_local_streams_heartbeats(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    helper = tmp_path / "fake_helper"
    helper.write_text(
        "#!/bin/sh\n"
        "printf '.\\n'\n"
        "printf '.\\n'\n"
        "printf 'TRANSCRIPT: hello from helper\\n'\n"
    )
    helper.chmod(0o755)

    audio_path = tmp_path / "sample.wav"
    audio_path.write_bytes(b"fake-audio")

    monkeypatch.setattr("marginalia.transcribe._ensure_binary", lambda: helper)

    heartbeats = 0
    def on_heartbeat() -> None:
        nonlocal heartbeats
        heartbeats += 1

    transcript = transcribe_local(audio_path, on_heartbeat=on_heartbeat)

    assert transcript == "hello from helper"
    assert heartbeats == 2
