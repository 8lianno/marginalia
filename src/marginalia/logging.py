from __future__ import annotations

import json
import threading
import traceback
from datetime import datetime, timezone
from pathlib import Path


class RunLogger:
    """Writes structured JSONL log entries for a single run. Thread-safe."""

    def __init__(self, output_dir: Path):
        self._log_dir = output_dir / ".logs"
        self._log_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        self._path = self._log_dir / f"run-{ts}.jsonl"
        self._file = open(self._path, "a")
        self._lock = threading.Lock()

    def _write(self, event: str, **fields: object) -> None:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": event,
            **fields,
        }
        line = json.dumps(entry, default=str) + "\n"
        with self._lock:
            self._file.write(line)
            self._file.flush()

    def run_start(self, mode: str, video_count: int, **extra: object) -> None:
        self._write("run_start", mode=mode, video_count=video_count, **extra)

    def video_stage(self, video: str, stage: str) -> None:
        self._write("video_stage", video=video, stage=stage)

    def video_success(self, video: str, mode: str, cost_usd: float = 0.0) -> None:
        self._write("video_success", video=video, mode=mode, cost_usd=cost_usd)

    def video_failure(self, video: str, mode: str, error: str, exc: BaseException | None = None) -> None:
        tb = None
        if exc is not None:
            tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        self._write("video_failure", video=video, mode=mode, error=error, traceback=tb)

    def run_end(self, processed: int, skipped: int, failed: int, wall_clock: str, cost_usd: float = 0.0) -> None:
        self._write("run_end", processed=processed, skipped=skipped, failed=failed, wall_clock=wall_clock, cost_usd=cost_usd)

    def close(self) -> None:
        self._file.close()

    @property
    def path(self) -> Path:
        return self._path
