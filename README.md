# Marginalia

Margin notes for the videos you watch.

Marginalia is a CLI tool that turns course video folders into searchable markdown files. It has two modes:

- **Transcript mode** (default) -- Uses Apple Speech on-device transcription. Zero cost, zero network, no API key needed.
- **Brief mode** -- Sends cached transcripts to an LLM to produce structured notes with fixed sections. Costs cents per course.

## Requirements

- macOS 13+ with Apple Silicon
- Python 3.12+
- [uv](https://docs.astral.sh/uv/) (recommended) or pip
- ffmpeg and ffprobe installed (`brew install ffmpeg`)
- For brief mode: a `GEMINI_API_KEY` environment variable

Apple Speech requires the on-device speech model to be downloaded. If it is not installed, Marginalia will tell you where to enable it in System Settings.

## Install

```bash
git clone https://github.com/8lianno/marginalia.git
cd marginalia
uv sync
```

## Usage

### Transcript mode (default)

```bash
marginalia extract ./my-course
```

This walks the course folder, extracts audio from every video, transcribes it locally using Apple Speech, and writes one markdown file per video to `./marginalia/`.

### Brief mode

```bash
export GEMINI_API_KEY=your-key
marginalia extract ./my-course --mode brief
```

Brief mode first transcribes any videos that don't have cached transcripts, then sends each transcript to the LLM to produce a structured brief with these sections:

1. Core Idea
2. Frameworks & Mental Models
3. Key Examples
4. Actionable Takeaways
5. Marginalia (open questions)

If you ran transcript mode first, brief mode reuses those transcripts and only pays for the LLM calls.

### Preview a run

```bash
marginalia plan ./my-course --mode brief
```

Shows what would be processed, estimated cost, and which transcripts are cached -- without writing anything.

### Check status

```bash
marginalia status ./my-course
```

Shows per-mode processing state: how many videos are transcribed, briefed, failed, or pending.

### Retry failures

```bash
marginalia retry ./my-course --mode transcript
```

Reprocesses only videos that failed in the specified mode.

## Options

```
marginalia extract <course> [options]

  -o, --output DIR     Output directory (default: ./marginalia)
  -m, --mode MODE      transcript (default) or brief
  --model TEXT          LLM model for brief mode (default: gemini-2.0-flash)
  --force              Reprocess everything, ignore prior state
  --yes                Skip confirmation prompts
  --verbose            Debug output
```

## Output format

### Transcript mode

```markdown
---
source: "01-intro/welcome.mp4"
fingerprint: "154893024:1712678400.0"
duration_seconds: 342.5
processed_at: "2026-04-09T10:30:00Z"
mode: "transcript"
engine: "apple-speech"
---

# Welcome

Hello and welcome to the course...
```

### Brief mode

```markdown
---
source: "01-intro/welcome.mp4"
fingerprint: "154893024:1712678400.0"
duration_seconds: 342.5
processed_at: "2026-04-09T10:30:00Z"
mode: "brief"
engine: "apple-speech"
model: "gemini-2.0-flash"
cost_usd: 0.0012
---

# Welcome

## Core Idea
...

## Frameworks & Mental Models
...

## Key Examples
...

## Actionable Takeaways
...

## Marginalia
...
```

Sections with no relevant content show `(not mentioned)` rather than being omitted.

## Incremental runs

Marginalia tracks processing state in `.marginalia-state.json` in the output directory. Re-running the same command skips already-processed videos. A fingerprint change (file size or modification time) triggers reprocessing and invalidates both transcript and brief caches.

## Cost

- Transcript mode: always $0.00
- Brief mode: typically under $0.30 for an 8-hour course when transcripts are cached

Pre-run cost estimates are shown before processing begins. Actual cost is reported in the end summary.

## Development

```bash
uv sync --all-extras
uv run pytest -v
```

## License

MIT -- see [LICENSE](LICENSE).
