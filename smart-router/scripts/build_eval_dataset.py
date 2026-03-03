"""
Build the 300-prompt evaluation dataset.
1. Pull 1000 prompts from LMSYS-Chat-1M
2. Pre-label with Claude Haiku 4.5 in batches of 50
3. Take 100 confident examples per class
4. Save to data/eval_prompts.csv for human spot-check
"""

import os
import time
import json
import pandas as pd
import anthropic
from datasets import load_dataset
from dotenv import load_dotenv

load_dotenv()

# ── Config ────────────────────────────────────────────────────────────────────
PULL_SIZE = 1000
BATCH_SIZE = 50
TARGET_PER_CLASS = 100
OUTPUT_DIR = "data"
os.makedirs(OUTPUT_DIR, exist_ok=True)

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

RUBRIC = """You are building an evaluation dataset for a prompt complexity classifier.

Classify each prompt as simple, medium, complex, or unsure using this rubric:

SIMPLE — Answer exists as a single fact or can be retrieved in one step. No reasoning chain needed.
- Single factual questions ("Who invented the telephone?", "What is the capital of Japan?")
- Basic definitions ("What does empathy mean?")
- Yes/no questions, greetings, simple conversions, basic translations
- Deciding test: Could a Wikipedia sentence or dictionary entry answer it?

MEDIUM — Requires explanation, multiple steps, or some synthesis across ideas.
- How-to explanations ("How do I make sourdough bread?", "How does a vaccine work?")
- Compare/contrast two things ("Difference between debit and credit")
- Step-by-step instructions for common tasks
- Opinion questions with moderate nuance ("Is remote work better than office work?")
- Short creative writing with basic constraints
- Deciding test: Needs a paragraph or two and some domain knowledge

COMPLEX — Requires synthesis across multiple ideas, handling ambiguity, or producing something original and substantial.
- Open-ended analysis ("What caused the fall of the Roman Empire?")
- Ethical dilemmas or philosophical questions
- Multi-constraint creative writing ("Write a story in second person, set in 1920s Paris, exploring grief")
- Strategic or planning questions with tradeoffs
- Long-form writing requiring structure, argument, and depth
- Deciding test: A small fast model would oversimplify or miss something important

UNSURE — Prompt is ambiguous, sits clearly on the boundary, is too vague to classify, or is not in English.

RULES:
- Be strict. When in doubt, label "unsure" — we want clean examples only
- Topic domain does NOT matter — cooking, finance, philosophy, relationships are all valid
- Judge by cognitive load required, not subject matter
- Respond with ONLY a valid JSON array, no preamble, no markdown fences

Format exactly:
[{"id": 0, "label": "simple"}, {"id": 1, "label": "medium"}, {"id": 2, "label": "unsure"}, ...]"""


def pull_lmsys_prompts(n: int) -> list[str]:
    """Pull n first-turn user prompts from LMSYS-Chat-1M."""
    print(f"Loading LMSYS-Chat-1M (streaming {n} prompts)...")
    dataset = load_dataset(
        "lmsys/lmsys-chat-1m",
        split="train",
        streaming=True,
        trust_remote_code=True
    )

    prompts = []
    seen = set()
    for item in dataset:
        for turn in item.get("conversation", []):
            if turn.get("role") == "user":
                text = turn.get("content", "").strip()
                if (text and
                    len(text) >= 20 and
                    len(text) <= 500 and
                    text not in seen and
                    not item.get("redacted", False) and
                    item.get("language", "English") == "English"):
                    prompts.append(text)
                    seen.add(text)
                break
        if len(prompts) >= n:
            break

    print(f"Pulled {len(prompts)} prompts from LMSYS-Chat-1M")
    return prompts


def label_batch(prompts: list[str], start_id: int) -> dict[int, str]:
    """Label a batch of prompts with Claude Haiku. Returns {id: label}."""
    prompt_block = "\n".join([
        f"[{start_id + i}] {p[:400]}"
        for i, p in enumerate(prompts)
    ])

    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            messages=[
                {
                    "role": "user",
                    "content": f"{RUBRIC}\n\nLabel these {len(prompts)} prompts:\n\n{prompt_block}"
                }
            ]
        )

        text = response.content[0].text.strip()
        # Strip markdown fences if present
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()

        results = json.loads(text)
        return {r["id"]: r["label"] for r in results}

    except Exception as e:
        print(f"\nBatch error (ids {start_id}-{start_id+len(prompts)-1}): {e}")
        return {}


def main():
    # ── Step 1: Pull prompts ──────────────────────────────────────────────────
    prompts = pull_lmsys_prompts(PULL_SIZE)

    # ── Step 2: Label in batches of 50 ───────────────────────────────────────
    total_batches = (len(prompts) + BATCH_SIZE - 1) // BATCH_SIZE
    print(f"\nLabeling {len(prompts)} prompts in {total_batches} batches of {BATCH_SIZE}...")

    all_labels = {}
    for i in range(0, len(prompts), BATCH_SIZE):
        batch = prompts[i:i + BATCH_SIZE]
        batch_num = (i // BATCH_SIZE) + 1
        print(f"  Batch {batch_num}/{total_batches} (prompts {i}-{i+len(batch)-1})...", end=" ")

        labels = label_batch(batch, start_id=i)
        all_labels.update(labels)
        print(f"got {len(labels)} labels")

        time.sleep(0.3)  # light rate limiting

    print(f"\nLabeled {len(all_labels)}/{len(prompts)} prompts successfully")

    # ── Step 3: Build dataframe ───────────────────────────────────────────────
    df = pd.DataFrame({
        "id": range(len(prompts)),
        "prompt": prompts,
        "claude_label": [all_labels.get(i, "unsure") for i in range(len(prompts))]
    })

    print("\nLabel distribution:")
    print(df["claude_label"].value_counts())

    # ── Step 4: Sample 100 per class ─────────────────────────────────────────
    classes = ["simple", "medium", "complex"]
    sampled = []

    for cls in classes:
        subset = df[df["claude_label"] == cls]
        count = len(subset)
        if count < TARGET_PER_CLASS:
            print(f"WARNING: Only {count} confident '{cls}' examples — using all of them")
            sampled.append(subset)
        else:
            sampled.append(subset.sample(n=TARGET_PER_CLASS, random_state=42))
            print(f"Sampled {TARGET_PER_CLASS} '{cls}' examples from {count} available")

    eval_df = pd.concat(sampled).reset_index(drop=True)
    eval_df["human_label"] = ""   # you fill this during spot-check
    eval_df["notes"] = ""         # optional notes

    # ── Step 5: Save ─────────────────────────────────────────────────────────
    df.to_csv(f"{OUTPUT_DIR}/lmsys_labeled_full.csv", index=False)
    eval_df.to_csv(f"{OUTPUT_DIR}/eval_prompts.csv", index=False)

    print(f"\n{'='*50}")
    print(f"DONE")
    print(f"  Full labeled set: {OUTPUT_DIR}/lmsys_labeled_full.csv ({len(df)} rows)")
    print(f"  Eval set:         {OUTPUT_DIR}/eval_prompts.csv ({len(eval_df)} rows)")
    print(f"\nNext: Open eval_prompts.csv and fill in the human_label column")


if __name__ == "__main__":
    main()