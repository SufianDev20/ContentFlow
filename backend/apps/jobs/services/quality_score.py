"""
Heuristic 0-100 quality scorers, one per output format. Pure functions of the
generated text: no I/O, no model calls. Each scorer awards fixed points per
satisfied rule and the rules of every scorer sum to at most 100.

Which scorer belongs to which format is declared in apps/jobs/formats.py.
"""

import re


def _word_count(text: str) -> int:
    return len(re.findall(r"\b[\w'-]+\b", text))


def _sentence_count(text: str) -> int:
    return sum(1 for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s.strip())


def _split_tweets(text: str) -> list[str]:
    """Split on "1/", "2/" markers; fall back to one tweet per non-empty line."""
    tweets = [s.strip() for s in re.split(r"(?=\b\d+/)", text) if s.strip()]
    return tweets or [line.strip() for line in text.splitlines() if line.strip()]


def score_tweet_thread(text: str) -> int:
    tweets = _split_tweets(text)
    points = 0
    if re.search(r"\b\d+/", text):
        points += 25
    if len(tweets) >= 3:
        points += 25
    if all(len(t) <= 280 for t in tweets):
        points += 25
    if len(text) <= 3000:
        points += 25
    return points


def score_linkedin(text: str) -> int:
    words = _word_count(text)
    points = 0
    if 150 <= words <= 300:
        points += 40
    elif 100 <= words < 150 or 300 < words <= 400:
        points += 20
    if "\n" in text:
        points += 30
    if text.rstrip().endswith((".", "?", "!")):
        points += 30
    return points


def score_email(text: str) -> int:
    lines = text.strip().splitlines()
    has_subject = bool(lines) and lines[0].lower().startswith("subject:")
    body = "\n".join(lines[1:]) if has_subject else text
    words = _word_count(text)

    points = 0
    if has_subject:
        points += 30
    if 200 <= words <= 400:
        points += 40
    elif 150 <= words < 200 or 400 < words <= 500:
        points += 20
    if "\n" in body:
        points += 30
    return points


def score_tldr(text: str) -> int:
    bullets = [line.strip() for line in text.splitlines() if line.strip().startswith("•")]
    points = 0
    if bullets:
        points += 30
    if 3 <= len(bullets) <= 5:
        points += 30
    elif len(bullets) in (2, 6):
        points += 20
    if bullets and all(_sentence_count(b) == 1 for b in bullets):
        points += 30
    return points
