# Cost per 1000 tokens (input + output blended) in USD
COST_PER_1K_TOKENS = {
    "claude-haiku-4-5":  0.001,    # $1/input, $5/output per MTok
    "claude-sonnet-4-6": 0.003,    # $3/input, $15/output per MTok
    "gpt-4o":            0.005,
    "phi3:mini":           0.0,      # local — free
}

# GPT-4o baseline — used to calculate savings
GPT4O_COST_PER_1K = 0.005

MODEL_FOR_TAG = {
    "simple":  "claude-haiku-4-5",
    "medium":  "claude-sonnet-4-6",
    "complex": "gpt-4o",
}

def calculate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    rates = {
        "claude-haiku-4-5":  (0.001, 0.005),
        "claude-sonnet-4-6": (0.003, 0.015),
        "gpt-4o":            (0.005, 0.015),
    }
    input_rate, output_rate = rates.get(model, (0.005, 0.015))
    return round((input_tokens / 1000) * input_rate + (output_tokens / 1000) * output_rate, 6)

def calculate_cost_saved(model: str, input_tokens: int, output_tokens: int) -> float:
    if model == "gpt-4o":
        return 0.0
    total_tokens = input_tokens + output_tokens
    gpt4o_cost = round((total_tokens / 1000) * GPT4O_COST_PER_1K, 6)
    actual_cost = calculate_cost(model, input_tokens, output_tokens)
    return round(gpt4o_cost - actual_cost, 6)