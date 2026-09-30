"""
stage3_a2ui_json.py — A2UI v0.9 JSON Generation
PRIMARY: Gemini API (ai.google.dev, GEMINI_API_KEYS — separate quota from Vertex)
FALLBACK: Vertex AI → Groq

CHANGES IN THIS VERSION:
- Style-aware prompts: each category now uses Spotify/Amazon/Airbnb/etc visual tokens
- REFERENCE_EXAMPLE updated with style variant fields (card_variant, button_variant)
- UI_HINTS updated with style-specific component guidance
- build_prompt_phase_a injects style description + color tokens from STYLE_TOKENS
- All parser/validator/retry logic unchanged
"""
import os, json, argparse, re, time
from datetime import datetime
from config import (
    CATEGORIES, RESPONSES_DIR, A2UI_JSON_DIR,
    A2UI_COMPONENTS, STAGE3_PRIMARY, SAVE_EVERY,
    CATEGORY_STYLES, STYLE_TOKENS,
)
from llm_client import query_llm

# ── Style-aware reference example ─────────────────────────────────────────────
REFERENCE_EXAMPLE = """
REFERENCE — match this exact structure. Component fields shown with style variants:

Card pattern (Card → Column → [Image + Texts + Button]):
{"id":"card-1","component":"Card","variant":"STYLE_CARD_VARIANT","elevation":2,"child":"card-1-col"}
{"id":"card-1-col","component":"Column","children":["card-1-img","card-1-title","card-1-desc","card-1-badge","card-1-btn"]}
{"id":"card-1-img","component":"Image","url":"https://loremflickr.com/600/400/KEYWORD","variant":"STYLE_IMAGE_VARIANT","fit":"cover"}
{"id":"card-1-title","component":"Text","text":"Item Name","variant":"h4"}
{"id":"card-1-desc","component":"Text","text":"Specs or description","variant":"body"}
{"id":"card-1-badge","component":"Badge","label":"$99 / ★4.5","color":"STYLE_ACCENT"}
{"id":"card-1-btn","component":"Button","variant":"STYLE_BUTTON_VARIANT","child":"card-1-btn-txt","action":{"functionCall":{"call":"openUrl","args":{"url":"https://real-url.com"}}}}
{"id":"card-1-btn-txt","component":"Text","text":"View / Buy / Book"}

Pseudo-table (Column of Rows — for ALL tabular data):
{"id":"table-col","component":"Column","children":["table-hdr-row","table-row-1","table-row-2","table-row-3"]}
{"id":"table-hdr-row","component":"Row","children":["th-1","th-2","th-3","th-4"]}
{"id":"th-1","component":"Text","text":"Feature","variant":"overline","weight":1}
{"id":"th-2","component":"Text","text":"Option A","variant":"overline","weight":1}
{"id":"table-row-1","component":"Row","children":["td-1-1","td-1-2","td-1-3","td-1-4"]}
{"id":"td-1-1","component":"Text","text":"Price","variant":"body","weight":1}
{"id":"td-1-2","component":"Text","text":"$100","variant":"body","weight":1}

Chip filter row:
{"id":"filter-row","component":"Row","children":["chip-1","chip-2","chip-3"]}
{"id":"chip-1","component":"Chip","label":"Filter A","selected":true}
{"id":"chip-2","component":"Chip","label":"Filter B"}

Inline icon row (Row → [Image icon + Text]):
{"id":"info-row-1","component":"Row","align":"center","children":["icon-1","label-1"]}
{"id":"icon-1","component":"Image","url":"https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/icons/star.svg","variant":"icon"}
{"id":"label-1","component":"Text","text":"Key point","variant":"body"}

Source buttons:
{"id":"source-btn-1","component":"Button","variant":"borderless","child":"source-txt-1","action":{"functionCall":{"call":"openUrl","args":{"url":"https://real-source.com"}}}}
{"id":"source-txt-1","component":"Text","text":"1. Source Title"}

KEY RULES:
- Replace STYLE_* placeholders with actual values from the style description given in the prompt
- Pseudo-table = Column of Rows, each Row has N Text children with weight:1 (NEVER Table/TableRow/TableCell)
- ALL components FLAT in the array — children/child hold STRING IDs only
- Image variant: STYLE_IMAGE_VARIANT for cards, "icon" for inline rows
- Source Buttons: always variant "borderless"
- Divider between every major section
- Badge for price, rating, status, distance — include color field matching style accent
- Chip for filters, tags, categories
"""

# ── System prompts ─────────────────────────────────────────────────────────────
SYSTEM = f"""Convert a user query + structured response into a rich A2UI v0.9 JSON UI array.
Output ONLY the raw JSON array. No markdown. No explanation. No code fences. Start with [ end with ].

FORMAT:
[
  {{"createSurface":{{"surfaceId":"SURFACE_ID","theme":{{"primaryColor":"#HEX"}}}},"version":"v0.9"}},
  {{"updateComponents":{{"surfaceId":"SURFACE_ID","components":[...FLAT array of 50-70 components...]}},"version":"v0.9"}}
]

CORE COMPONENTS:
Column Row Text Image Divider Card Button Badge Chip Icon
Tabs Stepper BottomNavigation AppBar ProgressBar

RULES (all mandatory):
1. Each component: unique kebab-case id + component field
2. ONE id="root" component="Column" — page root
3. ALL components FLAT in array — children/child hold STRING IDs only, never nested objects
4. Every referenced id MUST exist as a component in the flat array
5. Button: child → Text id + action.functionCall.call="openUrl" + action.functionCall.args.url="REAL_URL"
6. Card.child → Column id; Button.child → Text id
7. Pseudo-table = Column of Rows where each Row has N Text children with weight:1
8. Image.url = https://loremflickr.com/600/400/KEYWORD1,KEYWORD2
9. Text.variant: h1 h2 h3 h4 body caption overline
10. Badge: label + color fields; Chip: label + selected(bool) fields
11. Both envelope objects: "version":"v0.9"
12. Target 50-70 components

{REFERENCE_EXAMPLE}"""

SYSTEM_PHASE_A = """Output ONLY a flat JSON array of A2UI component objects.
No markdown. No explanation. No code fences. No outer envelope.
Just the raw array of component objects: [{...}, {...}, ...]

CORE COMPONENTS:
Column Row Text Image Divider Card Button Badge Chip Icon
Tabs Stepper BottomNavigation AppBar ProgressBar

RULES:
- Every component: unique kebab-case "id" + "component" field
- ONE id="root" component="Column" — page root, its children list ALL top-level ids
- ALL components FLAT — children/child hold STRING IDs only, never nested objects
- Button.child → Text id; Card.child → Column id
- Pseudo-table = Column of Rows where each Row has N Text children with weight:1
- Image.url = https://loremflickr.com/600/400/KEYWORD (use style image_variant for cards)
- Button action: {"functionCall":{"call":"openUrl","args":{"url":"REAL_URL"}}}
- Badge: label + color fields; Chip: label + selected(bool)
- Text.variant: h1 h2 h3 h4 body caption overline
- Target 50-70 components"""


# ── Style-aware UI hints ───────────────────────────────────────────────────────
UI_HINTS = {
    # Spotify style
    "media_playback":     "Dark musicCard per track/album: Image(square, album art)+Text(h4 title)+Text(caption artist)+Badge(rating/duration, green)+Button(pill, Play/Listen). Chip row for genre filter. Pseudo-table for top tracks.",
    "entertainment":      "Dark musicCard per show/event: Image(square)+Text(h4 title)+Text(body desc)+Badge(rating, green)+Button(pill). Chip filter row. Pseudo-table for schedule/pricing.",

    # Amazon style
    "product_lookup":     "White productCard per item: Image(square, product)+Text(h4 name)+Badge(price, orange)+Badge(★ rating)+Text(caption specs)+Button(cta, Buy Now, real URL). Pseudo-table for spec comparison.",
    "comparison":         "productCard per option: Image+Badge(price, orange)+Badge(winner category, orange)+Text(specs). Pseudo-table (features vs options). Chip per category filter.",

    # Airbnb style
    "booking":            "Large bookingCard: Image(mediumFeature)+Text(h4 name)+Badge(price/night, pink)+Badge(rating)+Text(body amenities)+Button(rounded, Book Now). Stepper for booking steps. Divider between cards.",
    "travel":             "bookingCard per destination/activity: Image(mediumFeature)+Text(h4)+Badge(price, pink)+Text(body). Tabs for Day 1/Day 2/Day 3. Pseudo-table for cost breakdown.",

    # Maps style
    "navigation":         "placeCard per route: Text(h4 mode)+Badge(time, blue)+Badge(cost)+Text(body steps)+Button(outlined, Open Maps). Pseudo-table (walk/drive/transit: time/cost/steps).",
    "localization":       "placeCard per business: Image(mediumFeature)+Text(h4 name)+Badge(★ rating, blue)+Chip(distance)+Text(caption hours)+Button(outlined, Directions). Chip row for category filter.",

    # Swiggy style
    "recipe":             "foodCard per dish option: Image(mediumFeature)+Text(h4)+Badge(price, orange)+Chip(veg/non-veg)+Text(body). Stepper for cooking steps. Pseudo-table for ingredients (item/qty/unit). ProgressBar for prep time.",

    # Notion style
    "education":          "infoCard per resource: Image+Text(h4)+Badge(format, blue tag)+Text(body). ProgressBar(completion). Tabs per subject. Pseudo-table for study schedule (day/topic/hours).",
    "documentation":      "infoCard per example: Text(h3 section)+Text(body code description)+Text(caption parameter). Tabs(Overview/API/Examples). Pseudo-table for params (name/type/required/desc).",
    "productivity":       "infoCard per task: Text(h4)+Badge(priority tag)+Text(body). Stepper for workflow. Pseudo-table for schedule (time/task/owner). ProgressBar per phase.",
    "planning":           "infoCard per phase: Text(h4 milestone)+Badge(status tag)+Text(body). Stepper for phases. Pseudo-table (budget: category/amount/total). ProgressBar.",
    "research_analysis":  "infoCard per finding: Text(h4)+Badge(confidence tag)+Text(body). Pseudo-table (study/method/result/year). Source borderless Buttons.",
    "creative_writing":   "infoCard content preview: Text(h3)+Text(body content). Chip row for tone options. Badge(word count). Button(ghost, Copy). Button(ghost, Download).",

    # Minimal style
    "weather":            "Pseudo-table (5-day: Day/High/Low/Rain%/UV/Wind). Badge per condition (sunny/rainy). Row+icon per weather stat. Button(primary, Full Forecast).",
    "calculation":        "Pseudo-table for result breakdown (item/value/formula). ProgressBar for visual ratio. infoCard per scenario. Badge(result highlight).",
    "data_visualization": "infoCard per KPI: Text(h4 metric)+Badge(trend up/down)+Text(body value). Pseudo-table for data. Chip row for filters.",
    "event_schedule":     "Pseudo-table (time/session/room/speaker). Tabs per day or track. Badge(session type). Button(primary, Register).",
    "information_retrieval": "Pseudo-table for key facts. infoCard per item with Badge(top pick). Source borderless Buttons.",
    "status_check":       "Stepper for status stages (ordered/shipped/out/delivered). Badge(current status, colored). Row+Text for details. Button(primary, Track).",
    "technical_support":  "Stepper for fix steps. infoCard per step with Text(code snippet). Badge(severity: critical/warning, red/orange). Source Buttons.",
    "qr_scanner":         "infoCard with QR Image. Pseudo-table for scan history (date/location/count). Badge(QR type). Button(primary, Download). Button(primary, Generate).",
}


def get_style(category: str) -> dict:
    """Return style tokens for a given category."""
    style_name = CATEGORY_STYLES.get(category, "minimal")
    return STYLE_TOKENS.get(style_name, STYLE_TOKENS["minimal"])


def build_prompt_phase_a(query: str, response: str, category: str, color: str) -> str:
    """
    Phase A: flat components array only (no outer envelope).
    Injects style description so model generates correct visual variants.
    """
    sid   = category.replace("_", "-") + "-surface"
    hint  = UI_HINTS.get(category, "Cards for items, pseudo-table for data, Buttons with real URLs.")
    style = get_style(category)

    return f"""Generate a flat JSON array of A2UI UI components for this query.

QUERY: {query}
CATEGORY: {category.upper()}
PRIMARY_COLOR: {color}
SURFACE_ID: {sid}

VISUAL STYLE — {style['desc']}
- card_variant: "{style['card_variant']}"
- button_variant: "{style['button_variant']}"
- image_variant: "{style['image_variant']}"
- accent_color: "{style['accent']}"
- Use Badge color: "{style['accent']}" for price/rating/status badges

UI HINT: {hint}

RESPONSE TO CONVERT:
{response[:2000]}

REQUIRED COMPONENTS:
- id="root" Column with all top-level IDs in children
- 3+ Cards: Card(variant="{style['card_variant']}") → Column → [Image(variant="{style['image_variant']}", loremflickr/keyword) + Text(h4) + Text(body) + Badge(label, color="{style['accent']}") + Button(variant="{style['button_variant']}", real URL → Text)]
- Chip row for filter/tags where relevant
- Pseudo-table: Column of Rows where each Row has N Text(weight:1) children
- 2+ Action Buttons with real URLs
- Sources Column: Button(borderless → Text) per source
- Dividers between sections
- Target: 50-70 components total

Output the flat array of component objects starting with ["""


def build_prompt_compact(query: str, response: str, category: str, color: str) -> str:
    """Compact prompt for retry attempts."""
    sid   = category.replace("_", "-") + "-surface"
    hint  = UI_HINTS.get(category, "Cards, table, Buttons.")
    style = get_style(category)

    return f"""A2UI v0.9 JSON array. SURFACE_ID={sid} COLOR={color}
STYLE: {style['desc']}
card_variant="{style['card_variant']}" button_variant="{style['button_variant']}" accent="{style['accent']}"

QUERY: {query}
HINT: {hint}

RESPONSE:
{response[:1800]}

BUILD: Text(h2) + 3 Cards(variant={style['card_variant']}, Image+Text+Badge+Button) + Chip row + pseudo-table(4+ rows) + Actions Row + Sources Column
TARGET: 40-60 components. Flat array. Children = string IDs only.

Output JSON array starting with ["""


def wrap_components_in_envelope(components: list, category: str, color: str) -> list:
    sid = category.replace("_", "-") + "-surface"
    return [
        {"createSurface": {"surfaceId": sid, "theme": {"primaryColor": color}}, "version": "v0.9"},
        {"updateComponents": {"surfaceId": sid, "components": components}, "version": "v0.9"},
    ]


# ── JSON repair + parsing ──────────────────────────────────────────────────────
def smart_repair(text: str) -> str:
    stack = []
    in_str = False
    esc = False
    pairs = {"{": "}", "[": "]"}
    close = {"}", "]"}
    for ch in text:
        if esc:       esc = False; continue
        if ch == "\\" and in_str: esc = True; continue
        if ch == '"': in_str = not in_str; continue
        if in_str:    continue
        if ch in pairs:   stack.append(pairs[ch])
        elif ch in close:
            if stack and stack[-1] == ch: stack.pop()
    return text + "".join(reversed(stack))


def parse_json(text: str):
    if not text or not text.strip():
        raise ValueError("Empty response from model")

    t = text.strip()
    for fence in ["```json\n", "```json", "```\n", "```"]:
        if t.startswith(fence): t = t[len(fence):]
    if t.endswith("```"): t = t[:-3].strip()
    if t.lower().startswith("json"): t = t[4:].strip()
    t = t.strip()

    # Strategy 1: direct parse
    try:
        r = json.loads(t)
        if isinstance(r, list): return r
    except Exception: pass

    # Strategy 2: outermost [ ] bracket tracking
    start = t.find("[")
    if start == -1:
        raise ValueError(f"No JSON array in response ({len(text)} chars): {text[:200]}")

    depth, in_str, esc, end = 0, False, False, -1
    for i, ch in enumerate(t[start:], start):
        if esc:        esc = False; continue
        if ch == "\\" and in_str: esc = True; continue
        if ch == '"':  in_str = not in_str; continue
        if in_str:     continue
        if ch == "[":  depth += 1
        elif ch == "]": depth -= 1
        if depth == 0: end = i + 1; break

    chunk = t[start:end] if end > start else t[start:]
    try:
        r = json.loads(chunk)
        if isinstance(r, list): return r
    except Exception: pass

    # Strategy 3: smart brace repair
    repaired = smart_repair(chunk)
    try:
        r = json.loads(repaired)
        if isinstance(r, list): return r
    except Exception: pass

    # Strategy 4: truncate to last complete top-level object
    depth2, in_str2, esc2, last_complete = 0, False, False, -1
    for i, ch in enumerate(repaired):
        if esc2:        esc2 = False; continue
        if ch == "\\" and in_str2: esc2 = True; continue
        if ch == '"':   in_str2 = not in_str2; continue
        if in_str2:     continue
        if ch in "{[":  depth2 += 1
        elif ch in "}]": depth2 -= 1
        if depth2 == 1 and ch == "}": last_complete = i

    if last_complete > 0:
        trunc = repaired[:last_complete + 1] + "]"
        try:
            r = json.loads(trunc)
            if isinstance(r, list) and len(r) >= 1: return r
        except Exception: pass

    # Strategy 5: extract updateComponents.components
    uc_match = re.search(r'"updateComponents"\s*:\s*\{[^{]*"components"\s*:\s*(\[)', repaired)
    if uc_match:
        comp_start = uc_match.start(1)
        comp_chunk = repaired[comp_start:]
        comp_repaired = smart_repair(comp_chunk)
        try:
            components = json.loads(comp_repaired)
            if isinstance(components, list) and len(components) >= 5:
                return components
        except Exception: pass

    # Strategy 6: extract all individual JSON objects
    objects = []
    depth3, in_str3, esc3, obj_start = 0, False, False, -1
    for i, ch in enumerate(repaired):
        if esc3:        esc3 = False; continue
        if ch == "\\" and in_str3: esc3 = True; continue
        if ch == '"':   in_str3 = not in_str3; continue
        if in_str3:     continue
        if ch == "{":
            if depth3 == 0: obj_start = i
            depth3 += 1
        elif ch == "}":
            depth3 -= 1
            if depth3 == 0 and obj_start >= 0:
                obj_str = repaired[obj_start:i + 1]
                try:
                    obj = json.loads(obj_str)
                    objects.append(obj)
                except Exception: pass
                obj_start = -1

    if len(objects) >= 2:
        has_create = any("createSurface"   in str(o) for o in objects[:3])
        has_update = any("updateComponents" in str(o) for o in objects[:3])
        if has_create and has_update:
            return objects[:2]
        if len(objects) >= 10:
            return objects

    if len(objects) == 1 and "createSurface" in str(objects[0]):
        raise ValueError(
            f"Response has createSurface only — updateComponents was truncated. "
            f"Response: {len(text)} chars."
        )

    raise ValueError(
        f"All 6 parse strategies failed. "
        f"Response: {len(text)} chars. Preview: {text[:300]}"
    )


# ── Helpers ────────────────────────────────────────────────────────────────────
def is_flat_components(data: list) -> bool:
    if not data: return False
    if len(data) >= 1 and isinstance(data[0], dict) and "createSurface" in data[0]:
        return False
    return any(isinstance(c, dict) and "component" in c for c in data[:5])


def has_only_envelope_header(data: list) -> bool:
    return (
        len(data) == 1
        and isinstance(data[0], dict)
        and "createSurface" in data[0]
        and "updateComponents" not in data[0]
    )


def validate(data: list) -> dict:
    errors, warnings = [], []
    stats = {
        "component_count": 0,
        "component_types": [],
        "has_root":        False,
        "hallucinated":    [],
        "dangling_refs":   [],
    }

    if not isinstance(data, list):
        return {"valid": False, "errors": ["Not a JSON array"], "warnings": [], "stats": stats}

    if is_flat_components(data):
        comps = data
    else:
        if has_only_envelope_header(data):
            return {"valid": False, "errors": ["Truncated: createSurface only, updateComponents missing"], "warnings": [], "stats": stats}
        if len(data) < 2:
            return {"valid": False, "errors": [f"Need 2 objects, got {len(data)}"], "warnings": [], "stats": stats}
        if "createSurface" not in data[0]:
            errors.append("Missing createSurface in obj[0]")
        if "updateComponents" not in data[1]:
            errors.append("Missing updateComponents in obj[1]")
            return {"valid": False, "errors": errors, "warnings": [], "stats": stats}
        comps = data[1]["updateComponents"].get("components", [])

    if not comps:
        return {"valid": False, "errors": ["components array is empty"], "warnings": [], "stats": stats}

    ids, refs = set(), set()
    for c in comps:
        if not isinstance(c, dict): continue
        cid   = c.get("id", "")
        ctype = c.get("component", "")
        if not cid or not ctype:
            warnings.append("Component missing id or type")
            continue
        if cid in ids:
            errors.append(f"Duplicate id: {cid}")
        ids.add(cid)
        if cid == "root": stats["has_root"] = True
        stats["component_count"] += 1
        if ctype not in stats["component_types"]:
            stats["component_types"].append(ctype)
        if ctype not in A2UI_COMPONENTS:
            stats["hallucinated"].append(ctype)
        for ch in c.get("children", []):
            if isinstance(ch, str): refs.add(ch)
        if isinstance(c.get("child"), str):
            refs.add(c["child"])
        for tab in c.get("tabs", []):
            if isinstance(tab, dict) and isinstance(tab.get("child"), str):
                refs.add(tab["child"])

    if not stats["has_root"]:
        errors.append("Missing id='root' component")

    dangling = refs - ids
    stats["dangling_refs"] = list(dangling)
    if len(dangling) > 15:
        errors.append(f"Too many dangling refs ({len(dangling)}): {list(dangling)[:5]}")
    elif dangling:
        warnings.append(f"{len(dangling)} dangling refs (minor): {list(dangling)[:3]}")

    if len(stats["hallucinated"]) > 3:
        errors.append(f"Too many hallucinated components: {stats['hallucinated'][:5]}")
    elif stats["hallucinated"]:
        warnings.append(f"Hallucinated ({len(stats['hallucinated'])}): {stats['hallucinated']} — minor")

    is_valid = (len(errors) == 0 and stats["has_root"] and stats["component_count"] >= 10)
    return {"valid": is_valid, "errors": errors, "warnings": warnings, "stats": stats}


def ensure_envelope(data: list, category: str, color: str) -> list:
    if is_flat_components(data):
        return wrap_components_in_envelope(data, category, color)
    return data


def cleanup_dangling_refs(data: list) -> list:
    try:
        if not data or len(data) < 2: return data
        comps = data[1].get("updateComponents", {}).get("components", [])
        if not comps: return data
        ids = {c["id"] for c in comps if isinstance(c, dict) and "id" in c}
        for c in comps:
            if not isinstance(c, dict): continue
            if "children" in c and isinstance(c["children"], list):
                c["children"] = [ch for ch in c["children"] if not isinstance(ch, str) or ch in ids]
            if "child" in c and isinstance(c["child"], str):
                if c["child"] not in ids: del c["child"]
        data[1]["updateComponents"]["components"] = comps
    except Exception: pass
    return data


def generate_a2ui(query: str, response: str, category: str, color: str) -> tuple:
    """
    4-attempt generation — phase-a first (flat array, all tokens go to components).
    Style tokens injected into every prompt via get_style(category).
    """
    attempts = [
        (lambda: build_prompt_phase_a(query, response, category, color),
         SYSTEM_PHASE_A, 0.4, "phase-a",    0),
        (lambda: build_prompt_phase_a(query, response, category, color),
         SYSTEM_PHASE_A, 0.3, "phase-a-t3", 5),
        (lambda: build_prompt_compact(query, response, category, color),
         SYSTEM,         0.2, "compact",     10),
        (lambda: build_prompt_phase_a(query, response, category, color),
         SYSTEM_PHASE_A, 0.2, "phase-a-t2", 15),
    ]

    last_result = None

    for attempt_num, (prompt_fn, system, temp, label, pre_sleep) in enumerate(attempts, 1):
        try:
            if pre_sleep > 0:
                print(f"    [waiting {pre_sleep}s before attempt {attempt_num}]", flush=True)
                time.sleep(pre_sleep)

            raw = query_llm(
                prompt=prompt_fn(),
                system_prompt=system,
                data_source=STAGE3_PRIMARY,
                max_tokens=8000,
                temperature=temp,
                json_mode=False,
            )
            raw_len = len(raw)
            print(f"    [attempt {attempt_num} / {label}] {raw_len} chars", flush=True)

            if raw_len < 3000:
                print(f"    -> Truncated ({raw_len} < 3000 chars) — trying next strategy")
                continue

            parsed = parse_json(raw)

            # Recovery: if createSurface-only, try regex component extraction
            if has_only_envelope_header(parsed):
                comp_matches = re.findall(
                    r'\{"id"\s*:\s*"[^"]+"\s*,\s*"component"\s*:\s*"[^"]+"[^}]*\}', raw
                )
                if len(comp_matches) >= 10:
                    try:
                        flat = [json.loads(m) for m in comp_matches]
                        parsed = wrap_components_in_envelope(flat, category, color)
                        print(f"    [recovered {len(flat)} components from raw text]")
                    except Exception: pass

            a2ui = ensure_envelope(parsed, category, color)
            a2ui = cleanup_dangling_refs(a2ui)
            v    = validate(a2ui)

            last_result = {
                "a2ui_json":  a2ui,
                "validation": v,
                "attempt":    attempt_num,
                "strategy":   label,
                "raw_chars":  raw_len,
            }

            if v["valid"]:
                n = v["stats"]["component_count"]
                t = len(v["stats"]["component_types"])
                print(f"    -> VALID ✓ ({n} components, {t} types, strategy={label})")
                if v.get("warnings"):
                    print(f"       Warnings: {v['warnings'][:2]}")
                return a2ui, v

            print(f"    -> INVALID (attempt {attempt_num}): {v['errors'][:2]}")

        except ValueError as e:
            err = str(e)
            print(f"    -> PARSE FAILED (attempt {attempt_num}): {err[:120]}")
            last_result = {
                "a2ui_json":  None,
                "validation": {"valid": False, "errors": [err], "warnings": [], "stats": {}},
                "attempt":    attempt_num, "strategy": label, "raw_chars": 0,
            }
        except Exception as e:
            err = str(e)
            print(f"    -> API FAILED (attempt {attempt_num}): {err[:120]}")
            last_result = {
                "a2ui_json":  None,
                "validation": {"valid": False, "errors": [err], "warnings": [], "stats": {}},
                "attempt":    attempt_num, "strategy": label, "raw_chars": 0,
            }

    if last_result:
        return last_result["a2ui_json"], last_result["validation"]
    return None, {"valid": False, "errors": ["All attempts failed"], "warnings": [], "stats": {}}


def process_category(category: str, meta: dict, limit: int = None) -> int:
    r_path = os.path.join(RESPONSES_DIR, f"{category}.json")
    a_path = os.path.join(A2UI_JSON_DIR,  f"{category}.json")

    if not os.path.exists(r_path):
        print(f"  [{category}] No responses — run stage2 first")
        return 0

    with open(r_path) as f:
        all_responses = [
            r for r in json.load(f).get("responses", [])
            if r.get("response") and r.get("valid", True)
        ]
    if limit:
        all_responses = all_responses[:limit]

    existing = {}
    if os.path.exists(a_path):
        with open(a_path) as f:
            for r in json.load(f).get("results", []):
                if r.get("validation", {}).get("valid"):
                    existing[r["query"]] = r

    to_do = [r for r in all_responses if r["query"] not in existing]

    style_name = CATEGORY_STYLES.get(category, "minimal")
    print(f"\n{'='*60}")
    print(f"Category: {category} | style={style_name} | done={len(existing)} | todo={len(to_do)}")
    if not to_do:
        print("  All valid! ✓")
        return len(existing)

    results = list(existing.values())
    color   = meta.get("color", "#2563EB")

    for i, item in enumerate(to_do):
        q = item["query"]
        r = item["response"]
        print(f"  [{i+1}/{len(to_do)}] {q[:65]}...", flush=True)

        a2ui, v = generate_a2ui(q, r, category, color)

        result = {
            "query":        q,
            "response":     r,
            "a2ui_json":    a2ui,
            "validation":   v,
            "category":     category,
            "style":        style_name,
            "generated_at": datetime.now().isoformat(),
        }
        if not v["valid"]:
            result["error"] = v["errors"][0] if v["errors"] else "Unknown"

        results.append(result)

        if (i + 1) % SAVE_EVERY == 0 or (i + 1) == len(to_do):
            order = {item["query"]: idx for idx, item in enumerate(all_responses)}
            results.sort(key=lambda x: order.get(x["query"], 9999))
            tv = sum(1 for r in results if r.get("validation", {}).get("valid"))
            with open(a_path, "w") as f:
                json.dump({
                    "category":     category,
                    "style":        style_name,
                    "generated_at": datetime.now().isoformat(),
                    "count":        len(results),
                    "valid_count":  tv,
                    "results":      results,
                }, f, indent=2)
            print(f"  [saved {tv}/{len(results)} valid]")

    return sum(1 for r in results if r.get("validation", {}).get("valid"))


def main():
    parser = argparse.ArgumentParser(description="Stage 3: A2UI JSON Generation")
    parser.add_argument("--category", help="Single category to process")
    parser.add_argument("--limit",    type=int, help="Max items (use 3-5 for testing)")
    parser.add_argument("--dry-run",  action="store_true")
    args = parser.parse_args()

    cats = {args.category: CATEGORIES[args.category]} if args.category else CATEGORIES

    if args.dry_run:
        print(f"\nDry run — {len(cats)} categories (PRIMARY: {STAGE3_PRIMARY})")
        for cat in cats:
            a_path = os.path.join(A2UI_JSON_DIR, f"{cat}.json")
            r_path = os.path.join(RESPONSES_DIR,  f"{cat}.json")
            s2, s3 = 0, 0
            if os.path.exists(r_path):
                with open(r_path) as f: s2 = json.load(f).get("valid_count", 0)
            if os.path.exists(a_path):
                with open(a_path) as f: s3 = json.load(f).get("valid_count", 0)
            sty = CATEGORY_STYLES.get(cat, "minimal")
            print(f"  {cat:<28} style={sty:<8} stage2={s2:<5} stage3={s3:<5} todo={s2-s3}")
        return

    print(f"\nStage 3: A2UI JSON Generation (PRIMARY: {STAGE3_PRIMARY})")
    print("Settings: json_mode=OFF, max_tokens=8000, style-aware prompts")
    total = 0
    for cat, meta in cats.items():
        total += process_category(cat, meta, limit=args.limit)

    print(f"\n{'='*60}")
    print(f"Stage 3 Complete: {total} valid A2UI JSONs")


if __name__ == "__main__":
    main()