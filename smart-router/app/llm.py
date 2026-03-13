import os
import anthropic
import openai
from cerebras.cloud.sdk import Cerebras
from dotenv import load_dotenv

load_dotenv()

_anthropic_client = None
_openai_client = None
_cerebras_client = None


def _get_anthropic_client():
    global _anthropic_client
    if _anthropic_client is None:
        key = os.getenv("ANTHROPIC_API_KEY")
        if not key:
            raise ValueError(
                "ANTHROPIC_API_KEY is required. Set it in the environment or in GitHub Actions secrets."
            )
        _anthropic_client = anthropic.Anthropic(api_key=key)
    return _anthropic_client


def _get_openai_client():
    global _openai_client
    if _openai_client is None:
        key = os.getenv("OPENAI_API_KEY")
        if not key:
            raise ValueError(
                "OPENAI_API_KEY is required. Set it in the environment or in GitHub Actions secrets."
            )
        _openai_client = openai.OpenAI(api_key=key)
    return _openai_client


def _get_cerebras_client():
    global _cerebras_client
    if _cerebras_client is None:
        key = os.getenv("CEREBRAS_API_KEY")
        if not key:
            raise ValueError(
                "CEREBRAS_API_KEY is required. Set it in the environment or in GitHub Actions secrets."
            )
        _cerebras_client = Cerebras(api_key=key)
    return _cerebras_client


def call_haiku(prompt: str) -> tuple:
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


def call_cerebras(prompt: str) -> tuple:
    response = _get_cerebras_client().chat.completions.create(
        model="gpt-oss-120b",
        max_completion_tokens=2048,
        messages=[{"role": "user", "content": prompt}]
    )
    return (
        response.choices[0].message.content,
        response.usage.prompt_tokens,
        response.usage.completion_tokens
    )


def call_gpt4o(prompt: str) -> tuple:
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


MODEL_CALLERS = {
    "claude-haiku-4-5":  call_haiku,
    "gpt-oss-120b":      call_cerebras,
    "gpt-4o":            call_gpt4o,
}