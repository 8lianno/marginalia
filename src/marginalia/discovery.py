from __future__ import annotations

import os
from pathlib import Path

from marginalia.models import VideoFile

VIDEO_EXTENSIONS = {".mp4", ".mkv", ".mov", ".webm", ".m4v"}


def discover(input_dir: Path) -> list[VideoFile]:
    """Recursively walk input_dir and return VideoFile entries for recognized video files."""
    videos: list[VideoFile] = []
    for root, dirs, files in os.walk(input_dir, followlinks=False):
        # Skip hidden directories
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        dirs.sort()

        for name in sorted(files):
            if name.startswith("."):
                continue
            p = Path(root) / name
            if p.suffix.lower() not in VIDEO_EXTENSIONS:
                continue
            stat = p.stat()
            videos.append(
                VideoFile(
                    path=p,
                    relative=str(p.relative_to(input_dir)),
                    size=stat.st_size,
                    mtime=stat.st_mtime,
                )
            )
    return videos
