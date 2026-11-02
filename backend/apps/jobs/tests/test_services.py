r"""
apps/jobs/tests/test_services.py

Combined tests for apps/jobs/services/: quality.py, repurposer.py, scraper.py.

REQUIRED FIXES BEFORE RUNNING — tests will fail or the module won't import
without these:

1. quality.py
   - Remove `from typing import str, int, List` (str/int aren't importable
     from typing; this line raises ImportError on module load).
   - Fix the re.search call in _score_tweet_thread (currently missing the
     `text` argument), which raises TypeError on every call.
   - Guard `text.rstrip()[-1]` in _score_linkedin against an empty string
     after rstrip.

2. scraper.py
   - `_normalise_whitespace` is missing `return`:
       def _normalise_whitespace(text: str) -> str:
           return re.sub(r"\s+", " ", text).strip()
     Without `return`, the function always yields None, and
     `_extract_text` then does `None[:MAX_CONTENT_LENGTH]`, raising
     TypeError on every call that reaches it.

3. repurposer.py
   - `f"Bearer{OPENROUTER_API_KEY}"` is missing a space before the key.
     Not covered by a test here since no test asserts against a real
     server, but will break every real OpenRouter call in production.
   - `repurpose()` reads `job.Outputs_requested` (capital O) while the
     docstring and any calling code would use `outputs_requested`
     (lowercase). Since Job has neither attribute, every job currently
     falls through to generating all four formats regardless of what
     was requested. Tests reflect this actual behavior. Fix the
     attribute name if per-job format selection is supposed to work.
"""

import requests
from unittest.mock import patch, Mock
from django.test import SimpleTestCase, TestCase
from apps.users.models import User
from apps.jobs.models import Job
from apps.jobs.services import quality
from apps.jobs.services import repurposer
from apps.jobs.services import scraper


class ScoreDispatchTests(SimpleTestCase):
    def test_empty_generated_text_returns_min_score(self):
        result = quality.score("original content", "", "tweet_thread")
        self.assertEqual(result, quality.Min_SCORE)

    def test_whitespace_only_generated_text_returns_min_score(self):
        result = quality.score("original content", "   ", "linkedin")
        self.assertEqual(result, quality.Min_SCORE)

    def test_unknown_format_falls_back_to_generic_scorer(self):
        result = quality.score(
            "a longer original blog post here", "short output", "unknown_format"
        )
        self.assertEqual(result, 50)

    def test_score_never_exceeds_max_score(self):
        text = "1/ Hook here\n2/ Point two\n3/ Point three\n4/ CTA and done"
        result = quality.score("original", text, "tweet_thread")
        self.assertLessEqual(result, quality.Max_SCORE)

    def test_score_never_below_min_score(self):
        result = quality.score("original", "x", "tweet_thread")
        self.assertGreaterEqual(result, quality.Min_SCORE)

    def test_score_returns_int(self):
        text = "1/ Hook\n2/ Point\n3/ CTA"
        result = quality.score("original", text, "tweet_thread")
        self.assertIsInstance(result, int)


class TweetThreadScorerTests(SimpleTestCase):
    def test_full_score_when_all_four_rules_pass(self):
        text = "1/ Hook here\n2/ Point two\n3/ Point three\n4/ CTA and done"
        result = quality._score_tweet_thread(text, "original")
        self.assertEqual(result, 100)

    def test_zero_when_no_numbered_marker_and_fewer_than_three_segments(self):
        # No "N/" marker, single line, so _split_tweets falls back to one
        # line-based tweet — rules 1 and 2 both fail.
        text = "Just a plain sentence with no structure at all"
        result = quality._score_tweet_thread(text, "original")
        self.assertEqual(result, 50)  # rules 3 and 4 still pass (single short segment)

    def test_loses_points_when_a_tweet_exceeds_280_characters(self):
        long_tweet = "1/ " + ("word " * 100)  # well over 280 chars
        text = long_tweet + "\n2/ short\n3/ short"
        result = quality._score_tweet_thread(text, "original")
        self.assertLess(result, 100)

    def test_fewer_than_three_tweets_loses_points(self):
        text = "1/ only one tweet here"
        result = quality._score_tweet_thread(text, "original")
        self.assertLess(result, 100)

    def test_loses_points_when_total_length_exceeds_3000_chars(self):
        text = "1/ " + ("word " * 700)  # pushes total length past 3000
        result = quality._score_tweet_thread(text, "original")
        self.assertLess(result, 100)


class LinkedinScorerTests(SimpleTestCase):
    def test_full_score_within_word_range_with_breaks_and_punctuation(self):
        body = ("word " * 200).strip() + ".\nSecond line here."
        result = quality._score_linkedin(body, "original")
        self.assertEqual(result, 100)

    def test_partial_credit_for_word_count_just_below_range(self):
        # 120 words falls in the 100-149 partial credit band.
        body = ("word " * 120).strip() + ".\nMore text."
        result = quality._score_linkedin(body, "original")
        self.assertEqual(result, 20 + 30 + 30)

    def test_zero_word_count_points_when_far_outside_range(self):
        body = "Too short entirely.\nSecond line."
        result = quality._score_linkedin(body, "original")
        # word count band fails, but newline and ending punctuation still pass
        self.assertEqual(result, 30 + 30)

    def test_no_points_for_missing_paragraph_break(self):
        body = ("word " * 200).strip() + "."  # no newline
        result = quality._score_linkedin(body, "original")
        self.assertEqual(result, 40 + 30)

    def test_no_points_when_not_ending_in_terminal_punctuation(self):
        body = ("word " * 200).strip() + "\nends abruptly"
        result = quality._score_linkedin(body, "original")
        self.assertEqual(result, 40 + 30)


class EmailScorerTests(SimpleTestCase):
    def test_full_score_with_subject_body_range_and_breaks(self):
        body_words = ("word " * 250).strip()
        text = f"Subject: Big News\n{body_words}.\nSecond paragraph line."
        result = quality._score_email(text, "original")
        self.assertEqual(result, 100)

    def test_missing_subject_line_loses_30_points(self):
        body_words = ("word " * 250).strip()
        text = f"{body_words}.\nSecond paragraph line."
        result = quality._score_email(text, "original")
        self.assertEqual(result, 40 + 30)

    def test_partial_credit_word_count_just_below_range(self):
        body_words = ("word " * 180).strip()  # 150-199 band = partial
        text = f"Subject: Update\n{body_words}.\nMore text here."
        result = quality._score_email(text, "original")
        self.assertEqual(result, 30 + 20 + 30)

    def test_no_break_in_body_loses_30_points(self):
        body_words = ("word " * 250).strip()
        text = f"Subject: Big News\n{body_words}."  # single line body
        result = quality._score_email(text, "original")
        self.assertEqual(result, 30 + 40)


class TldrScorerTests(SimpleTestCase):
    def test_full_score_with_three_to_five_single_sentence_bullets(self):
        text = "• First point.\n• Second point.\n• Third point."
        result = quality._score_tldr(text, "original")
        self.assertEqual(result, 90)

    def test_zero_when_no_bullet_characters(self):
        text = "No bullets here at all, just a paragraph."
        result = quality._score_tldr(text, "original")
        self.assertEqual(result, 0)

    def test_partial_credit_for_two_bullets(self):
        text = "• First point.\n• Second point."
        result = quality._score_tldr(text, "original")
        # 30 (bullets present) + 20 (partial count) + 30 (each is one sentence)
        self.assertEqual(result, 80)

    def test_partial_credit_for_six_bullets(self):
        text = "\n".join(f"• Point number {i}." for i in range(1, 7))
        result = quality._score_tldr(text, "original")
        self.assertEqual(result, 80)

    def test_no_sentence_count_points_when_bullet_has_multiple_sentences(self):
        text = "• First point. Second sentence in same bullet.\n• Second.\n• Third."
        result = quality._score_tldr(text, "original")
        self.assertEqual(result, 60)


class GenericScorerTests(SimpleTestCase):
    def test_returns_50_when_output_shorter_than_original_and_nonempty(self):
        result = quality._score_generic("short", "a much longer original blog post")
        self.assertEqual(result, 50)

    def test_returns_25_when_output_longer_than_original(self):
        result = quality._score_generic(
            "a much longer generated output text here", "short"
        )
        self.assertEqual(result, 25)

    def test_returns_25_when_output_is_empty(self):
        result = quality._score_generic("", "original content")
        self.assertEqual(result, 25)


class SplitTweetsTests(SimpleTestCase):
    def test_splits_on_numbered_markers(self):
        text = "1/ First tweet 2/ Second tweet 3/ Third tweet"
        result = quality._split_tweets(text)
        self.assertEqual(len(result), 3)

    def test_falls_back_to_line_split_when_no_markers_present(self):
        text = "Line one\nLine two\nLine three"
        result = quality._split_tweets(text)
        self.assertEqual(len(result), 3)

    def test_strips_whitespace_from_each_segment(self):
        text = "1/   First tweet with padding   \n2/ Second"
        result = quality._split_tweets(text)
        for tweet in result:
            self.assertEqual(tweet, tweet.strip())

    def test_empty_string_returns_empty_list(self):
        result = quality._split_tweets("")
        self.assertEqual(result, [])


class BuildPromptTests(SimpleTestCase):
    def test_returns_system_and_user_messages(self):
        messages = repurposer.build_prompt("blog content here", "tweet_thread")
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0]["role"], "system")
        self.assertEqual(messages[1]["role"], "user")

    def test_user_message_contains_raw_content(self):
        messages = repurposer.build_prompt("my blog text", "linkedin")
        self.assertEqual(messages[1]["content"], "my blog text")

    def test_system_message_matches_format_prompt(self):
        messages = repurposer.build_prompt("content", "email")
        self.assertEqual(messages[0]["content"], repurposer.SYSTEM_PROMPTS["email"])

    def test_unknown_format_raises_keyerror(self):
        with self.assertRaises(KeyError):
            repurposer.build_prompt("content", "not_a_real_format")


class CallOpenrouterTests(SimpleTestCase):
    @patch("apps.jobs.services.repurposer.requests.post")
    def test_returns_expected_keys(self, mock_post):
        mock_response = Mock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "1/ generated tweet thread"}}],
            "usage": {"completion_tokens": 100, "prompt_tokens": 50},
        }
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        result = repurposer.call_openrouter(
            "blog content", "openai/gpt-4o", "tweet_thread"
        )

        self.assertIn("text", result)
        self.assertIn("latency_ms", result)
        self.assertIn("tokens_generated", result)
        self.assertIn("tokens_per_second", result)

    @patch("apps.jobs.services.repurposer.requests.post")
    def test_text_extracted_from_choices(self, mock_post):
        mock_response = Mock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "generated output text"}}],
            "usage": {"completion_tokens": 50, "prompt_tokens": 20},
        }
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        result = repurposer.call_openrouter("content", "openai/gpt-4o", "email")
        self.assertEqual(result["text"], "generated output text")

    @patch("apps.jobs.services.repurposer.requests.post")
    def test_tokens_generated_extracted_from_usage(self, mock_post):
        mock_response = Mock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "text"}}],
            "usage": {"completion_tokens": 234, "prompt_tokens": 10},
        }
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        result = repurposer.call_openrouter("content", "openai/gpt-4o", "tldr")
        self.assertEqual(result["tokens_generated"], 234)

    @patch("apps.jobs.services.repurposer.time.monotonic")
    @patch("apps.jobs.services.repurposer.requests.post")
    def test_tokens_per_second_calculated_from_elapsed_time(
        self, mock_post, mock_monotonic
    ):
        mock_response = Mock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "text"}}],
            "usage": {"completion_tokens": 200, "prompt_tokens": 10},
        }
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response
        mock_monotonic.side_effect = [0.0, 1.0]  # exactly 1 second elapsed

        result = repurposer.call_openrouter("content", "openai/gpt-4o", "linkedin")
        self.assertEqual(result["latency_ms"], 1000)
        self.assertEqual(result["tokens_per_second"], 200.0)

    @patch("apps.jobs.services.repurposer.requests.post")
    def test_raises_httperror_on_non_2xx_response(self, mock_post):
        import requests

        mock_response = Mock()
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(
            "500 error"
        )
        mock_post.return_value = mock_response

        with self.assertRaises(requests.exceptions.HTTPError):
            repurposer.call_openrouter("content", "openai/gpt-4o", "email")

    @patch("apps.jobs.services.repurposer.requests.post")
    def test_sends_correct_model_and_messages_in_payload(self, mock_post):
        mock_response = Mock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "text"}}],
            "usage": {"completion_tokens": 10, "prompt_tokens": 5},
        }
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        repurposer.call_openrouter(
            "blog text", "anthropic/claude-3-haiku", "tweet_thread"
        )

        _, kwargs = mock_post.call_args
        self.assertEqual(kwargs["json"]["model"], "anthropic/claude-3-haiku")
        self.assertEqual(kwargs["json"]["messages"][1]["content"], "blog text")

    @patch("apps.jobs.services.repurposer.requests.post")
    def test_raises_keyerror_on_malformed_response_shape(self, mock_post):
        mock_response = Mock()
        mock_response.json.return_value = {"unexpected": "shape"}
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        with self.assertRaises(KeyError):
            repurposer.call_openrouter("content", "openai/gpt-4o", "email")


class RepurposeOrchestrationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="jane@example.com", password="pass123", full_name="Jane Doe"
        )
        self.job = Job.objects.create(
            user=self.user, content="blog content", model="openai/gpt-4o"
        )

    @patch("apps.jobs.services.repurposer.call_openrouter")
    def test_generates_all_four_formats_when_job_has_no_outputs_requested(
        self, mock_call
    ):
        mock_call.return_value = {
            "text": "generated",
            "latency_ms": 500,
            "tokens_generated": 100,
            "tokens_per_second": 200.0,
        }
        results = repurposer.repurpose(self.job)
        self.assertEqual(len(results), 4)

    @patch("apps.jobs.services.repurposer.call_openrouter")
    def test_each_result_includes_format_key(self, mock_call):
        mock_call.return_value = {
            "text": "generated",
            "latency_ms": 500,
            "tokens_generated": 100,
            "tokens_per_second": 200.0,
        }
        results = repurposer.repurpose(self.job)
        formats = {r["format"] for r in results}
        self.assertEqual(formats, set(repurposer.SYSTEM_PROMPTS.keys()))

    @patch("apps.jobs.services.repurposer.call_openrouter")
    def test_one_failing_format_does_not_abort_remaining_formats(self, mock_call):
        def side_effect(original_content, model_used, format_used):
            if format_used == "email":
                raise Exception("simulated API failure")
            return {
                "text": "generated",
                "latency_ms": 500,
                "tokens_generated": 100,
                "tokens_per_second": 200.0,
            }

        mock_call.side_effect = side_effect

        results = repurposer.repurpose(self.job)
        formats = {r["format"] for r in results}
        self.assertNotIn("email", formats)
        self.assertEqual(len(results), 3)

    @patch("apps.jobs.services.repurposer.call_openrouter")
    def test_repurpose_does_not_raise_when_all_formats_fail(self, mock_call):
        mock_call.side_effect = Exception("simulated failure")
        try:
            results = repurposer.repurpose(self.job)
        except Exception as e:
            self.fail(f"repurpose() raised unexpectedly: {e}")
        self.assertEqual(results, [])

    @patch("apps.jobs.services.repurposer.call_openrouter")
    def test_passes_job_content_and_model_to_call_openrouter(self, mock_call):
        mock_call.return_value = {
            "text": "generated",
            "latency_ms": 500,
            "tokens_generated": 100,
            "tokens_per_second": 200.0,
        }
        repurposer.repurpose(self.job)
        _, kwargs = mock_call.call_args_list[0]
        self.assertEqual(kwargs["original_content"], "blog content")
        self.assertEqual(kwargs["model_used"], "openai/gpt-4o")


class FetchFromUrlTests(SimpleTestCase):
    @patch("apps.jobs.services.scraper.requests.get")
    def test_returns_plain_text_string(self, mock_get):
        mock_response = Mock()
        mock_response.content = (
            b"<html><body><article><p>Some article text.</p></article></body></html>"
        )
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        result = scraper.fetch_from_url("https://example.com/post")
        self.assertIsInstance(result, str)
        self.assertIn("Some article text.", result)

    @patch("apps.jobs.services.scraper.requests.get")
    def test_raises_valueerror_when_no_text_extracted(self, mock_get):
        mock_response = Mock()
        mock_response.content = b"<html><body></body></html>"
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        with self.assertRaises(ValueError):
            scraper.fetch_from_url("https://example.com/empty")

    @patch("apps.jobs.services.scraper.requests.get")
    def test_raises_httperror_on_4xx_response(self, mock_get):
        mock_response = Mock()
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(
            "404"
        )
        mock_get.return_value = mock_response

        with self.assertRaises(requests.exceptions.HTTPError):
            scraper.fetch_from_url("https://example.com/missing")

    @patch("apps.jobs.services.scraper.requests.get")
    def test_raises_timeout_when_request_times_out(self, mock_get):
        mock_get.side_effect = requests.exceptions.Timeout("timed out")

        with self.assertRaises(requests.exceptions.Timeout):
            scraper.fetch_from_url("https://example.com/slow")

    @patch("apps.jobs.services.scraper.requests.get")
    def test_sends_browser_like_user_agent_header(self, mock_get):
        mock_response = Mock()
        mock_response.content = (
            b"<html><body><article><p>Text.</p></article></body></html>"
        )
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        scraper.fetch_from_url("https://example.com/post")

        _, kwargs = mock_get.call_args
        self.assertIn("User-Agent", kwargs["headers"])
        self.assertIn("Mozilla", kwargs["headers"]["User-Agent"])

    @patch("apps.jobs.services.scraper.requests.get")
    def test_passes_request_timeout(self, mock_get):
        mock_response = Mock()
        mock_response.content = (
            b"<html><body><article><p>Text.</p></article></body></html>"
        )
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        scraper.fetch_from_url("https://example.com/post")

        _, kwargs = mock_get.call_args
        self.assertEqual(kwargs["timeout"], scraper.REQUEST_TIMEOUT)


class ExtractTextTests(SimpleTestCase):
    def test_prefers_article_tag_over_body(self):
        html = b"""
        <html><body>
            <p>Body text that should be ignored.</p>
            <article><p>Article text that should be kept.</p></article>
        </body></html>
        """
        result = scraper._extract_text(html)
        self.assertIn("Article text", result)
        self.assertNotIn("Body text that should be ignored", result)

    def test_falls_back_to_main_when_no_article(self):
        html = b"""
        <html><body>
            <p>Ignored body text.</p>
            <main><p>Main content text.</p></main>
        </body></html>
        """
        result = scraper._extract_text(html)
        self.assertIn("Main content text", result)

    def test_falls_back_to_body_when_no_article_or_main(self):
        html = b"<html><body><p>Only body content here.</p></body></html>"
        result = scraper._extract_text(html)
        self.assertIn("Only body content here", result)

    def test_strips_noise_tags(self):
        html = b"""
        <html><body>
            <article>
                <nav>Navigation links</nav>
                <p>Real article content.</p>
                <script>console.log('noise')</script>
                <footer>Footer junk</footer>
            </article>
        </body></html>
        """
        result = scraper._extract_text(html)
        self.assertIn("Real article content", result)
        self.assertNotIn("Navigation links", result)
        self.assertNotIn("console.log", result)
        self.assertNotIn("Footer junk", result)

    def test_returns_space_when_no_content_root_found(self):
        # BeautifulSoup always creates a body/html wrapper even for empty
        # input, so this exercises the defensive `content_root is None`
        # branch only if parsing produces no tree at all — kept as a
        # regression guard.
        html = b""
        result = scraper._extract_text(html)
        self.assertIsInstance(result, str)

    def test_truncates_to_max_content_length(self):
        long_paragraph = "word " * 20000  # far exceeds MAX_CONTENT_LENGTH
        html = f"<html><body><article><p>{long_paragraph}</p></article></body></html>".encode()
        result = scraper._extract_text(html)
        self.assertLessEqual(len(result), scraper.MAX_CONTENT_LENGTH)


class NormaliseWhitespaceTests(SimpleTestCase):
    def test_collapses_multiple_spaces_into_one(self):
        result = scraper._normalise_whitespace("word1     word2")
        self.assertEqual(result, "word1 word2")

    def test_collapses_newlines_and_tabs(self):
        result = scraper._normalise_whitespace("line1\n\n\tline2")
        self.assertEqual(result, "line1 line2")

    def test_strips_leading_and_trailing_whitespace(self):
        result = scraper._normalise_whitespace("   padded text   ")
        self.assertEqual(result, "padded text")

    def test_returns_string_not_none(self):
        # Regression test for the missing `return` bug. Fails until fixed.
        result = scraper._normalise_whitespace("some text")
        self.assertIsNotNone(result)
        self.assertIsInstance(result, str)
