from __future__ import annotations

import os
import sys
import threading

# ANSI color codes
_GREEN = "\033[32m"
_YELLOW = "\033[33m"
_RED = "\033[31m"
_BOLD = "\033[1m"
_RESET = "\033[0m"

_verbose = False
_lock = threading.Lock()


def _use_color() -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    return sys.stderr.isatty()


def _c(code: str, text: str) -> str:
    if _use_color():
        return f"{code}{text}{_RESET}"
    return text


def _print(msg: str) -> None:
    """Thread-safe print to stderr."""
    with _lock:
        print(msg, file=sys.stderr)


def set_verbose(enabled: bool) -> None:
    global _verbose
    _verbose = enabled


def verbose(message: str) -> None:
    if _verbose:
        _print(f"  [verbose] {message}")


def stage(index: int, total: int, stage_name: str, video_relative: str) -> None:
    _print(f"  [{index}/{total}] {stage_name}... {video_relative}")


def skip(video_relative: str, mode: str) -> None:
    _print(f"  {_c(_YELLOW, f'- skipped: {video_relative} (already in {mode} mode)')}")


def success(video_relative: str, detail: str = "") -> None:
    suffix = f" ({detail})" if detail else ""
    _print(f"  {_c(_GREEN, f'+ done: {video_relative}{suffix}')}")


def failure(video_relative: str, reason: str) -> None:
    _print(f"  {_c(_RED, f'x failed: {video_relative} -- {reason}')}")


def header(message: str) -> None:
    _print(f"\n{_c(_BOLD, message)}")


def info(message: str) -> None:
    _print(f"  {message}")


def warning(message: str) -> None:
    _print(f"  {_c(_YELLOW, f'Warning: {message}')}")


def summary(processed: int, skipped: int, failed: int, wall_clock: str, cost_usd: float = 0.0) -> None:
    parts = []
    if processed:
        parts.append(_c(_GREEN, f"Processed: {processed}"))
    if skipped:
        parts.append(_c(_YELLOW, f"Skipped: {skipped}"))
    if failed:
        parts.append(_c(_RED, f"Failed: {failed}"))
    line = ", ".join(parts) if parts else "Nothing to do"
    cost_str = f" -- cost: ${cost_usd:.2f}" if cost_usd > 0 else " -- cost: $0.00"
    _print(f"\n{_c(_BOLD, 'Done.')} {line} in {wall_clock}{cost_str}")
    if failed:
        _print(f"  Run 'marginalia retry' to reprocess failed videos.")


def confirm(message: str) -> bool:
    if not sys.stdin.isatty():
        _print(f"  {message} (non-interactive, use --yes to skip)")
        return False
    with _lock:
        response = input(f"  {message} [y/N] ").strip().lower()
    return response in ("y", "yes")
