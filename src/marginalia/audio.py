from __future__ import annotations

import json
import subprocess
from pathlib import Path


def probe_duration(video_path: Path) -> float:
    """Return duration in seconds via ffprobe."""
    result = subprocess.run(
        [
            "ffprobe",
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            str(video_path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    info = json.loads(result.stdout)
    return float(info["format"]["duration"])


def has_audio_stream(video_path: Path) -> bool:
    """Check if the video file contains at least one audio stream."""
    result = subprocess.run(
        [
            "ffprobe",
            "-v", "quiet",
            "-select_streams", "a",
            "-show_entries", "stream=index",
            "-print_format", "json",
            str(video_path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    info = json.loads(result.stdout)
    return len(info.get("streams", [])) > 0


def extract_audio(video_path: Path, output_dir: Path) -> Path:
    """Extract audio from video as mono 16kHz WAV for Apple Speech. Returns path to audio file."""
    if not has_audio_stream(video_path):
        raise ValueError(f"No audio track found in {video_path}")

    audio_path = output_dir / f"{video_path.stem}.wav"
    subprocess.run(
        [
            "ffmpeg",
            "-i", str(video_path),
            "-vn",
            "-ac", "1",
            "-ar", "16000",
            "-f", "wav",
            "-y",
            str(audio_path),
        ],
        capture_output=True,
        check=True,
    )
    return audio_path
