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
  discovery.py     Recursive folder walk, video extension filtering, fingerprinting
  audio.py         ffmpeg/ffprobe: extract WAV audio, probe duration, detect audio streams
  transcribe.py    Apple Speech via Swift helper (local) + Gemini LLM (brief mode)
  brief.py         Prompt template, section validation, markdown formatting for both modes
  state.py         JSON state file: load, save (atomic), per-mode skip logic
  pipeline.py      Orchestration: run, run_retry, run_plan, run_status
  cost.py          Cost estimation (transcript=$0, brief=token-based estimate)
  console.py       Terminal output: stage indicators, skip/success/failure, summary

  swift/
    transcribe.swift   Apple Speech on-device transcription (compiled on first run)
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

## CLI Shape

```
marginalia extract <course>  [--mode transcript|brief] [--output ...] [--force] [--yes]
marginalia plan <course>     [--mode transcript|brief]
marginalia retry <course>    [--mode transcript|brief]
marginalia status <course>
```

## Testing

Tests mock `extract_audio`, `probe_duration`, and `transcribe_local` to avoid ffmpeg and Apple Speech dependencies. The pipeline tests verify:

- Flat and nested folder processing
- Incremental skip logic (same mode re-run)
- Cross-mode transcript caching (transcript then brief)
- Failure isolation (one video fails, others succeed)
- Plan mode (zero side effects)
- Retry mode (only failed entries)

```bash
uv run pytest -v
```
