from __future__ import annotations

import os
import sys

# ANSI color codes
_GREEN = "\033[32m"
_YELLOW = "\033[33m"
_RED = "\033[31m"
_BOLD = "\033[1m"
_RESET = "\033[0m"

_verbose = False


def _use_color() -> bool:
    """Check if color output should be used."""
    if os.environ.get("NO_COLOR"):
        return False
    return sys.stderr.isatty()


def _c(code: str, text: str) -> str:
    """Wrap text in ANSI code if color is enabled."""
    if _use_color():
        return f"{code}{text}{_RESET}"
    return text


def set_verbose(enabled: bool) -> None:
    global _verbose
    _verbose = enabled


def verbose(message: str) -> None:
    if _verbose:
        print(f"  [verbose] {message}", file=sys.stderr)


def stage(index: int, total: int, stage_name: str, video_relative: str) -> None:
    print(f"  [{index}/{total}] {stage_name}... {video_relative}", file=sys.stderr)


def skip(video_relative: str, mode: str) -> None:
    print(f"  {_c(_YELLOW, f'- skipped: {video_relative} (already in {mode} mode)')}", file=sys.stderr)


def success(video_relative: str, detail: str = "") -> None:
    suffix = f" ({detail})" if detail else ""
    print(f"  {_c(_GREEN, f'+ done: {video_relative}{suffix}')}", file=sys.stderr)


def failure(video_relative: str, reason: str) -> None:
    print(f"  {_c(_RED, f'x failed: {video_relative} -- {reason}')}", file=sys.stderr)


def header(message: str) -> None:
    print(f"\n{_c(_BOLD, message)}", file=sys.stderr)


def info(message: str) -> None:
    print(f"  {message}", file=sys.stderr)


def warning(message: str) -> None:
    print(f"  {_c(_YELLOW, f'Warning: {message}')}", file=sys.stderr)


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
    print(f"\n{_c(_BOLD, 'Done.')} {line} in {wall_clock}{cost_str}", file=sys.stderr)
    if failed:
        print(f"  Run 'marginalia retry' to reprocess failed videos.", file=sys.stderr)


def confirm(message: str) -> bool:
    """Prompt the user for confirmation. Returns False in non-TTY environments."""
    if not sys.stdin.isatty():
        print(f"  {message} (non-interactive, use --yes to skip)", file=sys.stderr)
        return False
    response = input(f"  {message} [y/N] ").strip().lower()
    return response in ("y", "yes")
