import os
import time
import logging
import anthropic
import openai
from together import Together
from dotenv import load_dotenv

load_dotenv()

_logger = logging.getLogger(__name__)

_anthropic_client = None
_openai_client = None
_together_client = None

# Configurable via env var; 60s covers slow streaming cold starts
_LLM_TIMEOUT = int(os.getenv("LLM_TIMEOUT_SECONDS", "60"))
_MAX_RETRIES = 3
# Status codes that are safe to retry (rate limit + server errors)
_RETRY_STATUSES = {429, 500, 502, 503, 504}


def _get_anthropic_client():
    global _anthropic_client
    if _anthropic_client is None:
        key = os.getenv("ANTHROPIC_API_KEY")
        if not key:
            raise ValueError(
                "ANTHROPIC_API_KEY is required. Set it in the environment or in GitHub Actions secrets."
            )
        _anthropic_client = anthropic.Anthropic(api_key=key, timeout=_LLM_TIMEOUT)
    return _anthropic_client


def _get_openai_client():
    global _openai_client
    if _openai_client is None:
        key = os.getenv("OPENAI_API_KEY")
        if not key:
            raise ValueError(
                "OPENAI_API_KEY is required. Set it in the environment or in GitHub Actions secrets."
            )
        _openai_client = openai.OpenAI(api_key=key, timeout=_LLM_TIMEOUT)
    return _openai_client


def _get_together_client():
    global _together_client
    if _together_client is None:
        key = os.getenv("TOGETHER_API_KEY")
        if not key:
            raise ValueError(
                "TOGETHER_API_KEY is required. Set it in the environment or in GitHub Actions secrets."
            )
        _together_client = Together(api_key=key, timeout=_LLM_TIMEOUT)
    return _together_client


def _with_retry(fn, label: str):
    """Call fn() up to _MAX_RETRIES times with exponential backoff on transient errors."""
    last_exc = None
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            return fn()
        except Exception as e:
            last_exc = e
            status = getattr(e, "status_code", None)
            if status is None:
                status = getattr(getattr(e, "response", None), "status_code", None)
            # Don't retry definitive client errors (4xx except 429)
            if status is not None and status not in _RETRY_STATUSES:
                raise
            if attempt < _MAX_RETRIES:
                delay = 2 ** (attempt - 1)  # 1s, 2s
                _logger.warning(
                    "llm %s attempt %d/%d failed (%s), retrying in %ds",
                    label, attempt, _MAX_RETRIES, e, delay
                )
                time.sleep(delay)
    raise last_exc


def call_haiku(prompt: str) -> tuple:
    def _call():
        message = _get_anthropic_client().messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}]
        )
        return (
            message.content[0].text,
            message.usage.input_tokens,
            message.usage.output_tokens
        )
    return _with_retry(_call, "haiku")


def call_together(prompt: str) -> tuple:
    def _call():
        response = _get_together_client().chat.completions.create(
            model="meta-llama/Llama-3.3-70B-Instruct-Turbo",
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}]
        )
        return (
            response.choices[0].message.content,
            response.usage.prompt_tokens,
            response.usage.completion_tokens
        )
    return _with_retry(_call, "together")


def call_gpt4o(prompt: str) -> tuple:
    def _call():
        response = _get_openai_client().chat.completions.create(
            model="gpt-4o",
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}]
        )
        return (
            response.choices[0].message.content,
            response.usage.prompt_tokens,
            response.usage.completion_tokens
        )
    return _with_retry(_call, "gpt4o")


MODEL_CALLERS = {
    "claude-haiku-4-5":                      call_haiku,
    "meta-llama/Llama-3.3-70B-Instruct-Turbo": call_together,
    "gpt-4o":                                call_gpt4o,
}