from __future__ import annotations

import sys

# ANSI color codes
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
BOLD = "\033[1m"
RESET = "\033[0m"


def stage(index: int, total: int, stage_name: str, video_relative: str) -> None:
    print(f"  [{index}/{total}] {stage_name}... {video_relative}", file=sys.stderr)


def skip(video_relative: str, mode: str) -> None:
    print(f"  {YELLOW}- skipped: {video_relative} (already in {mode} mode){RESET}", file=sys.stderr)


def success(video_relative: str, detail: str = "") -> None:
    suffix = f" ({detail})" if detail else ""
    print(f"  {GREEN}+ done: {video_relative}{suffix}{RESET}", file=sys.stderr)


def failure(video_relative: str, reason: str) -> None:
    print(f"  {RED}x failed: {video_relative} -- {reason}{RESET}", file=sys.stderr)


def header(message: str) -> None:
    print(f"\n{BOLD}{message}{RESET}", file=sys.stderr)


def info(message: str) -> None:
    print(f"  {message}", file=sys.stderr)


def summary(processed: int, skipped: int, failed: int, wall_clock: str, cost_usd: float = 0.0) -> None:
    parts = []
    if processed:
        parts.append(f"{GREEN}Processed: {processed}{RESET}")
    if skipped:
        parts.append(f"{YELLOW}Skipped: {skipped}{RESET}")
    if failed:
        parts.append(f"{RED}Failed: {failed}{RESET}")
    line = ", ".join(parts) if parts else "Nothing to do"
    cost_str = f" -- cost: ${cost_usd:.2f}" if cost_usd > 0 else " -- cost: $0.00"
    print(f"\n{BOLD}Done.{RESET} {line} in {wall_clock}{cost_str}", file=sys.stderr)
    if failed:
        print(f"  Run 'marginalia retry' to reprocess failed videos.", file=sys.stderr)
