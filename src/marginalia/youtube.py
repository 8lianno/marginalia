"""YouTube caption fetching and timestamp helpers.

Uses youtube_transcript_api to pull captions directly — no media download,
no whisper transcription. Captions come pre-segmented with start + duration,
so timestamps are free.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Segment:
    """A single timestamped transcript segment.

    Source-agnostic: produced both by YouTube caption fetches and by
    mlx-whisper local transcription, so the notes-mode prompt sees the
    same shape regardless of source.
    """
    start: float
    duration: float
    text: str


def fetch_youtube_transcript(
    video_id: str,
    languages: list[str] | None = None,
) -> list[Segment]:
    """Fetch YouTube's own captions for a video, returning timestamped segments.

    Preference order: manual transcript in `languages` (default ['en']), then
    auto-generated in those languages, then any available transcript in any
    language (so Persian/Arabic courses still work without needing the user
    to configure language codes).

    Raises RuntimeError with a clean message when the video has no captions
    at all or when captions are disabled — per-video isolation in the pipeline
    catches this and marks just that video failed.
    """
    from youtube_transcript_api import (
        NoTranscriptFound,
        TranscriptsDisabled,
        YouTubeTranscriptApi,
    )
    from youtube_transcript_api._errors import CouldNotRetrieveTranscript

    wanted = languages or ["en"]

    try:
        api = YouTubeTranscriptApi()
        transcript_list = api.list(video_id)
    except TranscriptsDisabled:
        raise RuntimeError(f"Captions are disabled for video {video_id}") from None
    except CouldNotRetrieveTranscript as e:
        raise RuntimeError(f"Could not retrieve transcript for {video_id}: {e}") from None

    transcript = None
    # 1. Manually-created in preferred languages
    try:
        transcript = transcript_list.find_manually_created_transcript(wanted)
    except NoTranscriptFound:
        pass

    # 2. Auto-generated in preferred languages
    if transcript is None:
        try:
            transcript = transcript_list.find_generated_transcript(wanted)
        except NoTranscriptFound:
            pass

    # 3. Any available transcript in any language
    if transcript is None:
        available = list(transcript_list)
        if not available:
            raise RuntimeError(f"No transcripts available for video {video_id}")
        transcript = available[0]

    try:
        fetched = transcript.fetch()
    except CouldNotRetrieveTranscript as e:
        raise RuntimeError(f"Could not fetch transcript for {video_id}: {e}") from None

    return [_snippet_to_segment(item) for item in fetched]


def _snippet_to_segment(item) -> Segment:
    """Normalize a youtube-transcript-api snippet (dataclass OR dict) into a Segment."""
    if isinstance(item, dict):
        return Segment(
            start=float(item.get("start", 0.0)),
            duration=float(item.get("duration", 0.0)),
            text=str(item.get("text", "")).strip(),
        )
    # FetchedTranscriptSnippet dataclass (youtube-transcript-api >= 1.0)
    return Segment(
        start=float(getattr(item, "start", 0.0)),
        duration=float(getattr(item, "duration", 0.0)),
        text=str(getattr(item, "text", "")).strip(),
    )


def format_timestamp(seconds: float) -> str:
    """Format seconds as `mm:ss` (or `h:mm:ss` for durations >= 1 hour)."""
    total = int(seconds)
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def format_timestamped_transcript(segments: list[Segment]) -> str:
    """Render segments as plain-text with `[mm:ss]` prefixes, one line per segment.

    This is the string shape fed to Gemini in notes mode so the model has
    timestamps to anchor claims to.
    """
    lines: list[str] = []
    for seg in segments:
        text = " ".join(seg.text.split())  # collapse internal whitespace/newlines
        if not text:
            continue
        lines.append(f"[{format_timestamp(seg.start)}] {text}")
    return "\n".join(lines)


def youtube_timestamp_url(video_id: str, seconds: float) -> str:
    """Return a YouTube watch URL that jumps to the given offset."""
    return f"https://www.youtube.com/watch?v={video_id}&t={int(seconds)}s"
