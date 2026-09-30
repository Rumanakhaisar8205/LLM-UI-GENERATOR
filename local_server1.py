from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import json
import time

# ============================================================
# CONFIGURATION
# ============================================================
OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "a2ui-model"
OLLAMA_TAGS_URL = "http://localhost:11434/api/tags"

# ============================================================
# CATEGORY STYLES (must match training-time categories)
# ============================================================
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
    "spotify":  {"desc": "Spotify dark: dark background #121212, surface #1E1E1E, green accent #1DB954, white text, pill buttons, square album images"},
    "amazon":   {"desc": "Amazon style: white background, orange accent #FF9900, bold price text, ratings, product image, yellow primary CTA"},
    "airbnb":   {"desc": "Airbnb style: white background, pink-red accent #FF385C, large feature images, rounded cards, price per night and primary booking button"},
    "maps":     {"desc": "Maps style: white background, blue accent #1A73E8, place cards, rating, distance, directions button"},
    "swiggy":   {"desc": "Food delivery style: white background, orange accent, food images, price, delivery time and Add button"},
    "notion":   {"desc": "Notion style: clean white background, warm gray surfaces, blue accents, tags and minimal borders"},
    "minimal":  {"desc": "Clean minimal UI: white background, slate gray text, blue accent, subtle cards and clear hierarchy"},
}

CATEGORY_KEYWORDS = {
    "weather": ["weather", "forecast", "rain", "temperature", "humidity", "climate"],
    "recipe": ["recipe", "cook", "ingredient", "biryani", "dish", "food"],
    "travel": ["trip", "itinerary", "travel", "vacation", "holiday"],
    "booking": ["book", "cab", "flight ticket", "reserve", "ride", "reservation"],
    "product_lookup": ["laptop", "phone", "buy", "price of", "under ₹", "under $", "product"],
    "comparison": ["vs", "compare", "versus", "better than"],
    "navigation": ["route", "directions", "how to get to", "distance to", "navigate"],
    "productivity": ["to-do", "todo", "task list", "schedule", "reminder"],
    "status_check": ["order #", "track my", "status of", "delivery status"],
    "information_retrieval": ["what is", "who is", "tell me about"],
    "entertainment": ["movie", "song", "playlist", "watch"],
    "media_playback": ["play ", "song", "music", "podcast"],
}

def guess_category(query):
    q = query.lower()
    for category, keywords in CATEGORY_KEYWORDS.items():
        for keyword in keywords:
            if keyword in q:
                return category
    return "information_retrieval"

# ============================================================
# AD-HOC STYLE OVERRIDES
# Free-text modifiers like "with red buttons" never reached the
# model — build_prompt() only ever injected the fixed category
# style. This extracts explicit overrides from the query so they
# can be forced into the prompt as a hard instruction.
# ============================================================
COLOR_KEYWORDS = {
    "red": "#DC2626", "blue": "#2563EB", "green": "#16A34A",
    "purple": "#7C3AED", "orange": "#EA580C", "pink": "#EC4899",
    "yellow": "#EAB308", "teal": "#0D9488", "black": "#111827",
    "dark": "#1F2937",
}

def extract_style_overrides(query):
    q = query.lower()
    overrides = []
    for word, hex_code in COLOR_KEYWORDS.items():
        if word in q and ("button" in q or "buttons" in q or "theme" in q or "color" in q):
            overrides.append(f'Override the button/accent color: use primaryColor {hex_code} '
                              f'instead of the category default, because the user explicitly asked for {word}.')
            break  # first color match wins
    if "dark mode" in q or "dark theme" in q:
        overrides.append("User asked for dark mode: use a dark background (#121212) with light text, "
                          "not the category's default light background.")
    return overrides

# ============================================================
# SYSTEM PROMPT
# ============================================================
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

# ============================================================
# BUILD PROMPT
# ============================================================
def build_prompt(query, response_context, category):
    style_name = CATEGORY_STYLES.get(category, "minimal")
    style_info = STYLE_TOKENS.get(style_name, STYLE_TOKENS["minimal"])
    context = response_context.strip() if response_context else "(no additional structured response provided)"
    overrides = extract_style_overrides(query)
    override_block = ("\nEXPLICIT USER OVERRIDES (must follow, take priority over Style description):\n"
                       + "\n".join(f"- {o}" for o in overrides)) if overrides else ""

    return f"""Category: {category}
Style: {style_name}
Style description: {style_info["desc"]}
{override_block}

User Query: {query}

Structured Response: {context}

Generate the complete A2UI v0.9 JSON array for this screen.
Remember: return ONLY the two-object JSON array format shown in the system rules — no other shape."""

# ============================================================
# JSON EXTRACTION
# ============================================================
def extract_json(raw):
    if not raw:
        return None
    raw = raw.strip()
    try:
        return json.loads(raw)
    except Exception:
        pass

    cleaned = raw.replace("```json", "").replace("```", "").strip()
    try:
        return json.loads(cleaned)
    except Exception:
        pass

    first, last = cleaned.find("["), cleaned.rfind("]")
    if first != -1 and last != -1 and last > first:
        try:
            parsed = json.loads(cleaned[first:last + 1])
            if isinstance(parsed, list):
                return parsed
        except Exception:
            pass

    first, last = cleaned.find("{"), cleaned.rfind("}")
    if first != -1 and last != -1 and last > first:
        try:
            return json.loads(cleaned[first:last + 1])
        except Exception:
            pass
    return None

app = Flask(__name__)
CORS(app)

@app.route("/health", methods=["GET"])
def health():
    try:
        response = requests.get(OLLAMA_TAGS_URL, timeout=5)
        response.raise_for_status()
        data = response.json()
        model_names = [m.get("name", "") for m in data.get("models", [])]
        model_available = any(name.startswith(OLLAMA_MODEL) for name in model_names)
        return jsonify({
            "status": "ok", "ollama": "reachable", "model": OLLAMA_MODEL,
            "model_available": model_available, "models": model_names
        })
    except Exception as e:
        return jsonify({"status": "error", "ollama": "unreachable", "error": str(e)}), 500

@app.route("/generate", methods=["POST"])
def generate():
    try:
        data = request.get_json(force=True)
    except Exception:
        return jsonify({"success": False, "error": "Invalid JSON request"}), 400

    query = (data.get("query") or data.get("prompt") or "").strip()
    response_context = (data.get("response") or "").strip()

    if not query:
        return jsonify({"success": False, "error": "No query provided"}), 400

    category = guess_category(query)
    prompt = build_prompt(query, response_context, category)

    print(f"\n{'='*70}\nQUERY: {query[:100]}\nCATEGORY: {category}\n{'='*70}")
    start_time = time.time()

    # Complex/long-content queries (comparisons, multi-item asks, multi-step
    # recipes, multi-day plans) need more headroom. "recipe" was missing
    # from the complex set, which is why step-heavy recipes (Paneer Masala,
    # Biryani) were getting cut off at 1800 tokens mid-generation.
    complex_signals = [
        "compare", "vs", "3 ", "recommend", "top 3", "top 5", "options",
        "steps", "step-by-step", "ingredients", "how to make", "recipe for",
        "itinerary", "day 1", "day-by-day", "plan a"
    ]
    is_complex = category in ("comparison", "product_lookup", "travel", "booking", "recipe") \
        or any(sig in query.lower() for sig in complex_signals)
    num_predict = 3200 if is_complex else 1800

    def call_ollama(n_predict):
        payload = {
            "model": OLLAMA_MODEL,
            "system": SYSTEM_PROMPT,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {"num_predict": n_predict, "temperature": 0.0, "num_ctx": 8192},
        }
        resp = requests.post(OLLAMA_URL, json=payload, timeout=300)
        resp.raise_for_status()
        body = resp.json()
        return body.get("response", ""), body.get("done_reason", "unknown")

    try:
        raw, done_reason = call_ollama(num_predict)

        # Ollama sets done_reason="length" when it hit num_predict and was
        # cut off mid-token — that's a hard signal of truncation, not just
        # a malformed model output. Retry once with a bigger budget instead
        # of giving up.
        if done_reason == "length" and num_predict < 4096:
            print(f"Truncated at {num_predict} tokens (done_reason=length) — retrying with 4096")
            num_predict = 4096
            raw, done_reason = call_ollama(num_predict)
    except Exception as e:
        print("OLLAMA ERROR:", str(e))
        return jsonify({"success": False, "error": f"Ollama call failed: {str(e)}"}), 500

    elapsed = time.time() - start_time
    print(f"Generation time: {elapsed:.2f}s | Output chars: {len(raw)} | done_reason={done_reason}")

    parsed = extract_json(raw)

    if parsed is not None:
        return jsonify({
            "success": True, "a2ui_json": parsed, "source": "ollama",
            "model": OLLAMA_MODEL, "category": category,
            "generation_time": round(elapsed, 2)
        })

    print("WARNING: Model output was not valid JSON.")
    print(raw[:2000])
    return jsonify({
        "success": False,
        "error": "Model output was not valid JSON"
                 + (" (truncated — hit token limit)" if done_reason == "length" else ""),
        "raw": raw[:5000], "category": category,
        "generation_time": round(elapsed, 2), "done_reason": done_reason
    })

# ============================================================
# LLM-AS-JUDGE
# Second model pass that scores a generated A2UI screen against
# the same style/richness rubric metrics.py measures numerically —
# but as qualitative judgment, catching things counting can't
# (e.g. "these components are the right types but arranged badly").
# ============================================================
JUDGE_PROMPT = """You are a UI/UX quality judge. You will be shown a user
query, the intended visual style, and the generated A2UI JSON screen for it.

Score the screen from 1-10 on each axis and give a one-line reason:
- style_fidelity: does it match the intended style description?
- component_richness: does it use varied, purposeful components (not just Text/Column)?
- relevance: does the content actually answer the user's query (not a generic/wrong topic)?
- completeness: does the JSON look finished (not truncated/cut off)?

Output ONLY this JSON shape, nothing else:
{"style_fidelity": {"score": N, "reason": "..."},
 "component_richness": {"score": N, "reason": "..."},
 "relevance": {"score": N, "reason": "..."},
 "completeness": {"score": N, "reason": "..."},
 "overall": N}
"""

@app.route("/judge", methods=["POST"])
def judge():
    try:
        data = request.get_json(force=True)
    except Exception:
        return jsonify({"success": False, "error": "Invalid JSON request"}), 400

    query = (data.get("query") or "").strip()
    a2ui_json = data.get("a2ui_json")
    category = data.get("category", "unknown")

    if not query or a2ui_json is None:
        return jsonify({"success": False, "error": "query and a2ui_json are required"}), 400

    style_name = CATEGORY_STYLES.get(category, "minimal")
    style_info = STYLE_TOKENS.get(style_name, STYLE_TOKENS["minimal"])

    judge_input = f"""User Query: {query}
Category: {category}
Intended Style: {style_info["desc"]}

Generated A2UI JSON:
{json.dumps(a2ui_json, indent=2)[:6000]}"""

    payload = {
        "model": OLLAMA_MODEL,
        "system": JUDGE_PROMPT,
        "prompt": judge_input,
        "stream": False,
        "format": "json",
        "options": {"num_predict": 500, "temperature": 0.0, "num_ctx": 8192},
    }
    try:
        resp = requests.post(OLLAMA_URL, json=payload, timeout=120)
        resp.raise_for_status()
        raw = resp.json().get("response", "")
    except Exception as e:
        return jsonify({"success": False, "error": f"Judge call failed: {str(e)}"}), 500

    scores = extract_json(raw)
    if scores is None:
        return jsonify({"success": False, "error": "Judge output was not valid JSON", "raw": raw[:2000]})

    return jsonify({"success": True, "scores": scores, "category": category})


if __name__ == "__main__":
    print(f"\n{'='*70}\nA2UI LOCAL BACKEND\n{'='*70}")
    print("Ollama:", OLLAMA_URL)
    print("Model:", OLLAMA_MODEL)
    print("\nHealth:  http://localhost:5000/health")
    print("Generate: POST http://localhost:5000/generate")
    print(f"{'='*70}\n")
    app.run(host="127.0.0.1", port=5000, debug=False)