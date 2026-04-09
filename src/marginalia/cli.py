from __future__ import annotations

import os
import sys
from pathlib import Path

import typer

from marginalia.models import Mode, PipelineConfig

app = typer.Typer(add_completion=False, help="Margin notes for the videos you watch.")


@app.command()
def extract(
    course: Path = typer.Argument(..., help="Course folder containing video files"),
    output: Path = typer.Option(Path("marginalia"), "--output", "-o", help="Output directory"),
    mode: Mode = typer.Option(Mode.TRANSCRIPT, "--mode", "-m", help="Output mode: transcript or brief"),
    model: str = typer.Option("gemini-2.0-flash", "--model", help="LLM model for brief mode"),
    force: bool = typer.Option(False, "--force", help="Bypass skip logic, reprocess everything"),
    force_path: str | None = typer.Option(None, "--path", help="Restrict --force to a specific video path"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompts"),
    verbose: bool = typer.Option(False, "--verbose", help="Show ffmpeg, Swift helper, and LLM details"),
    no_preflight: bool = typer.Option(False, "--no-preflight", help="Skip API key validation in brief mode"),
    concurrency: int = typer.Option(1, "--concurrency", "-j", help="Number of videos to process in parallel"),
) -> None:
    """Extract transcripts or structured briefs from course videos."""
    if not course.is_dir():
        print(f"Error: Input directory does not exist: {course}", file=sys.stderr)
        raise typer.Exit(1)

    if mode == Mode.BRIEF and not os.environ.get("GEMINI_API_KEY"):
        print("Error: GEMINI_API_KEY environment variable is required for brief mode", file=sys.stderr)
        raise typer.Exit(1)

    if force_path and not force:
        print("Error: --path requires --force", file=sys.stderr)
        raise typer.Exit(1)

    if concurrency < 1:
        print("Error: --concurrency must be at least 1", file=sys.stderr)
        raise typer.Exit(1)

    config = PipelineConfig(
        input_dir=course.resolve(),
        output_dir=output.resolve(),
        mode=mode,
        model=model,
        force=force,
        force_path=force_path,
        yes=yes,
        verbose=verbose,
        no_preflight=no_preflight,
        concurrency=concurrency,
    )

    from marginalia.pipeline import run

    result = run(config)
    raise typer.Exit(1 if result.failed > 0 else 0)


@app.command()
def plan(
    course: Path = typer.Argument(..., help="Course folder containing video files"),
    output: Path = typer.Option(Path("marginalia"), "--output", "-o", help="Output directory"),
    mode: Mode = typer.Option(Mode.TRANSCRIPT, "--mode", "-m", help="Output mode to plan"),
    model: str = typer.Option("gemini-2.0-flash", "--model", help="LLM model for brief mode"),
    force: bool = typer.Option(False, "--force", help="Show what force would reprocess"),
    force_path: str | None = typer.Option(None, "--path", help="Restrict plan to a specific video path"),
) -> None:
    """Preview what would be processed without making changes."""
    if not course.is_dir():
        print(f"Error: Input directory does not exist: {course}", file=sys.stderr)
        raise typer.Exit(1)

    config = PipelineConfig(
        input_dir=course.resolve(),
        output_dir=output.resolve(),
        mode=mode,
        model=model,
        force=force,
        force_path=force_path,
    )

    from marginalia.pipeline import run_plan

    run_plan(config)


@app.command()
def retry(
    course: Path = typer.Argument(..., help="Course folder containing video files"),
    output: Path = typer.Option(Path("marginalia"), "--output", "-o", help="Output directory"),
    mode: Mode = typer.Option(Mode.TRANSCRIPT, "--mode", "-m", help="Mode to retry failures in"),
    model: str = typer.Option("gemini-2.0-flash", "--model", help="LLM model for brief mode"),
    verbose: bool = typer.Option(False, "--verbose", help="Show debug details"),
    no_preflight: bool = typer.Option(False, "--no-preflight", help="Skip API key validation"),
    concurrency: int = typer.Option(1, "--concurrency", "-j", help="Number of videos to process in parallel"),
) -> None:
    """Retry only previously failed videos."""
    if not course.is_dir():
        print(f"Error: Input directory does not exist: {course}", file=sys.stderr)
        raise typer.Exit(1)

    if mode == Mode.BRIEF and not os.environ.get("GEMINI_API_KEY"):
        print("Error: GEMINI_API_KEY environment variable is required for brief mode", file=sys.stderr)
        raise typer.Exit(1)

    config = PipelineConfig(
        input_dir=course.resolve(),
        output_dir=output.resolve(),
        mode=mode,
        model=model,
        verbose=verbose,
        no_preflight=no_preflight,
        concurrency=concurrency,
    )

    from marginalia.pipeline import run_retry

    result = run_retry(config, mode)
    raise typer.Exit(1 if result.failed > 0 else 0)


@app.command()
def status(
    course: Path = typer.Argument(..., help="Course folder containing video files"),
    output: Path = typer.Option(Path("marginalia"), "--output", "-o", help="Output directory"),
) -> None:
    """Show processing status of a course."""
    config = PipelineConfig(
        input_dir=course.resolve(),
        output_dir=output.resolve(),
    )

    from marginalia.pipeline import run_status

    run_status(config)
