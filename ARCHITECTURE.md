# Architecture

## Overview

Marginalia is a Python CLI that converts video course folders into markdown files. It operates in two modes -- transcript (local, free) and brief (LLM-powered, paid) -- with a shared discovery, state, and output layer.

```
Course folder          Marginalia           Output folder
  videos/         -->  [pipeline]  -->    markdown files/
  01-intro.mp4         state.json          01-intro.md
  02-setup.mp4                             02-setup.md
```

## Module Map

```
src/marginalia/
  cli.py           Typer app with subcommands: extract, plan, retry, status
  models.py        Pydantic data models: VideoFile, VideoState, RunState, configs
  discovery.py     Recursive folder walk, video filtering, fingerprinting, collision detection
  audio.py         ffmpeg/ffprobe: extract WAV audio, probe duration (robust), detect audio
  transcribe.py    Apple Speech via Swift helper + Gemini LLM + preflight + transcript guard
  brief.py         Prompt template, section validation, markdown formatting for both modes
  state.py         JSON state file: load, save (atomic), per-mode skip logic
  pipeline.py      Orchestration: run, run_retry, run_plan, run_status, JSONL logging
  cost.py          Cost estimation (transcript=$0, brief=token-based estimate)
  console.py       Terminal output: colors (NO_COLOR aware), verbose mode, confirm prompts
  logging.py       Structured JSONL run logs to <output>/.logs/

  swift/
    transcribe.swift   Apple Speech on-device transcription with structured error codes
```

## Data Flow

### Transcript mode

```
discover(input_dir)
  |
  v
for each video:
  probe_duration(video)       # ffprobe
  extract_audio(video, tmp)   # ffmpeg -> mono 16kHz WAV
  transcribe_local(wav)       # Swift helper -> Apple Speech on-device
  format_transcript(text)     # markdown + YAML frontmatter
  write output .md
  update state
  cleanup temp audio
```

### Brief mode

```
discover(input_dir)
  |
  v
for each video:
  if transcript cached:
    read transcript from .md file
  else:
    extract_audio + transcribe_local  (same as transcript mode)
  |
  summarize_transcript(text, prompt, model)  # Gemini API
  format_brief(llm_output)                   # markdown + frontmatter
  write output .md
  update state
```

## State Model

State is stored in `{output_dir}/.marginalia-state.json`. Each video has independent per-mode tracking:

```json
{
  "version": 2,
  "videos": {
    "01-intro/welcome.mp4": {
      "fingerprint": "154893024:1712678400.0",
      "duration_seconds": 342.5,
      "transcript": {
        "status": "completed",
        "processed_at": "2026-04-09T10:30:00Z"
      },
      "brief": {
        "status": "completed",
        "processed_at": "2026-04-09T11:00:00Z",
        "model": "gemini-2.0-flash",
        "cost_usd": 0.0012
      }
    }
  }
}
```

A fingerprint change (file size or mtime) invalidates both modes for that video.

State is written atomically after every video (write to `.tmp`, then `os.replace`).

## Key Design Decisions

1. **Two modes, shared pipeline.** Transcript mode is a strict subset of brief mode. Brief mode reuses transcript outputs, so running transcript first then brief later costs nothing extra for transcription.

2. **Local-first transcription.** Apple Speech's on-device mode keeps audio on the machine. The LLM in brief mode only sees the text transcript, never the audio.

3. **Per-video error isolation.** Each video is processed inside a try/except. Failures are recorded in state and the run continues. No partial markdown files are left behind.

4. **State saved after every video.** If the process is killed mid-run, all previously completed videos are recorded.

5. **Swift helper compiled on first run.** The Apple Speech framework requires Swift. A small helper binary is compiled from source on first use and cached alongside the source file.

6. **WAV extraction for Apple Speech.** Apple's `SFSpeechRecognizer` works best with uncompressed audio. Mono 16kHz WAV is extracted via ffmpeg.

7. **Synchronous, one-at-a-time processing.** Keeps memory and disk bounded. Parallelism can be added later without architectural changes.

## Safety Layers

1. **Preflight check** -- In brief mode, a minimal API call verifies the key and model before the main loop. Skippable with `--no-preflight`.
2. **Transcript length guard** -- Before each LLM call, an estimated token count is compared against the model's context window (at 80% safe limit). If too long, the video is marked failed with a clear message instead of sending a request that will be rejected.
3. **Force confirmation** -- `--force` on >10 videos prompts for confirmation unless `--yes` is passed. Non-TTY environments error rather than block.
4. **Structured error messages** -- The Swift helper exits with distinct codes (2=permission, 3=model not downloaded, 4=runtime failure). The Python layer maps these to actionable instructions.
5. **Output collision detection** -- Discovery detects stem collisions (e.g., `intro.mp4` and `intro.mov`) and resolves them to `intro.mp4.md` and `intro.mov.md`.

## CLI Shape

```
marginalia extract <course>  [--mode transcript|brief] [--output ...] [--force] [--path ...] [--yes] [--verbose] [--no-preflight]
marginalia plan <course>     [--mode transcript|brief] [--force] [--path ...]
marginalia retry <course>    [--mode transcript|brief] [--verbose] [--no-preflight]
marginalia status <course>
```

## Testing

Tests mock `extract_audio`, `probe_duration`, `transcribe_local`, and `summarize_transcript` to avoid ffmpeg, Apple Speech, and API dependencies. 60 tests cover:

- Flat and nested folder processing
- Incremental skip logic (same mode re-run)
- Cross-mode transcript caching (transcript then brief)
- State consistency under nested operations (US-013 regression)
- Failure isolation (one video fails, others succeed, no partial .md files)
- Plan mode (zero side effects)
- Retry mode (only failed entries)
- JSONL log creation and structure
- Force path filtering
- Output file collision detection
- Transcript length guard (too-long rejection)
- Swift helper error message parsing

```bash
uv run pytest -v
```
