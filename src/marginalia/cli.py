from __future__ import annotations

import os
import sys
from pathlib import Path

import typer

from marginalia.models import Mode, PipelineConfig
from marginalia.sources import is_youtube_url

app = typer.Typer(add_completion=False, help="Margin notes for the videos you watch.")


def _resolve_output(course: Path, output: Path | None) -> Path:
    """Default output to <course>/marginalia/ when not specified."""
    if output is not None:
        return output.resolve()
    return (course / "marginalia").resolve()


def _resolve_youtube_output(url: str, output: Path | None) -> Path:
    """Default output for a YouTube source.

    When the user passes `-o`, honor it. Otherwise default to
    `./marginalia/<playlist-slug>/` — the slug is computed later from
    playlist metadata inside `discover_youtube`; here we use a stable
    placeholder the pipeline overrides once metadata is fetched.
    """
    if output is not None:
        return output.resolve()
    return (Path.cwd() / "marginalia").resolve()


def _build_youtube_config(
    url: str,
    output: Path | None,
    mode: Mode,
    model: str,
    force: bool,
    force_path: str | None,
    yes: bool,
    verbose: bool,
    no_preflight: bool,
    concurrency: int,
) -> PipelineConfig:
    append_slug = output is None
    return PipelineConfig(
        # `input_dir` is required by the model but unused for YouTube runs.
        # Use a recognisable synthetic path so any stray filesystem access
        # fails loudly instead of silently touching random directories.
        input_dir=Path("_marginalia_youtube_source_"),
        output_dir=_resolve_youtube_output(url, output),
        mode=mode,
        model=model,
        force=force,
        force_path=force_path,
        yes=yes,
        verbose=verbose,
        no_preflight=no_preflight,
        concurrency=concurrency,
        youtube_url=url,
        youtube_append_slug=append_slug,
    )


@app.command()
def extract(
    course: str = typer.Argument(..., help="Course folder OR YouTube playlist/video URL"),
    output: Path = typer.Option(None, "--output", "-o", help="Output directory (default: <course>/marginalia/ or ./marginalia/<playlist>/)"),
    mode: Mode = typer.Option(Mode.TRANSCRIPT, "--mode", "-m", help="Output mode: transcript, brief, or notes"),
    model: str = typer.Option("gemini-2.0-flash", "--model", help="LLM model for brief/notes mode"),
    force: bool = typer.Option(False, "--force", help="Bypass skip logic, reprocess everything"),
    force_path: str | None = typer.Option(None, "--path", help="Restrict --force to a specific video path"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompts"),
    verbose: bool = typer.Option(False, "--verbose", help="Show ffmpeg, whisper, and LLM details"),
    no_preflight: bool = typer.Option(False, "--no-preflight", help="Skip API key validation in brief/notes mode"),
    concurrency: int = typer.Option(1, "--concurrency", "-j", help="Number of videos to process in parallel"),
) -> None:
    """Extract transcripts, briefs, or detailed timestamped notes from course videos."""
    if mode in (Mode.BRIEF, Mode.NOTES) and not os.environ.get("GEMINI_API_KEY"):
        print(f"Error: GEMINI_API_KEY environment variable is required for {mode.value} mode", file=sys.stderr)
        raise typer.Exit(1)

    if force_path and not force:
        print("Error: --path requires --force", file=sys.stderr)
        raise typer.Exit(1)

    if concurrency < 1:
        print("Error: --concurrency must be at least 1", file=sys.stderr)
        raise typer.Exit(1)

    if is_youtube_url(course):
        config = _build_youtube_config(
            course, output, mode, model, force, force_path, yes, verbose, no_preflight, concurrency
        )
    else:
        course_path = Path(course)
        if not course_path.is_dir():
            print(f"Error: Input directory does not exist: {course_path}", file=sys.stderr)
            raise typer.Exit(1)
        config = PipelineConfig(
            input_dir=course_path.resolve(),
            output_dir=_resolve_output(course_path, output),
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
    course: str = typer.Argument(..., help="Course folder OR YouTube playlist/video URL"),
    output: Path = typer.Option(None, "--output", "-o", help="Output directory (default: <course>/marginalia/ or ./marginalia/<playlist>/)"),
    mode: Mode = typer.Option(Mode.TRANSCRIPT, "--mode", "-m", help="Output mode to plan"),
    model: str = typer.Option("gemini-2.0-flash", "--model", help="LLM model for brief/notes mode"),
    force: bool = typer.Option(False, "--force", help="Show what force would reprocess"),
    force_path: str | None = typer.Option(None, "--path", help="Restrict plan to a specific video path"),
) -> None:
    """Preview what would be processed without making changes."""
    if is_youtube_url(course):
        config = _build_youtube_config(
            course, output, mode, model, force, force_path,
            yes=False, verbose=False, no_preflight=True, concurrency=1,
        )
    else:
        course_path = Path(course)
        if not course_path.is_dir():
            print(f"Error: Input directory does not exist: {course_path}", file=sys.stderr)
            raise typer.Exit(1)
        config = PipelineConfig(
            input_dir=course_path.resolve(),
            output_dir=_resolve_output(course_path, output),
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
    output: Path = typer.Option(None, "--output", "-o", help="Output directory (default: <course>/marginalia/)"),
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
        output_dir=_resolve_output(course, output),
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
    output: Path = typer.Option(None, "--output", "-o", help="Output directory (default: <course>/marginalia/)"),
) -> None:
    """Show processing status of a course."""
    config = PipelineConfig(
        input_dir=course.resolve(),
        output_dir=_resolve_output(course, output),
    )

    from marginalia.pipeline import run_status

    run_status(config)
