from pathlib import Path
from unittest.mock import patch

from marginalia.models import Mode, ModeState, PipelineConfig, RunState, VideoState, VideoStatus
from marginalia.pipeline import run, run_plan, run_retry
from marginalia.state import load_state, save_state


def _make_course(tmp_path: Path, count: int = 3) -> Path:
    course = tmp_path / "course"
    course.mkdir()
    for i in range(count):
        (course / f"lesson{i + 1}.mp4").write_bytes(b"\x00" * (100 + i))
    return course


# --- Transcript mode tests ---

@patch("marginalia.pipeline.transcribe_local")
@patch("marginalia.pipeline.extract_audio")
@patch("marginalia.pipeline.probe_duration")
def test_transcript_mode_flat(mock_probe, mock_extract, mock_transcribe, tmp_path: Path):
    course = _make_course(tmp_path, 3)
    output = tmp_path / "output"

    mock_probe.return_value = 120.0

    def fake_extract(video_path, output_dir):
        audio = output_dir / "audio.wav"
        audio.write_bytes(b"\x00" * 50)
        return audio

    mock_extract.side_effect = fake_extract
    mock_transcribe.return_value = "This is the transcript text for the lesson."

    config = PipelineConfig(input_dir=course, output_dir=output, mode=Mode.TRANSCRIPT)
    result = run(config)

    assert result.processed == 3
    assert result.skipped == 0
    assert result.failed == 0
    assert result.total_cost_usd == 0.0
    assert (output / "lesson1.md").exists()
    assert (output / "lesson2.md").exists()
    assert (output / "lesson3.md").exists()
    # Check output contains transcript content
    content = (output / "lesson1.md").read_text()
    assert 'mode: "transcript"' in content
    assert 'engine: "apple-speech"' in content
    assert "This is the transcript text" in content


@patch("marginalia.pipeline.transcribe_local")
@patch("marginalia.pipeline.extract_audio")
@patch("marginalia.pipeline.probe_duration")
def test_transcript_incremental_skip(mock_probe, mock_extract, mock_transcribe, tmp_path: Path):
    """Second run in same mode skips already-processed videos."""
    course = _make_course(tmp_path, 2)
    output = tmp_path / "output"

    mock_probe.return_value = 60.0

    def fake_extract(video_path, output_dir):
        audio = output_dir / "audio.wav"
        audio.write_bytes(b"\x00" * 30)
        return audio

    mock_extract.side_effect = fake_extract
    mock_transcribe.return_value = "Transcript content."

    config = PipelineConfig(input_dir=course, output_dir=output, mode=Mode.TRANSCRIPT)

    # First run
    result1 = run(config)
    assert result1.processed == 2

    # Second run — should skip
    mock_transcribe.reset_mock()
    result2 = run(config)
    assert result2.skipped == 2
    assert result2.processed == 0
    mock_transcribe.assert_not_called()


@patch("marginalia.pipeline.transcribe_local")
@patch("marginalia.pipeline.extract_audio")
@patch("marginalia.pipeline.probe_duration")
def test_transcript_then_brief_skips_transcription(mock_probe, mock_extract, mock_transcribe, tmp_path: Path):
    """Brief mode reuses cached transcripts from prior transcript run."""
    course = _make_course(tmp_path, 2)
    output = tmp_path / "output"

    mock_probe.return_value = 60.0

    def fake_extract(video_path, output_dir):
        audio = output_dir / "audio.wav"
        audio.write_bytes(b"\x00" * 30)
        return audio

    mock_extract.side_effect = fake_extract
    mock_transcribe.return_value = "Some transcript."

    # First: transcript mode
    config_t = PipelineConfig(input_dir=course, output_dir=output, mode=Mode.TRANSCRIPT)
    run(config_t)

    # Second: brief mode — should NOT call transcribe_local again (uses cache)
    mock_transcribe.reset_mock()
    mock_extract.reset_mock()

    with patch("marginalia.pipeline.summarize_transcript") as mock_summarize:
        mock_summarize.return_value = (
            "## Core Idea\nStuff\n\n## Frameworks & Mental Models\n- F\n\n## Key Examples\n- E\n\n## Actionable Takeaways\n1. A\n\n## Marginalia\n- Q",
            100, 50, 0.001,
        )
        config_b = PipelineConfig(input_dir=course, output_dir=output, mode=Mode.BRIEF)
        result = run(config_b)

        assert result.processed == 2
        # transcribe_local should NOT be called — transcripts are cached
        mock_transcribe.assert_not_called()
        mock_extract.assert_not_called()
        # But summarize_transcript should be called for each video
        assert mock_summarize.call_count == 2


# --- Failure isolation ---

@patch("marginalia.pipeline.transcribe_local")
@patch("marginalia.pipeline.extract_audio")
@patch("marginalia.pipeline.probe_duration")
def test_failure_isolation(mock_probe, mock_extract, mock_transcribe, tmp_path: Path):
    course = _make_course(tmp_path, 3)
    output = tmp_path / "output"

    mock_probe.return_value = 60.0

    call_count = 0

    def fake_extract(video_path, output_dir):
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            raise RuntimeError("ffmpeg exploded")
        audio = output_dir / "audio.wav"
        audio.write_bytes(b"\x00" * 30)
        return audio

    mock_extract.side_effect = fake_extract
    mock_transcribe.return_value = "Transcript."

    config = PipelineConfig(input_dir=course, output_dir=output, mode=Mode.TRANSCRIPT)
    result = run(config)

    assert result.processed == 2
    assert result.failed == 1

    # State should record the failure
    state = load_state(output)
    failed_entries = [
        (rel, e) for rel, e in state.videos.items()
        if e.transcript and e.transcript.status == VideoStatus.FAILED
    ]
    assert len(failed_entries) == 1


# --- Plan mode ---

@patch("marginalia.pipeline.probe_duration")
def test_plan_mode(mock_probe, tmp_path: Path):
    course = _make_course(tmp_path, 3)
    output = tmp_path / "output"

    mock_probe.return_value = 60.0

    config = PipelineConfig(input_dir=course, output_dir=output, mode=Mode.TRANSCRIPT)
    result = run_plan(config)

    assert result.processed == 0
    # Plan should not create output directory
    assert not output.exists()


# --- Empty folder ---

def test_empty_folder(tmp_path: Path):
    course = tmp_path / "empty"
    course.mkdir()
    output = tmp_path / "output"

    config = PipelineConfig(input_dir=course, output_dir=output)
    result = run(config)

    assert result.processed == 0
    assert result.skipped == 0
    assert result.failed == 0


# --- Retry ---

@patch("marginalia.pipeline.transcribe_local")
@patch("marginalia.pipeline.extract_audio")
@patch("marginalia.pipeline.probe_duration")
def test_retry_failed(mock_probe, mock_extract, mock_transcribe, tmp_path: Path):
    course = _make_course(tmp_path, 2)
    output = tmp_path / "output"
    output.mkdir()

    # Manually create state with one failure
    (course / "lesson1.mp4").write_bytes(b"\x00" * 100)
    stat = (course / "lesson1.mp4").stat()

    state = RunState(
        videos={
            "lesson1.mp4": VideoState(
                fingerprint=f"{stat.st_size}:{stat.st_mtime}",
                duration_seconds=60.0,
                transcript=ModeState(status=VideoStatus.FAILED, error="boom"),
            ),
            "lesson2.mp4": VideoState(
                fingerprint="101:0.0",
                duration_seconds=60.0,
                transcript=ModeState(status=VideoStatus.COMPLETED),
            ),
        }
    )
    save_state(output, state)

    mock_probe.return_value = 60.0

    def fake_extract(video_path, output_dir):
        audio = output_dir / "audio.wav"
        audio.write_bytes(b"\x00" * 30)
        return audio

    mock_extract.side_effect = fake_extract
    mock_transcribe.return_value = "Fixed transcript."

    config = PipelineConfig(input_dir=course, output_dir=output, mode=Mode.TRANSCRIPT)
    result = run_retry(config, Mode.TRANSCRIPT)

    assert result.processed == 1
    assert result.failed == 0
