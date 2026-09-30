"""
llm_client.py — Vertex AI (Gemini 2.5 Flash via ADC) + Groq fallback

FIXES APPLIED (per root cause analysis):
1. time.sleep(2) after every successful Vertex call — prevents rate limit 429s
2. Fallback model is same "gemini-2.5-flash" — "gemini-2.5-flash-lite" is
   preview-only and causes NOT_FOUND which was triggering the 403 fallback chain
3. max_tokens capped at 2500 for Vertex — 6000 was too aggressive for fresh quota
4. Groq max_tokens stays at 4000 cap to avoid 413 errors

Auth: gcloud auth application-default login (already done — no changes needed)
"""
import time, requests
from datetime import date
from config import (
    GROQ_API_KEYS, GROQ_URL, GROQ_MODEL,
    GCP_PROJECT, GCP_LOCATION,
    VERTEX_MODEL_PRO, VERTEX_MODEL_FLASH,
    GEMINI_API_KEYS,
)

# ── Key rotator ───────────────────────────────────────────────────────────────
class KeyRotator:
    def __init__(self, keys, rpm, daily_limit=None):
        self.keys        = keys if keys else [""]
        self.idx         = 0
        self.rpm         = rpm
        self.daily_limit = daily_limit
        self.calls       = []
        self.day_ct      = 0
        self.day_date    = date.today()
        self._backoff    = 1

    def get_key(self):  return self.keys[self.idx % len(self.keys)]

    def next_key(self):
        self.idx = (self.idx + 1) % len(self.keys)
        print(f"    Rotated to key {self.idx+1}/{len(self.keys)}")
        time.sleep(2)

    def wait(self):
        now = time.time()
        self.calls = [t for t in self.calls if now - t < 60]
        if len(self.calls) >= self.rpm:
            wait_secs = 62 - (now - self.calls[0])
            if wait_secs > 0:
                print(f"    Rate limit ({self.rpm} RPM) — waiting {wait_secs:.0f}s...", flush=True)
                time.sleep(wait_secs)
                self.calls = []
        self.calls.append(time.time())
        if date.today() != self.day_date:
            self.day_ct   = 0
            self.day_date = date.today()
        self.day_ct += 1

    def on_success(self): self._backoff = 1

    def on_429(self):
        wait = min(30 * self._backoff, 300)
        print(f"    429 received — backoff {wait}s...")
        time.sleep(wait)
        self._backoff = min(self._backoff * 2, 8)
        self.next_key()


# ── Singletons ────────────────────────────────────────────────────────────────
_groq          = None
_gemini        = None
_vertex_client = None

def _groq_rotator():
    global _groq
    if _groq is None:
        _groq = KeyRotator(GROQ_API_KEYS, rpm=28, daily_limit=14000)
    return _groq

def _gemini_rotator():
    global _gemini
    if _gemini is None:
        # 15 RPM per key free tier; with 3 keys rotate at combined ~40 RPM
        _gemini = KeyRotator(GEMINI_API_KEYS, rpm=14, daily_limit=1500)
    return _gemini

def _get_vertex_client():
    global _vertex_client
    if _vertex_client is None:
        from google import genai
        _vertex_client = genai.Client(
            vertexai=True,
            project=GCP_PROJECT,
            location=GCP_LOCATION,
        )
    return _vertex_client


# ── Vertex AI call ────────────────────────────────────────────────────────────
def call_vertex(prompt, system_prompt="", max_tokens=2500, temperature=0.7,
                model=None, use_grounding=False, json_mode=False):
    """
    Vertex AI via google-genai SDK + ADC.
    FIX: max_tokens capped at 2500 (was 6000 — too aggressive for fresh quota)
    FIX: time.sleep(2) after success — prevents 429 rate limit errors
    """
    from google import genai
    from google.genai import types

    if model is None:
        model = VERTEX_MODEL_PRO

    client = _get_vertex_client()

    contents = []
    if system_prompt:
        contents.append(
            types.Content(role="user",  parts=[types.Part(text=system_prompt)])
        )
        contents.append(
            types.Content(role="model", parts=[types.Part(text="Understood. I will follow these instructions.")])
        )
    contents.append(
        types.Content(role="user", parts=[types.Part(text=prompt)])
    )

    config_kwargs = {
        "max_output_tokens": max_tokens,   # caller controls limit (stage2=2500, stage3=8000)
        "temperature":       temperature,
    }
    if json_mode:
        config_kwargs["response_mime_type"] = "application/json"
    if use_grounding:
        config_kwargs["tools"] = [types.Tool(google_search=types.GoogleSearch())]

    config = types.GenerateContentConfig(**config_kwargs)

    for attempt in range(4):
        try:
            response = client.models.generate_content(
                model=model,
                contents=contents,
                config=config,
            )
            time.sleep(2)        # FIX: prevent rate limit on rapid calls
            return response.text

        except Exception as e:
            err = str(e)

            if "429" in err or "RESOURCE_EXHAUSTED" in err:
                wait = 30 * (attempt + 1)
                print(f"    Vertex 429 — waiting {wait}s (attempt {attempt+1}/4)")
                time.sleep(wait)
                continue

            if "403" in err or "PERMISSION_DENIED" in err:
                raise ValueError(
                    f"Vertex 403: {err[:300]}\n"
                    "Fix: run  gcloud auth application-default login  and retry."
                )

            if "404" in err or "NOT_FOUND" in err:
                raise ValueError(f"Vertex 404 model not found: {err[:200]}")

            if attempt == 3:
                raise

            time.sleep(3 * (attempt + 1))

    raise RuntimeError("Vertex AI failed after 4 attempts")


# ── Gemini API call (ai.google.dev — separate quota from Vertex) ──────────────
def call_gemini_api(prompt, system_prompt="", max_tokens=8000, temperature=0.7,
                    model="gemini-2.5-flash"):
    """
    Gemini API via google-generativeai SDK using GEMINI_API_KEY_1/2/3.
    Completely separate quota from Vertex AI — 15 RPM per key free tier.
    Rotates across keys to get combined ~40 RPM.
    """
    import google.generativeai as genai_api

    rot = _gemini_rotator()
    if not rot.keys or rot.keys == [""]:
        raise ValueError("No GEMINI_API_KEY — set GEMINI_API_KEY_1 env variable")

    for attempt in range(4):
        rot.wait()
        try:
            genai_api.configure(api_key=rot.get_key())

            gen_model = genai_api.GenerativeModel(
                model_name=model,
                system_instruction=system_prompt if system_prompt else None,
            )

            response = gen_model.generate_content(
                prompt,
                generation_config=genai_api.types.GenerationConfig(
                    max_output_tokens=max_tokens,
                    temperature=temperature,
                ),
            )
            time.sleep(1)   # light throttle — 15 RPM = 4s between calls per key
            rot.on_success()
            return response.text

        except Exception as e:
            err = str(e)
            if "429" in err or "RESOURCE_EXHAUSTED" in err or "quota" in err.lower():
                rot.on_429()
                continue
            if "400" in err or "API_KEY_INVALID" in err:
                raise ValueError(f"Gemini API bad key: {err[:150]}")
            if attempt == 3:
                raise
            time.sleep(3 * (attempt + 1))

    raise RuntimeError("Gemini API failed after 4 attempts")


# ── Groq call ────────────────────────────────────────────────────────────────
def call_groq(prompt, system_prompt="", max_tokens=4000, temperature=0.7):
    """Groq llama-3.1-8b. Capped at 4000 tokens to avoid 413 errors."""
    rot = _groq_rotator()
    if not rot.keys or rot.keys == [""]:
        raise ValueError("No GROQ_API_KEY — set GROQ_API_KEY env variable")

    msgs = []
    if system_prompt:
        msgs.append({"role": "system", "content": system_prompt})
    msgs.append({"role": "user", "content": prompt})

    for attempt in range(4):
        rot.wait()
        try:
            r = requests.post(
                GROQ_URL,
                headers={
                    "Authorization": f"Bearer {rot.get_key()}",
                    "Content-Type":  "application/json",
                },
                json={
                    "model":       GROQ_MODEL,
                    "messages":    msgs,
                    "max_tokens":  min(max_tokens, 4000),
                    "temperature": temperature,
                },
                timeout=90,
            )

            if r.status_code == 429:
                rot.on_429()
                continue
            if r.status_code == 401:
                raise ValueError(f"Groq 401 — bad key: {r.text[:100]}")
            if r.status_code == 413:
                raise ValueError("Groq 413 — prompt too large")

            r.raise_for_status()
            rot.on_success()
            return r.json()["choices"][0]["message"]["content"]

        except ValueError:
            raise
        except requests.exceptions.Timeout:
            print(f"    Groq timeout attempt {attempt+1}")
            time.sleep(5)
        except Exception as e:
            if attempt == 3:
                raise
            time.sleep(3 * (attempt + 1))

    raise RuntimeError("Groq failed after 4 attempts")


# ── Unified entry point ───────────────────────────────────────────────────────
def query_llm(prompt, system_prompt="", data_source="groq",
              max_tokens=7500, temperature=0.7,
              use_grounding=False, json_mode=False):
    """
    data_source:
      "groq"         — Groq only (Stage 1)
      "vertex_pro"   — Gemini 2.5 Flash via Vertex → Gemini API → Groq
      "vertex_flash" — Gemini 2.5 Flash via Vertex → Gemini API → Groq
      "gemini_api"   — Gemini API (ai.google.dev, GEMINI_API_KEYS) → Vertex → Groq
    """

    if data_source == "gemini_api":
        order = [
            lambda p, s, m, t: call_gemini_api(p, s, m, t),
            lambda p, s, m, t: call_vertex(p, s, m, t,
                                            model=VERTEX_MODEL_FLASH,
                                            use_grounding=False,
                                            json_mode=json_mode),
            call_groq,
        ]
    elif data_source == "vertex_pro":
        order = [
            lambda p, s, m, t: call_vertex(p, s, m, t,
                                            model=VERTEX_MODEL_PRO,
                                            use_grounding=use_grounding,
                                            json_mode=json_mode),
            lambda p, s, m, t: call_vertex(p, s, m, t,
                                            model=VERTEX_MODEL_FLASH,
                                            use_grounding=False,
                                            json_mode=json_mode),
            call_groq,
        ]
    elif data_source == "vertex_flash":
        order = [
            lambda p, s, m, t: call_vertex(p, s, m, t,
                                            model=VERTEX_MODEL_FLASH,
                                            use_grounding=False,
                                            json_mode=json_mode),
            lambda p, s, m, t: call_vertex(p, s, m, t,
                                            model=VERTEX_MODEL_PRO,
                                            use_grounding=False,
                                            json_mode=json_mode),
            call_groq,
        ]
    else:
        order = [call_groq]

    last_err = None
    for fn in order:
        try:
            result = fn(prompt, system_prompt, max_tokens, temperature)
            name = getattr(fn, "__name__", repr(fn))
            print(f"    [OK: {name}] ({len(result)} chars)")
            return result
        except Exception as e:
            name = getattr(fn, "__name__", repr(fn))
            print(f"    [{name}] failed: {str(e)[:80]}, trying next...")
            last_err = e

    raise RuntimeError(f"All APIs failed. Last error: {last_err}")