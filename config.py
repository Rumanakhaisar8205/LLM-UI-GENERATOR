"""
config.py — Complete configuration for 10K dataset generation

CHANGES IN THIS VERSION:
- Added CATEGORY_STYLES: maps each category to a mobile app style
- Added STYLE_TOKENS: visual tokens (colors, variants) per style
- Added GEMINI_API_KEYS for separate quota from Vertex
- STAGE3_PRIMARY = "gemini_api"
- SAVE_EVERY = 10
"""
import os

BASE_DIR      = os.path.dirname(os.path.abspath(__file__))
QUERIES_DIR   = os.path.join(BASE_DIR, "data", "queries")
RESPONSES_DIR = os.path.join(BASE_DIR, "data", "responses")
A2UI_JSON_DIR = os.path.join(BASE_DIR, "data", "a2ui_json")
HTML_DIR      = os.path.join(BASE_DIR, "data", "html")
for d in [QUERIES_DIR, RESPONSES_DIR, A2UI_JSON_DIR, HTML_DIR]:
    os.makedirs(d, exist_ok=True)

# ── GROQ API KEYS ─────────────────────────────────────────────────────────────
GROQ_API_KEYS = [k for k in [
    os.environ.get("GROQ_API_KEY_1", os.environ.get("GROQ_API_KEY", "")),
    os.environ.get("GROQ_API_KEY_2", ""),
    os.environ.get("GROQ_API_KEY_3", ""),
] if k]

# ── GEMINI API KEYS (ai.google.dev — separate quota from Vertex) ──────────────
GEMINI_API_KEYS = [k for k in [
    os.environ.get("GEMINI_API_KEY_1", os.environ.get("GEMINI_API_KEY", "")),
    os.environ.get("GEMINI_API_KEY_2", ""),
    os.environ.get("GEMINI_API_KEY_3", ""),
] if k]

# ── VERTEX AI / GOOGLE CLOUD ──────────────────────────────────────────────────
GCP_PROJECT  = os.environ.get("GOOGLE_CLOUD_PROJECT", "project-3524613c-385d-4472-b40")
GCP_LOCATION = os.environ.get("GCP_LOCATION", "us-central1")

# ── MODEL SETTINGS ────────────────────────────────────────────────────────────
GROQ_URL   = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "llama-3.1-8b-instant"

VERTEX_MODEL_PRO   = "gemini-2.5-flash"
VERTEX_MODEL_FLASH = "gemini-2.5-flash"

# ── STAGE PRIMARY MODELS ──────────────────────────────────────────────────────
STAGE1_PRIMARY = "groq"
STAGE2_PRIMARY = "vertex_pro"
STAGE3_PRIMARY = "gemini_api"

# ── SCALE SETTINGS ────────────────────────────────────────────────────────────
QUERIES_PER_CATEGORY = 435
BATCH_SIZE           = 25
SAVE_EVERY           = 10

# ── GROUNDING CATEGORIES ──────────────────────────────────────────────────────
GROUNDING_CATEGORIES = set()

# ── WEAK CATEGORIES ───────────────────────────────────────────────────────────
WEAK_CATEGORIES = {
    "status_check", "research_analysis", "creative_writing",
    "technical_support", "data_visualization", "qr_scanner",
}

# ── CATEGORIES ────────────────────────────────────────────────────────────────
CATEGORIES = {
    
    "research_analysis":     {"color": "#673AB7"},
    "comparison":            {"color": "#FF9900"},
    "calculation":           {"color": "#00BCD4"},
    "information_retrieval": {"color": "#2563EB"},
    "entertainment":         {"color": "#1DB954"},
    "product_lookup":        {"color": "#FF9900"},
    "data_visualization":    {"color": "#9C27B0"},
    "productivity":          {"color": "#2383E2"},
    "technical_support":     {"color": "#2383E2"},
    "creative_writing":      {"color": "#2383E2"},
    "travel":                {"color": "#FF385C"},
    "navigation":            {"color": "#1A73E8"},
    "education":             {"color": "#2383E2"},
    "event_schedule":        {"color": "#8BC34A"},
    "localization":          {"color": "#1A73E8"},
    "booking":               {"color": "#FF385C"},
    "documentation":         {"color": "#2383E2"},
    "media_playback":        {"color": "#1DB954"},
    "recipe":                {"color": "#FC8019"},
    "qr_scanner":            {"color": "#558B2F"},
    "weather":               {"color": "#2563EB"},
    "planning":              {"color": "#2383E2"},
    "status_check":          {"color": "#6A1B9A"},
}

# ── CATEGORY → MOBILE APP STYLE ───────────────────────────────────────────────
# Maps each category to a visual style used by stage3 prompts + stage4 renderer.
CATEGORY_STYLES = {
    "media_playback":        "spotify",
    "entertainment":         "spotify",
    "product_lookup":        "amazon",
    "comparison":            "amazon",
    "booking":               "airbnb",
    "travel":                "airbnb",
    "navigation":            "maps",
    "localization":          "maps",
    "recipe":                "swiggy",
    "education":             "notion",
    "documentation":         "notion",
    "productivity":          "notion",
    "planning":              "notion",
    "research_analysis":     "notion",
    "creative_writing":      "notion",
    "weather":               "minimal",
    "calculation":           "minimal",
    "data_visualization":    "minimal",
    "event_schedule":        "minimal",
    "information_retrieval": "minimal",
    "status_check":          "minimal",
    "technical_support":     "minimal",
    "qr_scanner":            "minimal",
}

# ── STYLE DEFINITIONS ─────────────────────────────────────────────────────────
STYLE_TOKENS = {
    "spotify": {
        "bg":           "#121212",
        "surface":      "#1E1E1E",
        "text_primary": "#FFFFFF",
        "text_secondary":"#B3B3B3",
        "accent":       "#1DB954",
        "card_variant": "musicCard",
        "button_variant":"pill",
        "image_variant": "square",
        "desc": "Spotify dark: dark bg #121212, surface #1E1E1E, green accent #1DB954, "
                "white text, pill buttons, square album/cover images, Badge for ratings",
    },
    "amazon": {
        "bg":           "#FFFFFF",
        "surface":      "#F7F8F8",
        "text_primary": "#0F1111",
        "text_secondary":"#565959",
        "accent":       "#FF9900",
        "card_variant": "productCard",
        "button_variant":"cta",
        "image_variant": "square",
        "desc": "Amazon: white bg, orange accent #FF9900, bold price text variant='price', "
                "star Badge for ratings, yellow CTA buy button, product image square",
    },
    "airbnb": {
        "bg":           "#FFFFFF",
        "surface":      "#F7F7F7",
        "text_primary": "#222222",
        "text_secondary":"#717171",
        "accent":       "#FF385C",
        "card_variant": "bookingCard",
        "button_variant":"rounded",
        "image_variant": "mediumFeature",
        "desc": "Airbnb: white bg, pink-red accent #FF385C, large mediumFeature images, "
                "rounded cards, price per night Badge, Book Now primary button",
    },
    "maps": {
        "bg":           "#FFFFFF",
        "surface":      "#F5F5F5",
        "text_primary": "#202124",
        "text_secondary":"#70757A",
        "accent":       "#1A73E8",
        "card_variant": "placeCard",
        "button_variant":"outlined",
        "image_variant": "mediumFeature",
        "desc": "Google Maps: white bg, blue accent #1A73E8, place cards with rating Badge, "
                "distance Chip, Directions outlined button, open/closed Badge",
    },
    "swiggy": {
        "bg":           "#FFFFFF",
        "surface":      "#F5F5F5",
        "text_primary": "#282C3F",
        "text_secondary":"#93959F",
        "accent":       "#FC8019",
        "card_variant": "foodCard",
        "button_variant":"cta",
        "image_variant": "mediumFeature",
        "desc": "Swiggy: white bg, orange accent #FC8019, food images, price Badge, "
                "delivery time Chip, veg/non-veg Badge, Add button cta",
    },
    "notion": {
        "bg":           "#FFFFFF",
        "surface":      "#F7F6F3",
        "text_primary": "#37352F",
        "text_secondary":"#787774",
        "accent":       "#2383E2",
        "card_variant": "infoCard",
        "button_variant":"ghost",
        "image_variant": "mediumFeature",
        "desc": "Notion: clean white bg, warm gray surface, blue link accent #2383E2, "
                "tag Chips, ghost buttons, monospace code text, minimal borders",
    },
    "minimal": {
        "bg":           "#FFFFFF",
        "surface":      "#F8FAFC",
        "text_primary": "#1E293B",
        "text_secondary":"#64748B",
        "accent":       "#2563EB",
        "card_variant": "infoCard",
        "button_variant":"primary",
        "image_variant": "mediumFeature",
        "desc": "Clean minimal: white bg, slate grays, blue accent, subtle card shadows, "
                "clear text hierarchy, standard primary buttons",
    },
}

# ── A2UI COMPONENT REGISTRY ───────────────────────────────────────────────────
A2UI_COMPONENTS = {
    "Column","Row","Stack","Grid",
    "Text","Image","Icon","Divider","Video","AudioPlayer",
    "List","Table","TableRow","TableCell",
    "Card","Tabs","Tab","Modal","Drawer","Carousel","Gallery",
    "TextField","CheckBox","RadioGroup","Dropdown","Slider",
    "DateTimeInput","ChoicePicker","Switch",
    "Button","FloatingActionButton",
    "Loader","Skeleton","ProgressBar","Toast","Snackbar",
    "AppBar","BottomNavigation","Breadcrumb","Stepper",
    "Map","Tooltip","Badge","Chip","Tag",
    "RefreshControl","PullToRefresh","InfiniteScroll",
}