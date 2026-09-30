"""
inference.py — Standalone demo/inference script for the A2UI LLM UI Generator.

WHAT THIS DOES
    Takes a natural language query (e.g. "5-day weather forecast for Bengaluru"),
    sends it to the finetuned Qwen2.5-Coder-3B model (served locally via Ollama),
    and prints/saves the generated A2UI v0.9 JSON UI layout.

    This is the minimal reproducible path to verify the finetuned model works —
    it does NOT require the Flask backend or the web frontend. Use this to
    sanity-check the model in isolation.

PREREQUISITES
    1. Ollama installed:            https://ollama.com/download
    2. The finetuned GGUF model registered with Ollama:
           ollama create a2ui-model -f Modelfile
       (Modelfile contents: `FROM ./qwen2.5-coder-3b-instruct.Q4_K_M.gguf`)
    3. Ollama running:               ollama serve
       (usually starts automatically after installation)
    4. Python packages:              pip install requests

USAGE
    # Single query, prints JSON to stdout
    python inference.py --query "Show me a 5-day weather forecast for Bengaluru"

    # Save output to a file instead of printing
    python inference.py --query "Book a cab from hostel to airport" --out result.json

    # Run the built-in example suite (5 sample queries across categories)
    python inference.py --demo

OUTPUT
    A JSON object:
        {
          "success": true/false,
          "a2ui_json": {...},       # the generated UI layout (A2UI v0.9 schema)
          "category": "weather",    # auto-detected category used for style hints
          "generation_time": 46.2   # seconds
        }
"""
import argparse
import json
import re
import sys
import time

import requests

# ── Configuration ────────────────────────────────────────────────────────
OLLAMA_URL   = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "a2ui-model"   # must match: ollama create a2ui-model -f Modelfile

SYSTEM_PROMPT = """You are an A2UI v0.9 UI generation model.

Your job is to convert the supplied user query and structured response
into a valid A2UI v0.9 JSON array.

CRITICAL RULES:
1. Output ONLY valid JSON.
2. The output MUST be a JSON array with exactly two top-level objects:
   [{"createSurface": {...}, "version": "v0.9"}, {"updateComponents": {...}}]
3. Do NOT output Markdown, code fences, or explanations.
4. Do not create duplicate component IDs.
5. Every child ID must reference an existing component.
6. Keep the generated UI faithful to the supplied response.
7. Generate a complete screen, not a partial fragment.
"""

# Category -> visual style mapping (kept in sync with config.py / stage5's training data)
CATEGORY_STYLES = {
    "media_playback": "spotify", "entertainment": "spotify",
    "product_lookup": "amazon", "comparison": "amazon",
    "booking": "airbnb", "travel": "airbnb",
    "navigation": "maps", "localization": "maps",
    "recipe": "swiggy",
    "education": "notion", "documentation": "notion",
    "productivity": "notion", "planning": "notion",
    "research_analysis": "notion", "creative_writing": "notion",
    "weather": "minimal", "calculation": "minimal",
    "data_visualization": "minimal", "event_schedule": "minimal",
    "information_retrieval": "minimal", "status_check": "minimal",
    "technical_support": "minimal", "qr_scanner": "minimal",
}
STYLE_TOKENS = {
    "spotify":  "Spotify dark: dark background #121212, green accent #1DB954, pill buttons",
    "amazon":   "Amazon style: white background, orange accent #FF9900, bold price text",
    "airbnb":   "Airbnb style: white background, pink-red accent #FF385C, rounded cards",
    "maps":     "Maps style: white background, blue accent #1A73E8, place cards",
    "swiggy":   "Food delivery style: white background, orange accent, price and Add button",
    "notion":   "Notion style: clean white background, blue accents, minimal borders",
    "minimal":  "Clean minimal UI: white background, blue accent, clear hierarchy",
}
CATEGORY_KEYWORDS = {
    "weather": ["weather", "forecast", "rain", "temperature"],
    "recipe": ["recipe", "cook", "ingredient", "dish"],
    "travel": ["trip", "itinerary", "travel", "vacation"],
    "booking": ["book", "cab", "flight ticket", "reserve", "ride"],
    "product_lookup": ["laptop", "phone", "buy", "price of", "under"],
    "comparison": ["vs", "compare", "versus"],
    "navigation": ["route", "directions", "distance to"],
    "productivity": ["to-do", "todo", "task list", "schedule"],
    "entertainment": ["movie", "song", "playlist", "watch"],
}


def guess_category(query: str) -> str:
    q = query.lower()
    for cat, kws in CATEGORY_KEYWORDS.items():
        if any(kw in q for kw in kws):
            return cat
    return "information_retrieval"


def build_prompt(query: str, category: str) -> str:
    style = CATEGORY_STYLES.get(category, "minimal")
    desc = STYLE_TOKENS.get(style, STYLE_TOKENS["minimal"])
    return (
        f"Category: {category}\nStyle: {style}\nStyle description: {desc}\n\n"
        f"User Query: {query}\n\n"
        f"Generate the complete A2UI v0.9 JSON array for this screen."
    )


def extract_json(raw: str):
    """Best-effort JSON extraction — handles markdown fences and partial noise."""
    if not raw:
        return None
    raw = raw.strip()
    for candidate in (raw, raw.replace("```json", "").replace("```", "").strip()):
        try:
            return json.loads(candidate)
        except Exception:
            pass
    m = re.search(r"\[.*\]", raw, re.DOTALL)
    if m:
        try:
            return json.loads(m.group())
        except Exception:
            pass
    return None


def run_inference(query: str, num_predict: int = 2500) -> dict:
    """Sends one query to the local Ollama model and returns a structured result.
    Automatically retries with a higher token budget if the model gets cut off
    mid-generation (Ollama reports this as done_reason == "length")."""
    category = guess_category(query)
    prompt = build_prompt(query, category)

    def _call(budget):
        return requests.post(
            OLLAMA_URL,
            json={
                "model": OLLAMA_MODEL,
                "system": SYSTEM_PROMPT,
                "prompt": prompt,
                "stream": False,
                "format": "json",
                "options": {"num_predict": budget, "temperature": 0.0, "num_ctx": 8192},
            },
            timeout=300,
        )

    t0 = time.time()
    try:
        response = _call(num_predict)
        response.raise_for_status()
        body = response.json()
        raw = body.get("response", "")

        # Truncated mid-generation — retry once with a much bigger budget
        # instead of returning a guaranteed-invalid partial JSON.
        if body.get("done_reason") == "length":
            print(f"    Truncated at {num_predict} tokens — retrying with 4096")
            response = _call(4096)
            response.raise_for_status()
            raw = response.json().get("response", "")
    except requests.exceptions.ConnectionError:
        return {
            "success": False,
            "error": "Could not reach Ollama at http://localhost:11434 — "
                     "is `ollama serve` running, and did you run "
                     "`ollama create a2ui-model -f Modelfile`?",
        }
    except Exception as e:
        return {"success": False, "error": f"Ollama call failed: {e}"}

    elapsed = round(time.time() - t0, 2)
    parsed = extract_json(raw)

    if parsed is not None:
        return {
            "success": True,
            "a2ui_json": parsed,
            "category": category,
            "generation_time": elapsed,
        }
    return {
        "success": False,
        "error": "Model output was not valid JSON",
        "raw_output": raw[:1000],
        "category": category,
        "generation_time": elapsed,
    }


DEMO_QUERIES = [
    "Show me a 5-day weather forecast for Bengaluru",
    "Book a cab from hostel to airport at 6am tomorrow",
    "Compare iPhone 15 vs Samsung S24",
    "Recipe for Paneer Masala for 4 people with steps",
    "Top laptops under ₹60,000",
]


def main():
    parser = argparse.ArgumentParser(description="A2UI LLM UI Generator — inference demo")
    parser.add_argument("--query", type=str, help="Natural language query to generate a UI for")
    parser.add_argument("--out", type=str, help="Optional file path to save JSON output")
    parser.add_argument("--demo", action="store_true", help="Run all built-in demo queries")
    args = parser.parse_args()

    if args.demo:
        print(f"Running {len(DEMO_QUERIES)} demo queries...\n")
        results = []
        for q in DEMO_QUERIES:
            print(f"-> {q}")
            result = run_inference(q)
            status = "OK" if result.get("success") else "FAILED"
            print(f"   [{status}] {result.get('generation_time', '?')}s\n")
            results.append({"query": q, **result})
        out_path = args.out or "demo_results.json"
        with open(out_path, "w") as f:
            json.dump(results, f, indent=2)
        print(f"Saved all results to {out_path}")
        return

    if not args.query:
        print("Provide --query \"your text\" or use --demo to run the built-in examples.")
        sys.exit(1)

    print(f"Query: {args.query}")
    print("Generating (this can take 30-90s on a free-tier GPU/CPU)...\n")
    result = run_inference(args.query)

    if args.out:
        with open(args.out, "w") as f:
            json.dump(result, f, indent=2)
        print(f"Saved to {args.out}")
    else:
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()