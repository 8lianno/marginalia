from unittest.mock import MagicMock, patch

from marginalia.sources import discover_youtube, is_youtube_url


def test_is_youtube_url_recognizes_common_forms():
    assert is_youtube_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    assert is_youtube_url("https://youtube.com/watch?v=dQw4w9WgXcQ")
    assert is_youtube_url("https://youtu.be/dQw4w9WgXcQ")
    assert is_youtube_url("https://www.youtube.com/playlist?list=PLabc")
    assert is_youtube_url("https://m.youtube.com/watch?v=abc")
    assert is_youtube_url("https://music.youtube.com/playlist?list=X")
    assert is_youtube_url("http://youtube.com/watch?v=abc")


def test_is_youtube_url_rejects_non_urls():
    assert not is_youtube_url("/local/path/to/course")
    assert not is_youtube_url("course")
    assert not is_youtube_url("https://example.com/video")
    assert not is_youtube_url("")
    assert not is_youtube_url("youtube.com/watch?v=abc")  # no scheme


def test_is_youtube_url_rejects_non_strings():
    assert not is_youtube_url(None)  # type: ignore[arg-type]
    assert not is_youtube_url(123)  # type: ignore[arg-type]


def _make_ydl_mock(info: dict) -> MagicMock:
    ydl = MagicMock()
    ydl.__enter__.return_value = ydl
    ydl.__exit__.return_value = False
    ydl.extract_info.return_value = info
    return ydl


@patch("yt_dlp.YoutubeDL")
def test_discover_youtube_playlist(mock_ydl_cls):
    mock_ydl_cls.return_value = _make_ydl_mock(
        {
            "_type": "playlist",
            "title": "My Course",
            "entries": [
                {"id": "vid1", "title": "Lesson 1: Intro", "duration": 600, "channel": "Prof X"},
                {"id": "vid2", "title": "Lesson 2: Middle", "duration": 900, "channel": "Prof X"},
                {"id": "vid3", "title": "Lesson 3: End", "duration": 1200, "channel": "Prof X"},
            ],
        }
    )

    videos, slug = discover_youtube("https://www.youtube.com/playlist?list=FAKE")

    assert slug == "My-Course"
    assert len(videos) == 3
    assert videos[0].youtube_id == "vid1"
    assert videos[0].title == "Lesson 1: Intro"
    assert videos[0].duration_seconds == 600
    assert videos[0].channel == "Prof X"
    assert videos[0].playlist_index == 1
    assert videos[0].youtube_url == "https://www.youtube.com/watch?v=vid1"
    assert videos[0].fingerprint == "yt:vid1"
    # Output file should be zero-padded and slugged
    assert videos[0].md_relative == "01-Lesson-1-Intro.md"
    assert videos[1].md_relative == "02-Lesson-2-Middle.md"
    assert videos[2].md_relative == "03-Lesson-3-End.md"


@patch("yt_dlp.YoutubeDL")
def test_discover_youtube_single_video(mock_ydl_cls):
    mock_ydl_cls.return_value = _make_ydl_mock(
        {
            "id": "abc123",
            "title": "Single Video",
            "duration": 500,
            "uploader": "Someone",
            "webpage_url": "https://www.youtube.com/watch?v=abc123",
        }
    )

    videos, slug = discover_youtube("https://www.youtube.com/watch?v=abc123")

    assert len(videos) == 1
    assert slug == "Single-Video"
    assert videos[0].youtube_id == "abc123"
    assert videos[0].title == "Single Video"
    assert videos[0].channel == "Someone"


@patch("yt_dlp.YoutubeDL")
def test_discover_youtube_drops_null_entries(mock_ydl_cls):
    mock_ydl_cls.return_value = _make_ydl_mock(
        {
            "_type": "playlist",
            "title": "Mixed",
            "entries": [
                {"id": "good1", "title": "Good One", "duration": 100},
                None,  # yt-dlp sometimes returns None for deleted/private videos
                {"id": "good2", "title": "Good Two", "duration": 200},
            ],
        }
    )

    videos, _ = discover_youtube("https://www.youtube.com/playlist?list=X")
    assert len(videos) == 2
    assert [v.youtube_id for v in videos] == ["good1", "good2"]
