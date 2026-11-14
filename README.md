# Clearance

**AI expense approval powered by Drex: decisions in milliseconds, not seconds.**

> Drexathon 2026 · Track: **🦖 Apex Predator**
> Built with **Drex** (System 1) · **DeepInfra** (Qwen explanations, DeepSeek-V3 baseline) · **Keenable**
>
> Status: receipts are read with pypdf (NDI client is wired in but was not enabled for the benchmark). Intern and Adobe assets were planned but not used in this build.

Clearance reads a receipt or invoice (PDF, photo, scan or email), checks it against a company expense policy, and returns **Approve / Flag / Reject** with a calibrated confidence for every check, in milliseconds.

The point of the project is the benchmark. Every policy check that teams normally send to a frontier LLM is a *decision*, not a writing task. We move those decisions to **Drex** and measure **accuracy, latency and cost** against a frontier LLM on the same labeled receipts.

---

## 1. The problem

Finance teams review thousands of receipts a month. Today the options are:

| Option | Problem |
|---|---|
| Humans | Slow, inconsistent, expensive |
| Rules engines | Break on messy real documents |
| Frontier LLM prompts | Seconds per receipt, costly at volume, and the output is free text that must be parsed and can drift |

Every check is one of three question types: **yes/no** ("over the limit?"), **choice** ("which category?") or **score** ("how risky?"). That is exactly what a decision model is for.

## 2. How it works

```
 Receipt / invoice (PDF, JPG, scan, .eml)
            │
            ▼
   ┌─────────────────┐
   │  NDI            │  parse → classify → extract fields
   │  (the "eyes")   │  vendor, date, total, line items, tax, currency
   └────────┬────────┘
            │  structured "state" text
            ▼
   ┌─────────────────┐     ┌──────────────────┐
   │  Keenable       │────▶│ vendor web check │  is this a real business?
   └────────┬────────┘     └──────────────────┘
            ▼
   ┌─────────────────┐
   │  Drex           │  ONE /v1/systemone call, 7 typed questions
   │  (System 1)     │  → probabilities for every answer
   └────────┬────────┘
            ▼
   ┌─────────────────┐
   │  Policy engine  │  plain Python: combine answers → Approve / Flag / Reject
   └────────┬────────┘
            ▼  (only if Flag or Reject)
   ┌─────────────────┐
   │ Qwen on         │  one-sentence explanation for the employee
   │ DeepInfra (S2)  │
   └────────┬────────┘
            ▼
      Web UI + JSON API
```

**Design rule:** Drex makes every *decision*; the LLM only *writes*, and only when a human needs to read something.

## 3. Tech stack

| Layer | Choice | Why |
|---|---|---|
| Coding agent | **Intern** (`--system1 drex-latest --system2 deepinfra/Qwen/Qwen3.8-27B`) | Required; also scores on usage |
| Backend | Python 3.12, **FastAPI**, `httpx` | Fast to build, async |
| Document parsing | **NDI** (Nace Data Intelligence) | Bonus points for real-world docs |
| Decisions | **Drex** via `POST /v1/systemone` | The core of the project |
| Explanations + LLM baseline | **DeepInfra** (OpenAI-compatible API) | Partner tool |
| Vendor check | **Keenable** (`pip install keenable`, works keyless) | Partner tool |
| Frontend | One `index.html` + Tailwind CDN + vanilla JS | Apple-style UI with no build step |
| Charts | Chart.js (CDN) | Benchmark page |
| Visual assets / deck | **Adobe Firefly** (hero image, icons), **Adobe Express** (deck, results poster) | Partner tool + Best Use of Adobe prize |

## 4. Repository layout

```
clearance/
├── README.md
├── .env.example
├── requirements.txt
├── app/
│   ├── main.py            # FastAPI: POST /api/review, GET /api/benchmark, serves UI
│   ├── pipeline.py        # NDI -> Keenable -> Drex -> policy -> Qwen
│   ├── ndi.py             # NDI client -> extracted fields (pypdf / email / vision fallbacks)
│   ├── state.py           # builds the plain-text state both pipelines see
│   ├── drex.py            # Drex /v1/systemone client + the 7 questions
│   ├── baseline.py        # frontier-LLM baseline: same state, same questions, JSON prompt
│   ├── keenable_check.py  # vendor legitimacy lookup
│   ├── policy.py          # thresholds + decision combiner
│   ├── explain.py         # Qwen (DeepInfra) one-line explanation
│   └── config.py          # .env loading + the expense policy
├── bench/
│   ├── labels.csv         # file, expected_decision, expected_category, violations
│   ├── run_bench.py       # Drex vs frontier LLM on the same receipts
│   └── results.json       # written by run_bench.py, read by the UI
├── data/
│   ├── receipts/          # 37 synthetic receipts (+ your real ones)
│   └── history.json       # "previous submissions" used for duplicate checks
├── scripts/make_receipts.py  # regenerates the synthetic set + labels
└── web/
    ├── index.html         # upload + verdict
    ├── benchmark.html     # the charts
    └── style.css          # Apple-style tokens
```

## 5. Setup

```bash
git clone <this repo> && cd clearance
uv venv --python 3.12
# Windows:  .venv\Scripts\activate      macOS/Linux:  source .venv/bin/activate
uv pip install -r requirements.txt
cp .env.example .env    # fill in keys  (Windows: copy .env.example .env)
uvicorn app.main:app --reload
# open http://localhost:8000
```

Run the benchmark (writes `bench/results.json`, shown at `/benchmark`):

```bash
python bench/run_bench.py            # cached reruns are free
python bench/run_bench.py --fresh    # call everything again
```

No keys yet? `MOCK=1` in `.env` runs everything offline with keyword heuristics so you can work on
the UI. Mock results are labeled on every screen and must never be reported.

Intern (required coding agent):

```bash
uv tool install --python 3.12 "intern-agent @ git+https://github.com/nace-ai/intern"
intern --system1 drex-latest --system2 deepinfra/Qwen/Qwen3.8-27B
```

`.env.example` has every setting, including prices for the cost metric
(`BASELINE_PRICE_IN_PER_M`, `BASELINE_PRICE_OUT_PER_M`, `DREX_PRICE_PER_1K_CALLS`).

> ⚠️ Never commit `.env`. It is already in `.gitignore`. The repo must be public.

## 6. The Drex call (the heart of the project)

One request per receipt, seven questions. Drex returns a probability for every option in a single pass, with no text generation.

Request shape (TypeSafe System One format). **Verify the exact URL and auth header in console.nace.ai docs before building.**

```python
# app/drex.py
import os, time, httpx

QUESTIONS = {
    "over_limit": {
        "type": "noul",
        "instructions": "Is the total above the per-category limit stated in the POLICY section?",
    },
    "category": {
        "type": "choice",
        "instructions": "Which expense category does this receipt belong to?",
        "criteria": {
            "meals": "Restaurants, cafes, food delivery",
            "travel": "Flights, hotels, taxis, rideshare, fuel, parking",
            "software": "SaaS subscriptions, licenses, cloud services",
            "office": "Supplies, equipment, furniture",
            "other": "Anything else",
        },
    },
    "non_reimbursable": {
        "type": "noul",
        "instructions": "Does the receipt contain alcohol, tobacco, gifts, personal items or other items the POLICY says are not reimbursable?",
    },
    "duplicate": {
        "type": "noul",
        "instructions": "Does this receipt match one in PREVIOUS SUBMISSIONS (same vendor, same amount, same or adjacent date)?",
    },
    "missing_info": {
        "type": "noul",
        "instructions": "Is any required field missing or unreadable: vendor, date, total, or itemization?",
    },
    "weekend_or_holiday": {
        "type": "noul",
        "instructions": "Was this purchase made on a weekend or public holiday?",
    },
    "risk": {
        "type": "score",
        "instructions": "Overall, how likely is this expense to violate policy or be fraudulent?",
        "criteria": ["Clean", "Low risk", "Some concern", "High risk", "Almost certainly a violation"],
    },
}

def ask_drex(state: str) -> dict:
    t0 = time.perf_counter()
    r = httpx.post(
        f"{os.environ['DREX_BASE_URL']}/v1/systemone",
        headers={"Authorization": f"Bearer {os.environ['NACE_API_KEY']}"},
        json={"model": os.environ["DREX_MODEL"], "state": state, "questions": QUESTIONS},
        timeout=30,
    )
    r.raise_for_status()
    out = r.json()
    out["latency_ms"] = (time.perf_counter() - t0) * 1000
    return out
```

**The `state` string** is plain text built from NDI output plus context:

```
RECEIPT
Vendor: Blue Bottle Coffee
Date: 2026-11-08 (Saturday)
Total: 84.50 USD
Items: 2x latte 12.00; 1x pastry 6.50; 1x bottle wine 54.00 ...
Vendor web check: verified business (Keenable, 3 matching results)

POLICY
Meals limit 75 USD per receipt. Travel limit 500. Software limit 300. Office 200.
Not reimbursable: alcohol, tobacco, gifts, personal items.

PREVIOUS SUBMISSIONS (same employee, last 30 days)
2026-11-01 Uber 23.10 · 2026-11-03 Notion 10.00
```

**Expected response shape** (answers come back under the names you chose):

```json
{
  "answers": {
    "over_limit":       {"type": "noul",   "noul": 0.97},
    "category":         {"type": "choice", "choice": "meals", "confidence": 0.95,
                         "probabilities": {"meals": 0.96, "travel": 0.01, "...": 0.0}},
    "non_reimbursable": {"type": "noul",   "noul": 0.99},
    "risk":             {"type": "score",  "score": 3.1, "confidence": 0.81, "probabilities": {...}}
  }
}
```

## 7. Policy engine (plain Python, no model)

```python
# app/policy.py
def decide(a: dict) -> tuple[str, list[str]]:
    p = lambda k: a[k]["noul"]
    reasons = []
    if p("non_reimbursable") > 0.7: reasons.append("Contains non-reimbursable items")
    if p("duplicate") > 0.7:        reasons.append("Looks like a duplicate submission")
    if p("over_limit") > 0.6:       reasons.append("Over category limit")
    if p("missing_info") > 0.6:     reasons.append("Missing required information")
    if p("weekend_or_holiday") > 0.8: reasons.append("Weekend purchase")

    if p("duplicate") > 0.85 or p("non_reimbursable") > 0.9:
        return "reject", reasons
    if reasons or a["risk"]["score"] >= 2.5:
        return "flag", reasons
    return "approve", reasons
```

Keeping the final rule in code makes the system **auditable**. Every decision traces back to a probability and a threshold, which is a selling point for finance teams.

## 8. Benchmark (what the judges score)

**Dataset: 37 receipts in `data/receipts/`** (synthetic set from `scripts/make_receipts.py`; add real ones per `data/receipts/README.md`)

- About 60% genuine receipts from your inbox, phone photos, or public receipt datasets.
- About 40% with planted violations: total over the limit, wine on a meal receipt, an exact duplicate, a weekend date, a fake vendor name, a blurred total.
- `bench/labels.csv` holds the correct decision, category and violations for each file. You wrote the policy, so you know the truth.

**Run both pipelines on identical NDI output:**

| Pipeline | How |
|---|---|
| **Drex** | `ask_drex(state)` → `decide()` |
| **Frontier LLM baseline** | Same `state` + same 7 questions as a prompt to `BASELINE_MODEL`, asking for JSON answers; same `decide()` |

**Report:**

| Metric | How |
|---|---|
| Decision accuracy | % matching `expected_decision` |
| Violation recall | % of planted violations caught |
| Category accuracy | % matching `expected_category` |
| Median and p95 latency | `time.perf_counter()` around each call |
| Cost per 1,000 receipts | tokens × published price |
| Parse failures | LLM outputs that weren't valid JSON (Drex: always 0) |

`python bench/run_bench.py` writes `bench/results.json`. `web/benchmark.html` renders it.

**Headline slide:** *"Drex: __× faster, __× cheaper, __% vs __% accuracy, 0 parse failures."* Fill in with **real measured numbers only**.

## Results (measured Nov 14, 2026)

37 labeled receipts (23 clean, 14 with 15 planted violations). Both pipelines got identical input
(same parsed receipt, same vendor web check, same 8 questions, same `decide()` thresholds).
Baseline: `deepseek-ai/DeepSeek-V3` on DeepInfra. Latency is the decision call only, measured round trip from a home connection.

| Metric | Drex (`drex-latest`) | DeepSeek-V3 |
|---|---|---|
| Decision accuracy | **37/37 (100%)** | 34/37 (92%) |
| Violation recall | **15/15 (100%)** | 13/15 (87%) |
| Category accuracy | 36/37 (97%) | 36/37 (97%) |
| Clean receipts wrongly flagged | **0/23** | 1/23 |
| Median latency | **326 ms** (Drex server time 178 ms) | 2,487 ms |
| p95 latency | **526 ms** | 5,182 ms |
| Parse failures | 0 | 0 |
| Cost per 1,000 receipts | not computed (Drex pricing not set) | not computed |

**Drex: 7.6× faster, 100% vs 92% decision accuracy, 0 parse failures.**

Honest notes:
- v1 (7 questions, looser vendor matching) scored Drex 35/37 and the LLM 33/37, 5.1× faster. Drex missed both
  fake vendors. v2 added an 8th question (`vendor_unverified`) and a stricter Keenable name match, then reran both
  pipelines on the **same** 37 receipts, so v2 was tuned after seeing v1's misses.
- The dataset is small and synthetic, and we wrote both the policy and the labels.
- The LLM's misses: both duplicate submissions (approved) and one clean receipt flagged.

## 9. API

| Method | Path | Body | Returns |
|---|---|---|---|
| `POST` | `/api/review` | multipart `file` | `{decision, reasons, explanation, fields, answers, latency_ms}` |
| `GET` | `/api/benchmark` | — | contents of `bench/results.json` |
| `GET` | `/` | — | upload UI |
| `GET` | `/benchmark` | — | benchmark page |

---

## 10. Design spec: Apple-style UI

The UI should feel like an Apple product page: calm, spacious, typographic, one idea per screen.

### Principles
1. **Content first.** No borders where whitespace works. No dashboards crammed with widgets.
2. **One hero per screen.** The upload drop zone, then the verdict. Nothing competes.
3. **Big type, few words.** Headlines do the selling; body text explains.
4. **Motion is quiet.** 200–300 ms ease-out fades and lifts. Nothing bounces.
5. **Color means something.** Grayscale everywhere; color appears only for status.

### Tokens

| Token | Light | Dark |
|---|---|---|
| Background | `#FFFFFF` | `#000000` |
| Section background | `#F5F5F7` | `#1C1C1E` |
| Primary text | `#1D1D1F` | `#F5F5F7` |
| Secondary text | `#6E6E73` | `#A1A1A6` |
| Hairline | `rgba(0,0,0,0.08)` | `rgba(255,255,255,0.12)` |
| Accent (links, buttons) | `#0071E3` | `#2997FF` |
| Approve | `#34C759` | `#30D158` |
| Flag | `#FF9F0A` | `#FF9F0A` |
| Reject | `#FF3B30` | `#FF453A` |

**Typography:** `font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "Inter", "Helvetica Neue", sans-serif;`

| Role | Size / weight / tracking |
|---|---|
| Hero headline | 56–80px · 700 · `-0.015em` |
| Section headline | 40px · 600 · `-0.01em` |
| Verdict word ("Approved") | 64px · 700 |
| Body | 17px · 400 · line-height 1.47 |
| Caption / labels | 12–14px · 500 · secondary color |
| Numbers | `font-variant-numeric: tabular-nums` |

**Shape and depth**
- Card radius 18–22px; button radius 980px (pill).
- Shadow only on floating elements: `0 4px 24px rgba(0,0,0,0.06)`.
- Nav bar: `backdrop-filter: saturate(180%) blur(20px); background: rgba(255,255,255,0.72)`, height 52px, hairline bottom.
- Max content width 980px, centered; section padding 96px vertical.

### Screens

**1. Home / Upload**
```
┌──────────────────────────────────────────────────────────┐
│  Clearance                         Review   Benchmark    │  ← frosted nav
├──────────────────────────────────────────────────────────┤
│                                                          │
│                Expenses, cleared.                        │  ← 72px headline
│        Every receipt checked in milliseconds.            │  ← 24px secondary
│                                                          │
│     ╭──────────────────────────────────────────────╮     │
│     │                                              │     │
│     │          ⬆  Drop a receipt or invoice        │     │  ← #F5F5F7 card,
│     │         PDF, photo, scan or email            │     │    dashed hairline,
│     │                                              │     │    lifts on hover
│     ╰──────────────────────────────────────────────╯     │
│                                                          │
│          Try a sample:  ◯ Dinner  ◯ Flight  ◯ SaaS       │  ← pill chips
└──────────────────────────────────────────────────────────┘
```

**2. Processing (under 1 s, but show it)**
Three steps fade in sequence with small checkmarks: *Reading document · Checking vendor · Deciding*. Use a thin progress line, not a spinner.

**3. Verdict**
```
              ● Flagged                          ← 64px, status color dot
     Contains non-reimbursable items             ← 21px secondary
         Decided in 38 ms · 96% confident        ← caption, tabular nums

  ╭─ Blue Bottle Coffee ──────────────── $84.50 ╮
  │ Sat, Nov 8 · Meals                           │
  ╰──────────────────────────────────────────────╯

  Checks
  Within limit             ━━━━━━━━━━━━━━━  97%  ✕
  No restricted items      ━━━━━━━━━━━━━━━  99%  ✕
  Not a duplicate          ━━━━━━━━━━━━━━━   4%  ✓
  Vendor verified          ✓ Found on the web
  Risk                     ○ ○ ○ ● ○  High

  "This receipt includes a $54 bottle of wine, which
   isn't reimbursable under the meals policy."   ← Qwen, italic, secondary

          [ Approve anyway ]   [ Send back ]      ← pill buttons
```
Each probability bar is a 4px rounded track that animates from 0 to its value over 400 ms.

**4. Benchmark: the money page**
- Hero: **"38 ms vs 4.2 s."** (real numbers), subline *"Same receipts. Same questions. Drex vs a frontier LLM."*
- Three large stat tiles in a row: **Speed ×**, **Cost ×**, **Accuracy**. Each has a huge number and a small caption.
- Below: one horizontal bar chart per metric, Drex in accent blue, LLM in gray `#86868B`. No gridlines, no chart borders.
- Footer line: "Measured on 40 labeled receipts · Nov 14, 2026."

### Adobe assets
- **Firefly:** a soft abstract hero image (white and pale blue glass shapes, studio light) for the home page and the deck cover; also a set of minimal line icons for categories.
- **Express:** a 5-slide deck in the same style (white, huge type, one number per slide): Problem → How it works → Live demo → Benchmark → Built with. Export one "results poster" PNG for social media.

---

## 11. Build order (about 75 minutes)

| Time | Task | Done when |
|---|---|---|
| 0:00–0:10 | Repo, `.env`, `.gitignore`, collect 30–40 receipts, write `labels.csv` | Files in `data/` |
| 0:10–0:30 | `ndi.py` + `drex.py` + `policy.py`; test on one receipt from the CLI | Prints a verdict |
| 0:30–0:45 | `run_bench.py` against both pipelines | `results.json` exists |
| 0:45–1:00 | FastAPI routes + `index.html` + `benchmark.html` | Upload works in the browser |
| 1:00–1:05 | Keenable vendor check + Qwen explanation | Shown on verdict screen |
| 1:05–1:15 | Firefly image, Express deck, push, submit, **Finalize** | Entry finalized |

**If time runs out, cut in this order:** dark mode → Keenable → Qwen explanation → processing animation. **Never cut the benchmark.**

## 12. Fallbacks

- **NDI unavailable:** `pypdf` for PDFs; for images, send the image to Drex directly if the endpoint accepts `assets`, or OCR with a DeepInfra vision model. Note it in the deck.
- **Drex rate-limited:** cache answers by file hash in `bench/cache.json` so benchmark reruns are free.
- **Baseline returns broken JSON:** count it as a parse failure (that is a real finding), don't retry silently.

## 13. Submission checklist

- [ ] Public GitHub repo, no keys committed
- [ ] README with the benchmark table filled in with measured numbers
- [ ] Presentation (Adobe Express) linked
- [ ] Track: **Apex Predator**
- [ ] Demo URL (optional): local recording or tunnel
- [ ] Mention every tool used: Intern, Drex, NDI, DeepInfra, Keenable, Adobe Firefly, Adobe Express
- [ ] Click **Finalize** before 3:00 PM PT

## License
MIT