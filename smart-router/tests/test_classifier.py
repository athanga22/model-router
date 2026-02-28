import time
import pytest
from app.classifier import classify_prompt

# ------------------------------------------------------------
# 20 labeled test cases
# Format: (prompt, expected_tag)
# ------------------------------------------------------------
LABELED_PROMPTS = [
    # SIMPLE (8 cases)
    ("What is the capital of Japan?",                                      "simple"),
    ("Translate 'good morning' to French.",                                "simple"),
    ("What does HTML stand for?",                                          "simple"),
    ("Give me a synonym for 'happy'.",                                     "simple"),
    ("What year was Python created?",                                      "simple"),
    ("Convert 100 Fahrenheit to Celsius.",                                 "simple"),
    ("What is the plural of 'mouse'?",                                     "simple"),
    ("Summarize this in one sentence: The dog ran across the field.",      "simple"),

    # MEDIUM (7 cases)
    ("Compare SQL and NoSQL databases and when to use each.",              "medium"),
    ("Write a Python function that reverses a linked list.",               "medium"),
    ("Explain how HTTPS works in simple terms.",                           "medium"),
    ("Draft a professional email asking for a project deadline extension.","medium"),
    ("What are the pros and cons of remote work?",                         "medium"),
    ("Explain the difference between authentication and authorization.",   "medium"),
    ("Write a regex to validate an email address and explain it.",         "medium"),

    # COMPLEX (5 cases)
    ("Design a fault-tolerant microservices architecture for an e-commerce platform with 5M daily users.", "complex"),
    ("Debug this system: requests randomly fail under load, latency spikes to 10s, no obvious errors in logs.", "complex"),
    ("Implement a role-based access control system with FastAPI and PostgreSQL.", "complex"),
    ("Write a technical deep-dive comparing Redis and Memcached for caching strategies.", "complex"),
    ("Analyze the implications of the CAP theorem on distributed database design.", "complex"),
]

# Edge cases
EDGE_CASES = [
    ("",                                           "simple"),   # empty string
    ("   ",                                        "simple"),   # whitespace only
    ("a" * 2500,                                   "simple"),   # very long (>2000 chars) — truncated gibberish
    ("¿Cuál es la capital de España?",             "simple"),   # non-English simple
    ("Diseña una arquitectura de microservicios.", "complex"),  # non-English complex
]


class TestClassifierAccuracy:

    def test_accuracy_on_labeled_set(self):
        correct = 0
        results = []

        for prompt, expected in LABELED_PROMPTS:
            actual = classify_prompt(prompt)
            passed = actual == expected
            if passed:
                correct += 1
            results.append((passed, expected, actual, prompt[:50]))

        accuracy = correct / len(LABELED_PROMPTS)

        # Print breakdown for visibility
        print(f"\n--- Classifier Accuracy Report ---")
        for passed, expected, actual, prompt in results:
            status = "PASS" if passed else "FAIL"
            print(f"[{status}] expected={expected:>8} got={actual:>8}  {prompt}")
        print(f"\nAccuracy: {correct}/{len(LABELED_PROMPTS)} = {accuracy:.0%}")

        assert accuracy >= 0.80, f"Accuracy {accuracy:.0%} is below the 80% threshold"

    def test_output_is_always_valid_tag(self):
        valid = {"simple", "medium", "complex"}
        for prompt, _ in LABELED_PROMPTS:
            result = classify_prompt(prompt)
            assert result in valid, f"Invalid tag '{result}' for prompt: {prompt[:50]}"


class TestEdgeCases:

    def test_empty_string(self):
        assert classify_prompt("") == "simple"

    def test_whitespace_only(self):
        assert classify_prompt("   ") == "simple"

    def test_very_long_prompt(self):
        long_prompt = "explain machine learning " * 200  # ~5000 chars
        result = classify_prompt(long_prompt)
        assert result in {"simple", "medium", "complex"}

    def test_non_english_simple(self):
        result = classify_prompt("¿Cuál es la capital de España?")
        assert result in {"simple", "medium", "complex"}

    def test_non_english_complex(self):
        result = classify_prompt("Diseña una arquitectura de microservicios escalable.")
        assert result in {"simple", "medium", "complex"}


class TestLatency:

    def test_average_latency_under_2_seconds(self):
        test_prompts = [
            "What is 2 + 2?",
            "Explain REST APIs.",
            "What is the capital of Germany?",
            "Write a Python fibonacci function.",
            "What does CPU stand for?",
            "Compare Docker and VMs.",
            "Translate hello to Spanish.",
            "Design a distributed cache.",
            "What year was the internet invented?",
            "Explain OAuth2 flow.",
        ]

        times = []
        for prompt in test_prompts:
            start = time.time()
            classify_prompt(prompt)
            times.append(time.time() - start)

        avg = sum(times) / len(times)
        print(f"\nAverage latency: {avg:.3f}s over {len(times)} calls")
        assert avg < 5.0, f"Average latency {avg:.2f}s exceeds 2s threshold"