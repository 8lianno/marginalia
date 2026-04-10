"""YouTube source handling: URL detection and playlist enumeration.

Uses yt-dlp in metadata-only mode (extract_flat, skip_download) to expand a
playlist URL into a list of VideoFile entries. No media is ever downloaded;
actual transcript text comes from youtube_transcript_api in the pipeline.
"""
from __future__ import annotations

import re
from pathlib import Path

from marginalia.models import VideoFile

_YOUTUBE_HOSTS = ("youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be", "music.youtube.com")

# Synthetic path prefix for remote videos — never opened, just carried so the
# pipeline's existing VideoFile flow keeps working.
_REMOTE_PATH_PREFIX = Path("_yt")


def is_youtube_url(s: str) -> bool:
    """Return True if `s` looks like a YouTube video or playlist URL."""
    if not isinstance(s, str):
        return False
    s = s.strip()
    if not s.startswith(("http://", "https://")):
        return False
    return any(host in s for host in _YOUTUBE_HOSTS)


def _slugify(text: str, max_len: int = 60) -> str:
    """Produce a filesystem-safe slug from a title."""
    if not text:
        return "untitled"
    # Strip characters that are problematic on common filesystems, keep unicode
    # letters/numbers so Persian/Arabic titles survive readably.
    cleaned = re.sub(r"[\x00-\x1f/\\?%*:|\"<>]", "", text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    cleaned = cleaned.replace(" ", "-")
    if len(cleaned) > max_len:
        cleaned = cleaned[:max_len].rstrip("-")
    return cleaned or "untitled"


def _canonical_watch_url(video_id: str) -> str:
    return f"https://www.youtube.com/watch?v={video_id}"


def discover_youtube(url: str) -> tuple[list[VideoFile], str]:
    """Enumerate a YouTube playlist or single-video URL into VideoFile entries.

    Returns (videos, playlist_slug). The playlist_slug is derived from the
    playlist title (or the single video title if it's not a playlist), and is
    used as the default output subdirectory.

    Uses yt-dlp with extract_flat=in_playlist and skip_download=True — no media
    is downloaded; only metadata is read.
    """
    import yt_dlp

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": "in_playlist",
        "skip_download": True,
        "ignoreerrors": True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)

    if info is None:
        raise RuntimeError(f"yt-dlp returned no metadata for {url}")

    entries: list[dict]
    playlist_title: str | None
    if info.get("_type") == "playlist" or "entries" in info:
        entries = [e for e in (info.get("entries") or []) if e]
        playlist_title = info.get("title")
    else:
        # Single video
        entries = [info]
        playlist_title = info.get("title")

    playlist_slug = _slugify(playlist_title or "youtube")

    videos: list[VideoFile] = []
    total = len(entries)
    index_width = max(2, len(str(total)))
    for idx, entry in enumerate(entries, start=1):
        video_id = entry.get("id")
        if not video_id:
            continue
        title = entry.get("title") or video_id
        duration = entry.get("duration")
        channel = entry.get("channel") or entry.get("uploader")
        watch_url = entry.get("webpage_url") or _canonical_watch_url(video_id)

        title_slug = _slugify(title)
        # Zero-padded index so files sort in playlist order.
        output_name = f"{str(idx).zfill(index_width)}-{title_slug}.md"
        # `relative` is the state-key — must be unique and safe. Use the
        # output_name stem so state keys line up with output files.
        relative = f"{str(idx).zfill(index_width)}-{title_slug}"
        synthetic_path = _REMOTE_PATH_PREFIX / f"{video_id}"

        videos.append(
            VideoFile(
                path=synthetic_path,
                relative=relative,
                size=0,
                mtime=0.0,
                duration_seconds=float(duration) if duration is not None else None,
                output_name=output_name,
                youtube_id=video_id,
                youtube_url=watch_url,
                title=title,
                channel=channel,
                playlist_index=idx,
            )
        )

    return videos, playlist_slug
