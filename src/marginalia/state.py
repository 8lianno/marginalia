from __future__ import annotations

import json
import os
import sys
import threading
from pathlib import Path

from marginalia.models import Mode, ModeState, RunState, VideoFile, VideoState, VideoStatus

STATE_FILENAME = ".marginalia-state.json"

# Module-level lock: protects state mutations + disk writes together.
# Any code that mutates a RunState AND calls save_state must hold this lock.
_state_lock = threading.Lock()


def state_path(output_dir: Path) -> Path:
    return output_dir / STATE_FILENAME


def load_state(output_dir: Path) -> RunState:
    """Load state from disk. Returns empty state if file doesn't exist or is corrupted."""
    path = state_path(output_dir)
    if not path.exists():
        return RunState()
    try:
        data = json.loads(path.read_text())
        return RunState.model_validate(data)
    except Exception as e:
        backup = path.with_suffix(".json.bak")
        path.rename(backup)
        print(
            f"Warning: State file corrupted ({e}). Backed up to {backup.name}; all videos will be reprocessed.",
            file=sys.stderr,
        )
        return RunState()


def save_state(output_dir: Path, state: RunState) -> None:
    """Atomically write state to disk. Thread-safe."""
    with _state_lock:
        path = state_path(output_dir)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(state.model_dump(mode="json"), indent=2) + "\n")
        os.replace(tmp, path)


def get_mode_state(entry: VideoState, mode: Mode) -> ModeState | None:
    if mode == Mode.TRANSCRIPT:
        return entry.transcript
    return entry.brief


def is_changed(video: VideoFile, state: RunState) -> bool:
    entry = state.videos.get(video.relative)
    if entry is None:
        return True
    return entry.fingerprint != video.fingerprint


def needs_processing(video: VideoFile, state: RunState, mode: Mode, force: bool = False) -> bool:
    if force:
        return True
    entry = state.videos.get(video.relative)
    if entry is None:
        return True
    if entry.fingerprint != video.fingerprint:
        return True
    ms = get_mode_state(entry, mode)
    if ms is None:
        return True
    return ms.status != VideoStatus.COMPLETED


def get_failed_videos(
    state: RunState, mode: Mode, input_dir: Path
) -> list[VideoFile]:
    failed: list[VideoFile] = []
    for rel, entry in state.videos.items():
        ms = get_mode_state(entry, mode)
        if ms is not None and ms.status == VideoStatus.FAILED:
            video_path = input_dir / rel
            if video_path.exists():
                stat = video_path.stat()
                failed.append(
                    VideoFile(
                        path=video_path,
                        relative=rel,
                        size=stat.st_size,
                        mtime=stat.st_mtime,
                        duration_seconds=entry.duration_seconds,
                    )
                )
    return failed


def has_cached_transcript(video_relative: str, state: RunState) -> bool:
    entry = state.videos.get(video_relative)
    if entry is None:
        return False
    return entry.transcript is not None and entry.transcript.status == VideoStatus.COMPLETED
