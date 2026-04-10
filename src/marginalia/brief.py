from __future__ import annotations

import re

from marginalia.models import BriefMeta, NotesMeta, TranscriptMeta

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


# --- Notes mode: comprehensive timestamped lecture notes ---


def build_notes_prompt(title: str, duration_formatted: str, source_description: str) -> str:
    """Prompt for comprehensive, handout-quality lecture notes with inline timestamps.

    The transcript fed alongside this prompt is pre-formatted with `[mm:ss]`
    prefixes per segment so the model can anchor every claim to a timestamp.
    """
    return f"""You are a meticulous course notes assistant. Read the timestamped lecture transcript below and produce comprehensive, handout-quality lecture notes (in Persian called جزوه) — NOT a summary.

Lecture: {title}
Source: {source_description}
Duration: {duration_formatted}

Your goal: produce notes so complete and well-structured that a learner can review them without rewatching the video — while still giving them timestamp cues to jump back to any specific concept they want to hear again.

REQUIREMENTS:

1. Cover EVERY concept, definition, framework, formula, example, and diagram reference presented in the lecture. Do not omit material. Do not compress for brevity.

2. Organize the notes into H2 (`##`) and H3 (`###`) sections that reflect the lecture's own structure and flow. Use the speaker's section boundaries when they exist.

3. **Anchor every claim, definition, example, and formula with an inline `[mm:ss]` timestamp** taken from the nearest matching line in the transcript. Multiple timestamps per paragraph are encouraged. Place the timestamp immediately after the sentence or bullet it refers to. Examples:
   - "A monad is a monoid in the category of endofunctors [12:34]."
   - "The speaker walks through a concrete example with lists [15:07] and then with Maybe [16:42]."

4. Preserve the speaker's terminology, notation, and examples verbatim where possible. Do not paraphrase technical terms.

5. Write the notes in the SAME LANGUAGE as the transcript. If the lecture is in Persian, write Persian notes. If it is in English, write English. Never translate.

6. Include:
   - Definitions (bold the term: **Term** — definition [mm:ss])
   - Step-by-step walkthroughs for examples and derivations
   - Diagram/figure descriptions in prose when the speaker references them
   - Code snippets in fenced code blocks when code is read out or written on screen
   - A short "Key Takeaways" section at the end, with each takeaway anchored to a timestamp

7. Do NOT include:
   - A leading H1 title (the formatter adds one)
   - Frontmatter
   - Meta-commentary about what you're doing
   - Fabricated content not in the transcript

Format timestamps as `[mm:ss]` or `[h:mm:ss]` for lectures over an hour. Do not wrap them in links — a post-processor will convert them to clickable links.

Output only the markdown body of the notes, starting with an H2 section."""


def format_notes(raw_text: str, meta: NotesMeta) -> str:
    """Format the model's notes output into final markdown with frontmatter."""
    # Prefer an H1 from the model output; otherwise use the video's actual
    # title verbatim (don't title-case a human-authored title); finally fall
    # back to a cleaned filename.
    h1_match = re.search(r"^#\s+(.+)$", raw_text, re.MULTILINE)
    if h1_match:
        title = h1_match.group(1).strip()
    elif meta.title:
        title = meta.title
    else:
        title = _clean_filename_to_title(meta.source.split("/")[-1])
    body = _strip_title(raw_text)

    source_url_line = f'source_url: "{meta.source_url}"\n' if meta.source_url else ""
    title_line = f'title: "{_escape_yaml(meta.title)}"\n' if meta.title else ""
    channel_line = f'channel: "{_escape_yaml(meta.channel)}"\n' if meta.channel else ""

    frontmatter = (
        "---\n"
        f'source: "{meta.source}"\n'
        f"{source_url_line}"
        f"{title_line}"
        f"{channel_line}"
        f'fingerprint: "{meta.fingerprint}"\n'
        f"duration_seconds: {meta.duration_seconds}\n"
        f'processed_at: "{meta.processed_at}"\n'
        f'mode: "{meta.mode}"\n'
        f'engine: "{meta.engine}"\n'
        f'model: "{meta.model}"\n'
        f"cost_usd: {meta.cost_usd}\n"
        "---"
    )

    return f"{frontmatter}\n\n# {title}\n\n{body}\n"


def _escape_yaml(value: str | None) -> str:
    if value is None:
        return ""
    return value.replace("\\", "\\\\").replace('"', '\\"')


_TIMESTAMP_RE = re.compile(r"\[(\d{1,3}):(\d{2})(?::(\d{2}))?\]")


def linkify_timestamps(body: str, video_id: str | None) -> str:
    """Convert `[mm:ss]` / `[h:mm:ss]` markers into clickable YouTube links.

    When `video_id` is None (local source), leaves the markers as plain text.
    """
    if not video_id:
        return body

    def repl(match: re.Match) -> str:
        a, b, c = match.group(1), match.group(2), match.group(3)
        if c is not None:
            # h:mm:ss
            total = int(a) * 3600 + int(b) * 60 + int(c)
            label = f"{int(a)}:{int(b):02d}:{int(c):02d}"
        else:
            # mm:ss
            total = int(a) * 60 + int(b)
            label = f"{int(a):02d}:{int(b):02d}"
        url = f"https://www.youtube.com/watch?v={video_id}&t={total}s"
        return f"[[{label}]]({url})"

    return _TIMESTAMP_RE.sub(repl, body)
