import pytest

from marginalia.console import (
    ProgressTracker,
    _EXTRACT_FRACTION,
    _MIN_HEARTBEAT_SECONDS,
    _TRANSCRIBE_CAP,
)


def test_progress_tracker_uses_duration_aware_heartbeat(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("NO_COLOR", "1")

    tracker = ProgressTracker(total=1)
    tracker.mark_extracted("lesson.mp4")
    tracker.begin_transcription("lesson.mp4", 120.0)
    tracker.heartbeat("lesson.mp4")

    expected_step = (_TRANSCRIBE_CAP - _EXTRACT_FRACTION) / 120.0
    assert tracker._video_progress["lesson.mp4"] == pytest.approx(_EXTRACT_FRACTION + expected_step)


def test_progress_tracker_uses_minimum_duration_floor(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("NO_COLOR", "1")

    tracker = ProgressTracker(total=1)
    tracker.mark_extracted("short.mp4")
    tracker.begin_transcription("short.mp4", 5.0)
    tracker.heartbeat("short.mp4")

    expected_step = (_TRANSCRIBE_CAP - _EXTRACT_FRACTION) / _MIN_HEARTBEAT_SECONDS
    assert tracker._video_progress["short.mp4"] == pytest.approx(_EXTRACT_FRACTION + expected_step)

