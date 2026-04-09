from __future__ import annotations

import re
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from marginalia import console
from marginalia.audio import extract_audio, probe_duration
from marginalia.brief import build_prompt, format_brief, format_duration, format_transcript
from marginalia.cost import estimate_cost
from marginalia.discovery import discover
from marginalia.logging import RunLogger
from marginalia.models import (
    BriefMeta,
    Mode,
    ModeState,
    PipelineConfig,
    RunState,
    TranscriptMeta,
    VideoFile,
    VideoState,
    VideoStatus,
)
from marginalia.state import (
    get_failed_videos,
    has_cached_transcript,
    load_state,
    needs_processing,
    save_state,
)
from marginalia.transcribe import preflight_check, summarize_transcript, transcribe_local


@dataclass
class RunResult:
    processed: int = 0
    skipped: int = 0
    failed: int = 0
    total_cost_usd: float = 0.0
    transcripts_reused: int = 0
    errors: list[tuple[str, str]] = field(default_factory=list)


def run(config: PipelineConfig) -> RunResult:
    """Main entry point for the extract pipeline."""
    start_time = time.monotonic()
    result = RunResult()

    console.set_verbose(config.verbose)

    # 1. Discover videos
    videos = discover(config.input_dir)
    if not videos:
        console.info(f"No videos found in {config.input_dir}")
        return result

    # 2. Load state
    state = load_state(config.output_dir)

    # 3. Filter to videos needing work in current mode
    if config.force and config.force_path:
        # Force only the specified path
        to_process = [v for v in videos if v.relative == config.force_path]
        if not to_process:
            console.info(f"No video found matching path: {config.force_path}")
            return result
    elif config.force:
        to_process = list(videos)
    else:
        to_process = [v for v in videos if needs_processing(v, state, config.mode)]

    skipped_count = len(videos) - len(to_process)
    result.skipped = skipped_count

    for v in videos:
        if v not in to_process:
            console.skip(v.relative, config.mode.value)

    if not to_process:
        elapsed = format_duration(time.monotonic() - start_time)
        console.summary(result.processed, result.skipped, result.failed, elapsed)
        return result

    # Probe durations
    for v in to_process:
        if v.duration_seconds is None:
            v.duration_seconds = probe_duration(v.path)

    total_duration = sum(v.duration_seconds or 0.0 for v in to_process)
    cost_est = estimate_cost(to_process, config.mode)

    # Count cached transcripts for brief mode
    cached_count = 0
    if config.mode == Mode.BRIEF:
        cached_count = sum(1 for v in to_process if has_cached_transcript(v.relative, state))

    engine = "apple-speech"
    console.header(
        f"{len(to_process)} videos . {format_duration(total_duration)} . "
        f"mode: {config.mode.value} . engine: {engine} . "
        f"est. cost: ${cost_est.estimated_cost_usd:.2f}"
    )
    if config.mode == Mode.BRIEF and cached_count:
        console.info(f"Transcripts cached: {cached_count}/{len(to_process)}")

    # Force confirmation for large runs
    if config.force and len(to_process) > 10 and not config.yes:
        if not console.confirm(
            f"Force mode: {len(to_process)} videos will be reprocessed "
            f"(est. ${cost_est.estimated_cost_usd:.2f}). Continue?"
        ):
            console.info("Aborted.")
            return result

    # Preflight check for brief mode
    if config.mode == Mode.BRIEF and not config.no_preflight:
        console.verbose("Running preflight check...")
        try:
            preflight_check(config.model)
            console.verbose("Preflight OK")
        except RuntimeError as e:
            console.failure("preflight", str(e))
            result.failed = len(to_process)
            return result

    # 4. Ensure output dir exists
    config.output_dir.mkdir(parents=True, exist_ok=True)

    # 5. Start structured log
    logger = RunLogger(config.output_dir)
    logger.run_start(
        mode=config.mode.value,
        video_count=len(to_process),
        total_duration=total_duration,
        estimated_cost=cost_est.estimated_cost_usd,
    )

    # 6. Process each video
    total = len(to_process)
    for i, video in enumerate(to_process, 1):
        try:
            cost = _process_single(config, state, video, i, total, logger)
            result.processed += 1
            result.total_cost_usd += cost
        except Exception as e:
            error_msg = f"{type(e).__name__}: {e}"
            console.failure(video.relative, str(e))
            logger.video_failure(video.relative, config.mode.value, error_msg, exc=e)
            _record_failure(config, state, video, error_msg)
            result.failed += 1
            result.errors.append((video.relative, error_msg))

    elapsed = format_duration(time.monotonic() - start_time)
    console.summary(result.processed, result.skipped, result.failed, elapsed, result.total_cost_usd)
    logger.run_end(result.processed, result.skipped, result.failed, elapsed, result.total_cost_usd)
    logger.close()
    return result


def run_retry(config: PipelineConfig, mode: Mode) -> RunResult:
    """Retry only failed videos in the given mode."""
    start_time = time.monotonic()
    result = RunResult()

    console.set_verbose(config.verbose)

    state = load_state(config.output_dir)
    to_retry = get_failed_videos(state, mode, config.input_dir)

    if not to_retry:
        console.info(f"No failed videos to retry in {mode.value} mode")
        return result

    # Re-probe durations for videos that may not have been probed before
    for v in to_retry:
        if v.duration_seconds is None:
            v.duration_seconds = probe_duration(v.path)

    console.header(f"Retrying {len(to_retry)} previously failed videos in {mode.value} mode...")

    # Preflight for brief mode
    if mode == Mode.BRIEF and not config.no_preflight:
        try:
            preflight_check(config.model)
        except RuntimeError as e:
            console.failure("preflight", str(e))
            result.failed = len(to_retry)
            return result

    config.output_dir.mkdir(parents=True, exist_ok=True)
    logger = RunLogger(config.output_dir)
    logger.run_start(mode=mode.value, video_count=len(to_retry), retry=True)

    retry_config = config.model_copy(update={"mode": mode})

    total = len(to_retry)
    for i, video in enumerate(to_retry, 1):
        try:
            cost = _process_single(retry_config, state, video, i, total, logger)
            result.processed += 1
            result.total_cost_usd += cost
        except Exception as e:
            error_msg = f"{type(e).__name__}: {e}"
            console.failure(video.relative, str(e))
            logger.video_failure(video.relative, mode.value, error_msg, exc=e)
            _record_failure(retry_config, state, video, error_msg)
            result.failed += 1
            result.errors.append((video.relative, error_msg))

    elapsed = format_duration(time.monotonic() - start_time)
    console.summary(result.processed, result.skipped, result.failed, elapsed, result.total_cost_usd)
    logger.run_end(result.processed, result.skipped, result.failed, elapsed, result.total_cost_usd)
    logger.close()
    return result


def run_plan(config: PipelineConfig) -> RunResult:
    """Plan mode: show what would be processed without side effects."""
    result = RunResult()

    videos = discover(config.input_dir)
    if not videos:
        console.info(f"No videos found in {config.input_dir}")
        return result

    state = load_state(config.output_dir)

    if config.force and config.force_path:
        to_process = [v for v in videos if v.relative == config.force_path]
    elif config.force:
        to_process = list(videos)
    else:
        to_process = [v for v in videos if needs_processing(v, state, config.mode)]

    # Probe durations
    for v in to_process:
        if v.duration_seconds is None:
            v.duration_seconds = probe_duration(v.path)

    total_duration = sum(v.duration_seconds or 0.0 for v in to_process)
    cost_est = estimate_cost(to_process, config.mode)

    console.header("PLAN -- no changes will be made")
    console.info(f"Mode: {config.mode.value}")
    console.info(f"Videos to process: {len(to_process)} of {len(videos)}")
    console.info(f"Total duration: {format_duration(total_duration)}")
    console.info(f"Estimated cost: ${cost_est.estimated_cost_usd:.2f}")

    if config.mode == Mode.BRIEF:
        cached = sum(1 for v in to_process if has_cached_transcript(v.relative, state))
        console.info(f"Transcripts cached: {cached}/{len(to_process)}")

    console.info("")
    for v in to_process:
        dur = format_duration(v.duration_seconds or 0) if v.duration_seconds else "??:??:??"
        size_mb = v.size / (1024 * 1024)
        cache_tag = ""
        if config.mode == Mode.BRIEF and has_cached_transcript(v.relative, state):
            cache_tag = " [transcript cached]"
        console.info(f"  {v.relative}  ({size_mb:.1f} MB, {dur}){cache_tag}")

    return result


def run_status(config: PipelineConfig) -> None:
    """Show status of a course's processing state."""
    state = load_state(config.output_dir)

    if not state.videos:
        console.info("No Marginalia state for this course")
        return

    total = len(state.videos)
    t_done = t_fail = b_done = b_fail = 0
    total_duration = 0.0
    failures: list[tuple[str, str, str]] = []

    for rel, entry in state.videos.items():
        total_duration += entry.duration_seconds or 0.0
        if entry.transcript:
            if entry.transcript.status == VideoStatus.COMPLETED:
                t_done += 1
            else:
                t_fail += 1
                failures.append((rel, "transcript", entry.transcript.error or "unknown"))
        if entry.brief:
            if entry.brief.status == VideoStatus.COMPLETED:
                b_done += 1
            else:
                b_fail += 1
                failures.append((rel, "brief", entry.brief.error or "unknown"))

    t_pending = total - t_done - t_fail
    b_pending = total - b_done - b_fail

    console.header(f"course: {config.input_dir}")
    console.info(f"videos: {total} . duration: {format_duration(total_duration)}")
    console.info(f"  transcript: {t_done} processed . {t_fail} failed . {t_pending} pending")
    console.info(f"  brief:      {b_done} processed . {b_fail} failed . {b_pending} pending")

    if failures:
        console.info("failed:")
        for rel, mode, error in failures:
            console.info(f"  - {rel} ({mode}) -- {error}")


def _process_single(
    config: PipelineConfig,
    state: RunState,
    video: VideoFile,
    index: int,
    total: int,
    logger: RunLogger,
) -> float:
    """Process a single video. Returns cost_usd for this video."""
    rel = video.relative
    now = datetime.now(timezone.utc).isoformat()
    cost_usd = 0.0

    # Ensure video state entry exists
    if rel not in state.videos:
        state.videos[rel] = VideoState(fingerprint=video.fingerprint)
    entry = state.videos[rel]

    # Update fingerprint if changed (invalidates both modes)
    if entry.fingerprint != video.fingerprint:
        entry.fingerprint = video.fingerprint
        entry.transcript = None
        entry.brief = None

    # Probe duration if needed
    if video.duration_seconds is None:
        console.stage(index, total, "Probing", rel)
        logger.video_stage(rel, "probing")
        video.duration_seconds = probe_duration(video.path)
    entry.duration_seconds = video.duration_seconds

    if config.mode == Mode.TRANSCRIPT:
        cost_usd = _do_transcript(config, state, entry, video, index, total, now, logger)
    else:
        cost_usd = _do_brief(config, state, entry, video, index, total, now, logger)

    return cost_usd


def _do_transcript(
    config: PipelineConfig,
    state: RunState,
    entry: VideoState,
    video: VideoFile,
    index: int,
    total: int,
    now: str,
    logger: RunLogger,
) -> float:
    """Run transcript mode for a single video."""
    rel = video.relative

    console.stage(index, total, "Extracting audio", rel)
    logger.video_stage(rel, "extracting_audio")
    with tempfile.TemporaryDirectory() as tmp_dir:
        audio_path = extract_audio(video.path, Path(tmp_dir))

        console.stage(index, total, "Transcribing", rel)
        logger.video_stage(rel, "transcribing")
        transcript_text = transcribe_local(audio_path)

    meta = TranscriptMeta(
        source=rel,
        fingerprint=video.fingerprint,
        duration_seconds=video.duration_seconds or 0.0,
        processed_at=now,
    )
    markdown = format_transcript(transcript_text, meta)

    output_path = config.output_dir / video.md_relative
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(markdown)

    entry.transcript = ModeState(status=VideoStatus.COMPLETED, processed_at=now)
    save_state(config.output_dir, state)
    console.success(rel)
    logger.video_success(rel, "transcript")
    return 0.0


def _do_brief(
    config: PipelineConfig,
    state: RunState,
    entry: VideoState,
    video: VideoFile,
    index: int,
    total: int,
    now: str,
    logger: RunLogger,
) -> float:
    """Run brief mode for a single video. Transcribes first if needed."""
    rel = video.relative
    detail_parts = []

    # Step 1: Get transcript (from cache or fresh)
    if entry.transcript and entry.transcript.status == VideoStatus.COMPLETED:
        transcript_path = config.output_dir / video.md_relative
        if transcript_path.exists():
            transcript_text = _extract_transcript_body(transcript_path.read_text())
            detail_parts.append("cached")
        else:
            transcript_text = _fresh_transcribe(config, state, entry, video, index, total, now, logger)
            detail_parts.append("transcribed")
    else:
        transcript_text = _fresh_transcribe(config, state, entry, video, index, total, now, logger)
        detail_parts.append("transcribed")

    if not transcript_text.strip():
        raise RuntimeError("Transcript is empty — cannot generate brief")

    # Step 2: Call LLM to produce brief
    console.stage(index, total, "Generating brief", rel)
    logger.video_stage(rel, "generating_brief")
    duration_str = format_duration(video.duration_seconds or 0.0)
    prompt = build_prompt(rel, duration_str)

    raw_text, input_tokens, output_tokens, cost_usd = summarize_transcript(
        transcript_text, prompt, config.model
    )
    cost_usd = cost_usd or 0.0
    detail_parts.append("summarized")

    console.verbose(f"LLM tokens: input={input_tokens}, output={output_tokens}, cost=${cost_usd:.4f}")

    meta = BriefMeta(
        source=rel,
        fingerprint=video.fingerprint,
        duration_seconds=video.duration_seconds or 0.0,
        processed_at=now,
        model=config.model,
        cost_usd=cost_usd,
    )
    markdown = format_brief(raw_text, meta)

    output_path = config.output_dir / video.md_relative
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(markdown)

    entry.brief = ModeState(
        status=VideoStatus.COMPLETED,
        processed_at=now,
        model=config.model,
        cost_usd=cost_usd,
    )
    save_state(config.output_dir, state)
    console.success(rel, ", ".join(detail_parts))
    logger.video_success(rel, "brief", cost_usd)
    return cost_usd


def _fresh_transcribe(
    config: PipelineConfig,
    state: RunState,
    entry: VideoState,
    video: VideoFile,
    index: int,
    total: int,
    now: str,
    logger: RunLogger,
) -> str:
    """Extract audio and transcribe locally, updating the live state object."""
    console.stage(index, total, "Extracting audio", video.relative)
    logger.video_stage(video.relative, "extracting_audio")
    with tempfile.TemporaryDirectory() as tmp_dir:
        audio_path = extract_audio(video.path, Path(tmp_dir))
        console.stage(index, total, "Transcribing", video.relative)
        logger.video_stage(video.relative, "transcribing")
        transcript_text = transcribe_local(audio_path)

    # Save transcript output so it can be reused later
    transcript_meta = TranscriptMeta(
        source=video.relative,
        fingerprint=video.fingerprint,
        duration_seconds=video.duration_seconds or 0.0,
        processed_at=now,
    )
    transcript_md = format_transcript(transcript_text, transcript_meta)
    transcript_path = config.output_dir / video.md_relative
    transcript_path.parent.mkdir(parents=True, exist_ok=True)
    transcript_path.write_text(transcript_md)

    # US-013 fix: update the LIVE state object, not a stale reload from disk
    entry.transcript = ModeState(status=VideoStatus.COMPLETED, processed_at=now)
    save_state(config.output_dir, state)
    return transcript_text


def _extract_transcript_body(markdown: str) -> str:
    """Extract the body text from a transcript markdown file (strip frontmatter and title)."""
    if markdown.startswith("---"):
        end = markdown.find("---", 3)
        if end != -1:
            markdown = markdown[end + 3:].strip()
    markdown = re.sub(r"^#\s+.+\n*", "", markdown, count=1).strip()
    return markdown


def _record_failure(config: PipelineConfig, state: RunState, video: VideoFile, error_msg: str) -> None:
    """Record a failure in the state file."""
    now = datetime.now(timezone.utc).isoformat()
    rel = video.relative

    if rel not in state.videos:
        state.videos[rel] = VideoState(fingerprint=video.fingerprint)
    entry = state.videos[rel]
    entry.duration_seconds = video.duration_seconds

    mode_state = ModeState(
        status=VideoStatus.FAILED,
        error=error_msg,
        processed_at=now,
    )
    if config.mode == Mode.TRANSCRIPT:
        entry.transcript = mode_state
    else:
        entry.brief = mode_state

    save_state(config.output_dir, state)
