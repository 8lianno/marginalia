from pathlib import Path

from marginalia.models import Mode, ModeState, RunState, VideoFile, VideoState, VideoStatus
from marginalia.state import (
    get_failed_videos,
    has_cached_transcript,
    is_changed,
    load_state,
    needs_processing,
    save_state,
)


def _make_video(tmp_path: Path, name: str = "test.mp4", size: int = 100) -> VideoFile:
    p = tmp_path / name
    p.write_bytes(b"\x00" * size)
    stat = p.stat()
    return VideoFile(path=p, relative=name, size=stat.st_size, mtime=stat.st_mtime)


def test_save_and_load_roundtrip(tmp_path: Path):
    state = RunState(
        videos={
            "test.mp4": VideoState(
                fingerprint="100:123.0",
                transcript=ModeState(status=VideoStatus.COMPLETED, processed_at="2026-04-09T00:00:00Z"),
            )
        }
    )
    save_state(tmp_path, state)
    loaded = load_state(tmp_path)
    assert loaded.videos["test.mp4"].transcript.status == VideoStatus.COMPLETED


def test_load_missing_state(tmp_path: Path):
    state = load_state(tmp_path)
    assert state.videos == {}


def test_load_corrupted_state(tmp_path: Path):
    (tmp_path / ".marginalia-state.json").write_text("not valid json!!!")
    state = load_state(tmp_path)
    assert state.videos == {}
    assert (tmp_path / ".marginalia-state.json.bak").exists()


def test_is_changed_new_video(tmp_path: Path):
    video = _make_video(tmp_path)
    assert is_changed(video, RunState()) is True


def test_is_changed_unchanged(tmp_path: Path):
    video = _make_video(tmp_path)
    state = RunState(videos={"test.mp4": VideoState(fingerprint=video.fingerprint)})
    assert is_changed(video, state) is False


def test_is_changed_modified(tmp_path: Path):
    video = _make_video(tmp_path)
    state = RunState(videos={"test.mp4": VideoState(fingerprint="999:0.0")})
    assert is_changed(video, state) is True


def test_needs_processing_new_video(tmp_path: Path):
    video = _make_video(tmp_path)
    assert needs_processing(video, RunState(), Mode.TRANSCRIPT) is True


def test_needs_processing_transcript_done(tmp_path: Path):
    video = _make_video(tmp_path)
    state = RunState(
        videos={
            "test.mp4": VideoState(
                fingerprint=video.fingerprint,
                transcript=ModeState(status=VideoStatus.COMPLETED),
            )
        }
    )
    assert needs_processing(video, state, Mode.TRANSCRIPT) is False


def test_needs_processing_transcript_done_brief_pending(tmp_path: Path):
    video = _make_video(tmp_path)
    state = RunState(
        videos={
            "test.mp4": VideoState(
                fingerprint=video.fingerprint,
                transcript=ModeState(status=VideoStatus.COMPLETED),
            )
        }
    )
    assert needs_processing(video, state, Mode.BRIEF) is True


def test_needs_processing_both_done(tmp_path: Path):
    video = _make_video(tmp_path)
    state = RunState(
        videos={
            "test.mp4": VideoState(
                fingerprint=video.fingerprint,
                transcript=ModeState(status=VideoStatus.COMPLETED),
                brief=ModeState(status=VideoStatus.COMPLETED),
            )
        }
    )
    assert needs_processing(video, state, Mode.TRANSCRIPT) is False
    assert needs_processing(video, state, Mode.BRIEF) is False


def test_needs_processing_force(tmp_path: Path):
    video = _make_video(tmp_path)
    state = RunState(
        videos={
            "test.mp4": VideoState(
                fingerprint=video.fingerprint,
                transcript=ModeState(status=VideoStatus.COMPLETED),
            )
        }
    )
    assert needs_processing(video, state, Mode.TRANSCRIPT, force=True) is True


def test_needs_processing_fingerprint_changed(tmp_path: Path):
    video = _make_video(tmp_path)
    state = RunState(
        videos={
            "test.mp4": VideoState(
                fingerprint="999:0.0",
                transcript=ModeState(status=VideoStatus.COMPLETED),
            )
        }
    )
    assert needs_processing(video, state, Mode.TRANSCRIPT) is True


def test_fingerprint_change_invalidates_both_modes(tmp_path: Path):
    """When fingerprint changes, both transcript and brief should need reprocessing."""
    video = _make_video(tmp_path)
    state = RunState(
        videos={
            "test.mp4": VideoState(
                fingerprint="999:0.0",
                transcript=ModeState(status=VideoStatus.COMPLETED),
                brief=ModeState(status=VideoStatus.COMPLETED),
            )
        }
    )
    assert needs_processing(video, state, Mode.TRANSCRIPT) is True
    assert needs_processing(video, state, Mode.BRIEF) is True


def test_get_failed_videos(tmp_path: Path):
    (tmp_path / "a.mp4").write_bytes(b"\x00" * 10)
    (tmp_path / "b.mp4").write_bytes(b"\x00" * 20)
    state = RunState(
        videos={
            "a.mp4": VideoState(
                fingerprint="10:0",
                transcript=ModeState(status=VideoStatus.FAILED, error="boom"),
            ),
            "b.mp4": VideoState(
                fingerprint="20:0",
                transcript=ModeState(status=VideoStatus.COMPLETED),
            ),
        }
    )
    failed = get_failed_videos(state, Mode.TRANSCRIPT, tmp_path)
    assert len(failed) == 1
    assert failed[0].relative == "a.mp4"


def test_has_cached_transcript():
    state = RunState(
        videos={
            "a.mp4": VideoState(
                fingerprint="10:0",
                transcript=ModeState(status=VideoStatus.COMPLETED),
            ),
            "b.mp4": VideoState(fingerprint="20:0"),
        }
    )
    assert has_cached_transcript("a.mp4", state) is True
    assert has_cached_transcript("b.mp4", state) is False
    assert has_cached_transcript("c.mp4", state) is False


def test_atomic_write(tmp_path: Path):
    state = RunState(videos={"a.mp4": VideoState(fingerprint="1:1")})
    save_state(tmp_path, state)
    assert (tmp_path / ".marginalia-state.json").exists()
    assert not (tmp_path / ".marginalia-state.json.tmp").exists()
