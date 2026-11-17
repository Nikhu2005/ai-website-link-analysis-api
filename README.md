# AI-Powered Website Link Analysis API

A FastAPI service that analyses a website with an LLM and returns structured JSON:
competitor comparison, top 5 target search queries, SEO improvements, top 5 services and target audience.

## How it works

```
POST /link-analysis {"url": "..."}
  1. validate URL  -> scheme/host checks + SSRF guard (public IPs only, re-checked on every redirect)
  2. fetch HTML    -> httpx, timeouts, size cap, content-type check, manual redirect handling
  3. extract       -> title, meta, headings, nav labels, cleaned main text (deduped, capped)
  4. LLM call      -> one structured prompt, JSON mode, provider selectable by env var
  5. validate      -> Pydantic schema, one retry on malformed JSON, "top 5" enforced
  6. respond       -> JSON (+ in-memory cache so repeat URLs cost nothing)
```

```
app/
  main.py                      FastAPI app, endpoint, error handlers
  config.py                    env-based settings
  schemas.py                   request / LLM / response models
  errors.py                    domain errors -> HTTP status codes
  services/website_extractor.py  fetch + clean content
  services/llm_service.py        Gemini / OpenAI / Anthropic via HTTPX
  services/analysis_service.py   pipeline + cache
  utils/validators.py            URL validation + SSRF protection
tests/test_link_analysis.py    23 tests (LLM and network mocked)
```

## Setup

Requires Python 3.10+.

```bash
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env        # then add ONE API key (never commit .env)
uvicorn app.main:app --host 0.0.0.0 --port 4000
```

- Swagger docs: http://localhost:4000/docs
- Health check: `GET /health`
- Tests: `pytest`

### Choosing the LLM

Set in `.env`:

| `LLM_PROVIDER` | Key variable | Default model |
|---|---|---|
| `gemini` (default) | `GEMINI_API_KEY` | `gemini-3.5-flash-lite` |
| `openai` | `OPENAI_API_KEY` | `gpt-5-mini` |
| `anthropic` | `ANTHROPIC_API_KEY` | `claude-haiku-5-5` |

Override the model with `LLM_MODEL`.

> **Gemini note:** `gemini-2.5-flash-lite` is no longer available to new API keys and returns HTTP 404.
> The default is now `gemini-3.5-flash-lite`. Setting `LLM_MODEL` in `.env` is optional.

Example `.env` for Gemini:

```
LLM_PROVIDER=gemini
GEMINI_API_KEY=your_key_here
```

Restart the server after any `.env` change, because settings are read only at startup.

## API

### `POST /link-analysis`

```bash
curl -X POST http://localhost:4000/link-analysis \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com"}'
```

Response shape (abridged):

```json
{
  "success": true,
  "website": "https://example.com/",
  "brand": {"name": "...", "category": "...", "summary": "..."},
  "analysis": {
    "competitor_analysis": {
      "brand_overview": "...",
      "main_products_services": ["..."],
      "competitors": [{"name": "...", "main_service": "...", "target_market": "...",
                       "strengths": ["..."], "weaknesses": ["..."], "source": "ai_suggested"}],
      "brand_strengths": ["..."],
      "positioning_opportunities": ["..."]
    },
    "target_search_queries": [{"query": "...", "platforms": ["Google", "LinkedIn"], "intent": "...",
                               "business_relevance": "...", "target_audience": "..."}],
    "seo_improvements": {"primary_keyword": "...", "secondary_keywords": [], "long_tail_keywords": [],
                         "business_keywords": [], "recommended_title": "...", "meta_description": "...",
                         "supporting_content": []},
    "top_services": [{"name": "...", "description": "...", "target_industry": "...",
                      "target_customer": "...", "main_benefit": "...", "basis": "from_website"}],
    "target_audience": {"primary_audience": [], "secondary_audience": [], "industries": [],
                        "business_types": [], "customer_profiles": [], "geographic_focus": "",
                        "customer_needs": [], "customer_interests": [], "recommended_marketing_segments": []}
  },
  "meta": {"provider": "gemini", "model": "gemini-3.5-flash-lite", "cached": false,
           "content_chars_sent": 6707, "note": "..."}
}
```

### Real sample run

Request: `{"url": "https://www.kitcoek.in/"}` (a public college website). Output below is abridged
(first item of each list); the real response has 3 competitors, 5 search queries and 5 services.

```json
{
  "success": true,
  "website": "https://www.kitcoek.in/",
  "brand": {
    "name": "KIT'S College Of Engineering (Autonomous)",
    "category": "Higher Education / Engineering College",
    "summary": "KIT'S College Of Engineering (Autonomous) in Kolhapur offers undergraduate, postgraduate, and Ph.D. engineering programs with industry-integrated curriculum, strong placement records, and state-of-the-art infrastructure."
  },
  "analysis": {
    "competitor_analysis": {
      "competitors": [
        {"name": "Walchand College of Engineering, Sangli", "main_service": "Engineering Education",
         "target_market": "Engineering aspirants in Maharashtra",
         "strengths": ["Autonomous status", "Strong alumni network", "Legacy brand"],
         "weaknesses": ["Older infrastructure in parts", "High cut-off competition"],
         "source": "ai_suggested"}
      ]
    },
    "target_search_queries": [
      {"query": "top ranked engineering college in Kolhapur", "platforms": ["Google"],
       "intent": "Informational / Navigational",
       "target_audience": "Prospective engineering students and parents"}
    ],
    "seo_improvements": {
      "primary_keyword": "Top Ranked Engineering College in Kolhapur",
      "secondary_keywords": ["KIT College of Engineering autonomous", "BTech admissions Kolhapur"]
    },
    "top_services": [
      {"name": "Undergraduate Engineering Programs (B.Tech / B.E.)",
       "target_customer": "High school graduates (12th grade pass-outs)", "basis": "from_website"}
    ],
    "target_audience": {
      "primary_audience": ["High school graduates seeking engineering admissions"],
      "geographic_focus": "Kolhapur, Sangli, Satara, Ratnagiri, and broader Maharashtra, India"
    }
  },
  "meta": {"provider": "gemini", "model": "gemini-3.5-flash-lite", "cached": false, "content_chars_sent": 6707}
}
```

Note: competitor strengths/weaknesses and SEO suggestions are model-generated and unverified. They are
labelled `ai_suggested`; review them before acting on them.

> Screenshots of the Swagger UI (`/docs`) runs are in the `docs/` folder (add them before submitting).

### Errors

Always `{"success": false, "error": "<code>", "message": "..."}`

| Status | `error` | When |
|---|---|---|
| 400 | `invalid_url` | bad URL, non-http(s), embedded credentials, private/internal address |
| 422 | `invalid_request` | body missing `url` |
| 422 | `website_unreachable` | timeout, HTTP 4xx/5xx, blocked, non-HTML, empty/JS-only page |
| 502 | `llm_error` | provider failure or unusable output |
| 503 | `llm_not_configured` | missing API key / unknown provider |

### Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `{"detail":"Not Found"}` | Wrong path. The app has no `/`, `/analyze` or `/get/health` route. | Use `POST /link-analysis`, `GET /health` or `GET /docs`. |
| `{"detail":"Method Not Allowed"}` (405) | `GET /link-analysis` in a browser. The endpoint accepts POST only. | Send a POST, for example from `/docs` with "Try it out". |
| `llm_error`, "LLM provider returned HTTP 404" | The configured Gemini model is retired (for example, an old `LLM_MODEL` value in `.env`). | Remove or update `LLM_MODEL` in `.env` and restart. |
| `llm_error`, "LLM provider returned HTTP 503" | Provider overload, usually temporary. | Retry after a short wait. |
| `llm_not_configured` | `.env` is missing or the key is empty. | Create `.env` from `.env.example` and set the key. |

## Security and honesty notes

- **SSRF:** only public `http(s)` hosts. The hostname is resolved and every IP must be globally routable
  (blocks localhost, RFC1918, link-local/cloud metadata). Redirects are followed manually and re-checked per hop.
  Known limit: a DNS-rebinding attacker could change DNS between our check and the connection; a production
  deployment should pin the resolved IP or use an egress proxy.
- **Secrets:** API keys only via environment variables; `.env` is git-ignored; error messages never echo provider responses.
- **No invented data:** the prompt forbids search volumes/rankings and none are returned. Competitors are
  LLM suggestions and are labelled `"source": "ai_suggested"`. Services the model had to infer are labelled `"basis": "inferred"`.
- **Limitation:** JavaScript-rendered sites (SPAs) return little HTML; the API reports this instead of guessing.

## LLM platform and model research

Prices are USD per 1M tokens, standard (non-batch) tier, short context. **They come from third-party pricing
trackers and news pages dated Oct 2026 and have not been checked against the official pricing pages.
Verify them there before relying on them:**
[Gemini](https://ai.google.dev/gemini-api/docs/pricing) ·
[OpenAI](https://platform.openai.com/docs/pricing) ·
[Anthropic](https://docs.claude.com/en/docs/about-claude/pricing).

| Provider | Model | Input | Output | Context | JSON support | Notes |
|---|---|---|---|---|---|---|
| Google | `gemini-3.5-flash-lite` (default) | $0.30 | $2.50 | 1M | native (`responseMimeType`) | used for the sample run; works with a standard AI Studio key |
| Google | `gemini-2.5-flash-lite` | $0.10 | $0.40 | 1M | native | returned HTTP 404 for new API keys in my testing, so not usable |
| Anthropic | `claude-haiku-5-5` | $0.10 (prompts ≤100k) | $0.50 | 1M | prompted JSON + validation | rates rise above 100k-token prompts |
| OpenAI | `gpt-5-mini` | $0.25 | $2.00 | 400K | native (`json_object`) | reasoning model; output is pricier |
| OpenAI | `gpt-4o-mini` (older) | $0.15 | $0.60 | 128K | native | older generation, for reference |

### Estimated cost per analysis

Estimate, not measured: ~4,000 input tokens (up to 12,000 characters of site text plus the prompt) and
~1,800 output tokens. The sample run sent 6,707 characters of content, so it was below this.

| Model | Est. cost / analysis |
|---|---|
| gemini-3.5-flash-lite | ~$0.006 |
| claude-haiku-5-5 | ~$0.0013 |
| gpt-4o-mini | ~$0.0017 |
| gpt-5-mini | ~$0.0046 (+ any reasoning tokens) |

### Recommendation

- **Primary (default): `gemini-3.5-flash-lite`.** It is the model I actually ran and tested. It has native JSON
  output mode, a 1M-token context window and works with a standard Google AI Studio key. It is **not** the cheapest option here.
- **Lower cost at scale: `claude-haiku-5-5`.** By listed price it is roughly 4x cheaper per analysis, mostly because of its lower
  output price. I have not benchmarked its quality against Gemini on this task, so I would test it on a few sample sites before switching.
- **Balancing accuracy, speed and cost:** start with the default for quality and reliability, reduce cost with input cleaning and
  caching, and move to the cheaper model if volume grows and quality tests pass. Switch models with `LLM_PROVIDER` / `LLM_MODEL`.
- **Not measured:** accuracy and latency. I did not benchmark the models against each other, so these recommendations rest on
  published pricing and capabilities and on one tested run.

### Cost optimisation implemented

- Strip scripts/styles/nav/footers and deduplicate repeated sentences before sending text.
- Hard cap on content (`MAX_CONTENT_CHARS`, default 12,000).
- One LLM call produces all five sections (shared context, one prompt overhead).
- In-memory TTL cache (default 1 hour) so repeat URLs skip the LLM.
- Retry only on malformed output, not on provider errors.
- Further options: batch API (50% off) for bulk jobs, provider prompt caching for the static instructions, a smaller model for extraction and a larger one only if needed.
