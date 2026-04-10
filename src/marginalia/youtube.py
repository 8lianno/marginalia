"""YouTube caption fetching and timestamp helpers.

Fetches captions directly — no media download, no whisper transcription.
Two backends:

1. **yt-dlp** (primary) — writes subtitle files via the watch-page flow.
   More robust against YouTube's IP-blocks of caption endpoints.
2. **youtube_transcript_api** (fallback) — uses the timedtext endpoint.
   Faster when it works, but YouTube blocks it aggressively.

Captions come pre-segmented with start + duration, so timestamps are free.
"""
from __future__ import annotations

import re
import tempfile
from dataclasses import dataclass
from pathlib import Path


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

    Tries yt-dlp first (more robust against YouTube IP-blocks), then falls
    back to youtube-transcript-api. Raises RuntimeError with both error
    messages when both backends fail.
    """
    wanted = languages or ["en"]

    ytdlp_error: str | None = None
    try:
        return _fetch_via_ytdlp(video_id, wanted)
    except RuntimeError as e:
        ytdlp_error = str(e)

    try:
        return _fetch_via_transcript_api(video_id, wanted)
    except RuntimeError as e:
        raise RuntimeError(
            f"Both caption backends failed for {video_id}.\n"
            f"  yt-dlp: {ytdlp_error}\n"
            f"  youtube-transcript-api: {e}"
        ) from None


def _fetch_via_transcript_api(video_id: str, wanted: list[str]) -> list[Segment]:
    """Fallback: youtube_transcript_api (timedtext endpoint)."""
    from youtube_transcript_api import (
        NoTranscriptFound,
        TranscriptsDisabled,
        YouTubeTranscriptApi,
    )
    from youtube_transcript_api._errors import CouldNotRetrieveTranscript

    try:
        api = YouTubeTranscriptApi()
        transcript_list = api.list(video_id)
    except TranscriptsDisabled:
        raise RuntimeError(f"Captions are disabled for video {video_id}") from None
    except CouldNotRetrieveTranscript as e:
        raise RuntimeError(f"Could not retrieve transcript for {video_id}: {e}") from None

    transcript = None
    try:
        transcript = transcript_list.find_manually_created_transcript(wanted)
    except NoTranscriptFound:
        pass

    if transcript is None:
        try:
            transcript = transcript_list.find_generated_transcript(wanted)
        except NoTranscriptFound:
            pass

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


def _fetch_via_ytdlp(video_id: str, wanted: list[str]) -> list[Segment]:
    """Primary: yt-dlp writes subtitles via the watch-page flow.

    Downloads no media. Writes a .vtt file to a temp dir, parses it, and
    returns segments. Prefers manual subtitles; falls back to auto-generated
    if the wanted languages are only available as auto-captions.
    """
    import yt_dlp

    url = f"https://www.youtube.com/watch?v={video_id}"
    # Ask for the wanted languages plus common fallbacks. The "live_chat" /
    # other non-caption tracks are ignored by yt-dlp when only writesubtitles
    # / writeautomaticsub are set.
    lang_filter = list(wanted) + [f"{lang}.*" for lang in wanted]

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp = Path(tmp_dir)
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "writesubtitles": True,
            "writeautomaticsub": True,
            "subtitleslangs": lang_filter,
            "subtitlesformat": "vtt",
            "outtmpl": str(tmp / "%(id)s.%(ext)s"),
        }
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
        except yt_dlp.utils.DownloadError as e:
            raise RuntimeError(f"yt-dlp failed to fetch captions for {video_id}: {e}") from None
        except Exception as e:  # yt-dlp raises a variety of exception types
            raise RuntimeError(f"yt-dlp error fetching captions for {video_id}: {e}") from None

        vtt_files = sorted(tmp.glob("*.vtt"))
        if not vtt_files:
            raise RuntimeError(
                f"yt-dlp produced no subtitle file for {video_id} "
                f"(video may have no captions in any of: {lang_filter})"
            )
        # Prefer manual track over auto-generated if both exist.
        # yt-dlp names auto tracks "<id>.<lang>.vtt" and manual "<id>.<lang>.vtt"
        # identically; but auto tracks are requested only when manual isn't
        # available, so taking the first file alphabetically is fine.
        vtt_content = vtt_files[0].read_text(encoding="utf-8")
        segments = _parse_vtt(vtt_content)
        if not segments:
            raise RuntimeError(f"yt-dlp subtitle file for {video_id} parsed to zero segments")
        return segments


_VTT_TIME_RE = re.compile(r"(\d{1,2}):(\d{2}):(\d{2})[.,](\d{3})|(\d{1,2}):(\d{2})[.,](\d{3})")
_VTT_INLINE_TAG_RE = re.compile(r"<[^>]+>")


def _parse_vtt_time(token: str) -> float:
    """Parse a VTT cue time like `00:01:23.456` or `01:23.456` into seconds."""
    token = token.strip().replace(",", ".")
    parts = token.split(":")
    if len(parts) == 3:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
    if len(parts) == 2:
        return int(parts[0]) * 60 + float(parts[1])
    return float(parts[0])


def _parse_vtt(content: str) -> list[Segment]:
    """Parse WebVTT subtitle content into Segment objects with dedup.

    YouTube auto-caption VTT files include rolling duplicate lines (the same
    phrase repeats as it's being built up on screen). This function keeps only
    the final form of each phrase.
    """
    raw_segments: list[Segment] = []
    lines = content.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if "-->" in line:
            # Split at "-->" and take the first token from each side
            left, _, right = line.partition("-->")
            try:
                start = _parse_vtt_time(left)
                # right side may have additional cue settings after the time
                end = _parse_vtt_time(right.strip().split()[0])
            except (ValueError, IndexError):
                i += 1
                continue

            # Collect text lines until blank line or EOF
            i += 1
            text_parts: list[str] = []
            while i < len(lines) and lines[i].strip():
                text = _VTT_INLINE_TAG_RE.sub("", lines[i])
                text = text.strip()
                if text:
                    text_parts.append(text)
                i += 1

            if text_parts:
                text = " ".join(text_parts)
                text = re.sub(r"\s+", " ", text).strip()
                if text:
                    raw_segments.append(
                        Segment(start=start, duration=max(0.0, end - start), text=text)
                    )
        i += 1

    return _dedupe_rolling_captions(raw_segments)


def _dedupe_rolling_captions(segments: list[Segment]) -> list[Segment]:
    """Collapse YouTube's rolling auto-caption duplicates.

    Auto-captions emit overlapping cues where cue N+1's text starts with
    cue N's text (as new words are added to a rolling line). We keep the
    longest form and discard the intermediate copies.
    """
    if not segments:
        return []

    result: list[Segment] = []
    for seg in segments:
        if not result:
            result.append(seg)
            continue
        prev = result[-1]
        if seg.text == prev.text:
            # Pure duplicate — extend the previous duration.
            result[-1] = Segment(
                start=prev.start,
                duration=(seg.start + seg.duration) - prev.start,
                text=prev.text,
            )
            continue
        if seg.text.startswith(prev.text) and len(seg.text) > len(prev.text):
            # Rolling extension of the previous cue.
            result[-1] = Segment(
                start=prev.start,
                duration=(seg.start + seg.duration) - prev.start,
                text=seg.text,
            )
            continue
        if prev.text.endswith(seg.text):
            # New cue is a trailing fragment of the previous — skip.
            continue
        result.append(seg)
    return result


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
