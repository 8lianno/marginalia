from unittest.mock import MagicMock, patch

import pytest

from marginalia.youtube import (
    Segment,
    format_timestamp,
    format_timestamped_transcript,
    youtube_timestamp_url,
)


def test_format_timestamp_under_hour():
    assert format_timestamp(0) == "00:00"
    assert format_timestamp(5) == "00:05"
    assert format_timestamp(65) == "01:05"
    assert format_timestamp(599) == "09:59"
    assert format_timestamp(3599) == "59:59"


def test_format_timestamp_hours():
    assert format_timestamp(3600) == "1:00:00"
    assert format_timestamp(3665) == "1:01:05"
    assert format_timestamp(7325) == "2:02:05"


def test_format_timestamped_transcript_basic():
    segments = [
        Segment(start=0.0, duration=5.0, text="Hello world"),
        Segment(start=12.5, duration=3.0, text="Welcome to the course"),
        Segment(start=65.8, duration=4.0, text="Let's begin"),
    ]
    out = format_timestamped_transcript(segments)
    assert out == (
        "[00:00] Hello world\n"
        "[00:12] Welcome to the course\n"
        "[01:05] Let's begin"
    )


def test_format_timestamped_transcript_collapses_whitespace_and_skips_empty():
    segments = [
        Segment(start=0.0, duration=2.0, text="  multi\n  line\n  text  "),
        Segment(start=5.0, duration=1.0, text=""),
        Segment(start=6.0, duration=1.0, text="next"),
    ]
    out = format_timestamped_transcript(segments)
    assert "[00:00] multi line text" in out
    assert "[00:06] next" in out
    # empty segment was dropped
    assert out.count("\n") == 1


def test_youtube_timestamp_url():
    assert youtube_timestamp_url("abc123", 0) == "https://www.youtube.com/watch?v=abc123&t=0s"
    assert youtube_timestamp_url("abc123", 65.7) == "https://www.youtube.com/watch?v=abc123&t=65s"
    assert youtube_timestamp_url("xyz", 3600) == "https://www.youtube.com/watch?v=xyz&t=3600s"


def _make_snippet(text, start, duration):
    # Mimic youtube_transcript_api FetchedTranscriptSnippet (object with attrs)
    snippet = MagicMock()
    snippet.text = text
    snippet.start = start
    snippet.duration = duration
    return snippet


@patch("youtube_transcript_api.YouTubeTranscriptApi")
def test_fetch_youtube_transcript_prefers_manual(mock_api_cls):
    from marginalia.youtube import fetch_youtube_transcript

    manual_transcript = MagicMock()
    manual_transcript.fetch.return_value = [
        _make_snippet("first", 0.0, 2.0),
        _make_snippet("second", 2.5, 3.0),
    ]

    transcript_list = MagicMock()
    transcript_list.find_manually_created_transcript.return_value = manual_transcript

    mock_api = MagicMock()
    mock_api.list.return_value = transcript_list
    mock_api_cls.return_value = mock_api

    segments = fetch_youtube_transcript("vid1")

    assert len(segments) == 2
    assert segments[0].text == "first"
    assert segments[0].start == 0.0
    assert segments[1].text == "second"
    # Manual was preferred — generated should NOT have been called.
    transcript_list.find_generated_transcript.assert_not_called()


@patch("youtube_transcript_api.YouTubeTranscriptApi")
def test_fetch_youtube_transcript_falls_back_to_generated(mock_api_cls):
    from youtube_transcript_api import NoTranscriptFound

    from marginalia.youtube import fetch_youtube_transcript

    generated_transcript = MagicMock()
    generated_transcript.fetch.return_value = [_make_snippet("auto", 1.0, 2.0)]

    transcript_list = MagicMock()
    transcript_list.find_manually_created_transcript.side_effect = NoTranscriptFound(
        "vid1", ["en"], []
    )
    transcript_list.find_generated_transcript.return_value = generated_transcript

    mock_api = MagicMock()
    mock_api.list.return_value = transcript_list
    mock_api_cls.return_value = mock_api

    segments = fetch_youtube_transcript("vid1")
    assert len(segments) == 1
    assert segments[0].text == "auto"


@patch("youtube_transcript_api.YouTubeTranscriptApi")
def test_fetch_youtube_transcript_raises_when_disabled(mock_api_cls):
    from youtube_transcript_api import TranscriptsDisabled

    from marginalia.youtube import fetch_youtube_transcript

    mock_api = MagicMock()
    mock_api.list.side_effect = TranscriptsDisabled("vid1")
    mock_api_cls.return_value = mock_api

    with pytest.raises(RuntimeError, match="disabled"):
        fetch_youtube_transcript("vid1")
