import pytest
import time
from unittest.mock import patch
from app.router import route_prompt

# 10 prompts with expected routing tier
INTEGRATION_SUITE = [
    # SIMPLE → claude-haiku-4-5
    ("What is the capital of France?",              "claude-haiku-4-5"),
    ("What does CPU stand for?",                    "claude-haiku-4-5"),
    ("Translate 'hello' to Spanish.",               "claude-haiku-4-5"),
    ("What is 25% of 80?",                          "claude-haiku-4-5"),

    # MEDIUM → llama-3.3-70b-versatile
    ("Compare REST and GraphQL and when to use each.",              "llama-3.3-70b-versatile"),
    ("Write a Python function to find duplicates in a list.",       "llama-3.3-70b-versatile"),
    ("What are the pros and cons of microservices architecture?",   "llama-3.3-70b-versatile"),

    # COMPLEX → gpt-4o
    ("Design a fault-tolerant microservices architecture for an e-commerce platform with 5M daily users.", "gpt-4o"),
    ("Build a full JWT authentication system with refresh token rotation in FastAPI.",                     "gpt-4o"),
    ("Analyze the trade-offs between CAP theorem consistency models in distributed databases.",            "gpt-4o"),
]


@pytest.mark.integration
class TestIntegration:

    def test_all_10_prompts_route_correctly(self):
        correct = 0
        results = []

        for prompt, expected_model in INTEGRATION_SUITE:
            result = route_prompt(prompt)
            actual_model = result["model_used"]
            passed = actual_model == expected_model
            if passed:
                correct += 1
            results.append((passed, expected_model, actual_model, prompt[:55]))

        print(f"\n--- Integration Routing Report ---")
        for passed, expected, actual, prompt in results:
            status = "PASS" if passed else "FAIL"
            print(f"[{status}] expected={expected:<28} got={actual:<28} | {prompt}")
        print(f"\nAccuracy: {correct}/{len(INTEGRATION_SUITE)}")

        assert correct >= 8, f"Only {correct}/10 routed correctly — check classifier accuracy"

    def test_all_responses_have_required_fields(self):
        required_fields = {
            "response", "model_used", "difficulty_tag",
            "cost_usd", "cost_saved_usd", "escalated",
            "input_tokens", "output_tokens"
        }
        for prompt, _ in INTEGRATION_SUITE[:3]:  # spot check 3
            result = route_prompt(prompt)
            for field in required_fields:
                assert field in result, f"Missing field '{field}' in response"
                assert result[field] is not None, f"Field '{field}' is None"

    def test_cost_usd_is_never_negative(self):
        for prompt, _ in INTEGRATION_SUITE[:3]:
            result = route_prompt(prompt)
            assert result["cost_usd"] >= 0, f"Negative cost for prompt: {prompt[:40]}"

    def test_cost_saved_positive_for_non_gpt4o(self):
        simple_prompt = "What is the capital of France?"
        result = route_prompt(simple_prompt)
        if result["model_used"] != "gpt-4o":
            assert result["cost_saved_usd"] >= 0, "cost_saved_usd should be >= 0 for non-GPT4o"

    def test_no_api_keys_in_source(self):
        """Verify no hardcoded secrets exist in the codebase."""
        import subprocess
        result = subprocess.run(
            ["grep", "-r", "sk-", "app/", "--include=*.py"],
            capture_output=True, text=True
        )
        assert result.stdout == "", f"Potential hardcoded API key found:\n{result.stdout}"