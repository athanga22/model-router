"""Request classifier for routing decisions."""
import httpx
import os
import time
from dotenv import load_dotenv

load_dotenv()

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
CLASSIFIER_MODEL = "phi3:mini"
VALID_TAGS = {"simple", "medium", "complex"}

SYSTEM_PROMPT = """You are a prompt difficulty classifier. Your only job is to read a user prompt and return exactly one word — nothing else.

The three difficulty tiers are:

SIMPLE — Single-step tasks requiring no reasoning. Examples:
- "What is the capital of France?"
- "Summarize this paragraph in one sentence."
- "Translate 'hello' to Spanish."
- "What does API stand for?"

MEDIUM — Multi-step tasks requiring some reasoning or synthesis. Examples:
- "Compare REST and GraphQL and explain when to use each."
- "Write a Python function to parse a CSV and return the top 5 rows by value."
- "Explain the pros and cons of microservices architecture."
- "Draft a professional email declining a job offer."

COMPLEX — Deep reasoning, long-form generation, or expert-level analysis. Examples:
- "Design a scalable system architecture for a real-time chat app with 10M users."
- "Debug this 100-line Python class and explain every issue you find."
- "Write a research summary comparing transformer vs. mamba architectures."
- "Build a full authentication flow with JWT refresh tokens in FastAPI."

Rules:
1. Return ONLY one word: simple, medium, or complex
2. No explanation, no punctuation, no extra text
3. If the prompt is empty or nonsensical, return: simple
4. If you are unsure between two tiers, return: medium
5. Non-English prompts: classify by apparent complexity, return the tag in English"""


def classify_prompt(prompt: str) -> str:
    """
    Classify a prompt's difficulty using Phi-3 mini via Ollama.
    Returns exactly one of: 'simple', 'medium', 'complex'
    """

    # Edge case: empty or whitespace
    if not prompt or not prompt.strip():
        return "simple"

    # Edge case: very long prompt — truncate for classifier only
    classifier_input = prompt.strip()
    if len(classifier_input) > 2000:
        classifier_input = classifier_input[:2000] + "... [truncated]"

    try:
        response = httpx.post(
            f"{OLLAMA_BASE_URL}/api/generate",
            json={
                "model": CLASSIFIER_MODEL,
                "system": SYSTEM_PROMPT,
                "prompt": f"Classify this prompt:\n\n{classifier_input}",
                "stream": False,
                "options": {
                    "temperature": 0.0,
                    "num_predict": 5       # We only need one word
                }
            },
            timeout=10.0
        )
        response.raise_for_status()
        raw = response.json().get("response", "").strip().lower()

        # Strip punctuation just in case
        tag = raw.strip(".,!? \n")

        if tag in VALID_TAGS:
            return tag

        # Partial match fallback
        for valid in VALID_TAGS:
            if valid in tag:
                return valid

        # If nothing matched, default to medium
        return "medium"

    except httpx.TimeoutException:
        return "medium"
    except Exception:
        return "medium"


if __name__ == "__main__":
    test_prompts = [
        "What is 2 + 2?",
        "Design a distributed rate limiter for a high-traffic API.",
        "Summarize this in one sentence: The sky is blue."
    ]
    for p in test_prompts:
        start = time.time()
        tag = classify_prompt(p)
        elapsed = (time.time() - start) * 1000
        print(f"[{tag:>8}] ({elapsed:.0f}ms)  {p[:60]}")