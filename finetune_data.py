"""
stage5_build_finetune_data.py — Build SFT dataset from your existing triplets

Reads data/responses/*.json + data/a2ui_json/*.json, pairs them up wherever
both are valid for the same query, and writes a single JSONL file in the
{"prompt": ..., "completion": ...} format trl's SFTTrainer expects.

The prompt reconstructs exactly what stage3_a2ui_json.py currently sends to
the API (query + response + style hint), so the finetuned model learns to
do stage3's job locally — no more Gemini/Vertex calls for that stage.

Run: python stage5_build_finetune_data.py
Output: data/finetune/train.jsonl, data/finetune/val.jsonl
"""
import os, json, random
from config import (
    CATEGORIES, RESPONSES_DIR, A2UI_JSON_DIR,
    CATEGORY_STYLES, STYLE_TOKENS,
)

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "finetune")
os.makedirs(OUT_DIR, exist_ok=True)

VAL_FRACTION = 0.05  # 5% held out for eval

SYSTEM = (
    "Convert a user query + structured response into a rich A2UI v0.9 JSON UI array. "
    "Output ONLY the raw JSON array. No markdown, no explanation, no code fences."
)


def build_prompt(query: str, response: str, category: str) -> str:
    style_name = CATEGORY_STYLES.get(category, "minimal")
    tok = STYLE_TOKENS.get(style_name, STYLE_TOKENS["minimal"])
    return (
        f"Category: {category.upper().replace('_', ' ')}\n"
        f"Style: {style_name} — {tok['desc']}\n\n"
        f"User Query: {query}\n\n"
        f"Structured Response:\n{response}\n\n"
        f"Generate the A2UI v0.9 JSON array for this screen."
    )


def main():
    examples = []

    for cat in CATEGORIES:
        r_path = os.path.join(RESPONSES_DIR, f"{cat}.json")
        a_path = os.path.join(A2UI_JSON_DIR, f"{cat}.json")
        if not (os.path.exists(r_path) and os.path.exists(a_path)):
            continue

        with open(r_path) as f:
            responses = {
                r["query"]: r["response"]
                for r in json.load(f).get("responses", [])
                if r.get("response") and r.get("valid", True)
            }
        with open(a_path) as f:
            a2ui_results = json.load(f).get("results", [])

        cat_count = 0
        for r in a2ui_results:
            v = r.get("validation", {})
            if not v.get("valid"):
                continue
            q = r["query"]
            if q not in responses:
                continue

            prompt = build_prompt(q, responses[q], cat)
            completion = json.dumps(r["a2ui_json"], separators=(",", ":"))

            examples.append({
                "system":     SYSTEM,
                "prompt":     prompt,
                "completion": completion,
                "category":   cat,
            })
            cat_count += 1

        print(f"  {cat:<25} {cat_count} triplets")

    random.seed(42)
    random.shuffle(examples)

    n_val = max(1, int(len(examples) * VAL_FRACTION))
    val_set, train_set = examples[:n_val], examples[n_val:]

    train_path = os.path.join(OUT_DIR, "train.jsonl")
    val_path   = os.path.join(OUT_DIR, "val.jsonl")

    with open(train_path, "w") as f:
        for ex in train_set:
            f.write(json.dumps(ex) + "\n")
    with open(val_path, "w") as f:
        for ex in val_set:
            f.write(json.dumps(ex) + "\n")

    print(f"\nTotal triplets: {len(examples)}")
    print(f"Train: {len(train_set)} -> {train_path}")
    print(f"Val:   {len(val_set)} -> {val_path}")


if __name__ == "__main__":
    main()