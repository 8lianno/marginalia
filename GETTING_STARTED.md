# Getting Started

A step-by-step guide to go from zero to your first course notes.

## 1. Prerequisites

Make sure you have these installed before starting:

```bash
# Check Python version (need 3.12+)
python3 --version

# Install uv if you don't have it
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install ffmpeg
brew install ffmpeg

# Verify ffmpeg and ffprobe are available
ffmpeg -version
ffprobe -version
```

You also need **Xcode Command Line Tools** for compiling the Apple Speech helper:

```bash
xcode-select --install
```

## 2. Install Marginalia

```bash
git clone https://github.com/8lianno/marginalia.git
cd marginalia
uv sync
```

Verify it works:

```bash
marginalia --help
```

You should see the four subcommands: `extract`, `plan`, `retry`, `status`.

## 3. Enable Apple Speech (one-time)

Marginalia uses Apple's on-device speech recognition. You need to enable it once:

1. Open **System Settings**
2. Go to **General > Keyboard > Dictation**
3. Turn on **Dictation** and enable **On-Device Dictation** (this downloads the speech model)
4. Go to **Privacy & Security > Speech Recognition** and allow Terminal (or your terminal app)

Marginalia will tell you exactly what's missing if you skip this step.

## 4. Your first transcript run

Point Marginalia at any folder containing video files:

```bash
marginalia extract ./my-course
```

This will:
- Discover all video files (`.mp4`, `.mkv`, `.mov`, `.webm`, `.m4v`)
- Extract audio from each video
- Transcribe using Apple Speech (on-device, free, no network)
- Write one `.md` file per video to the current directory

Example output:

```
3 videos . 00:15:30 . mode: transcript . engine: apple-speech . est. cost: $0.00

  [1/3] Extracting audio... 01-intro.mp4
  [1/3] Transcribing... 01-intro.mp4
  + done: 01-intro.mp4
  [2/3] Extracting audio... 02-setup.mp4
  [2/3] Transcribing... 02-setup.mp4
  + done: 02-setup.mp4
  [3/3] Extracting audio... 03-basics.mp4
  [3/3] Transcribing... 03-basics.mp4
  + done: 03-basics.mp4

Done. Processed: 3 in 00:02:14 -- cost: $0.00
```

## 5. Preview before running (optional)

If you want to see what would happen without actually doing anything:

```bash
marginalia plan ./my-course
```

This lists every video with its size and duration, and shows the estimated cost. Nothing is written to disk.

## 6. Speed it up with parallel processing

For courses with many short videos, use `-j` to process multiple videos at once:

```bash
marginalia extract ./my-course -j 4
```

This runs 4 videos in parallel. Apple Silicon Macs handle this well.

## 7. Generate structured briefs (optional)

If you want more than raw transcripts -- structured notes with frameworks, examples, and takeaways:

```bash
# Set your API key (get one from https://aistudio.google.com/apikey)
export GEMINI_API_KEY=your-key-here

# Run brief mode
marginalia extract ./my-course --mode brief
```

If you already ran transcript mode, brief mode reuses those transcripts and only pays for the LLM summarization. Typical cost: under $0.30 for an 8-hour course.

The output has five fixed sections:

```markdown
## Core Idea
## Frameworks & Mental Models
## Key Examples
## Actionable Takeaways
## Marginalia
```

## 8. Check progress

See what's been processed:

```bash
marginalia status ./my-course
```

Output:

```
course: ./my-course
videos: 20 . duration: 06:42:31
  transcript: 20 processed . 0 failed . 0 pending
  brief:       5 processed . 0 failed . 15 pending
```

## 9. Handle failures

If some videos failed (bad audio, network issues in brief mode):

```bash
# See what failed
marginalia status ./my-course

# Retry only the failures
marginalia retry ./my-course --mode transcript
```

## 10. Use with Obsidian

The output folder is ready to drop into an Obsidian vault. Each `.md` file has YAML frontmatter that Obsidian can index:

```
my-vault/
  courses/
    reforge-growth/        <-- copy Marginalia output here
      01-intro.md
      02-frameworks.md
      ...
```

You can then search, link, and tag your course notes like any other Obsidian note.

## Common workflows

### Process a new course end-to-end

```bash
# Free transcripts first
marginalia extract ./new-course -j 4

# Then structured briefs for the ones worth it
export GEMINI_API_KEY=your-key
marginalia extract ./new-course --mode brief -j 2
```

### Re-run after adding new videos

```bash
# Just run the same command -- Marginalia skips what's already done
marginalia extract ./my-course
```

### Iterate on a specific video's brief

```bash
marginalia extract ./my-course --mode brief --force --path 03-core/02-scoring.mp4
```

### Preview cost before a brief run

```bash
marginalia plan ./my-course --mode brief
```

## Troubleshooting

| Problem | Fix |
|---|---|
| `swiftc not found` | Run `xcode-select --install` |
| `Speech recognizer is not available` | System Settings > Privacy & Security > Speech Recognition |
| `On-device speech model not downloaded` | System Settings > General > Keyboard > Dictation > enable On-Device |
| `GEMINI_API_KEY not set` | `export GEMINI_API_KEY=your-key` (brief mode only) |
| `API key invalid` | Check your key at https://aistudio.google.com/apikey |
| `Transcript too long for model context` | Very long videos (2+ hours) may exceed limits; chunking is planned |
| Video with no audio | Marked as failed with "no audio track"; other videos continue |

## What's next

- Read the full [README](README.md) for all options and output format details
- Read [ARCHITECTURE.md](ARCHITECTURE.md) to understand how the code is structured
- Check [SECURITY.md](SECURITY.md) for the privacy model
