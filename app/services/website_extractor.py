"""Fetch a website and extract compact, LLM-friendly content."""
import re
from dataclasses import dataclass, field
from typing import List
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from app.config import settings
from app.errors import InvalidURLError, WebsiteFetchError
from app.utils.validators import assert_public_host, normalize_url

REMOVE_TAGS = ["script", "style", "noscript", "svg", "iframe", "form", "nav", "footer", "header", "aside"]


@dataclass
class WebsiteContent:
    url: str
    title: str = ""
    meta_description: str = ""
    headings: List[str] = field(default_factory=list)
    text: str = ""
    link_texts: List[str] = field(default_factory=list)

    def to_prompt_block(self) -> str:
        parts = [
            f"URL: {self.url}",
            f"Title: {self.title}",
            f"Meta description: {self.meta_description}",
        ]
        if self.headings:
            parts.append("Headings:\n- " + "\n- ".join(self.headings))
        if self.link_texts:
            parts.append("Navigation/link labels: " + ", ".join(self.link_texts))
        parts.append("Main text:\n" + self.text)
        return "\n\n".join(parts)


async def fetch_html(url: str) -> tuple[str, str]:
    """GET with manual redirect handling so every hop is SSRF-checked.

    Returns (final_url, html). Raises InvalidURLError / WebsiteFetchError.
    """
    headers = {"User-Agent": settings.USER_AGENT, "Accept": "text/html,application/xhtml+xml"}
    current = url
    async with httpx.AsyncClient(
        timeout=settings.FETCH_TIMEOUT_SECONDS, follow_redirects=False, headers=headers
    ) as client:
        for _ in range(settings.MAX_REDIRECTS + 1):
            assert_public_host(current)
            try:
                async with client.stream("GET", current) as resp:
                    if resp.status_code in (301, 302, 303, 307, 308):
                        location = resp.headers.get("location")
                        if not location:
                            raise WebsiteFetchError("Redirect without a Location header.")
                        current = normalize_url(urljoin(current, location))
                        continue
                    if resp.status_code in (401, 403, 429):
                        raise WebsiteFetchError(
                            f"The website refused automated access (HTTP {resp.status_code})."
                        )
                    if resp.status_code >= 400:
                        raise WebsiteFetchError(f"The website returned HTTP {resp.status_code}.")
                    ctype = resp.headers.get("content-type", "").lower()
                    if "html" not in ctype and "xml" not in ctype and ctype:
                        raise WebsiteFetchError(f"Unsupported content type: {ctype.split(';')[0]}.")
                    chunks, size = [], 0
                    async for chunk in resp.aiter_bytes():
                        size += len(chunk)
                        if size > settings.MAX_DOWNLOAD_BYTES:
                            break  # truncate oversized pages; we only need the start
                        chunks.append(chunk)
                    raw = b"".join(chunks)
                    encoding = resp.encoding or "utf-8"
                    return current, raw.decode(encoding, errors="replace")
            except httpx.TimeoutException:
                raise WebsiteFetchError("The website took too long to respond.")
            except httpx.HTTPError as e:
                raise WebsiteFetchError(f"Could not fetch the website: {type(e).__name__}.")
    raise WebsiteFetchError("Too many redirects.")


def extract_content(url: str, html: str) -> WebsiteContent:
    soup = BeautifulSoup(html, "html.parser")

    title = soup.title.get_text(strip=True) if soup.title else ""
    meta = soup.find("meta", attrs={"name": re.compile("^description$", re.I)})
    meta_desc = (meta.get("content") or "").strip() if meta else ""
    if not meta_desc:
        og = soup.find("meta", attrs={"property": "og:description"})
        meta_desc = (og.get("content") or "").strip() if og else ""

    headings = []
    for h in soup.find_all(["h1", "h2", "h3"]):
        t = h.get_text(" ", strip=True)
        if t and t not in headings:
            headings.append(t)
        if len(headings) >= 40:
            break

    # Nav labels help identify services/products, so grab them before stripping nav.
    link_texts = []
    for a in soup.find_all("a"):
        t = a.get_text(" ", strip=True)
        if 2 < len(t) < 40 and t not in link_texts:
            link_texts.append(t)
        if len(link_texts) >= 40:
            break

    for tag in soup(REMOVE_TAGS):
        tag.decompose()
    body = soup.body or soup
    text = body.get_text(" ", strip=True)
    text = re.sub(r"\s+", " ", text)
    text = _dedupe_sentences(text)[: settings.MAX_CONTENT_CHARS]

    if len(text) < 50 and not headings and not meta_desc:
        raise WebsiteFetchError(
            "The page has very little readable content (it may be JavaScript-rendered or blocked)."
        )

    return WebsiteContent(
        url=url,
        title=title,
        meta_description=meta_desc,
        headings=headings,
        text=text,
        link_texts=link_texts,
    )


def _dedupe_sentences(text: str) -> str:
    """Drop repeated sentences (menus, cookie banners) to save tokens."""
    seen, out = set(), []
    for s in re.split(r"(?<=[.!?])\s+", text):
        key = s.strip().lower()
        if key and key not in seen:
            seen.add(key)
            out.append(s.strip())
    return " ".join(out)


async def get_website_content(url: str) -> WebsiteContent:
    final_url, html = await fetch_html(url)
    return extract_content(final_url, html)
