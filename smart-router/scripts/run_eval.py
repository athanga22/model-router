"""
Run the classifier against the 300-prompt eval dataset.
Collects predictions and saves results for metric computation.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import time
import pandas as pd
from dotenv import load_dotenv
from app.classifier import classify_prompt

load_dotenv()

INPUT  = "data/eval_prompts.csv"
OUTPUT = "data/eval_results.csv"

SLEEP = float(os.getenv("EVAL_SLEEP", "0.1"))
MAX_RETRIES = int(os.getenv("EVAL_MAX_RETRIES", "5"))
# If set, only run on first N prompts (e.g. EVAL_LIMIT=50).
LIMIT = os.getenv("EVAL_LIMIT")
LIMIT = int(LIMIT) if LIMIT else None


def _norm(s):
    return str(s).strip().lower()


def classify_with_backoff(prompt: str, index: int, total: int) -> str:
    """
    Call classify_prompt with simple exponential backoff on errors (e.g. rate limits).
    On final failure, log and fall back to 'medium' so the eval can complete.
    """
    attempt = 0
    while True:
        try:
            return classify_prompt(prompt)
        except Exception as e:
            attempt += 1
            if attempt > MAX_RETRIES:
                print(
                    f"  {index}/{total} ERROR after {MAX_RETRIES} retries: {e}. "
                    "Falling back to 'medium' and continuing.",
                    flush=True,
                )
                return "medium"

            # Exponential backoff capped at 60s
            wait = min(60.0, SLEEP * (2 ** (attempt - 1)))
            print(
                f"  {index}/{total} error: {e} — retry {attempt}/{MAX_RETRIES} in {wait:.1f}s",
                flush=True,
            )
            time.sleep(wait)


def main():
    df = pd.read_csv(INPUT)
    if LIMIT is not None:
        df = df.head(LIMIT)
        print(f"Loaded {len(df)} prompts from {INPUT} (EVAL_LIMIT={LIMIT})", flush=True)
    else:
        print(f"Loaded {len(df)} prompts from {INPUT}", flush=True)

    predictions = []
    total = len(df)
    print("Classifying (first call may take a few seconds)...", flush=True)
    for i, row in df.iterrows():
        n = i + 1
        label = classify_with_backoff(row["prompt"], n, total)
        predictions.append(label)
        correct_so_far = sum(
            1 for j in range(n) if _norm(df.iloc[j]["human_label"]) == _norm(predictions[j])
        )
        acc = correct_so_far / n
        print(f"  {n}/{total} classified — accuracy so far: {correct_so_far}/{n} ({acc:.1%})", flush=True)

        time.sleep(SLEEP)

    df["classifier_label"] = predictions
    df.to_csv(OUTPUT, index=False)

    print(f"\nDone. Results saved to {OUTPUT}", flush=True)
    print(f"\nClassifier label distribution:", flush=True)
    print(df["classifier_label"].value_counts(), flush=True)

    correct = sum(1 for j in range(len(df)) if _norm(df.iloc[j]["human_label"]) == _norm(df.iloc[j]["classifier_label"]))
    print(f"\nRaw accuracy: {correct}/{len(df)} ({correct/len(df):.1%})", flush=True)

    tiers = ["simple", "medium", "complex"]
    confusion = {h: {c: 0 for c in tiers} for h in tiers}
    for _, row in df.iterrows():
        h = _norm(row["human_label"])
        c = _norm(row["classifier_label"])
        if h in tiers and c in tiers:
            confusion[h][c] += 1

    print("\nConfusion matrix (rows=human_label, cols=classifier):", flush=True)
    print(f"{'':>10}  {'simple':>8}  {'medium':>8}  {'complex':>8}", flush=True)
    for tier in tiers:
        print(f"  {tier:>8}  " + "  ".join(f"{confusion[tier][p]:>8}" for p in tiers), flush=True)

    print("\nMisclassified prompts:", flush=True)
    misses = df[df["human_label"].map(_norm) != df["classifier_label"].map(_norm)]
    for _, row in misses.iterrows():
        print(f"  expected={_norm(row['human_label']):<8} got={_norm(row['classifier_label']):<8} {row['prompt'][:70]}", flush=True)


if __name__ == "__main__":
    main()