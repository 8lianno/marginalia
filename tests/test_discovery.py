from pathlib import Path

from marginalia.discovery import discover


def test_discover_flat_folder(tmp_path: Path):
    (tmp_path / "lesson1.mp4").write_bytes(b"\x00" * 100)
    (tmp_path / "lesson2.mkv").write_bytes(b"\x00" * 200)
    (tmp_path / "notes.txt").write_bytes(b"hello")
    (tmp_path / "slides.pdf").write_bytes(b"pdf")

    videos = discover(tmp_path)
    assert len(videos) == 2
    names = {v.relative for v in videos}
    assert names == {"lesson1.mp4", "lesson2.mkv"}


def test_discover_nested_folder(tmp_path: Path):
    (tmp_path / "01-intro").mkdir()
    (tmp_path / "01-intro" / "video.mp4").write_bytes(b"\x00" * 50)
    (tmp_path / "02-advanced").mkdir()
    (tmp_path / "02-advanced" / "deep.mov").write_bytes(b"\x00" * 80)

    videos = discover(tmp_path)
    assert len(videos) == 2
    relatives = {v.relative for v in videos}
    assert "01-intro/video.mp4" in relatives
    assert "02-advanced/deep.mov" in relatives


def test_discover_skips_hidden_files(tmp_path: Path):
    (tmp_path / ".hidden.mp4").write_bytes(b"\x00" * 10)
    (tmp_path / ".hidden_dir").mkdir()
    (tmp_path / ".hidden_dir" / "video.mp4").write_bytes(b"\x00" * 10)
    (tmp_path / "visible.mp4").write_bytes(b"\x00" * 10)

    videos = discover(tmp_path)
    assert len(videos) == 1
    assert videos[0].relative == "visible.mp4"


def test_discover_empty_folder(tmp_path: Path):
    assert discover(tmp_path) == []


def test_discover_all_extensions(tmp_path: Path):
    for ext in [".mp4", ".mkv", ".mov", ".webm", ".m4v"]:
        (tmp_path / f"video{ext}").write_bytes(b"\x00" * 10)
    (tmp_path / "audio.mp3").write_bytes(b"\x00" * 10)

    videos = discover(tmp_path)
    assert len(videos) == 5


def test_discover_fingerprint(tmp_path: Path):
    (tmp_path / "v.mp4").write_bytes(b"\x00" * 42)
    videos = discover(tmp_path)
    assert videos[0].size == 42
    assert videos[0].fingerprint.startswith("42:")
