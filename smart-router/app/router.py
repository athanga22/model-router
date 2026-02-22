"""Request router logic."""
from app.classifier import classify_prompt
from app.cost import MODEL_FOR_TAG, calculate_cost, calculate_cost_saved
from app.llm import MODEL_CALLERS

def route_prompt(prompt: str) -> dict:
    """
    Classify -> route -> call model -> return result dict
    """
    tag = classify_prompt(prompt)
    model = MODEL_FOR_TAG[tag]
    caller = MODEL_CALLERS[model]

    response_text, input_tokens, output_tokens = caller(prompt)
    cost = calculate_cost(model, input_tokens, output_tokens)
    cost_saved = calculate_cost_saved(model, input_tokens, output_tokens)

    return {
        "response":      response_text,
        "model_used":    model,
        "difficulty_tag": tag,
        "input_tokens":  input_tokens,
        "output_tokens": output_tokens,
        "cost_usd":      cost,
        "cost_saved_usd": cost_saved,
        "escalated":     False,
    }