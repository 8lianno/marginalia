# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 0.1.x   | Yes       |

## Reporting a Vulnerability

If you discover a security vulnerability, please report it responsibly:

1. **Do not** open a public GitHub issue.
2. Email the maintainer directly or use GitHub's private vulnerability reporting feature on this repository.
3. Include a description of the vulnerability, steps to reproduce, and potential impact.

You should receive an acknowledgment within 48 hours. Fixes for confirmed vulnerabilities will be released as soon as possible.

## Security Model

### Transcript mode

- All processing is local. Audio is extracted to a temporary directory and deleted after transcription.
- No network calls are made. No data leaves the machine.
- The Apple Speech framework runs in on-device mode (`requiresOnDeviceRecognition = true`).

### Brief mode

- Transcript text is sent to the configured LLM provider (Google Gemini by default) over HTTPS.
- The API key is read from the `GEMINI_API_KEY` environment variable. It is never logged, written to disk, or passed as a CLI argument.
- No audio is sent to the LLM -- only the text transcript.

### General

- Marginalia never writes to the input directory.
- Temporary audio files are created in the system temp directory and cleaned up after each video.
- The state file (`.marginalia-state.json`) contains file paths, fingerprints, and processing metadata. It does not contain transcript or brief content.
- The compiled Swift helper binary is stored alongside the source in `src/marginalia/swift/` and is not fetched from the network.

## Dependencies

Marginalia depends on:

- `typer` -- CLI framework
- `google-genai` -- Google Gemini SDK (brief mode only)
- `pydantic` -- Data validation

All dependencies are installed from PyPI. Pin versions in `uv.lock` for reproducibility.
