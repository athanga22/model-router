import os
import anthropic
import openai
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

anthropic_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
openai_client    = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
groq_client      = Groq(api_key=os.getenv("GROQ_API_KEY"))


def call_haiku(prompt: str) -> tuple:
    message = anthropic_client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}]
    )
    return (
        message.content[0].text,
        message.usage.input_tokens,
        message.usage.output_tokens
    )


def call_llama(prompt: str) -> tuple:
    response = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}]
    )
    return (
        response.choices[0].message.content,
        response.usage.prompt_tokens,
        response.usage.completion_tokens
    )


def call_gpt4o(prompt: str) -> tuple:
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
    "claude-haiku-4-5":       call_haiku,
    "llama-3.3-70b-versatile": call_llama,
    "gpt-4o":                  call_gpt4o,
}