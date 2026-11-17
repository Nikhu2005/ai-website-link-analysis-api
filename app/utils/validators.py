"""URL validation with SSRF protection.

Only public http(s) hosts are allowed. The hostname is resolved and every
resulting IP must be globally routable, so localhost, RFC1918 ranges,
link-local (cloud metadata 169.254.169.254), etc. are all rejected.
"""
import ipaddress
import socket
from urllib.parse import urlparse, urlunparse

from app.errors import InvalidURLError

ALLOWED_SCHEMES = {"http", "https"}
MAX_URL_LENGTH = 2048


def normalize_url(raw: str) -> str:
    """Trim, add https:// if no scheme, drop fragment. Raises InvalidURLError."""
    if not raw or not raw.strip():
        raise InvalidURLError("URL is empty.")
    url = raw.strip()
    if len(url) > MAX_URL_LENGTH:
        raise InvalidURLError("URL is too long.")
    if "://" not in url:
        url = "https://" + url
    parsed = urlparse(url)
    if parsed.scheme.lower() not in ALLOWED_SCHEMES:
        raise InvalidURLError("Only http and https URLs are supported.")
    if not parsed.hostname:
        raise InvalidURLError("URL has no hostname.")
    if parsed.username or parsed.password:
        raise InvalidURLError("URLs with embedded credentials are not allowed.")
    try:
        parsed.port  # raises ValueError on a bad port
    except ValueError:
        raise InvalidURLError("URL has an invalid port.")
    if "." not in parsed.hostname and not _is_ip(parsed.hostname):
        raise InvalidURLError("URL must contain a valid public domain name.")
    return urlunparse(parsed._replace(fragment=""))


def _is_ip(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False


def assert_public_host(url: str) -> None:
    """Resolve the host and reject any non-public address (SSRF guard)."""
    parsed = urlparse(url)
    host = parsed.hostname
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        raise InvalidURLError(f"Could not resolve host '{host}'.")
    if not infos:
        raise InvalidURLError(f"Could not resolve host '{host}'.")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global:
            raise InvalidURLError("Access to private or internal network addresses is not allowed.")


def validate_url(raw: str) -> str:
    """Full validation. Returns the normalized, safe-to-fetch URL."""
    url = normalize_url(raw)
    assert_public_host(url)
    return url
