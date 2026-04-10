from marginalia.brief import (
    _clean_filename_to_title,
    _ensure_sections,
    _extract_title,
    build_notes_prompt,
    build_prompt,
    format_brief,
    format_duration,
    format_notes,
    format_transcript,
    linkify_timestamps,
)
from marginalia.models import BriefMeta, NotesMeta, TranscriptMeta


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
    assert "## Core Idea" not in result


def test_format_duration():
    assert format_duration(0) == "00:00:00"
    assert format_duration(3661) == "01:01:01"
    assert format_duration(90) == "00:01:30"


# --- Notes mode ---


def test_build_notes_prompt_mentions_key_requirements():
    prompt = build_notes_prompt("My Lesson", "00:10:00", "https://youtu.be/abc")
    assert "My Lesson" in prompt
    assert "https://youtu.be/abc" in prompt
    assert "00:10:00" in prompt
    # Must demand comprehensive coverage with timestamps
    assert "[mm:ss]" in prompt
    assert "comprehensive" in prompt.lower() or "handout" in prompt.lower()
    # Must instruct to keep speaker language
    assert "language" in prompt.lower()
    # Must forbid H1 / frontmatter
    assert "H1" in prompt or "h1" in prompt


def test_linkify_timestamps_youtube():
    body = "A claim here [12:34]. Another [05:07] and [1:02:30] cue."
    result = linkify_timestamps(body, "abc123")
    assert "[[12:34]](https://www.youtube.com/watch?v=abc123&t=754s)" in result
    assert "[[05:07]](https://www.youtube.com/watch?v=abc123&t=307s)" in result
    assert "[[1:02:30]](https://www.youtube.com/watch?v=abc123&t=3750s)" in result


def test_linkify_timestamps_local_passthrough():
    body = "A claim here [12:34]. Another [05:07]."
    result = linkify_timestamps(body, None)
    # No links — plain markers preserved
    assert result == body


def test_linkify_timestamps_does_not_mangle_non_timestamps():
    body = "Room [12x34] and list [a,b]."
    result = linkify_timestamps(body, "vid")
    assert result == body


def test_format_notes_full_frontmatter():
    raw = "## Section 1\nClaim [00:15].\n\n## Section 2\nAnother [01:20]."
    meta = NotesMeta(
        source="01-intro",
        source_url="https://www.youtube.com/watch?v=vid1",
        fingerprint="yt:vid1",
        duration_seconds=600.0,
        processed_at="2026-04-10T00:00:00Z",
        engine="youtube-captions",
        model="gemini-2.0-flash",
        cost_usd=0.002,
        title="Intro to Things",
        channel="Prof X",
    )
    result = format_notes(raw, meta)
    assert result.startswith("---\n")
    assert 'source: "01-intro"' in result
    assert 'source_url: "https://www.youtube.com/watch?v=vid1"' in result
    assert 'mode: "notes"' in result
    assert 'engine: "youtube-captions"' in result
    assert 'title: "Intro to Things"' in result
    assert 'channel: "Prof X"' in result
    assert "# Intro to Things" in result
    assert "## Section 1" in result
    # Fixed-sections logic from brief mode must NOT apply to notes
    assert "(not mentioned)" not in result


def test_format_notes_local_no_source_url():
    raw = "## Only section\nContent [00:05]."
    meta = NotesMeta(
        source="lesson1.mp4",
        source_url=None,
        fingerprint="100:123.0",
        duration_seconds=60.0,
        processed_at="2026-04-10T00:00:00Z",
        engine="mlx-whisper",
        model="gemini-2.0-flash",
        cost_usd=0.0001,
    )
    result = format_notes(raw, meta)
    assert 'source_url' not in result  # omitted when None
    assert 'engine: "mlx-whisper"' in result
    assert 'mode: "notes"' in result
