"""Orchestrates: validate -> fetch -> extract -> LLM -> validate -> respond."""
import time
from typing import Dict, Tuple

from pydantic import ValidationError

from app.config import settings
from app.errors import LLMError
from app.schemas import AnalyzeResponse, LLMResult, Meta
from app.services import llm_service, website_extractor
from app.utils.validators import validate_url

# Simple in-memory TTL cache: normalized url -> (timestamp, response).
# Avoids paying for repeat LLM calls on the same site.
_cache: Dict[str, Tuple[float, AnalyzeResponse]] = {}


def clear_cache() -> None:
    _cache.clear()


def _cache_get(key: str):
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < settings.CACHE_TTL_SECONDS:
        return hit[1]
    _cache.pop(key, None)
    return None


async def analyze_website(raw_url: str) -> AnalyzeResponse:
    url = validate_url(raw_url)

    cached = _cache_get(url)
    if cached:
        out = cached.model_copy(deep=True)
        out.meta.cached = True
        return out

    content = await website_extractor.get_website_content(url)
    block = content.to_prompt_block()

    data = None
    last_err: Exception | None = None
    for _ in range(2):  # one retry if the model returns malformed / off-schema JSON
        try:
            data = await llm_service.generate_json(block)
            result = LLMResult.model_validate(data)
            break
        except (LLMError, ValidationError) as e:
            last_err = e
            data = None
            if isinstance(e, LLMError) and "HTTP" in e.message:
                raise  # provider/HTTP failures are not worth retrying blindly
    if data is None:
        if isinstance(last_err, LLMError):
            raise last_err
        raise LLMError("The LLM response did not match the expected structure.")

    # Enforce the spec's "top 5" even if the model over-produces.
    result.analysis.target_search_queries = result.analysis.target_search_queries[:5]
    result.analysis.top_services = result.analysis.top_services[:5]

    response = AnalyzeResponse(
        website=content.url,
        brand=result.brand,
        analysis=result.analysis,
        meta=Meta(provider=settings.LLM_PROVIDER, model=settings.model, content_chars_sent=len(block)),
    )
    _cache[url] = (time.time(), response.model_copy(deep=True))
    return response
