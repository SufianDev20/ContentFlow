from unittest.mock import Mock, patch

import pytest
import requests

from apps.jobs.services import scraper


def page(html: str):
    return Mock(content=html.encode(), raise_for_status=Mock())


@pytest.fixture
def public_dns():
    with patch(
        "apps.jobs.services.scraper.socket.getaddrinfo",
        return_value=[(None, None, None, None, ("93.184.216.34", 0))],
    ):
        yield


@pytest.fixture
def get():
    with patch("apps.jobs.services.scraper.requests.get") as get:
        yield get


class TestIsSafeUrl:
    @pytest.mark.parametrize(
        "url",
        [
            "ftp://example.com/x",
            "file:///etc/passwd",
            "http://localhost/admin",
            "http://127.0.0.1/",
            "http://169.254.169.254/latest/meta-data",
            "http://10.0.0.5/",
            "http://192.168.1.1/",
            "http://[::1]/",
            "http:///no-host",
        ],
    )
    def test_internal_or_non_web_urls_are_blocked(self, url, settings):
        assert not scraper.is_safe_url(url)

    def test_public_host_resolving_to_internal_ip_is_blocked(self):
        with patch(
            "apps.jobs.services.scraper.socket.getaddrinfo",
            return_value=[(None, None, None, None, ("10.0.0.7", 0))],
        ):
            assert not scraper.is_safe_url("https://rebind.example.com/")

    def test_host_in_configured_blocklist_is_blocked(self, settings, public_dns):
        settings.SCRAPER_BLOCKED_DOMAINS = ["evil.test"]

        assert not scraper.is_safe_url("https://evil.test/post")
        assert scraper.is_safe_url("https://example.com/post")


class TestFetchFromUrl:
    def test_returns_title_and_article_text(self, get, public_dns):
        get.return_value = page(
            "<html><head><title> Post </title></head>"
            "<body><article><p>Some  article\n text.</p></article></body></html>"
        )

        result = scraper.fetch_from_url("https://example.com/post")

        assert result == {"title": "Post", "text": "Some article text.", "word_count": 3}

    def test_unsafe_url_is_never_requested(self, get):
        with pytest.raises(ValueError):
            scraper.fetch_from_url("http://localhost/")

        get.assert_not_called()

    def test_redirects_are_not_followed(self, get, public_dns):
        get.return_value = page("<body><p>text</p></body>")

        scraper.fetch_from_url("https://example.com/post")

        assert get.call_args.kwargs["allow_redirects"] is False

    def test_page_without_text_is_a_value_error(self, get, public_dns):
        get.return_value = page("<html><body></body></html>")

        with pytest.raises(ValueError):
            scraper.fetch_from_url("https://example.com/empty")

    def test_http_errors_propagate(self, get, public_dns):
        get.return_value = Mock(
            raise_for_status=Mock(side_effect=requests.exceptions.HTTPError("404"))
        )

        with pytest.raises(requests.exceptions.HTTPError):
            scraper.fetch_from_url("https://example.com/missing")


class TestExtractText:
    def test_prefers_article_then_main_then_body(self):
        both = b"<body><p>body</p><main>main</main><article>article</article></body>"
        no_article = b"<body><p>body</p><main>main</main></body>"
        only_body = b"<body><p>body</p></body>"

        assert scraper._extract_text(both)["text"] == "article"
        assert scraper._extract_text(no_article)["text"] == "main"
        assert scraper._extract_text(only_body)["text"] == "body"

    def test_noise_tags_are_dropped(self):
        html = (
            b"<article><nav>menu</nav><p>Real</p><script>track()</script>"
            b"<footer>legal</footer></article>"
        )

        assert scraper._extract_text(html)["text"] == "Real"

    def test_text_is_capped(self):
        html = f"<article>{'word ' * 20000}</article>".encode()

        assert len(scraper._extract_text(html)["text"]) == scraper.MAX_CONTENT_LENGTH
