from marginalia.brief import (
    _clean_filename_to_title,
    _ensure_sections,
    _extract_title,
    build_prompt,
    format_brief,
    format_duration,
    format_transcript,
)
from marginalia.models import BriefMeta, TranscriptMeta


def test_build_prompt_contains_source():
    prompt = build_prompt("Module 1/intro.mp4", "00:05:30")
    assert "Module 1/intro.mp4" in prompt
    assert "00:05:30" in prompt
    assert "Core Idea" in prompt
    assert "Marginalia" in prompt
    assert "Do not invent content" in prompt


def test_build_prompt_uses_transcript_language():
    prompt = build_prompt("file.mp4", "00:01:00")
    assert "transcript" in prompt.lower()
    assert "audio" not in prompt.lower() or "transcript" in prompt.lower()


def test_clean_filename_to_title():
    assert _clean_filename_to_title("02-core-framework.mp4") == "Core Framework"
    assert _clean_filename_to_title("intro.mp4") == "Intro"
    assert _clean_filename_to_title("03_advanced_topics.mov") == "Advanced Topics"


def test_extract_title_from_h1():
    text = "# My Lesson Title\n\n## Core Idea\nSomething"
    assert _extract_title(text, "fallback.mp4") == "My Lesson Title"


def test_extract_title_fallback():
    text = "## Core Idea\nSomething"
    assert _extract_title(text, "02-setup.mp4") == "Setup"


def test_ensure_sections_fills_missing():
    text = "## Core Idea\nGreat stuff\n\n## Key Examples\nExample 1"
    result = _ensure_sections(text)
    assert "## Frameworks & Mental Models" in result
    assert "## Actionable Takeaways" in result
    assert "## Marginalia" in result
    assert "(not mentioned)" in result


def test_ensure_sections_preserves_existing():
    text = "\n".join(
        [
            "## Core Idea", "stuff",
            "## Frameworks & Mental Models", "stuff",
            "## Key Examples", "stuff",
            "## Actionable Takeaways", "stuff",
            "## Marginalia", "stuff",
        ]
    )
    result = _ensure_sections(text)
    assert result.count("(not mentioned)") == 0


def test_format_brief_full():
    raw = "# Lesson Title\n\n## Core Idea\nMain point\n\n## Frameworks & Mental Models\n- Framework A\n\n## Key Examples\n- Example 1\n\n## Actionable Takeaways\n1. Do this\n\n## Marginalia\n- What about X?"
    meta = BriefMeta(
        source="mod1/lesson.mp4",
        fingerprint="100:123.0",
        duration_seconds=300.0,
        processed_at="2026-04-09T00:00:00Z",
        model="gemini-2.0-flash",
        cost_usd=0.001,
    )
    result = format_brief(raw, meta)
    assert result.startswith("---\n")
    assert 'source: "mod1/lesson.mp4"' in result
    assert 'mode: "brief"' in result
    assert 'model: "gemini-2.0-flash"' in result
    assert "cost_usd:" in result
    assert "# Lesson Title" in result
    assert "(not mentioned)" not in result


def test_format_brief_sparse():
    raw = "## Core Idea\nOnly this"
    meta = BriefMeta(
        source="video.mp4",
        fingerprint="50:99.0",
        duration_seconds=60.0,
        processed_at="2026-04-09T00:00:00Z",
        model="gemini-2.0-flash",
        cost_usd=0.0005,
    )
    result = format_brief(raw, meta)
    assert "## Frameworks & Mental Models" in result
    assert "## Marginalia" in result
    assert "(not mentioned)" in result
    assert "# Video" in result


def test_format_transcript():
    meta = TranscriptMeta(
        source="intro.mp4",
        fingerprint="100:123.0",
        duration_seconds=120.0,
        processed_at="2026-04-09T00:00:00Z",
    )
    result = format_transcript("Hello this is the transcript text.", meta)
    assert result.startswith("---\n")
    assert 'mode: "transcript"' in result
    assert 'engine: "apple-speech"' in result
    assert "Hello this is the transcript text." in result
    assert "## Core Idea" not in result  # No brief sections in transcript mode


def test_format_duration():
    assert format_duration(0) == "00:00:00"
    assert format_duration(3661) == "01:01:01"
    assert format_duration(90) == "00:01:30"
