import sys
sys.path.append(".")

import time
import random
from app.database import get_connection
from app.cost import calculate_cost, calculate_cost_saved, MODEL_FOR_TAG

# Realistic production distribution
# 70% simple, 20% medium, 10% complex
SEED_REQUESTS = [
    # SIMPLE (14 requests)
    ("What is the capital of France?",                    "simple"),
    ("What does API stand for?",                          "simple"),
    ("Translate 'good morning' to Spanish.",              "simple"),
    ("What year was Python created?",                     "simple"),
    ("What is 15% of 200?",                               "simple"),
    ("Give me a synonym for 'fast'.",                     "simple"),
    ("What is the plural of 'mouse'?",                    "simple"),
    ("Convert 100 USD to EUR approximately.",             "simple"),
    ("What does HTTP stand for?",                         "simple"),
    ("What is the capital of Japan?",                     "simple"),
    ("Summarize this in one sentence: The sky is blue.",  "simple"),
    ("What year did World War 2 end?",                    "simple"),
    ("What is the boiling point of water in Celsius?",    "simple"),
    ("What does RAM stand for?",                          "simple"),

    # MEDIUM (4 requests)
    ("Compare REST and GraphQL and when to use each.",                     "medium"),
    ("Explain how HTTPS works in simple terms.",                           "medium"),
    ("What are the pros and cons of microservices architecture?",          "medium"),
    ("Write a Python function to find duplicates in a list.",              "medium"),

    # COMPLEX (2 requests)
    ("Design a fault-tolerant microservices architecture for e-commerce.", "complex"),
    ("Build a JWT authentication system with refresh token rotation.",     "complex"),
]

# Realistic token counts per tier
TOKEN_RANGES = {
    "simple":  (input_range := (20, 60),   (10, 50)),
    "medium":  ((60, 150),  (100, 400)),
    "complex": ((150, 300), (400, 1200)),
}

def seed():
    conn = get_connection()
    cur = conn.cursor()

    # Wipe existing data
    cur.execute("TRUNCATE TABLE requests RESTART IDENTITY;")
    conn.commit()
    print("Cleared existing requests.")

    for prompt, tag in SEED_REQUESTS:
        model = MODEL_FOR_TAG[tag]
        input_range, output_range = TOKEN_RANGES[tag]
        input_tokens  = random.randint(*input_range)
        output_tokens = random.randint(*output_range)
        cost          = calculate_cost(model, input_tokens, output_tokens)
        cost_saved    = calculate_cost_saved(model, input_tokens, output_tokens)
        latency_ms    = random.randint(200, 2000) if tag == "simple" else random.randint(1000, 8000)
        escalated     = False

        cur.execute("""
            INSERT INTO requests (
                raw_prompt, difficulty_tag, model_used,
                input_tokens, output_tokens, cost_usd,
                latency_ms, escalated, cost_saved_usd,
                created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s,
                NOW() - INTERVAL '%s seconds'
            )
        """, (
            prompt, tag, model,
            input_tokens, output_tokens, cost,
            latency_ms, escalated, cost_saved,
            random.randint(0, 7200)   # spread over last 2 hours
        ))

    conn.commit()
    cur.close()
    conn.close()

    total = len(SEED_REQUESTS)
    simple  = sum(1 for _, t in SEED_REQUESTS if t == "simple")
    medium  = sum(1 for _, t in SEED_REQUESTS if t == "medium")
    complex_ = sum(1 for _, t in SEED_REQUESTS if t == "complex")
    print(f"Seeded {total} requests: {simple} simple, {medium} medium, {complex_} complex")

if __name__ == "__main__":
    seed()