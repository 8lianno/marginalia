from __future__ import annotations

from enum import Enum
from pathlib import Path

from pydantic import BaseModel


class Mode(str, Enum):
    TRANSCRIPT = "transcript"
    BRIEF = "brief"


class VideoFile(BaseModel):
    path: Path
    relative: str
    size: int
    mtime: float
    duration_seconds: float | None = None

    @property
    def fingerprint(self) -> str:
        return f"{self.size}:{self.mtime}"


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


class RunState(BaseModel):
    version: int = 2
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


class CostEstimate(BaseModel):
    total_duration_seconds: float
    estimated_cost_usd: float


class PipelineConfig(BaseModel):
    input_dir: Path
    output_dir: Path
    mode: Mode = Mode.TRANSCRIPT
    model: str = "gemini-2.0-flash"
    force: bool = False
    yes: bool = False
    verbose: bool = False
