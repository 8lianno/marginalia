from __future__ import annotations

import os
import sys
from collections import Counter
from pathlib import Path

from marginalia.models import VideoFile

VIDEO_EXTENSIONS = {".mp4", ".mkv", ".mov", ".webm", ".m4v"}


def discover(input_dir: Path) -> list[VideoFile]:
    """Recursively walk input_dir and return VideoFile entries for recognized video files."""
    videos: list[VideoFile] = []
    for root, dirs, files in os.walk(input_dir, followlinks=False):
        # Skip hidden directories
        dirs[:] = sorted(d for d in dirs if not d.startswith("."))

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

    # Detect output filename collisions and resolve them
    videos = _resolve_collisions(videos)
    return videos


def _resolve_collisions(videos: list[VideoFile]) -> list[VideoFile]:
    """Detect stem collisions in the same folder and set output_name to avoid overwrites."""
    # Group by (parent_dir, stem)
    output_paths: Counter[str] = Counter()
    for v in videos:
        output_path = str(Path(v.relative).with_suffix(".md"))
        output_paths[output_path] += 1

    collisions = {p for p, count in output_paths.items() if count > 1}
    if not collisions:
        return videos

    # Mark colliding videos with full-extension output names
    resolved: list[VideoFile] = []
    for v in videos:
        output_path = str(Path(v.relative).with_suffix(".md"))
        if output_path in collisions:
            # Use "filename.ext.md" instead of "filename.md"
            v.output_name = v.relative + ".md"
            print(
                f"  Warning: Output collision resolved: {v.relative} -> {v.output_name}",
                file=sys.stderr,
            )
        resolved.append(v)
    return resolved
