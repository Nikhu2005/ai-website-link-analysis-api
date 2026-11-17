"""Thin multi-provider LLM client (Gemini, OpenAI, Anthropic) over plain HTTPX.

Everything returns a parsed JSON dict. Provider is chosen with LLM_PROVIDER.
"""
import json
import re

import httpx

from app.config import settings
from app.errors import LLMConfigError, LLMError

SYSTEM_PROMPT = """You are a senior digital-marketing and business analyst.
You analyse a website using ONLY the extracted content provided, then return a single JSON object.

Rules:
- Base brand details and services on the actual website content. If you must infer something, set "basis": "inferred".
- Competitors are your own suggestions, not verified research. Suggest at least 3 real, well-known competitors when you can do so confidently; otherwise return fewer. Never invent companies.
- NEVER invent search volumes, rankings, traffic or other numeric data.
- Output valid JSON only. No markdown fences, no commentary.
- Keep every string concise and specific to THIS website; avoid generic filler.
"""

JSON_SHAPE = """Return JSON with exactly this shape:
{
  "brand": {"name": str, "category": str, "summary": str},
  "analysis": {
    "competitor_analysis": {
      "brand_overview": str,
      "main_products_services": [str],
      "competitors": [{"name": str, "main_service": str, "target_market": str, "strengths": [str], "weaknesses": [str], "source": "ai_suggested"}],
      "brand_strengths": [str],
      "positioning_opportunities": [str]
    },
    "target_search_queries": [  // exactly 5
      {"query": str, "platforms": [one or more of "Google","Facebook","Instagram","LinkedIn","X"], "intent": str, "business_relevance": str, "target_audience": str}
    ],
    "seo_improvements": {
      "primary_keyword": str, "secondary_keywords": [str], "long_tail_keywords": [str], "business_keywords": [str],
      "recommended_title": str, "meta_description": str, "supporting_content": [str]
    },
    "top_services": [  // exactly 5
      {"name": str, "description": str, "target_industry": str, "target_customer": str, "main_benefit": str, "basis": "from_website" | "inferred"}
    ],
    "target_audience": {
      "primary_audience": [str], "secondary_audience": [str], "industries": [str], "business_types": [str],
      "customer_profiles": [str], "geographic_focus": str, "customer_needs": [str], "customer_interests": [str],
      "recommended_marketing_segments": [str]
    }
  }
}"""


def build_user_prompt(content_block: str) -> str:
    return f"{JSON_SHAPE}\n\nWEBSITE CONTENT:\n\"\"\"\n{content_block}\n\"\"\""


def _extract_json(text: str) -> dict:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                pass
    raise LLMError("The LLM did not return valid JSON.")


async def _post(client: httpx.AsyncClient, url: str, headers: dict, body: dict) -> dict:
    try:
        resp = await client.post(url, headers=headers, json=body)
    except httpx.TimeoutException:
        raise LLMError("The LLM request timed out.")
    except httpx.HTTPError as e:
        raise LLMError(f"Could not reach the LLM provider: {type(e).__name__}.")
    if resp.status_code != 200:
        # Never echo response bodies that may include request details / keys.
        raise LLMError(f"LLM provider returned HTTP {resp.status_code}.")
    return resp.json()


async def _call_gemini(client, system: str, user: str) -> str:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{settings.model}:generateContent"
    body = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0.3},
    }
    data = await _post(client, url, {"x-goog-api-key": settings.api_key}, body)
    try:
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError):
        raise LLMError("Unexpected response format from Gemini.")


async def _call_openai(client, system: str, user: str) -> str:
    body = {
        "model": settings.model,
        # No temperature: newer OpenAI models only accept the default.
        "response_format": {"type": "json_object"},
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
    }
    data = await _post(
        client,
        "https://api.openai.com/v1/chat/completions",
        {"Authorization": f"Bearer {settings.api_key}"},
        body,
    )
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError):
        raise LLMError("Unexpected response format from OpenAI.")


async def _call_anthropic(client, system: str, user: str) -> str:
    body = {
        "model": settings.model,
        "max_tokens": 4096,
        # No temperature: some newer Claude models reject non-default sampling params.
        "system": system,
        "messages": [{"role": "user", "content": user}],
    }
    data = await _post(
        client,
        "https://api.anthropic.com/v1/messages",
        {"x-api-key": settings.api_key, "anthropic-version": "2023-06-01"},
        body,
    )
    try:
        return data["content"][0]["text"]
    except (KeyError, IndexError):
        raise LLMError("Unexpected response format from Anthropic.")


_PROVIDERS = {"gemini": _call_gemini, "openai": _call_openai, "anthropic": _call_anthropic}


async def generate_json(content_block: str) -> dict:
    """Send the website content to the configured LLM and return parsed JSON."""
    caller = _PROVIDERS.get(settings.LLM_PROVIDER)
    if caller is None:
        raise LLMConfigError(
            f"Unknown LLM_PROVIDER '{settings.LLM_PROVIDER}'. Use gemini, openai or anthropic."
        )
    if not settings.api_key:
        raise LLMConfigError(f"No API key configured for provider '{settings.LLM_PROVIDER}'.")
    async with httpx.AsyncClient(timeout=settings.LLM_TIMEOUT_SECONDS) as client:
        raw = await caller(client, SYSTEM_PROMPT, build_user_prompt(content_block))
    return _extract_json(raw)
