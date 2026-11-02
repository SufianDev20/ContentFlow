"""
URL content extraction service for ContentFlow AI.

Responsibility:
    Fetch raw HTML from a given URL and extract the article body as clean,
    readable plain text. The result is passed directly to repurposer.py as
    the blog post content when a user submits a URL instead of pasting text.

Usage:
    from apps.jobs.services.scraper import fetch_from_url

    text = fetch_from_url("https://example.com/blog/post")
"""

import logging, requests, re, ipaddress, socket
from urllib.parse import urlparse
from bs4 import BeautifulSoup
import environ
from typing import Dict

env = environ.Env()

logger = logging.getLogger(__name__)
# Unwanted tags that don't contain article context.
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
# In scraper.py
BLOCKED_DOMAINS = env.list(
    "SCRAPER_BLOCKED_DOMAINS",
    default=[
        "localhost",
        "127.0.0.1",
        "metadata.google.internal",
        "169.254.169.254",
        "metadata.aws.internal",
    ],
)
# Hard ceiling on extracted content length since OpenRouter have context limits that covers any blog post
MAX_CONTENT_LENGTH = 50_000

# HTTP request timeout in seconds (connect, read).
REQUEST_TIMEOUT = (5, 15)


def is_safe_url(url: str) -> bool:
    """
    Validate URL to prevent SSRF attacks.

    Blocks:
    - Private IP ranges (192.168.x.x, 10.x.x.x, 172.16-31.x.x)
    - Loopback addresses (127.0.0.0/8)
    - Link-local addresses (169.254.0.0/16)
    - Non-HTTP(S) schemes
    - Known internal/metadata service domains

    Args:
        url (str): URL to validate

    Returns:
        bool: True if URL is safe, False otherwise
    """
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname

        # Block non-HTTP(S) schemes
        if parsed.scheme not in ["http", "https"]:
            logger.warning(f"Blocked URL with unsafe scheme: {parsed.scheme}")
            return False

        # Block if no hostname
        if not hostname:
            logger.warning("Blocked URL with no hostname")
            return False

        # Block known internal domains
        if any(blocked in hostname.lower() for blocked in BLOCKED_DOMAINS):
            logger.warning(f"Blocked URL with blocked domain: {hostname}")
            return False

        # Check if hostname is an IP address
        try:
            ip = ipaddress.ip_address(hostname)
            if ip.is_private or ip.is_loopback or ip.is_link_local:
                logger.warning(f"Blocked URL with private IP: {hostname}")
                return False
        except ValueError:
            pass

        # Resolve DNS and validate all resolved IPs to prevent DNS rebinding
        try:
            for family, _type, _proto, _canon, sockaddr in socket.getaddrinfo(
                hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM
            ):
                resolved_ip = ipaddress.ip_address(sockaddr[0])
                if resolved_ip.is_private or resolved_ip.is_loopback or resolved_ip.is_link_local:
                    logger.warning(
                        f"Blocked URL: {hostname} resolves to private IP {resolved_ip}"
                    )
                    return False
        except socket.gaierror:
            logger.warning(f"DNS resolution failed for {hostname}")
            return False

        return True

    except (ValueError, AttributeError) as e:
        logger.warning(f"URL validation failed: {e}")
        return False


def fetch_from_url(url: str) -> Dict:
    """
    Fetch a web page and return its article body as plain text.

    Steps:
        1. Validate URL for SSRF protection
        2. GET the URL with a browser-like User-Agent so sites do not
           serve bot-detection pages.
        3. Raise immediately on non-2xx HTTP status codes.
        4. Parse the HTML with lxml (fastest, handles malformed markup).
        5. Strip all noise tags (nav, footer, script, etc.).
        6. Prefer <article> or <main> elements; fall back to <body>.
        7. Collapse whitespace and truncate to _MAX_CONTENT_LENGTH.

    Args:
        url (str): Fully-qualified URL of the blog post to scrape.
        Example: "https://example.com/blog/my-post"

    Returns:
        str: Cleaned plain-text content of the article body.

    Raises:
         requests.exceptions.Timeout:
            Server did not respond within _REQUEST_TIMEOUT seconds.
        requests.exceptions.HTTPError:
            Server returned a 4xx or 5xx status code.
        requests.exceptions.RequestException:
            Any other network-level failure (DNS, connection refused, etc.).
        ValueError:
            Page was fetched successfully but no usable text was extracted,
            or URL is unsafe (SSRF protection).
    """
    logger.info(f"Fetching URL: {url}")

    # Validate URL for SSRF protection
    if not is_safe_url(url):
        raise ValueError(f"Unsafe or blocked URL: {url}")

    # Contain a real browser names inorder to avoid pages from thinking of a bot trying to access and scrape info.
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-language": "en-US,en;q=0.5",
    }

    response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT, allow_redirects=False)
    response.raise_for_status()
    result = _extract_text(response.content)
    if not result["text"]:
        raise ValueError(
            f"Could not extract readable content from {url}. "
            "This page may require JavaScript to display content. "
            "Try pasting the text directly instead."
        )
    logger.info(f"Extracted {len(result['text'])} characters from {url}")
    return result


def _extract_text(html_bytes: bytes) -> dict:
    """
    Parse raw HTML bytes and return clean article text.

    Parsing strategy:
        - Use lxml as the parser backend: faster than html.parser and
          more resilient to malformed markup found in real-world blogs.
        - Prefer <article> or <main> as content roots because most CMS
          platforms (WordPress, Ghost, Substack) wrap the post body in one
          of these semantic elements.
        - Fall back to <body> if neither semantic element is present.
        - Strip all _NOISE_TAGS before reading text so nav links, cookie
          banners, and inline scripts do not appear in the output.
    Args:
        html_bytes (bytes): Raw HTTP response body from requests.get().

    Returns:
        dict: Dictionary with keys 'title', 'text', and 'word_count'. Whitespace-normalised plain text, truncated to _MAX_CONTENT_LENGTH.
    """
    soup = BeautifulSoup(html_bytes, "lxml")
    title_tag = soup.find("title")
    title = title_tag.get_text().strip() if title_tag else ""

    for tag in soup.find_all(NOISE_TAGS):
        tag.decompose()
    content_root = soup.find("article") or soup.find("main") or soup.find("body")
    text = (
        ""
        if content_root is None
        else _normalise_whitespace(content_root.get_text(separator=" "))[
            :MAX_CONTENT_LENGTH
        ]
    )

    return {"title": title, "text": text, "word_count": len(text.split())}


def _normalise_whitespace(text: str) -> str:
    """
    Collapse all consecutive whitespace characters into a single space
    and strip leading/trailing whitespace.

    Args:
        text (str): Raw text extracted by BeautifulSoup.get_text().

    Returns:
        str: Single-line normalised string. Paragraph breaks are lost; the repurposer service operates on plain text, not structured HTML.
    """
    return re.sub(r"\s+", " ", text).strip()
