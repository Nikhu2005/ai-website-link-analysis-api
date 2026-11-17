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
  "meta": {"provider": "gemini", "model": "gemini-2.5-flash-lite", "cached": false,
           "content_chars_sent": 9000, "note": "..."}
}
```

> TODO before submitting: paste 1-2 REAL responses here from your own runs and add screenshots/logs.

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

Prices are USD per 1M tokens, standard (non-batch) tier, short context. **Sourced from third-party pricing
trackers and news pages dated Oct 2026; I could not open the official pricing pages from my build environment,
so re-verify on the official pages before relying on them:**
[Gemini](https://ai.google.dev/gemini-api/docs/pricing) ·
[OpenAI](https://platform.openai.com/docs/pricing) ·
[Anthropic](https://docs.claude.com/en/docs/about-claude/pricing).

| Provider | Model | Input | Output | Context | JSON support | Notes |
|---|---|---|---|---|---|---|
| Google | `gemini-2.5-flash-lite` | $0.10 | $0.40 | 1M | native (`responseMimeType`) | cheapest; free tier for dev |
| Anthropic | `claude-haiku-5-5` | $0.10 (≤100k prompt) | $0.50 | 1M | prompted JSON + validation | listed price jump above 100k tokens |
| OpenAI | `gpt-5-mini` | $0.25 | $2.00 | 400K | native (`json_object`) | reasoning model, pricier output |
| OpenAI | `gpt-4o-mini` (older) | $0.15 | $0.60 | 128K | native | older generation, for reference |

### Estimated cost per analysis

Assumption (estimate, not measured): ~4,000 input tokens (≤12,000 chars of site text + prompt) and ~1,800 output tokens.

| Model | Est. cost / analysis |
|---|---|
| gemini-2.5-flash-lite | ~$0.0011 |
| claude-haiku-5-5 | ~$0.0013 |
| gpt-4o-mini | ~$0.0017 |
| gpt-5-mini | ~$0.0046 (+ any reasoning tokens) |

### Recommendation

- **Primary: `gemini-3.5-flash-lite`** (default; replaces `gemini-2.5-flash-lite`, which is retired for new keys). Lowest cost, large context, native JSON mode, and a free tier that makes development and testing cost nothing. Prices below were not re-checked for the replacement model.
- **Fallback: `claude-haiku-5-5`.** Similar price class; a reasonable upgrade if the primary's analysis quality proves too shallow.
- **Balancing accuracy/speed/cost:** use the cheap model by default; cleaning and capping the input keeps token use low; the cache avoids repeat calls.
- **What is NOT measured:** accuracy and latency. I did not benchmark the models against each other, so I make no accuracy claim beyond published pricing and capabilities. Swap models with `LLM_MODEL` and compare on your own sample sites.

### Cost optimisation implemented

- Strip scripts/styles/nav/footers and deduplicate repeated sentences before sending text.
- Hard cap on content (`MAX_CONTENT_CHARS`, default 12,000).
- One LLM call produces all five sections (shared context, one prompt overhead).
- In-memory TTL cache (default 1 hour) so repeat URLs skip the LLM.
- Retry only on malformed output, not on provider errors.
- Further options: batch API (50% off) for bulk jobs, provider prompt caching for the static instructions, a smaller model for extraction and a larger one only if needed.
