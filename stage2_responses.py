"""
stage2_responses.py — LLM Response Generation
PRIMARY: Vertex AI Gemini 2.5 Flash (via ADC)
FALLBACK: Groq llama-3.1-8b

FIX: max_tokens reduced from 6000 → 2500 in both call sites
     (6000 was too aggressive for fresh Vertex quota)
"""
import os, json, argparse, re
from datetime import datetime
from config import (
    CATEGORIES, QUERIES_DIR, RESPONSES_DIR,
    SAVE_EVERY, STAGE2_PRIMARY, GROUNDING_CATEGORIES
)
from llm_client import query_llm

SYSTEM = """You are an expert AI assistant generating rich, STRUCTURED responses for a UI generation system.
Your response will be directly converted into a visual mobile UI screen — structure it accordingly.

MANDATORY FORMAT:
1. ## Title — clear heading
2. Short intro (1-2 sentences max)
3. Structured content using the MOST suitable format:
   - Comparisons → markdown tables
   - Product/travel results → cards or option sections
   - Procedures → numbered steps
   - Informational topics → concise sections with headers

RICH UI ELEMENTS:
- Include Image URLs when products, places, food, travel, media, or visual items are discussed
- Include Action links/buttons when booking, shopping, navigation, downloads, or external actions are relevant
- Include Icons when useful for UI clarity
- Include Sources/references for factual or research-based topics
- Use tables whenever comparing multiple items

CONTENT RULES:
- Use real product names and realistic pricing
- Include ratings, specs, locations, schedules, or dates when relevant
- Prefer concise UI-friendly sections over long prose
- Use markdown formatting naturally

OPTIONAL ENHANCEMENTS:
Image: https://...
Icon: https://cdn.jsdelivr.net/...
Action: [Button: Label] https://...
Source: Title - https://...

FORBIDDEN:
- Large unstructured paragraphs
- Repetitive filler
- Fake placeholder text
"""

CATEGORY_HINTS = {
    "product_lookup":        "spec table, price on Flipkart/Amazon/Croma, pros/cons, buy buttons with real URLs",
    "comparison":            "detailed comparison table (5+ columns), winner per category, recommendation",
    "booking":               "3 option cards (price/ETA/rating), form fields, steps, DateTimeInput for dates",
    "weather":               "5-day table (day/temp/rain/wind/UV), hourly today, icons, links to weather service",
    "recipe":                "ingredient table (item/quantity/notes), numbered steps, nutrition table, prep/cook time",
    "travel":                "day-wise itinerary table, cost breakdown, transport options, hotel cards with links",
    "calculation":           "formula, result table with breakdown, amortization if loan, comparison scenarios",
    "navigation":            "route options table (mode/time/cost), step-by-step directions, Google Maps link",
    "education":             "topic breakdown table, resource comparison (format/depth/cost), study plan schedule",
    "data_visualization":    "data table with metrics, trend description, chart type recommendation, filter options",
    "technical_support":     "error explanation, step-by-step fix with code blocks, prevention, reference links",
    "information_retrieval": "key facts table, comparison if multiple options, source links, action buttons",
    "status_check":          "timeline of events (checklist/stepper), current status badge, map if location, contact",
    "research_analysis":     "findings table (study/methodology/result), trend summary, key stats, source links",
    "creative_writing":      "generated content in a preview card, tone/style options, word count, copy button",
    "qr_scanner":            "QR preview card, customization options (color/logo), scan analytics table, download",
    "media_playback":        "media cards with ratings/duration/platform, play buttons, genre filter chips",
    "entertainment":         "event cards with date/venue/price, ticket options, map, booking form",
    "planning":              "timeline/Stepper for phases, checklist cards, budget breakdown table, calendar",
    "productivity":          "schedule table/Stepper, task cards with priority, OKR breakdown, progress bars",
    "localization":          "map with pins, business cards (hours/rating/distance), filter chips, directions",
    "event_schedule":        "multi-track table (time/session/room/speaker), filter by topic, registration buttons",
    "documentation":         "code blocks with syntax, parameter table, example cards, copy buttons, source links",
}


def make_prompt(query: str, category: str) -> str:
    hint = CATEGORY_HINTS.get(
        category,
        "structured sections, comparison table if applicable, action buttons, image URLs"
    )
    return f"""Category: {category.upper().replace("_", " ")}
User Query: {query}

Category-specific format hint: {hint}

Generate a RICH, STRUCTURED response following the system prompt format exactly.
- Use ## headers for each section
- Include at least 1 comparison table with real data
- Include 2-3 Action: [Button: Label] URL lines with REAL URLs
- Include Image: https://loremflickr.com/600/400/KEYWORD URLs for each item
- Min length: 300 words
- All data must be specific and real (real product names, real prices, real URLs)"""


def validate_response(response: str) -> tuple:
    """Relaxed validation for rich UI dataset generation"""

    if not response:
        return False, "Empty response"

    text = response.strip()

    # Basic size checks
    if len(text) < 500:
        return False, f"Too short ({len(text)} chars)"

    if len(text.split()) < 70:
        return False, f"Too few words ({len(text.split())})"

    # Flexible structure detection
    structure_score = 0

    # Headers
    if "##" in text or "#" in text:
        structure_score += 1

    # Lists/tables
    if "|" in text or "-" in text or re.search(r'\d+\.', text):
        structure_score += 1

    # Links/actions
    if "http" in text or "www." in text:
        structure_score += 1

    # Images
    if "Image:" in text or "loremflickr" in text:
        structure_score += 1

    # UI richness
    ui_words = [
        "table", "price", "rating", "button",
        "compare", "specs", "card", "steps",
        "schedule", "plan", "details"
    ]

    if any(w in text.lower() for w in ui_words):
        structure_score += 1

    if structure_score < 2:
        return False, f"Low structure score ({structure_score})"

    return True, "OK"

def process_category(category: str, limit: int = None) -> int:
    q_path = os.path.join(QUERIES_DIR,   f"{category}.json")
    r_path = os.path.join(RESPONSES_DIR, f"{category}.json")

    if not os.path.exists(q_path):
        print(f"  [{category}] No queries file — run stage1 first")
        return 0

    with open(q_path) as f:
        queries = json.load(f).get("queries", [])
    if limit:
        queries = queries[:limit]

    existing = {}
    if os.path.exists(r_path):
        with open(r_path) as f:
            for r in json.load(f).get("responses", []):
                if r.get("response") and r.get("valid", True):
                    existing[r["query"]] = r

    to_do = [q for q in queries if q not in existing]

    print(f"\n{'='*60}")
    use_grounding = category in GROUNDING_CATEGORIES
    print(f"Category: {category} | done={len(existing)} | todo={len(to_do)} "
          f"| grounding={'ON' if use_grounding else 'off'}")

    if not to_do:
        print("  All done! ✓")
        return len(existing)

    results = list(existing.values())

    for i, query in enumerate(to_do):
        print(f"  [{i+1}/{len(to_do)}] {query[:70]}...", flush=True)
        try:
            response = query_llm(
                prompt=make_prompt(query, category),
                system_prompt=SYSTEM,
                data_source=STAGE2_PRIMARY,
                max_tokens=2500,              # FIX: was 6000, reduced to 2500
                temperature=0.7,
                use_grounding=use_grounding,
            )

            is_valid, reason = validate_response(response)

            if not is_valid:
                print(f"    Quality FAIL: {reason} — retrying")
                response = query_llm(
                    prompt=make_prompt(query, category) +
                           "\n\nIMPORTANT: Response MUST be 300+ words with ## headers and a table.",
                    system_prompt=SYSTEM,
                    data_source=STAGE2_PRIMARY,
                    max_tokens=2500,          # FIX: was 6000, reduced to 2500
                    temperature=0.6,
                    use_grounding=use_grounding,
                )
                is_valid, reason = validate_response(response)

            results.append({
                "query":        query,
                "response":     response if is_valid else None,
                "valid":        is_valid,
                "quality_note": reason,
                "category":     category,
                "grounding":    use_grounding,
                "word_count":   len(response.split()) if response else 0,
                "generated_at": datetime.now().isoformat(),
            })
            status = "✓" if is_valid else "⚠ INVALID"
            print(f"    -> {status} ({len(response)} chars, {len(response.split())} words)")

        except Exception as e:
            results.append({
                "query": query, "response": None, "valid": False,
                "error": str(e), "category": category,
            })
            print(f"    -> FAILED: {str(e)[:100]}")

        if (i + 1) % SAVE_EVERY == 0 or (i + 1) == len(to_do):
            order = {q: idx for idx, q in enumerate(queries)}
            results.sort(key=lambda x: order.get(x["query"], 9999))
            valid_count = sum(1 for r in results if r.get("response"))
            with open(r_path, "w") as f:
                json.dump({
                    "category":     category,
                    "count":        len(results),
                    "valid_count":  valid_count,
                    "generated_at": datetime.now().isoformat(),
                    "responses":    results,
                }, f, indent=2)
            print(f"  [saved {valid_count}/{len(results)} valid]")

    return sum(1 for r in results if r.get("response"))


def main():
    parser = argparse.ArgumentParser(description="Stage 2: Response Generation")
    parser.add_argument("--category", help="Single category to process")
    parser.add_argument("--limit",    type=int, help="Max queries per category")
    parser.add_argument("--dry-run",  action="store_true")
    args = parser.parse_args()

    cats = {args.category: CATEGORIES[args.category]} if args.category else CATEGORIES

    if args.dry_run:
        print(f"\nDry run — {len(cats)} categories (PRIMARY: {STAGE2_PRIMARY})")
        for cat in cats:
            path = os.path.join(RESPONSES_DIR, f"{cat}.json")
            done = 0
            if os.path.exists(path):
                with open(path) as f:
                    done = json.load(f).get("valid_count", 0)
            g = "🌐 grounding" if cat in GROUNDING_CATEGORIES else "  local"
            print(f"  {cat:<30} valid={done}  {g}")
        return

    print(f"\nStage 2: Generating responses (PRIMARY: {STAGE2_PRIMARY})")
    print("Grounding categories:", sorted(GROUNDING_CATEGORIES) or ["none — disabled"])
    total = 0
    for cat in cats:
        total += process_category(cat, limit=args.limit)

    print(f"\n{'='*60}")
    print(f"Stage 2 Complete: {total} valid responses")


if __name__ == "__main__":
    main()