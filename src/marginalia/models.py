from __future__ import annotations

from enum import Enum
from pathlib import Path

from pydantic import BaseModel


class Mode(str, Enum):
    TRANSCRIPT = "transcript"
    BRIEF = "brief"
    NOTES = "notes"


class VideoFile(BaseModel):
    path: Path
    relative: str
    size: int
    mtime: float
    duration_seconds: float | None = None
    output_name: str | None = None  # Override for collision resolution

    # Remote-source fields (populated when the video is a YouTube item)
    youtube_id: str | None = None
    youtube_url: str | None = None
    title: str | None = None
    channel: str | None = None
    playlist_index: int | None = None

    @property
    def fingerprint(self) -> str:
        if self.youtube_id:
            return f"yt:{self.youtube_id}"
        return f"{self.size}:{self.mtime}"

    @property
    def md_relative(self) -> str:
        """The relative path for the output .md file."""
        if self.output_name:
            return self.output_name
        return str(Path(self.relative).with_suffix(".md"))


class VideoStatus(str, Enum):
    COMPLETED = "completed"
    FAILED = "failed"


class ModeState(BaseModel):
    """Per-mode processing state for a single video."""
    status: VideoStatus
    error: str | None = None
    processed_at: str | None = None
    model: str | None = None
    cost_usd: float | None = None


class VideoState(BaseModel):
    fingerprint: str
    duration_seconds: float | None = None
    transcript: ModeState | None = None
    brief: ModeState | None = None
    notes: ModeState | None = None


class RunState(BaseModel):
    version: int = 3
    videos: dict[str, VideoState] = {}


class TranscriptMeta(BaseModel):
    source: str
    fingerprint: str
    duration_seconds: float
    processed_at: str
    mode: str = "transcript"
    engine: str = "apple-speech"


class BriefMeta(BaseModel):
    source: str
    fingerprint: str
    duration_seconds: float
    processed_at: str
    mode: str = "brief"
    engine: str = "apple-speech"
    model: str
    cost_usd: float


class NotesMeta(BaseModel):
    source: str
    source_url: str | None = None
    fingerprint: str
    duration_seconds: float
    processed_at: str
    mode: str = "notes"
    engine: str  # "youtube-captions" or "mlx-whisper"
    model: str
    cost_usd: float
    title: str | None = None
    channel: str | None = None


class CostEstimate(BaseModel):
    total_duration_seconds: float
    estimated_cost_usd: float


class PipelineConfig(BaseModel):
    input_dir: Path
    output_dir: Path
    mode: Mode = Mode.TRANSCRIPT
    model: str = "gemini-2.0-flash"
    force: bool = False
    force_path: str | None = None
    yes: bool = False
    verbose: bool = False
    no_preflight: bool = False
    concurrency: int = 1
    youtube_url: str | None = None  # Set when source is a YouTube URL instead of a local directory
    youtube_append_slug: bool = False  # If True, pipeline appends the playlist slug to output_dir after discovery
    limit: int | None = None  # Max number of videos to process (applied after sort/discovery). Useful for one-off tests.
