from app.classifier import classify_prompt
from app.escalation import run_with_escalation

def route_prompt(prompt: str) -> dict:
    """
    Classify -> route with escalation support -> return result dict
    """
    tag = classify_prompt(prompt)
    return run_with_escalation(prompt, initial_tag=tag)