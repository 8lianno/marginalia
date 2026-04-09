import json
from pathlib import Path

from marginalia.logging import RunLogger


def test_logger_creates_jsonl(tmp_path: Path):
    logger = RunLogger(tmp_path)
    logger.run_start(mode="transcript", video_count=5)
    logger.video_stage("lesson1.mp4", "extracting")
    logger.video_success("lesson1.mp4", "transcript")
    logger.video_failure("lesson2.mp4", "transcript", "boom", exc=ValueError("test"))
    logger.run_end(processed=1, skipped=0, failed=1, wall_clock="00:01:00")
    logger.close()

    log_dir = tmp_path / ".logs"
    assert log_dir.exists()
    log_files = list(log_dir.glob("run-*.jsonl"))
    assert len(log_files) == 1

    lines = log_files[0].read_text().strip().split("\n")
    events = [json.loads(line) for line in lines]
    assert len(events) == 5
    assert events[0]["event"] == "run_start"
    assert events[0]["video_count"] == 5
    assert events[1]["event"] == "video_stage"
    assert events[2]["event"] == "video_success"
    assert events[3]["event"] == "video_failure"
    assert events[3]["traceback"] is not None
    assert events[4]["event"] == "run_end"


def test_logger_failure_no_traceback(tmp_path: Path):
    logger = RunLogger(tmp_path)
    logger.video_failure("lesson1.mp4", "transcript", "boom", exc=None)
    logger.close()

    log_files = list((tmp_path / ".logs").glob("run-*.jsonl"))
    entry = json.loads(log_files[0].read_text().strip())
    assert entry["traceback"] is None
