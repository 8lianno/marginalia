from __future__ import annotations

from marginalia.models import CostEstimate, Mode, VideoFile

# Average speech rate: ~150 words/min, ~200 tokens/min (rough estimate for transcript length)
# Gemini 2.0 Flash pricing: $0.10 per 1M input tokens, $0.40 per 1M output tokens
# For a brief, input is the transcript (~200 tokens/min of audio) + prompt (~500 tokens)
# Output is ~800 tokens per brief
TOKENS_PER_MINUTE_OF_AUDIO = 200
PROMPT_TOKENS = 500
OUTPUT_TOKENS_PER_BRIEF = 800
INPUT_PRICE_PER_TOKEN = 0.10 / 1_000_000
OUTPUT_PRICE_PER_TOKEN = 0.40 / 1_000_000


def estimate_cost(videos: list[VideoFile], mode: Mode) -> CostEstimate:
    """Estimate API cost. Transcript mode is always $0."""
    total_seconds = sum(v.duration_seconds or 0.0 for v in videos)

    if mode == Mode.TRANSCRIPT:
        return CostEstimate(total_duration_seconds=total_seconds, estimated_cost_usd=0.0)

    # Brief mode: estimate from transcript length
    total_minutes = total_seconds / 60.0
    input_tokens = total_minutes * TOKENS_PER_MINUTE_OF_AUDIO + PROMPT_TOKENS * len(videos)
    output_tokens = OUTPUT_TOKENS_PER_BRIEF * len(videos)
    cost = input_tokens * INPUT_PRICE_PER_TOKEN + output_tokens * OUTPUT_PRICE_PER_TOKEN
    return CostEstimate(
        total_duration_seconds=total_seconds,
        estimated_cost_usd=round(cost, 4),
    )
