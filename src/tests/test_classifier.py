import csv
import time
import pathlib
import pytest
from collections import Counter
from app.classifier import classify_prompt

pytestmark = pytest.mark.integration

_DATA_DIR = pathlib.Path(__file__).parent.parent / "data"
_VALID_TAGS = {"simple", "medium", "complex"}


def _load_eval_prompts():
    """300 human-labeled prompts from eval_prompts.csv."""
    rows = []
    with open(_DATA_DIR / "eval_prompts.csv", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            label = row["human_label"].strip()
            if label in _VALID_TAGS:
                rows.append((row["prompt"].strip(), label))
    return rows


class TestClassifierAccuracy:

    def test_accuracy_on_eval_set(self):
        labeled = _load_eval_prompts()
        correct = 0
        misses = []
        confusion = Counter()

        for prompt, expected in labeled:
            actual = classify_prompt(prompt)
            confusion[(expected, actual)] += 1
            if actual == expected:
                correct += 1
            else:
                misses.append((expected, actual, prompt[:70]))

        accuracy = correct / len(labeled)

        tiers = ("simple", "medium", "complex")
        print(f"\n=== Classifier Accuracy: {correct}/{len(labeled)} = {accuracy:.0%} ===\n")
        print("Confusion matrix (rows=human_label, cols=classifier):")
        print(f"{'':>10}  {'simple':>8}  {'medium':>8}  {'complex':>8}")
        for tier in tiers:
            print(f"  {tier:>8}  " + "  ".join(f"{confusion[(tier, p)]:>8}" for p in tiers))

        if misses:
            print(f"\nFirst 20 misses:")
            for expected, actual, prompt in misses[:20]:
                print(f"  expected={expected:<8} got={actual:<8} {prompt}")

        assert accuracy >= 0.75, (
            f"Accuracy {accuracy:.0%} is below 75% on eval set — classifier may be broken."
        )

    def test_output_is_always_valid_tag(self):
        for prompt, _ in _load_eval_prompts()[:30]:
            result = classify_prompt(prompt)
            assert result in _VALID_TAGS, f"Invalid tag '{result}' for: {prompt[:60]}"


class TestEdgeCases:

    def test_empty_string(self):
        assert classify_prompt("") == "simple"

    def test_whitespace_only(self):
        assert classify_prompt("   ") == "simple"

    def test_very_long_prompt(self):
        result = classify_prompt("explain machine learning " * 200)
        assert result in _VALID_TAGS

    def test_non_english_simple(self):
        assert classify_prompt("¿Cuál es la capital de España?") in _VALID_TAGS

    def test_non_english_complex(self):
        assert classify_prompt("Diseña una arquitectura de microservicios escalable.") in _VALID_TAGS


class TestLatency:

    def test_average_latency_under_10_seconds(self):
        prompts = [
            "What is 2 + 2?",
            "Explain REST APIs.",
            "What is the capital of Germany?",
            "Write a Python fibonacci function.",
            "Compare Docker and VMs.",
        ]
        times = []
        for prompt in prompts:
            start = time.time()
            classify_prompt(prompt)
            times.append(time.time() - start)

        avg = sum(times) / len(times)
        print(f"\nAverage latency: {avg:.3f}s over {len(times)} calls")
        assert avg < 10.0, f"Average latency {avg:.2f}s exceeds 10s"
