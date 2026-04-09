from pathlib import Path

from marginalia.cost import estimate_cost
from marginalia.models import Mode, VideoFile


def test_transcript_mode_always_free():
    videos = [
        VideoFile(path=Path("/a.mp4"), relative="a.mp4", size=100, mtime=0, duration_seconds=3600),
    ]
    est = estimate_cost(videos, Mode.TRANSCRIPT)
    assert est.estimated_cost_usd == 0.0


def test_brief_mode_has_cost():
    videos = [
        VideoFile(path=Path("/a.mp4"), relative="a.mp4", size=100, mtime=0, duration_seconds=3600),
    ]
    est = estimate_cost(videos, Mode.BRIEF)
    assert est.estimated_cost_usd > 0


def test_brief_mode_scales_with_duration():
    one_hour = [
        VideoFile(path=Path("/a.mp4"), relative="a.mp4", size=100, mtime=0, duration_seconds=3600),
    ]
    two_hours = [
        VideoFile(path=Path("/a.mp4"), relative="a.mp4", size=100, mtime=0, duration_seconds=3600),
        VideoFile(path=Path("/b.mp4"), relative="b.mp4", size=100, mtime=0, duration_seconds=3600),
    ]
    est1 = estimate_cost(one_hour, Mode.BRIEF)
    est2 = estimate_cost(two_hours, Mode.BRIEF)
    assert est2.estimated_cost_usd > est1.estimated_cost_usd


def test_no_duration_means_zero_cost():
    videos = [
        VideoFile(path=Path("/a.mp4"), relative="a.mp4", size=100, mtime=0, duration_seconds=None),
    ]
    est = estimate_cost(videos, Mode.BRIEF)
    assert est.estimated_cost_usd >= 0
