import re
from app.cost import MODEL_FOR_TAG, calculate_cost, calculate_cost_saved
from app.llm import MODEL_CALLERS
from typing import Optional, Tuple

# Tier chain — defines escalation order
ESCALATION_CHAIN = {
    "simple":  "medium",
    "medium":  "complex",
    "complex": None,  # top tier — no escalation possible
}

# Regex patterns with word boundaries prevent false positives like
# "I cannot stress enough…" or "unclear to me" appearing mid-word.
# The negative lookahead on "i cannot" excludes emphasis phrases.
LOW_CONFIDENCE_PATTERNS = [
    r"\bi don't know\b",
    r"\bi do not know\b",
    r"\bi cannot\b(?!\s+(?:stress|emphasize|overstate))",
    r"\bi can't\b",
    r"\bi am not sure\b",
    r"\bi'm not sure\b",
    r"\bi am unable\b",
    r"\bi'm unable\b",
    r"\bnot enough information\b",
    r"\binsufficient information\b",
    r"\bbeyond my knowledge\b",
    r"\bi lack the\b",
    r"\bunclear to me\b",
]


def should_escalate(response_text: str) -> bool:
    """Check if a response contains low-confidence signals."""
    lowered = response_text.lower().strip()
    return any(re.search(pattern, lowered) for pattern in LOW_CONFIDENCE_PATTERNS)


def get_next_tier(current_tag: str) -> Optional[Tuple[str, str]]:
    """Returns the next model in the escalation chain, or None if at top."""
    next_tag = ESCALATION_CHAIN.get(current_tag)
    if next_tag is None:
        return None
    return MODEL_FOR_TAG[next_tag], next_tag


def run_with_escalation(prompt: str, initial_tag: str) -> dict:
    """
    Run prompt through model tier. If response is low-confidence,
    escalate once to the next tier. Never escalates more than once.
    """
    model = MODEL_FOR_TAG[initial_tag]
    caller = MODEL_CALLERS[model]
    escalated = False
    final_tag = initial_tag

    try:
        response_text, input_tokens, output_tokens = caller(prompt)
    except Exception as e:
        # Model call failed — treat as escalation trigger
        response_text = None
        input_tokens, output_tokens = 0, 0

    # Check if we need to escalate
    needs_escalation = (
        response_text is None or
        should_escalate(response_text)
    )

    if needs_escalation:
        result = get_next_tier(initial_tag)

        if result is None:
            # Already at complex tier — can't escalate further
            if response_text is None:
                raise Exception("model_call_failed_at_max_tier")
            # Return the weak response as-is with escalation flag
            # (we tried our best)
        else:
            next_model, next_tag = result
            next_caller = MODEL_CALLERS[next_model]

            try:
                response_text, input_tokens, output_tokens = next_caller(prompt)
                escalated = True
                final_tag = next_tag
                model = next_model
            except Exception as e:
                raise Exception(f"escalation_model_failed: {str(e)}")

    cost = calculate_cost(model, input_tokens, output_tokens)
    cost_saved = calculate_cost_saved(model, input_tokens, output_tokens)

    return {
        "response":       response_text,
        "model_used":     model,
        "difficulty_tag": final_tag,
        "input_tokens":   input_tokens,
        "output_tokens":  output_tokens,
        "cost_usd":       cost,
        "cost_saved_usd": cost_saved,
        "escalated":      escalated,
    }