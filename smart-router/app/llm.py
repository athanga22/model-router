import os
import anthropic
import openai
from dotenv import load_dotenv

load_dotenv()

anthropic_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
openai_client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def call_haiku(prompt: str) -> tuple[str, int, int]:
    message = anthropic_client.messages.create(
        model="claude-haiku-4-5-20251001",   # ← was claude-haiku-3-5-20251001
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}]
    )
    return (
        message.content[0].text,
        message.usage.input_tokens,
        message.usage.output_tokens
    )

def call_sonnet(prompt: str) -> tuple[str, int, int]:
    message = anthropic_client.messages.create(
        model="claude-sonnet-4-6",           # ← was claude-sonnet-4-5
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}]
    )
    return (
        message.content[0].text,
        message.usage.input_tokens,
        message.usage.output_tokens
    )

def call_gpt4o(prompt: str) -> tuple[str, int, int]:
    response = openai_client.chat.completions.create(
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
    "claude-sonnet-4-6": call_sonnet,
    "gpt-4o":            call_gpt4o,
}