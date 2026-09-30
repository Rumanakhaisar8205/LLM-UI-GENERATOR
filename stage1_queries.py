"""
stage1_queries.py — Query Generation with forced regeneration support
NEW: --force flag deletes + regenerates weak categories with improved prompts
NEW: Tighter per-category constraints for the 6 weak categories identified in audit:
     status_check, research_analysis, creative_writing,
     technical_support, data_visualization, qr_scanner
Resumes automatically for all other categories.
"""
import os, json, re, argparse
from datetime import datetime
from config import (
    CATEGORIES, QUERIES_DIR, QUERIES_PER_CATEGORY,
    BATCH_SIZE, STAGE1_PRIMARY, WEAK_CATEGORIES
)
from llm_client import query_llm

SYSTEM = """You are a dataset generator for a UI generation AI system.
Generate realistic, CONSTRAINT-RICH user queries for a voice/text assistant.

MANDATORY per query:
- Include 2-4 specific constraints (budget, location, time, count, features, comparison)
- Multi-intent when possible (compare + recommend, plan + book, search + filter)
- Queries that REQUIRE rich UI output (tables, cards, maps, forms, image carousels)
- Real-world specificity (actual cities, actual product categories, real price ranges)

FORBIDDEN — reject these patterns:
- Generic: "what is X", "tell me about X", "list of X", "find me a list"
- Vague: "top 5 things", "some options for", "help me with"
- Single-intent with no constraints
- Category drift: queries that belong to another category

Output ONLY a JSON array of strings. No numbering. No explanation."""

# ── Per-category constraint templates ────────────────────────────────────────
CATEGORY_CONSTRAINTS = {
    "information_retrieval": [
        "Compare specs, price, and availability of {item} across 3 vendors under {budget} in {city}",
        "What are the best {items} released after {year} with {feature1} and {feature2} under {budget}?",
    ],
    "product_lookup": [
        "Find a {product} under ₹{price} with {feature1}, {feature2}, and at least {rating}★ on Flipkart",
        "Compare {brand1} vs {brand2} {product} for {use_case} — include price, warranty, delivery in {city}",
    ],
    "booking": [
        "Book a {room_type} hotel near {landmark} in {city} for {N} nights checking in {date} under ₹{budget}/night",
        "Reserve a table for {N} at a {cuisine} restaurant near {location} for {date} under ₹{budget} per head",
    ],
    "weather": [
        "Show {N}-day weather forecast for {city} with hourly rainfall probability, UV index, and humidity",
        "Compare weather across {city1}, {city2}, {city3} this weekend — best city for outdoor trip?",
        "Best month to visit {destination} — show 10-year historical rainfall and temperature trends",
    ],
    "recipe": [
        "Step-by-step {dish} recipe for {N} people under {time} minutes with exact measurements and calories",
        "How to make {dish} without {ingredient} — show substitutions and nutritional breakdown",
    ],
    "comparison": [
        "Compare {item1} vs {item2} vs {item3} on {attr1}, {attr2}, {attr3} — show winner per category",
        "Should I choose {option1} or {option2} for {use_case}? Include cost, pros/cons for {user_type}",
    ],
    "travel": [
        "Plan a {N}-day trip to {destination} for {N_people} under ₹{budget} — day-wise itinerary with transport",
        "Weekend trip from {city} to {destination}: compare bus vs train vs flight on cost, time, comfort",
    ],
    "calculation": [
        "Calculate EMI for ₹{amount} loan at {rate}% for {years} years — show amortization table",
        "Calculate CAGR for SIP of ₹{monthly} for {years} years at {rate}% — show year-wise growth table",
        "Compare total cost of owning {vehicle} in {city} over 5 years — fuel, insurance, EMI breakdown",
    ],
    "education": [
        "Create a {N}-day study plan for {exam} covering {subject1}, {subject2} with {hours}/day",
        "Best {N} free resources for learning {topic} from scratch in {timeframe} — compare by format",
    ],
    "navigation": [
        "Find fastest route from {location1} to {location2} — compare driving vs metro vs bike",
        "Show all {service_type} within {radius}km of {location} — sort by rating and distance with map",
    ],
    "planning": [
        "Plan a {event_type} for {N} guests on {date} in {city} under ₹{budget} — venue, catering, decoration",
        "Create a {N}-week project plan for {project} with {N_people} team — milestones, deadlines",
    ],
    "productivity": [
        "Create a {role} daily schedule optimizing {goal1} and {goal2} with {N} deep work blocks",
        "Design a {timeframe} OKR framework for {department} — objectives, key results, check-in template",
    ],
    "localization": [
        "Show nearby {service_type} in {city} area open on {day} after {time} — sort by distance and rating",
        "Find {N} {type} stores in {area} of {city} — show map, hours, contact, reviews",
    ],
    "event_schedule": [
        "Show schedule for {event} on {date} at {venue} — sessions, speakers, rooms, registration links",
        "Upcoming {category} events in {city} this {month} — filter by free/paid, format, date",
    ],
    "media_playback": [
        "Find {genre} {media_type} on {platform} released after {year} with rating above {N} — sort by popularity",
        "Create a {mood} playlist for {activity} on Spotify — {N} songs with BPM {min}-{max}",
    ],
    "entertainment": [
        "Find {genre} movies on Netflix released in {year} with rating above {N} and under {duration} minutes",
        "Compare prices for {event} tickets in {city} under ₹{budget} for {N} people on {date}",
    ],
    "documentation": [
        "Generate API docs for {function} with parameters, return types, error codes, and {N} code examples",
        "Create README for {project_type} with setup, usage, config, troubleshooting, and contributing guide",
    ],

    # ── WEAK CATEGORIES — tighter, more specific constraints ─────────────────

    "status_check": [
        # MUST be about tracking/monitoring real service status — NOT restaurant finding
        "Track order #{order_id} from {platform} — show current location, ETA, and delay history on map",
        "Check flight {airline}{flight_no} on {date} from {city1} to {city2} — show gate, delay, baggage claim",
        "Monitor {cloud_service} API uptime in {N} regions — show incident history, SLA breaches, alert status",
        "Check train {train_no} live status on {date} — show current station, delay, platform number, coach position",
        "Track my {courier} parcel #{tracking_id} — show checkpoint timeline, estimated delivery, contact support button",
    ],
    "research_analysis": [
        # MUST have scope constraints: year range, metric, comparison, domain
        "Analyze {company} Q{N} {year} earnings — compare revenue, margins, EPS vs {competitor} with 5-year trend chart",
        "Summarize peer-reviewed research on {treatment} for {condition} from {year1}-{year2} — compare {N} studies by methodology and effect size",
        "Compare {country1} vs {country2} on {metric1}, {metric2}, {metric3} from {year1} to {year2} — show trend lines and key events",
        "Analyze market share of {industry} sector in India {year} — top {N} players by revenue, growth rate, and geography",
        "Find {N} research papers on {topic} published after {year} in {journal_type} — compare by citation count, methodology, and key findings",
    ],
    "creative_writing": [
        # MUST specify: format + length + audience/platform + tone + subject constraints
        "Write a {N}-word product description for a {product} targeting {audience} on Amazon — {tone} tone with {N} bullet points",
        "Create a {N}-second video script for a {product} ad targeting {age_group} on Instagram — include hook, benefit, CTA",
        "Write {N} {tone} email subject lines for a {discount}% sale campaign at {brand} targeting {segment} users",
        "Generate a {N}-slide pitch deck outline for a {startup_type} startup targeting {investor_type} investors in {city}",
        "Write a {N}-word {genre} blog post for a {niche} audience on Medium — include {N} headers, SEO keywords, and CTA",
    ],
    "technical_support": [
        # MUST specify: error/issue + platform/OS/version + what was attempted
        "Fix '{error_msg}' in Python {version} on {OS} when running {script_type} — show root cause, fix with code, prevention",
        "Debug {framework} {version} app crashing with '{error}' on {device} — show stack trace analysis, fix steps, test command",
        "Set up {tool} {version} for {use_case} on {OS} — step-by-step config, common errors with solutions, verify command",
        "Resolve '{error}' in {IDE} when {action} on a {project_type} project — show screenshot reference, fix steps, alternative",
        "Fix Docker container failing to start with '{exit_code}' on {OS} — show log analysis, config fix, health check command",
    ],
    "data_visualization": [
        # MUST specify: real dataset/metric + chart type + time period + comparison
        "Visualize monthly sales data for {product_category} in {city} across {N} months — show bar chart, trend line, YoY growth",
        "Create a dashboard for {N} e-commerce KPIs: revenue, conversion rate, AOV — filter by {city} and {date_range}",
        "Compare {country1} vs {country2} GDP per capita from {year1} to {year2} — show line chart, % change table, key events",
        "Visualize India's EV adoption by state from {year1}-{year2} — choropleth map, top {N} states bar chart, growth table",
        "Show {company} stock price vs {index} over {N} years — candlestick chart, volume bars, {N} technical indicators",
    ],
    "qr_scanner": [
        # MUST have: content type + customization + analytics/tracking use case
        "Generate a QR code for my restaurant menu at {restaurant} with logo, brand color {color}, expiry {date}, track {N} scans",
        "Create batch QR codes for {N} products in my {category} store — each linking to product page with UTM tracking",
        "Scan {N} QR codes from uploaded image — validate each URL, show broken links, categorize by domain, export CSV",
        "Generate event check-in QR code for {event} on {date} — unique per ticket, scan limit {N}, show real-time scan analytics",
        "Create a vCard QR code for {name} at {company} with phone, email, LinkedIn — add logo, track {N} scans per week",
    ],
}

# ── Weak pattern detector ─────────────────────────────────────────────────────
WEAK_PATTERNS = [
    r"^what is\b", r"^tell me about\b", r"^list of\b", r"^top \d+\b",
    r"^some options\b", r"^show me some\b", r"^give me a list\b",
    r"^help me with\b", r"^i need information\b", r"^can you tell\b",
    r"^what are the\b", r"^find me a list\b", r"^find me the\b",
]
WEAK_RE = [re.compile(p, re.IGNORECASE) for p in WEAK_PATTERNS]

MIN_WORDS = 12
MIN_CHARS = 60

def is_quality_query(q: str) -> bool:
    if len(q) < MIN_CHARS: return False
    if len(q.split()) < MIN_WORDS: return False
    if any(r.match(q) for r in WEAK_RE): return False
    return True

def make_prompt(category: str, existing: list, batch_size: int) -> str:
    constraints = CATEGORY_CONSTRAINTS.get(category, [
        "Find {item} with {feature1} and {feature2} under {budget} in {location}",
    ])
    existing_sample = existing[-5:] if len(existing) > 5 else existing

    # Extra instructions for weak categories
    extra = ""
    if category == "status_check":
        extra = """
CRITICAL FOR STATUS_CHECK: Queries MUST be about tracking/monitoring status of:
  - Orders (Amazon, Flipkart, Meesho), parcels (FedEx, DHL, Delhivery, BlueDart)
  - Flights (with flight numbers), trains (with train numbers)  
  - Cloud services/APIs (AWS, GCP, Azure, Razorpay, Stripe uptime)
  - Internet/utility services (ISP outage, power grid status)
  - Subscriptions/accounts (credit card status, loan account)
DO NOT generate: restaurant finders, product searches, or location queries."""

    elif category == "research_analysis":
        extra = """
CRITICAL FOR RESEARCH_ANALYSIS: Every query MUST have:
  - A specific year range (e.g., 2019-2024)
  - A measurable metric to compare (revenue, citations, mortality rate, etc.)
  - At least 2 entities to compare (companies, countries, treatments, papers)
  - Output format hint (table, chart, summary with N studies)
DO NOT generate: vague summaries, single-topic explanations."""

    elif category == "creative_writing":
        extra = """
CRITICAL FOR CREATIVE_WRITING: Every query MUST specify:
  - Exact word/character count or duration
  - Target platform (Instagram, Amazon, LinkedIn, Medium, YouTube)
  - Target audience (age group, profession, interest)
  - Tone (professional, humorous, urgent, inspirational)
  - Format (bullet points, script, headline, email subject)
These must drive a rich UI with text fields, tone selectors, and preview cards."""

    elif category == "technical_support":
        extra = """
CRITICAL FOR TECHNICAL_SUPPORT: Every query MUST include:
  - Specific error message or symptom (in quotes if possible)
  - Platform/OS/version (Python 3.11, Ubuntu 22.04, React 18, etc.)
  - What was attempted (when running X, after installing Y)
  - Expected output: step-by-step fix with code blocks
DO NOT generate: generic "how to set up X" without error/version context."""

    elif category == "data_visualization":
        extra = """
CRITICAL FOR DATA_VISUALIZATION: Every query MUST specify:
  - A concrete dataset or metric (monthly sales, stock price, COVID cases)
  - A time period (last 12 months, 2019-2024, Q1-Q4)
  - A comparison (city vs city, company vs competitor, product vs product)
  - Expected chart type (bar chart, line chart, heatmap, choropleth map)
  - At least 2 filter dimensions (region, category, date range)"""

    elif category == "qr_scanner":
        extra = """
CRITICAL FOR QR_SCANNER: Every query MUST include:
  - The content type (menu, product page, event ticket, vCard, WiFi credentials)
  - A customization requirement (logo, brand color, expiry date)
  - A tracking/analytics need (scan count, geographic breakdown, UTM)
  - A business context (restaurant, e-commerce store, event, business card)
DO NOT generate: simple "generate QR for URL" without customization."""

    return f"""Generate {batch_size} NEW, DIVERSE, CONSTRAINT-RICH queries for: {category.upper().replace("_", " ")}
{extra}
RULES — each query MUST:
1. Have 2-4 specific constraints (price/budget, location, time, features, count)
2. Be multi-intent where possible (compare + recommend, plan + book)
3. Require a RICH UI to answer (table for comparison, cards for options, map, form)
4. Be 12-25 words long — specific, real-world, detailed
5. Sound like a real person asking a voice assistant

CONSTRAINT TEMPLATES to inspire (do NOT copy literally):
{chr(10).join(f"• {c}" for c in constraints[:4])}

ALREADY GENERATED (do NOT repeat or rephrase):
{json.dumps(existing_sample, indent=None)}

FORBIDDEN patterns (these will be REJECTED):
• "What is X", "Tell me about X", "List of X", "Find me a list of X"
• Generic queries with no constraints or no UI-driving intent

Output ONLY a valid JSON array of {batch_size} query strings.
Start with [ and end with ]. No explanation. No numbering."""


def parse_queries(raw: str) -> list:
    text = raw.strip()
    for fence in ["```json", "```"]:
        if text.startswith(fence):
            text = text[len(fence):]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()
    s, e = text.find("["), text.rfind("]") + 1
    if s != -1 and e > s:
        text = text[s:e]
    try:
        result = json.loads(text)
        if isinstance(result, list):
            return [q for q in result if isinstance(q, str)]
    except json.JSONDecodeError:
        pass
    return re.findall(r'"([^"]{' + str(MIN_CHARS) + r',})"', text)


def process_category(category: str, target: int = QUERIES_PER_CATEGORY,
                     force: bool = False) -> int:
    out_path = os.path.join(QUERIES_DIR, f"{category}.json")

    # --force: delete existing file to trigger full regeneration
    if force and os.path.exists(out_path):
        os.remove(out_path)
        print(f"  [{category}] Deleted existing queries (--force)")

    existing = []
    if os.path.exists(out_path):
        with open(out_path) as f:
            existing = json.load(f).get("queries", [])

    need = target - len(existing)
    if need <= 0:
        print(f"  {category}: already have {len(existing)} ✓")
        return len(existing)

    print(f"\n{'='*60}")
    is_weak = category in WEAK_CATEGORIES
    print(f"Category: {category} | have={len(existing)} | need={need}"
          + (" [WEAK — using tighter prompt]" if is_weak else ""))

    failures = 0
    MAX_FAILURES = 5

    while len(existing) < target and failures < MAX_FAILURES:
        batch_size = 10 if is_weak else BATCH_SIZE
        batch = min(batch_size, target - len(existing))
        print(f"  Generating {batch} queries... [{len(existing)}/{target}]", flush=True)

        try:
            raw = query_llm(
                prompt=make_prompt(category, existing, batch),
                system_prompt=SYSTEM,
                data_source=STAGE1_PRIMARY,
                max_tokens=2500,
                temperature=0.75 if is_weak else 0.8,
            )
            new_queries = parse_queries(raw)

            before = len(new_queries)
            new_queries = [q for q in new_queries if is_quality_query(q)]
            rejected = before - len(new_queries)
            if rejected > 0:
                print(f"  Quality filter: rejected {rejected}/{before} weak queries")

            new_queries = [q for q in new_queries if q not in existing]

            if not new_queries:
                print("  No new valid queries — retrying")
                failures += 1
                continue

            existing.extend(new_queries)
            failures = 0
            print(f"  Added {len(new_queries)} | total={len(existing)}/{target}")

            with open(out_path, "w") as f:
                json.dump({
                    "category":     category,
                    "count":        len(existing),
                    "target":       target,
                    "generated_at": datetime.now().isoformat(),
                    "queries":      existing,
                }, f, indent=2)

        except Exception as e:
            failures += 1
            print(f"  FAILED ({failures}/{MAX_FAILURES}): {e}")
            if failures >= MAX_FAILURES:
                break

    print(f"  Final: {len(existing)} queries → {out_path}")
    return len(existing)


def main():
    parser = argparse.ArgumentParser(description="Stage 1: Query Generation")
    parser.add_argument("--category",  help="Single category to process")
    parser.add_argument("--target",    type=int, default=QUERIES_PER_CATEGORY)
    parser.add_argument("--force",     action="store_true",
                        help="Delete + regenerate weak categories (status_check, "
                             "research_analysis, creative_writing, technical_support, "
                             "data_visualization, qr_scanner)")
    parser.add_argument("--force-all", action="store_true",
                        help="Delete + regenerate ALL categories from scratch")
    parser.add_argument("--dry-run",   action="store_true")
    args = parser.parse_args()

    # Determine which categories to run
    if args.category:
        cats = {args.category: CATEGORIES[args.category]}
        force_set = {args.category} if (args.force or args.force_all) else set()
    else:
        cats = CATEGORIES
        if args.force_all:
            force_set = set(CATEGORIES.keys())
        elif args.force:
            force_set = WEAK_CATEGORIES
        else:
            force_set = set()

    if args.dry_run:
        print(f"\nDry run — {len(cats)} categories")
        for cat in cats:
            path = os.path.join(QUERIES_DIR, f"{cat}.json")
            have = 0
            if os.path.exists(path):
                with open(path) as f:
                    have = json.load(f).get("count", 0)
            flag = " [WILL REGEN]" if cat in force_set else ""
            weak = " ⚠WEAK" if cat in WEAK_CATEGORIES else ""
            print(f"  {cat:<30} have={have:>4} need={max(0, args.target-have):>4}{weak}{flag}")
        return

    if force_set:
        print(f"\n⚠ Force regenerating: {sorted(force_set)}")

    print(f"\nStage 1: Generating queries (PRIMARY: {STAGE1_PRIMARY})")
    total = 0
    for cat in cats:
        total += process_category(cat, target=args.target,
                                  force=(cat in force_set))

    print(f"\n{'='*60}")
    print(f"Stage 1 Complete: {total} total queries across {len(cats)} categories")


if __name__ == "__main__":
    main()
