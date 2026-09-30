# import os
# print("gemini:", os.environ.get("GEMINI_API_KEY_1"))
# print("gemini:", os.environ.get("GEMINI_API_KEY_2"))
# print("gemini:", os.environ.get("GEMINI_API_KEY_3"))
# print("groq:", os.environ.get("GROQ_API_KEY_1"))
# print("groq:", os.environ.get("GROQ_API_KEY_2"))

# """
# test.py — Quick sanity check for Vertex AI connectivity
# Run this before stage2_responses.py to confirm everything works.

# Expected output: some greeting text from Gemini
# If it prints text → stage2 will work.
# If it errors → fix the error before running stage2.
# """
# from google import genai
# from google.genai import types

# # Uses ADC automatically (gcloud auth application-default login)
# # No need to set GOOGLE_APPLICATION_CREDENTIALS or any env vars
# client = genai.Client(
#     vertexai=True,
#     project="project-3524613c-385d-4472-b40",
#     location="us-central1",
# )

# # Test 1: basic call
# print("Test 1: Basic call...")
# response = client.models.generate_content(
#     model="gemini-2.5-flash",
#     contents="Say hello in one sentence.",
# )
# print(f"  OK: {response.text.strip()}")

# # Test 2: with grounding (used for weather/product/travel categories)
# print("\nTest 2: Grounding call...")
# response = client.models.generate_content(
#     model="gemini-2.5-flash",
#     contents="What is the current price of iPhone 15 in India?",
#     config=types.GenerateContentConfig(
#         tools=[types.Tool(google_search=types.GoogleSearch())],
#         max_output_tokens=500,
#     ),
# )
# print(f"  OK: {response.text[:200].strip()}...")

# print("\nAll tests passed! You can now run: python stage2_responses.py")

"""
metrics.py — Dataset Quality Metrics
Covers all 4 mentor requirements:
  1. Aesthetic metrics   — style coverage, component diversity, visual richness
  2. Agentic IR          — intent classification accuracy, query constraint density
  3. Dataset-10K         — total counts, valid rates, category distribution
  4. UI Renderer quality — component type coverage, rendering success rate

Run: python metrics.py
     python metrics.py --category information_retrieval
     python metrics.py --export metrics_report.json
"""
import os, json, argparse, re
from collections import Counter, defaultdict
from config import (
    CATEGORIES, QUERIES_DIR, RESPONSES_DIR,
    A2UI_JSON_DIR, HTML_DIR,
    CATEGORY_STYLES, STYLE_TOKENS, A2UI_COMPONENTS,
)

# ── 1. Aesthetic Metrics ──────────────────────────────────────────────────────
def aesthetic_metrics(category: str = None) -> dict:
    """
    Measures visual quality of generated A2UI JSONs:
    - Style coverage: how many categories have correct style applied
    - Component diversity: avg unique component types per screen
    - Rich component rate: % screens using Badge, Chip, Stepper, ProgressBar, Tabs
    - Image coverage: % screens with loremflickr images
    - Card density: avg Cards per screen
    """
    cats = [category] if category else list(CATEGORIES.keys())
    results = {}

    style_correct     = 0
    component_types   = []
    rich_comp_screens = 0
    image_screens     = 0
    card_counts       = []
    total_screens     = 0
    style_distribution = Counter()

    RICH_COMPONENTS = {"Badge","Chip","Stepper","ProgressBar","Tabs","Carousel","Map","Gallery"}

    for cat in cats:
        a_path = os.path.join(A2UI_JSON_DIR, f"{cat}.json")
        if not os.path.exists(a_path): continue

        with open(a_path) as f:
            data = json.load(f)

        expected_style = CATEGORY_STYLES.get(cat, "minimal")
        actual_style   = data.get("style", "unknown")

        if actual_style == expected_style:
            style_correct += 1

        valid_results = [r for r in data.get("results",[]) if r.get("validation",{}).get("valid")]
        # weight by number of screens in this category, not 1-per-file
        # (old code counted the category file once, so 16 files summed to
        # ~16 instead of reflecting all 5581 screens)
        style_distribution[actual_style] += len(valid_results)

        for r in valid_results:
            total_screens += 1
            a2ui = r.get("a2ui_json", [])
            if not a2ui or len(a2ui) < 2: continue

            comps = a2ui[1].get("updateComponents",{}).get("components",[])
            types = set(c.get("component","") for c in comps if c.get("component"))

            component_types.append(len(types))

            if types & RICH_COMPONENTS:
                rich_comp_screens += 1

            has_image = any(
                c.get("component") == "Image" and
                c.get("url","").startswith("https://loremflickr.com")
                for c in comps
            )
            if has_image:
                image_screens += 1

            n_cards = sum(1 for c in comps if c.get("component") == "Card")
            card_counts.append(n_cards)

        cat_valid = len(valid_results)
        cat_types_sum = 0
        for r in valid_results:
            a2ui = r.get("a2ui_json",[])
            if a2ui and len(a2ui) >= 2:
                comps = a2ui[1].get("updateComponents",{}).get("components",[])
                cat_types_sum += len(set(c.get("component","") for c in comps))

        results[cat] = {
            "style":           actual_style,
            "style_correct":   actual_style == expected_style,
            "valid_screens":   cat_valid,
            "avg_comp_types":  round(cat_types_sum / cat_valid, 1) if cat_valid else 0,
        }

    n_cats = len([c for c in cats if os.path.exists(os.path.join(A2UI_JSON_DIR, f"{c}.json"))])

    return {
        "metric":              "Aesthetic",
        "total_screens":       total_screens,
        "style_coverage":      f"{style_correct}/{n_cats} categories have correct style",
        "style_coverage_pct":  round(style_correct / n_cats * 100, 1) if n_cats else 0,
        "style_distribution":  dict(style_distribution),
        "avg_component_types": round(sum(component_types)/len(component_types), 1) if component_types else 0,
        "rich_component_rate": round(rich_comp_screens / total_screens * 100, 1) if total_screens else 0,
        "image_coverage_pct":  round(image_screens / total_screens * 100, 1) if total_screens else 0,
        "avg_cards_per_screen":round(sum(card_counts)/len(card_counts), 1) if card_counts else 0,
        "per_category":        results,
    }


# ── 2. Agentic IR Metrics ─────────────────────────────────────────────────────
def agentic_ir_metrics(category: str = None) -> dict:
    """
    Measures intent and query quality:
    - Intent accuracy: does response category match query category
    - Constraint density: avg constraints per query (location, price, spec, count, time)
    - Response structure rate: % responses with tables, headers, action buttons
    - Grounding usage: % responses that used Google Search grounding
    - Avg word count per response
    """
    cats = [category] if category else list(CATEGORIES.keys())

    CONSTRAINT_PATTERNS = [
        r'\$[\d,]+', r'£[\d,]+', r'₹[\d,]+',        # price
        r'\d+\s*(km|miles|mile|m\b)',                  # distance
        r'\b(under|below|less than|max|minimum|min|at least)\b',  # bounds
        r'\b\d{4}\b',                                  # year
        r'\b(GB|MB|TB|GHz|MHz|mAh|MP|inch|kg|lb)\b', # specs
        r'\b(in|near|at|from|to)\s+[A-Z][a-z]+',     # location
        r'\b\d+\s*(star|rating)',                      # rating
        r'\b(top|best|most|highest|lowest)\s+\d+',    # ranking
    ]

    total_queries = 0
    total_constraints = 0
    response_structured = 0
    response_with_table = 0
    response_with_actions = 0
    grounded_responses = 0
    total_words = 0
    total_responses = 0
    per_cat = {}

    for cat in cats:
        q_path = os.path.join(QUERIES_DIR,   f"{cat}.json")
        r_path = os.path.join(RESPONSES_DIR, f"{cat}.json")

        cat_queries      = 0
        cat_constraints  = 0
        cat_structured   = 0
        cat_grounded     = 0
        cat_words        = 0
        cat_responses    = 0

        if os.path.exists(q_path):
            with open(q_path) as f:
                queries = json.load(f).get("queries", [])
            for q in queries:
                cat_queries += 1
                n = sum(1 for p in CONSTRAINT_PATTERNS if re.search(p, q, re.IGNORECASE))
                cat_constraints += n

        if os.path.exists(r_path):
            with open(r_path) as f:
                responses = json.load(f).get("responses", [])
            for r in responses:
                if not r.get("response"): continue
                cat_responses += 1
                text = r["response"]
                if "##" in text or "|" in text: cat_structured += 1
                if r.get("grounding"): cat_grounded += 1
                cat_words += len(text.split())

        total_queries      += cat_queries
        total_constraints  += cat_constraints
        response_structured += cat_structured
        grounded_responses += cat_grounded
        total_words        += cat_words
        total_responses    += cat_responses

        per_cat[cat] = {
            "queries":           cat_queries,
            "avg_constraints":   round(cat_constraints / cat_queries, 2) if cat_queries else 0,
            "valid_responses":   cat_responses,
            "structured_rate":   round(cat_structured / cat_responses * 100, 1) if cat_responses else 0,
            "grounded_pct":      round(cat_grounded / cat_responses * 100, 1) if cat_responses else 0,
            "avg_word_count":    round(cat_words / cat_responses, 0) if cat_responses else 0,
        }

    return {
        "metric":                "Agentic IR",
        "total_queries":         total_queries,
        "total_responses":       total_responses,
        "avg_constraints_per_query": round(total_constraints / total_queries, 2) if total_queries else 0,
        "structured_response_rate":  round(response_structured / total_responses * 100, 1) if total_responses else 0,
        "grounded_response_pct":     round(grounded_responses / total_responses * 100, 1) if total_responses else 0,
        "avg_response_word_count":   round(total_words / total_responses, 0) if total_responses else 0,
        "per_category":          per_cat,
    }


# ── 3. Dataset-10K Metrics ────────────────────────────────────────────────────
def dataset_metrics(category: str = None) -> dict:
    """
    Measures overall dataset completeness:
    - Total valid triplets (query + response + a2ui_json)
    - Per-stage valid counts
    - Category distribution balance
    - Overall completion %
    """
    cats = [category] if category else list(CATEGORIES.keys())

    s1_total = s2_valid = s3_valid = 0
    triplets  = 0
    per_cat   = {}
    category_sizes = []

    for cat in cats:
        q_path = os.path.join(QUERIES_DIR,   f"{cat}.json")
        r_path = os.path.join(RESPONSES_DIR, f"{cat}.json")
        a_path = os.path.join(A2UI_JSON_DIR,  f"{cat}.json")

        q_count  = 0
        r_count  = 0
        a_count  = 0
        triplet  = 0

        if os.path.exists(q_path):
            with open(q_path) as f: q_count = len(json.load(f).get("queries",[]))

        if os.path.exists(r_path):
            with open(r_path) as f:
                r_data  = json.load(f)
                r_count = r_data.get("valid_count", 0)

        if os.path.exists(a_path):
            with open(a_path) as f:
                a_data  = json.load(f)
                a_count = a_data.get("valid_count", 0)

        # Triplet = all 3 stages valid for same query
        if os.path.exists(a_path) and os.path.exists(r_path):
            with open(a_path) as f: a_results = json.load(f).get("results",[])
            valid_queries_a = {r["query"] for r in a_results if r.get("validation",{}).get("valid")}
            with open(r_path) as f: r_results = json.load(f).get("responses",[])
            valid_queries_r = {r["query"] for r in r_results if r.get("response") and r.get("valid",True)}
            triplet = len(valid_queries_a & valid_queries_r)

        s1_total  += q_count
        s2_valid  += r_count
        s3_valid  += a_count
        triplets  += triplet
        category_sizes.append(a_count)

        per_cat[cat] = {
            "stage1_queries":   q_count,
            "stage2_valid":     r_count,
            "stage3_valid":     a_count,
            "full_triplets":    triplet,
            "s2_rate":          round(r_count/q_count*100,1) if q_count else 0,
            "s3_rate":          round(a_count/r_count*100,1) if r_count else 0,
            "triplet_rate":     round(triplet/q_count*100,1) if q_count else 0,
        }

    target = 10000
    balance = round(min(category_sizes) / max(category_sizes) * 100, 1) if category_sizes and max(category_sizes) > 0 else 0

    return {
        "metric":           "Dataset-10K",
        "target":           target,
        "stage1_queries":   s1_total,
        "stage2_valid":     s2_valid,
        "stage3_valid":     s3_valid,
        "full_triplets":    triplets,
        "completion_pct":   round(triplets / target * 100, 1),
        "s2_valid_rate":    round(s2_valid / s1_total * 100, 1) if s1_total else 0,
        "s3_valid_rate":    round(s3_valid / s2_valid * 100, 1) if s2_valid else 0,
        "triplet_rate":     round(triplets / s1_total * 100, 1) if s1_total else 0,
        "category_balance": f"{balance}% (min/max ratio)",
        "per_category":     per_cat,
    }


# ── 4. UI Renderer Metrics ────────────────────────────────────────────────────
def renderer_metrics(category: str = None) -> dict:
    """
    Measures UI rendering quality:
    - Component type coverage: how many of the 50 allowed types are being used
    - Hallucination rate: % components with invalid types
    - Dangling ref rate: % screens with dangling references
    - HTML render success: % valid a2ui that produced HTML files
    - Avg component count per screen
    """
    cats = [category] if category else list(CATEGORIES.keys())

    all_types_used   = set()
    total_comps      = 0
    total_hallucin   = 0
    screens_dangling = 0
    total_screens    = 0
    comp_counts      = []
    html_generated   = 0
    html_possible    = 0

    per_cat = {}

    for cat in cats:
        a_path = os.path.join(A2UI_JSON_DIR, f"{cat}.json")
        h_dir  = os.path.join(HTML_DIR, cat)

        if not os.path.exists(a_path): continue

        with open(a_path) as f:
            data = json.load(f)

        valid_results = [r for r in data.get("results",[]) if r.get("validation",{}).get("valid")]
        html_files    = len(os.listdir(h_dir)) if os.path.exists(h_dir) else 0

        cat_comps   = 0
        cat_hall    = 0
        cat_dang    = 0
        cat_types   = set()
        cat_screens = 0

        for r in valid_results:
            v = r.get("validation", {})
            s = v.get("stats", {})

            cat_screens    += 1
            total_screens  += 1
            cat_comps      += s.get("component_count", 0)
            total_comps    += s.get("component_count", 0)
            cat_hall       += len(s.get("hallucinated", []))
            total_hallucin += len(s.get("hallucinated", []))
            comp_counts.append(s.get("component_count", 0))

            if s.get("dangling_refs"):
                cat_dang      += 1
                screens_dangling += 1

            for t in s.get("component_types", []):
                cat_types.add(t)
                all_types_used.add(t)

        html_generated += html_files
        html_possible  += len(valid_results)

        per_cat[cat] = {
            "valid_screens":      cat_screens,
            "html_files":         html_files,
            "html_render_pct":    round(html_files/cat_screens*100,1) if cat_screens else 0,
            "avg_component_count":round(cat_comps/cat_screens,1) if cat_screens else 0,
            "unique_types_used":  len(cat_types),
            "hallucin_per_screen":round(cat_hall/cat_screens,2) if cat_screens else 0,
            "dangling_ref_pct":   round(cat_dang/cat_screens*100,1) if cat_screens else 0,
        }

    return {
        "metric":               "UI Renderer",
        "total_screens":        total_screens,
        "allowed_component_types": len(A2UI_COMPONENTS),
        "types_used":           len(all_types_used),
        "type_coverage_pct":    round(len(all_types_used)/len(A2UI_COMPONENTS)*100,1),
        "types_used_list":      sorted(all_types_used),
        "types_not_used":       sorted(A2UI_COMPONENTS - all_types_used),
        "avg_component_count":  round(sum(comp_counts)/len(comp_counts),1) if comp_counts else 0,
        "hallucin_per_screen":  round(total_hallucin/total_screens,2) if total_screens else 0,
        "dangling_ref_rate":    round(screens_dangling/total_screens*100,1) if total_screens else 0,
        "html_render_success":  round(html_generated/html_possible*100,1) if html_possible else 0,
        "html_generated":       html_generated,
        "html_possible":        html_possible,
        "per_category":         per_cat,
    }


# ── Main ───────────────────────────────────────────────────────────────────────
def print_section(title: str, data: dict, skip_keys: list = None):
    skip = set(skip_keys or ["per_category","types_used_list","types_not_used"])
    print(f"\n{'─'*55}")
    print(f"  {title}")
    print(f"{'─'*55}")
    for k, v in data.items():
        if k in skip: continue
        print(f"  {k:<35} {v}")


def main():
    parser = argparse.ArgumentParser(description="Dataset Quality Metrics")
    parser.add_argument("--category", help="Single category to analyze")
    parser.add_argument("--export",   help="Export full report to JSON file")
    parser.add_argument("--detail",   action="store_true", help="Show per-category breakdown")
    args = parser.parse_args()

    print(f"\n{'='*55}")
    print("  A2UI Dataset Quality Report")
    print(f"{'='*55}")

    m1 = aesthetic_metrics(args.category)
    m2 = agentic_ir_metrics(args.category)
    m3 = dataset_metrics(args.category)
    m4 = renderer_metrics(args.category)

    print_section("1. Aesthetic Metrics", m1)
    print_section("2. Agentic IR Metrics", m2)
    print_section("3. Dataset-10K Metrics", m3)
    print_section("4. UI Renderer Metrics", m4)

    # Summary table
    print(f"\n{'='*55}")
    print("  SUMMARY")
    print(f"{'='*55}")
    print(f"  Dataset completion:    {m3['completion_pct']}% ({m3['full_triplets']}/{m3['target']} triplets)")
    print(f"  Stage 2 valid rate:    {m3['s2_valid_rate']}%")
    print(f"  Stage 3 valid rate:    {m3['s3_valid_rate']}%")
    print(f"  Style coverage:        {m1['style_coverage_pct']}%")
    print(f"  Rich component rate:   {m1['rich_component_rate']}%")
    print(f"  Component type coverage:{m4['type_coverage_pct']}%")
    print(f"  HTML render success:   {m4['html_render_success']}%")
    print(f"  Avg constraints/query: {m2['avg_constraints_per_query']}")
    print(f"  Structured resp rate:  {m2['structured_response_rate']}%")

    if args.detail:
        print(f"\n{'='*55}")
        print("  PER-CATEGORY BREAKDOWN")
        print(f"{'='*55}")
        for cat in (CATEGORIES if not args.category else [args.category]):
            d3 = m3["per_category"].get(cat, {})
            d4 = m4["per_category"].get(cat, {})
            print(f"\n  {cat}")
            print(f"    triplets={d3.get('full_triplets',0)}  "
                  f"s2={d3.get('stage2_valid',0)}  "
                  f"s3={d3.get('stage3_valid',0)}  "
                  f"html={d4.get('html_files',0)}  "
                  f"types={d4.get('unique_types_used',0)}  "
                  f"hall={d4.get('hallucin_per_screen',0)}")

    if args.export:
        report = {
            "generated_at":  __import__("datetime").datetime.now().isoformat(),
            "aesthetic":     m1,
            "agentic_ir":    m2,
            "dataset_10k":   m3,
            "ui_renderer":   m4,
        }
        with open(args.export, "w") as f:
            json.dump(report, f, indent=2)
        print(f"\n  Report exported to: {args.export}")


if __name__ == "__main__":
    main()