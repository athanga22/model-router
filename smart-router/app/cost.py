from typing import Tuple

RATES = {
    "claude-haiku-4-5":  (0.001,    0.005),
    # Cerebras gpt-oss-120b: $0.25/M input, $0.69/M output (per-1000-token rates)
    "gpt-oss-120b":      (0.00025,  0.00069),
    "gpt-4o":            (0.0025,   0.010),
}

GPT4O_RATES = (0.0025, 0.010)

MODEL_FOR_TAG = {
    "simple":  "claude-haiku-4-5",
    "medium":  "gpt-oss-120b",
    "complex": "gpt-4o",
}

def calculate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    input_rate, output_rate = RATES.get(model, GPT4O_RATES)
    return round(
        (input_tokens / 1000) * input_rate +
        (output_tokens / 1000) * output_rate,
        6
    )

def calculate_cost_saved(model: str, input_tokens: int, output_tokens: int) -> float:
    if model == "gpt-4o":
        return 0.0
    gpt4o_cost = round(
        (input_tokens / 1000) * GPT4O_RATES[0] +
        (output_tokens / 1000) * GPT4O_RATES[1],
        6
    )
    actual = calculate_cost(model, input_tokens, output_tokens)
    return round(gpt4o_cost - actual, 6)