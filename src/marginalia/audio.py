from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def probe_duration(video_path: Path) -> float | None:
    """Return duration in seconds via ffprobe, or None if unavailable."""
    try:
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
        duration = info.get("format", {}).get("duration")
        if duration is None:
            print(f"  Warning: No duration in format data for {video_path.name}", file=sys.stderr)
            return None
        return float(duration)
    except (subprocess.CalledProcessError, json.JSONDecodeError, ValueError) as e:
        print(f"  Warning: Could not probe duration for {video_path.name}: {e}", file=sys.stderr)
        return None


def has_audio_stream(video_path: Path) -> bool:
    """Check if the video file contains at least one audio stream."""
    try:
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
    except (subprocess.CalledProcessError, json.JSONDecodeError):
        return False


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
