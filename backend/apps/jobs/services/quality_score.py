"""
Content quality scoring service for ContentFlow AI

Responsibility:
  Score AI-generated content on a 0-100 scale before it is saved as an Output record. The score gives users an at-a-glance signal about whether the generated content meets the format requirements.
Scoring Approach:
  Each format has its own set of rules. Rules are additive: a format starts at 0 and gains points for meeting each criterion. The total is normalised to 100 so adding new rules does not change the scale.

  This is a heuristic scorer, not an LLM judge. It runs synchronously in
    the same request cycle with zero external calls, so it adds no latency
    or API cost. It trades precision for speed and simplicity, which is the
    right trade-off for a v1 product.

Format-specific scoring criteria:
    tweet_thread:
        - Contains numbered tweets (e.g. "1/", "2/")
        - At least 3 tweets present
        - No individual tweet exceeds 280 characters
        - Total length is reasonable (not empty, not absurdly long)

    linkedin:
        - Word count between 150 and 300 (PRD target range)
        - Contains a line break (paragraph structure)
        - Does not end mid-sentence

    email:
        - Starts with "Subject:" line
        - Body word count between 200 and 400 (PRD target range)
        - Contains paragraph breaks

    tldr:
        - Contains bullet characters ("•")
        - Has between 3 and 5 bullets
        - Each bullet is one sentence (ends with ".")

Usage:
    from apps.jobs.services.quality import score

    quality_score = score(
        original_content="Full blog post text...",
        generated_text="1/ First tweet...",
        fmt="tweet_thread",
    )
"""

import logging
import re

logger = logging.getLogger(__name__)


def _word_count(text: str) -> int:
    """Count words without relying on the external textstat package."""
    return len(re.findall(r"\b[\w'-]+\b", text or ""))


def _sentence_count(text: str) -> int:
    """Count sentence-like segments using punctuation-aware splitting."""
    if not text or not text.strip():
        return 0
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    return sum(1 for s in sentences if s.strip())


# Minimum score to return a generated text is empty or clearly broken.

# Minimum score to return a generated text is empty or clearly broken.
Min_SCORE = 0

# Maximum score to not exceed beyond the threshold
Max_SCORE = 100


def score(original_text: str, generated_text: str, format: str) -> int:
    """
    Score generated content for a specific output format.

    Dispatches to a format-specific scorer function. Falls back to a generic.
    length-based score if the format is unrecognised.

    Args:
        original_text (str): The original blog post text. Used to check that the output no longer than input (a sign the model ignored the summarisation instructions).
        generated_text (str): AI-generated content to score.
        format (str): Output format key. One of "tweet thread","linkedin","email","tldr".

    Returns:
        int: Score points in range [0,100].
    """
    # check if generated text is empty
    if not generated_text or not generated_text.strip():
        logger.warning(
            f"Empty generated_text passed to quality score of format {format} "
        )
        return Min_SCORE
    scorers = {
        "tweet_thread": _score_tweet_thread,
        "linkedin": _score_linkedin,
        "email": _score_email,
        "tldr": _score_tldr,
    }
    scorer_fn = scorers.get(format)
    if scorer_fn is None:
        logger.warning(
            f"Unknown format {format} in quality scorer — using generic scorer."
        )
        return _score_generic(generated_text, original_text)
    raw_content = scorer_fn(generated_text, original_text)
    return max(Min_SCORE, min(Max_SCORE, raw_content))


def _score_tweet_thread(text: str, original_content: str) -> int:
    """
    Score a tweet thread on structure and per tweet length compliance
    Rules (eac worth 25 point each, total=100):
        1. Contains at least one numbered tweet marker (e.g. "1/").
        2. Has at least 3 tweet segments.
        3. No individual tweet segment exceeds 280 characters.
        4. Total character count is under 3 000 (10 tweets × 280 + separators).
    Args:
        text (str): Generated tweet thread text.
        original_content (str): Source Blog post (unused here, kept for consistent signature).

    Returns:
        int: Raw integer score before clamping.
    """
    points = 0
    tweets = _split_tweets(text)

    # Rule 1: numbered markers present.
    if re.search(r"\b\d+/", text):
        points += 25
    # Rule 2. Tweet length
    if len(tweets) >= 3:
        points += 25
    # Rule 3. no tweets more than 280 characters
    if all(len(t) <= 280 for t in tweets):
        points += 25
    # Rule 4. Total length is under 3000
    if len(text) <= 3000:
        points += 25
    return points


def _score_linkedin(text: str, original_content: str) -> int:
    """
    Score a LinkedIn post on word count and structure.

    Rules:
        - Word count 150–300: 40 points.
        - Contains at least one paragraph break (double newline or long gap): 30 points.
        - Does not appear truncated (ends with "." or "!" or "?"): 30 points.
    Args:
        text (str): Generated LinkedIn post text.
        original_content (str): source blog post

    Returns:
        int: Raw integer score before clamping.
    """
    points = 0
    word_lex_count = _word_count(text)

    if 150 <= word_lex_count <= 300:
        points += 40
    # Partial points if the word doesn't fall in the above category.
    elif 100 <= word_lex_count < 150 or 300 < word_lex_count <= 400:
        points += 20
    if "\n" in text:
        points += 30
    stripped = text.rstrip()
    if stripped and stripped[-1] in ".?!":
        points += 30
    return points


def _score_email(text: str, original_content: str) -> int:
    """
    Score an email newsletter on structure and word count.

    Rules:
        - Starts with "Subject:" on the first line: 30 points.
        - Body word count 200–400: 40 points.
        - Contains paragraph breaks (newlines): 30 points.

    Args:
        text (str): Generated Email Text.
        original_content (str): Original Blog post used here.

    Returns:
        int: Raw integer score before clamping.
    """
    points = 0
    lines = text.strip().splitlines()
    # Rule 1: Subject line present
    if lines and lines[0].lower().startswith("subject:"):
        points += 30
        body = "\n".join(lines[1:])
    else:
        body = text

    # Rule 2: Body word count.
    word_count = _word_count(text)
    if 200 <= word_count <= 400:
        points += 40
    elif 150 <= word_count < 200 or 400 < word_count <= 500:
        points += 20

    # Rule 3: paragraph breaks.
    if "\n" in body:
        points += 30

    return points


def _score_tldr(text: str, original_content: str) -> int:
    """
    Score a TL;DR summary on bullet structure and count.

    Rules:
        - Contains "•" bullet characters: 30 points.
        - Bullet count is 3–5: 40 points.
        - Each bullet ends with a full stop: 30 points.
    Args:
        text (str):  Generated TL;DR text.
        original_content (str): Source blog post (unused here).

    Returns:
        int: Raw integer score before clamping.
    """
    points = 0
    bullets = [
        line.strip() for line in text.splitlines() if line.strip().startswith("•")
    ]
    # Rule 1: Bullet Characters present
    if bullets:
        points += 30
    # Rule 2: Correct Bullet point
    if 3 <= len(bullets) <= 5:
        points += 30
    elif len(bullets) == 2 or len(bullets) == 6:
        # One bullet off the target range — partial credit.
        points += 20
    if bullets and all(_sentence_count(b) == 1 for b in bullets):
        points += 30
    return points


def _score_generic(text: str, original_content: str) -> int:
    """
    Fallback scorer for unrecognised formats.

    Awards points based on whether the output is non-empty and shorter than the original content (a minimal proxy for summarisation quality).
    Args:
        text (str): Generated Content.
        original_content (str): source blog post.

    Returns:
        int: 50 if output is shorter than original and non-empty, else 25.
    """
    if text and len(text) < len(original_content):
        return 50
    return 25


def _split_tweets(text: str) -> list[str]:
    """
    Split a tweet thread string into individual tweet segments.

    Splits on numbered tweet markers ("1/", "2/", etc.). If no markers are found, treats each non-empty line as a separate tweet so length checks still run.
    Args:
        text (str): Raw tweet thread string from the LLM.

    Returns:
        list[str]: List of individual tweet strings with whitespace stripped.
    """
    segments = re.split(r"(?=\b\d+/)", text)
    tweets = [s.strip() for s in segments if s.strip()]

    if not tweets:
        tweets = [line.strip() for line in text.splitlines() if line.strip()]

    return tweets
