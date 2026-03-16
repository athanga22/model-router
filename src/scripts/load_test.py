"""
Load test: hit the /v1/chat API with a sampled set of prompts (70/20/10 simple/medium/complex).
Each prompt is sent exactly once. Slower than run_eval.py: run_eval calls the classifier only
with 0.1s sleep; this script calls the full pipeline with 0.5s delay between requests.
"""
import os
import time
import pandas as pd
import httpx
from dotenv import load_dotenv

load_dotenv()

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
CSV_PATH = os.path.join(os.path.dirname(__file__), "../data/eval_prompts.csv")

DISTRIBUTION = {"simple": 70, "medium": 20, "complex": 10}

DELAY_BETWEEN_REQUESTS = 0.5  # seconds


def sample_prompts(csv_path: str) -> list[dict]:
    """Sample prompts by label (70/20/10). Each prompt appears at most once (no replacement)."""
    df = pd.read_csv(csv_path)
    df = df.rename(columns={"human_label": "label"})
    df = df[["prompt", "label"]].dropna()

    sampled = []
    for label, count in DISTRIBUTION.items():
        pool = df[df["label"] == label]
        if len(pool) < count:
            print(f"WARNING: Only {len(pool)} '{label}' prompts available, using all of them.")
            count = len(pool)
        sampled.append(pool.sample(n=count, random_state=42))

    return pd.concat(sampled).sample(frac=1, random_state=42).to_dict("records")


def fire(prompt: str, idx: int, total: int) -> dict:
    url = f"{API_BASE_URL}/v1/chat"
    try:
        resp = httpx.post(url, json={"prompt": prompt}, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        print(
            f"[{idx+1}/{total}] {data['difficulty_tag']:8s} → {data['model_used']:25s} "
            f"${data['cost_usd']:.6f}  {'escalated' if data['escalated'] else ''}"
        )
        return data
    except Exception as e:
        print(f"[{idx+1}/{total}] ERROR: {e}")
        return {}


def main():
    print(f"Loading prompts from {CSV_PATH}...")
    prompts = sample_prompts(CSV_PATH)
    total   = len(prompts)
    print(f"Firing {total} requests at {API_BASE_URL}\n")

    results   = []
    total_cost  = 0.0
    total_saved = 0.0

    for idx, row in enumerate(prompts):
        result = fire(row["prompt"], idx, total)
        if result:
            results.append(result)
            total_cost += result.get("cost_usd", 0)
            total_saved += result.get("cost_saved_usd", 0)
        time.sleep(DELAY_BETWEEN_REQUESTS)

    print(f"\n{'─'*50}")
    print(f"Done.  {len(results)}/{total} succeeded")
    print(f"Total cost:   ${total_cost:.4f}")

    # Blocking ChatResponse has no cost_saved_usd; savings estimated below from gpt4o equiv
    model_counts = {}
    for r in results:
        m = r.get("model_used", "unknown")
        model_counts[m] = model_counts.get(m, 0) + 1

    print(f"Model usage:  {model_counts}")
    gpt4o_equiv = sum(
        (0.0025 * 200 / 1000) + (0.010 * 300 / 1000)  # rough 200 in / 300 out avg
        for _ in results
    )
    print(f"GPT-4o equiv: ${gpt4o_equiv:.4f}")
    print(f"Est. savings: ${gpt4o_equiv - total_cost:.4f}")
    print(f"{'─'*50}")
    print("Refresh the dashboard to see updated metrics.")


if __name__ == "__main__":
    main()