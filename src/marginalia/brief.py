from __future__ import annotations

import re

from marginalia.models import BriefMeta, TranscriptMeta

SECTIONS = [
    "Core Idea",
    "Frameworks & Mental Models",
    "Key Examples",
    "Actionable Takeaways",
    "Marginalia",
]

PLACEHOLDER = "(not mentioned)"


def build_prompt(video_relative: str, duration_formatted: str) -> str:
    return f"""You are a course notes assistant. Read this lecture transcript and produce a structured brief.

Source file: {video_relative}
Duration: {duration_formatted}

Produce EXACTLY these 5 sections using the headers shown. If a section has no relevant content from the transcript, write "(not mentioned)" under that header.

## Core Idea
One paragraph summarizing the central thesis or main teaching point.

## Frameworks & Mental Models
Bullet list of any frameworks, models, taxonomies, or structured thinking tools presented.

## Key Examples
Bullet list of concrete examples, case studies, or anecdotes used to illustrate points.

## Actionable Takeaways
Numbered list of specific things a learner should do, try, or change after this lesson.

## Marginalia
Bullet list of questions left unanswered, topics deferred, or areas worth further exploration.

Rules:
- Be concise. Each section should be 2-8 bullet points or 1-3 short paragraphs max.
- Use the speaker's terminology and language where possible.
- Do not invent content that was not in the transcript.
- Do not include timestamps."""


def _clean_filename_to_title(filename: str) -> str:
    """Convert a filename like '02-core-framework.mp4' into 'Core Framework'."""
    name = re.sub(r"\.\w+$", "", filename)  # strip extension
    name = re.sub(r"^\d+[-_.\s]*", "", name)  # strip leading numbers
    name = re.sub(r"[-_]", " ", name)  # dashes/underscores to spaces
    return name.strip().title() or filename


def _extract_title(raw_text: str, fallback_filename: str) -> str:
    """Extract H1 title from model output, or derive from filename."""
    match = re.search(r"^#\s+(.+)$", raw_text, re.MULTILINE)
    if match:
        return match.group(1).strip()
    return _clean_filename_to_title(fallback_filename)


def _ensure_sections(raw_text: str) -> str:
    """Ensure all 5 required sections exist. Fill missing ones with placeholder."""
    for section in SECTIONS:
        pattern = rf"^##\s+{re.escape(section)}\s*$"
        if not re.search(pattern, raw_text, re.MULTILINE):
            raw_text += f"\n\n## {section}\n{PLACEHOLDER}"
    return raw_text


def _strip_title(text: str) -> str:
    """Remove any H1 title line from model output (we prepend our own)."""
    return re.sub(r"^#\s+.+\n*", "", text, count=1).strip()


def format_transcript(transcript_text: str, meta: TranscriptMeta) -> str:
    """Format a raw transcript into the final markdown with frontmatter."""
    frontmatter = f"""---
source: "{meta.source}"
fingerprint: "{meta.fingerprint}"
duration_seconds: {meta.duration_seconds}
processed_at: "{meta.processed_at}"
mode: "{meta.mode}"
engine: "{meta.engine}"
---"""

    title = _clean_filename_to_title(meta.source.split("/")[-1])
    return f"{frontmatter}\n\n# {title}\n\n{transcript_text}\n"


def format_brief(raw_text: str, meta: BriefMeta) -> str:
    """Format the model's raw output into the final markdown brief with frontmatter."""
    title = _extract_title(raw_text, meta.source.split("/")[-1])
    body = _strip_title(raw_text)
    body = _ensure_sections(body)

    frontmatter = f"""---
source: "{meta.source}"
fingerprint: "{meta.fingerprint}"
duration_seconds: {meta.duration_seconds}
processed_at: "{meta.processed_at}"
mode: "{meta.mode}"
engine: "{meta.engine}"
model: "{meta.model}"
cost_usd: {meta.cost_usd}
---"""

    return f"{frontmatter}\n\n# {title}\n\n{body}\n"


def format_duration(seconds: float) -> str:
    """Format seconds into HH:MM:SS."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h:02d}:{m:02d}:{s:02d}"
