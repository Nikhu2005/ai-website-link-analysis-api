import ipaddress
import socket

import pytest
from fastapi.testclient import TestClient

from app.errors import InvalidURLError, LLMError
from app.main import app
from app.services import analysis_service, llm_service, website_extractor
from app.utils import validators

client = TestClient(app)

SAMPLE_HTML = """
<html><head><title>Acme Web Studio</title>
<meta name="description" content="We build websites for small businesses."></head>
<body><nav>Home About</nav>
<h1>Websites that grow your business</h1>
<p>Acme Web Studio offers web design, SEO and e-commerce development for small businesses in Pune.</p>
<script>var x = 1;</script></body></html>
"""

FAKE_LLM = {
    "brand": {"name": "Acme Web Studio", "category": "Web Development", "summary": "Web agency."},
    "analysis": {
        "competitor_analysis": {
            "brand_overview": "Small web agency.",
            "competitors": [{"name": "Rival Co", "strengths": ["Brand"], "weaknesses": ["Price"]}],
        },
        "target_search_queries": [{"query": f"q{i}", "platforms": ["Google"]} for i in range(7)],
        "seo_improvements": {"primary_keyword": "web design pune"},
        "top_services": [{"name": f"s{i}"} for i in range(7)],
        "target_audience": {"primary_audience": ["Small businesses"]},
    },
}


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    analysis_service.clear_cache()
    # Never do real DNS in tests: pretend every host resolves to a public IP.
    def fake_getaddrinfo(host, port, **kw):
        try:
            ipaddress.ip_address(host)
            ip = host  # IP literals resolve to themselves, as in real life
        except ValueError:
            ip = "93.184.216.34"
        fam = socket.AF_INET6 if ":" in ip else socket.AF_INET
        return [(fam, socket.SOCK_STREAM, 6, "", (ip, port))]

    monkeypatch.setattr(validators.socket, "getaddrinfo", fake_getaddrinfo)


# ---------- validators ----------
@pytest.mark.parametrize(
    "bad",
    ["", "   ", "ftp://example.com", "javascript:alert(1)", "http://user:pw@example.com", "http://localhost"],
)
def test_invalid_urls_rejected(bad):
    with pytest.raises(InvalidURLError):
        validators.validate_url(bad)


@pytest.mark.parametrize(
    "ip", ["127.0.0.1", "10.0.0.5", "192.168.1.1", "172.16.0.1", "169.254.169.254", "0.0.0.0", "[::1]"]
)
def test_private_and_internal_addresses_blocked(ip):
    with pytest.raises(InvalidURLError):
        validators.validate_url(f"http://{ip}/")


def test_scheme_added_and_fragment_removed():
    assert validators.validate_url("example.com/path#frag") == "https://example.com/path"


# ---------- extractor ----------
def test_extract_content_strips_noise():
    c = website_extractor.extract_content("https://acme.test", SAMPLE_HTML)
    assert c.title == "Acme Web Studio"
    assert "small businesses" in c.meta_description
    assert "var x" not in c.text
    assert "Websites that grow your business" in c.headings


def test_extract_content_empty_page_errors():
    with pytest.raises(Exception):
        website_extractor.extract_content("https://acme.test", "<html><body></body></html>")


# ---------- LLM JSON parsing ----------
def test_extract_json_handles_fences_and_noise():
    assert llm_service._extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert llm_service._extract_json('Sure! {"a": 1} hope that helps') == {"a": 1}
    with pytest.raises(LLMError):
        llm_service._extract_json("not json at all")


# ---------- endpoint ----------
def _patch_pipeline(monkeypatch, calls=None):
    async def fake_fetch(url):
        return url, SAMPLE_HTML

    async def fake_llm(block):
        if calls is not None:
            calls.append(1)
        return FAKE_LLM

    monkeypatch.setattr(website_extractor, "fetch_html", fake_fetch)
    monkeypatch.setattr(llm_service, "generate_json", fake_llm)


def test_endpoint_success_and_top5_enforced(monkeypatch):
    _patch_pipeline(monkeypatch)
    r = client.post("/link-analysis", json={"url": "https://acme.test"})
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert body["brand"]["name"] == "Acme Web Studio"
    assert len(body["analysis"]["target_search_queries"]) == 5
    assert len(body["analysis"]["top_services"]) == 5
    assert body["analysis"]["competitor_analysis"]["competitors"][0]["source"] == "ai_suggested"


def test_endpoint_caches_repeat_urls(monkeypatch):
    calls = []
    _patch_pipeline(monkeypatch, calls)
    client.post("/link-analysis", json={"url": "https://acme.test"})
    r = client.post("/link-analysis", json={"url": "https://acme.test"})
    assert r.json()["meta"]["cached"] is True
    assert len(calls) == 1


def test_endpoint_invalid_url_returns_400():
    r = client.post("/link-analysis", json={"url": "ftp://x.com"})
    assert r.status_code == 400
    assert r.json()["error"] == "invalid_url"


def test_endpoint_private_ip_blocked():
    r = client.post("/link-analysis", json={"url": "http://169.254.169.254/latest/meta-data"})
    assert r.status_code in (400,)


def test_endpoint_missing_body_returns_422():
    r = client.post("/link-analysis", json={})
    assert r.status_code == 422
    assert r.json()["success"] is False


def test_endpoint_llm_failure_returns_502(monkeypatch):
    async def fake_fetch(url):
        return url, SAMPLE_HTML

    async def boom(block):
        raise LLMError("LLM provider returned HTTP 500.")

    monkeypatch.setattr(website_extractor, "fetch_html", fake_fetch)
    monkeypatch.setattr(llm_service, "generate_json", boom)
    r = client.post("/link-analysis", json={"url": "https://acme.test"})
    assert r.status_code == 502
    assert r.json()["error"] == "llm_error"
