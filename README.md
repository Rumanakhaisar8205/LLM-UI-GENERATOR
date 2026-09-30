# LLM-Powered UI Generator for Context-Aware Voice Assistant (A2UI)

An LLM finetuned to convert natural language queries into structured **A2UI v0.9** JSON UI layouts, rendered as mobile-app-style screens. Built for the voice-assistant visual-overlay use case: a spoken query like *"book a cab to the airport"* becomes a fully-formed, styled mobile UI instead of plain text.

## System Architecture

![System Architecture](D:\llm-ui-generator-v2\architecture\system_architecture.jpeg)

---

## 1. Project Summary

| | |
|---|---|
| **Base model** | Qwen2.5-Coder-3B-Instruct |
| **Finetuning** | QLoRA (4-bit), 1 epoch, ~5,300 training examples |
| **Deployment format** | GGUF (Q4_K_M quantization), served via Ollama |
| **Output schema** | A2UI v0.9 (JSON UI component tree) |
| **Categories covered** | 23 (weather, booking, recipe, travel, product lookup, comparison, etc.) — see `config.py` |
| **Dataset size** | 5,558 complete (query → response → A2UI JSON → HTML) training triplets |

## Model

| Component | Implementation |
|---|---|
| Base Model | Qwen2.5-Coder-3B-Instruct |
| Fine-Tuning | QLoRA |
| Training Epochs | 1 |
| Training Examples | ~5,300 |
| Complete Dataset Triplets | 5,558 |
| Quantization | Q4_K_M |
| Model Format | GGUF |
| Runtime | Ollama |
| Backend | Python Flask |
| Frontend | HTML / CSS / JavaScript |
| UI Representation | A2UI v0.9 JSON |

## Fine-Tuned Model

The fine-tuned Qwen2.5-Coder-3B-Instruct model is distributed in
GGUF Q4_K_M format for local inference through Ollama.

**Fine-Tuned Model:**
[Hugging Face Model Repository](https://huggingface.co/Rumanakhiasar/qwen3b-a2ui-v1)

**Base Model:**
[Qwen2.5-Coder-3B-Instruct](https://huggingface.co/Qwen/Qwen2.5-Coder-3B-Instruct)

### Pipeline overview
```
Stage 1: Query generation        (stage1_queries.py)     — Groq
Stage 2: Structured responses    (stage2_responses.py)   — Gemini/Vertex
Stage 3: A2UI JSON generation    (stage3_a2ui_json.py)   — Gemini/Vertex
Stage 4: HTML rendering          (stage4_html.py)        — local, no API
Stage 5: Finetuning data prep    (stage5_build_finetune_data.py)
Finetuning: QLoRA on Kaggle      (finetune_qlora.py)
Inference/Demo: local Ollama     (inference.py)
```
Stages 1–4 build the training dataset using third-party LLM APIs (Groq for cheap/fast query generation, Gemini/Vertex for rich structured responses and A2UI JSON). Stage 5 converts that dataset into SFT training pairs. The finetuning script trains a local, self-contained model that replaces the API dependency entirely for inference.

---

## 2. Dataset Quality Metrics

Measured via `python metrics.py` against the final dataset (5,581 A2UI screens generated, 5,558 complete triplets).

### Aesthetic Metrics
| Metric | Value |
|---|---|
| Total screens | 5,581 |
| Style coverage | 15/16 categories correctly styled (93.8%) |
| Style distribution | notion: 1,851 · minimal: 1,248 · maps: 768 · airbnb: 699 · amazon: 339 · spotify: 327 · unknown: 349 |
| Avg. component types per screen | 8.8 |
| Rich component rate | 83.2% |
| Image coverage | 89.7% |
| Avg. cards per screen | 2.3 |

### Agentic IR (Intent Representation) Metrics
| Metric | Value |
|---|---|
| Total queries generated | 10,015 |
| Total valid responses | 9,335 |
| Avg. constraints per query | 1.68 |
| Structured response rate | 100.0% |
| Grounded response rate | 0.4% (grounding intentionally disabled for the bulk of generation — see note below) |
| Avg. response word count | 359.0 |

### Dataset-10K Completion Metrics
| Metric | Value |
|---|---|
| Target | 10,000 triplets |
| Stage 1 (queries) | 10,015 |
| Stage 2 valid (responses) | 9,335 (93.2%) |
| Stage 3 valid (A2UI JSON) | 5,581 (59.8%) |
| **Full triplets (query → response → A2UI JSON)** | **5,558 (55.6% of target)** |

### UI Renderer Metrics
| Metric | Value |
|---|---|
| Allowed component types | 48 |
| Types actually used | 27 (56.2% coverage) |
| Avg. components per screen | 56.9 |
| Hallucinated component rate | 0.06 per screen |
| Dangling reference rate | 1.5% |
| HTML render success | 96.7% (5,397 / 5,581) |

**Notes on these numbers (for evaluators):**
- The 55.6% completion rate against the 10K target is due to free-tier API rate limits (Groq/Gemini) during Stage 2/3 generation, not a quality issue with the pipeline itself — Stage 2's 93.2% valid rate shows the response-generation step is reliable; the drop happens at Stage 3 (A2UI JSON generation, 59.8% valid), the more schema-constrained step.
- `unknown` in the style distribution (349 screens) reflects one category generated before the style-tagging field was added to the schema — regenerating that category would close this gap, deferred due to time constraints.
- Grounding (web-search-backed responses) was intentionally disabled (`GROUNDING_CATEGORIES = set()`) for the majority of generation to conserve API quota — the 0.4% reflects leftover data from early testing, not a bug.

---

## 3. Repository Structure

```
├── config.py                          # categories, style tokens, model settings
├── llm_client.py                      # API client wrappers (Groq/Gemini/Vertex) — dataset generation only
├── stage1_queries.py                  # Stage 1: synthetic query generation
├── stage2_responses.py                # Stage 2: structured text responses
├── stage3_a2ui_json.py                # Stage 3: A2UI JSON generation
├── stage4_html.py                     # Stage 4: HTML rendering (mobile frame)
├── stage5_build_finetune_data.py      # Builds train.jsonl / val.jsonl for finetuning
├── metrics.py                         # Dataset quality report (aesthetic/IR/renderer metrics)
├── run_pipeline.ipynb                 # Orchestrates stages 1-4 (Colab/Kaggle)
├── finetune_qlora.py                  # QLoRA finetuning script (run on Kaggle)
│
├── inference.py                       # ★ STANDALONE DEMO SCRIPT — run this to test the model
├── local_server1.py                   # Flask backend wrapping Ollama for the web frontend
├── index.html                         # Web frontend (mobile-styled UI renderer)
│
└── data/
    ├── queries/                       # Stage 1 output
    ├── responses/                     # Stage 2 output
    ├── a2ui_json/                     # Stage 3 output
    ├── html/                          # Stage 4 output
    └── finetune/                      # Stage 5 output (train.jsonl, val.jsonl)
```

---

## 4. Quick Start — Run the Demo (minimum steps)

This is the fastest path for a mentor/evaluator to verify the model works, with no dataset regeneration or training required.

### Step 1: Install Ollama
Download and install from **https://ollama.com/download** (Windows/Mac/Linux).

Verify it's installed:
```bash
ollama --version
```

### Step 2: Register the finetuned model
The finetuned model is distributed as a quantized `.gguf` file (see repository release / provided artifact). In the same folder as the `.gguf` file:
```bash
echo 'FROM ./qwen2.5-coder-3b-instruct.Q4_K_M.gguf' > Modelfile
ollama create a2ui-model -f Modelfile
```

### Step 3: Install Python dependencies
```bash
pip install requests flask flask-cors
```

### Step 4: Run the standalone inference script
```bash
python inference.py --query "Show me a 5-day weather forecast for Bengaluru"
```
Expected output: a JSON object containing `a2ui_json` (the generated UI layout), `category` (auto-detected), and `generation_time`.

To run the full demo suite (5 sample queries across different categories):
```bash
python inference.py --demo
```
This saves `demo_results.json` with results for every sample query — useful for a one-command sanity check.

### Step 5 (optional): Run the full web demo
For the visual, interactive version (mobile-styled rendered UI, not just raw JSON):
```bash
python local_server1.py
```
Leave that terminal running, then open `index.html` in a browser (double-click it, or serve it via any static file server). It connects automatically to `http://localhost:5000`.

---

## 5. Reproducing the Full Pipeline (dataset generation → finetuning)

Only needed if regenerating the dataset or retraining from scratch — **not required to run the demo above.**

### 4.1 Dataset generation (Colab/Kaggle)
Requires API keys for Groq and Gemini (free tiers work). Set them as environment variables (see `run_pipeline.ipynb` Cell 1), then:
```bash
python stage1_queries.py      # ~30 min
python stage2_responses.py    # ~6 hours (API rate limits)
python stage3_a2ui_json.py    # ~8 hours (API rate limits)
python stage4_html.py         # ~5 min (no API, pure Python)
```
Each stage is resumable — safe to interrupt and rerun.

Check dataset quality at any point:
```bash
python metrics.py
```

### 4.2 Finetuning data prep
```bash
python stage5_build_finetune_data.py
```
Produces `data/finetune/train.jsonl` and `val.jsonl`.

### 4.3 Finetuning (Kaggle, free T4 GPU)
Upload `train.jsonl`/`val.jsonl` as a Kaggle Dataset, open `finetune_qlora.py` in a Kaggle notebook (GPU accelerator enabled), update the file paths at the top of the script, and run. Produces:
- A LoRA adapter (`final_adapter/`)
- A quantized GGUF export (`gguf_export/*.gguf`) — this is the file used in the Quick Start above

**Hardware notes:** trains in a few hours on a single free-tier T4 (16GB) using QLoRA + Unsloth. bf16 is not supported on T4/P100 (Turing architecture) — the script uses fp16 instead.

---

## 6. Known Limitations

- **Dataset size**: 5,558 triplets (vs. an original 10,000 target) due to free-tier API rate limits during dataset generation. The model learns the schema and style patterns well but has less variety exposure than a larger dataset would provide.
- **Output shape consistency**: the finetuned model occasionally varies its JSON structure (e.g. nesting components differently) across generations of the same query. The frontend (`index.html`) includes a normalization layer that handles multiple observed output shapes, but this is a known soft spot — not a hard guarantee of schema conformance on every generation.
- **Generation latency**: 30–90 seconds per query on free-tier hardware (CPU or single consumer GPU via Ollama/llama.cpp), depending on query complexity. Not optimized for production-latency use.
- **Category detection**: the demo backend uses keyword-based category guessing (the original training pipeline had ground-truth categories; live queries don't). This is a heuristic, not a classifier — atypically phrased queries may get a suboptimal style hint.

---

## 7. Android APK

Not applicable — this project's frontend is a web-based mobile-styled UI (`index.html`), not a native Android application. No APK is included.
