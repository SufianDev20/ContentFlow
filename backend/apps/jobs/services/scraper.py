"""
Fetch a web page and extract its article body as plain text, guarded against SSRF.
"""

import ipaddress
import logging
import re
import socket
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from django.conf import settings

logger = logging.getLogger(__name__)

NOISE_TAGS = [
    "form",
    "svg",
    "script",
    "style",
    "aside",
    "iframe",
    "footer",
    "header",
    "nav",
    "button",
]
# Jobs accept at most this much content, so extraction stops here.
MAX_CONTENT_LENGTH = 50_000
REQUEST_TIMEOUT = (5, 15)
# Sent so sites don't serve bot-detection pages.
BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-language": "en-US,en;q=0.5",
}


def _is_internal_ip(ip) -> bool:
    return ip.is_private or ip.is_loopback or ip.is_link_local


def is_safe_url(url: str) -> bool:
    """False for non-http(s) URLs, blocked domains, and hosts that are or resolve to internal IPs."""
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname
    except ValueError:
        return False

    if parsed.scheme not in ("http", "https") or not hostname:
        logger.warning("Blocked URL with unsafe scheme or no hostname: %s", url)
        return False

    if any(blocked in hostname.lower() for blocked in settings.SCRAPER_BLOCKED_DOMAINS):
        logger.warning("Blocked URL with blocked domain: %s", hostname)
        return False

    try:
        if _is_internal_ip(ipaddress.ip_address(hostname)):
            logger.warning("Blocked URL with private IP: %s", hostname)
            return False
    except ValueError:
        pass  # a hostname, not a literal IP

    # Check every resolved address too, so a public name can't point at an internal one.
    try:
        addresses = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
    except socket.gaierror:
        logger.warning("DNS resolution failed for %s", hostname)
        return False
    for *_, sockaddr in addresses:
        try:
            internal = _is_internal_ip(ipaddress.ip_address(sockaddr[0]))
        except ValueError:  # e.g. IPv6 with a scope id
            internal = True
        if internal:
            logger.warning("Blocked URL: %s resolves to internal IP %s", hostname, sockaddr[0])
            return False
    return True


def fetch_from_url(url: str) -> dict:
    """
    Return {"title", "text", "word_count"} for the page at url.

    Raises:
        ValueError: unsafe URL, or no readable text on the page.
        requests.exceptions.RequestException: the fetch failed.
    """
    if not is_safe_url(url):
        raise ValueError(f"Unsafe or blocked URL: {url}")

    # Redirects are refused: the target would bypass the safety check above.
    response = requests.get(
        url, headers=BROWSER_HEADERS, timeout=REQUEST_TIMEOUT, allow_redirects=False
    )
    response.raise_for_status()
    result = _extract_text(response.content)
    if not result["text"]:
        raise ValueError(
            f"Could not extract readable content from {url}. "
            "This page may require JavaScript to display content. "
            "Try pasting the text directly instead."
        )
    return result


def _extract_text(html_bytes: bytes) -> dict:
    """Prefer <article>, then <main>, then <body>, after dropping noise tags."""
    soup = BeautifulSoup(html_bytes, "lxml")
    title_tag = soup.find("title")
    title = title_tag.get_text().strip() if title_tag else ""

    for tag in soup.find_all(NOISE_TAGS):
        tag.decompose()
    root = soup.find("article") or soup.find("main") or soup.find("body")
    text = ""
    if root is not None:
        text = re.sub(r"\s+", " ", root.get_text(separator=" ")).strip()[:MAX_CONTENT_LENGTH]

    return {"title": title, "text": text, "word_count": len(text.split())}
