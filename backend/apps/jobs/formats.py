"""
The output formats ContentFlow can generate. Adding a format means adding one
entry to FORMATS: the model choices, API validation, prompt, and quality scorer
all derive from it.
"""

from dataclasses import dataclass
from typing import Callable

from .services import quality_score


@dataclass(frozen=True)
class Format:
    label: str
    system_prompt: str
    scorer: Callable[[str], int]

    def score(self, generated_text: str) -> int:
        if not generated_text.strip():
            return 0
        return self.scorer(generated_text)


EMAIL = "email"

# The quality scorers check the targets the prompts ask for (tweet count and length,
# word counts, bullet counts); change a prompt target and its scorer together.
FORMATS: dict[str, Format] = {
    "tweet_thread": Format(
        label="Tweet Thread",
        system_prompt=(
            "You are a social media expert. Convert the blog post into a Twitter/X thread. "
            "Number each tweet (1/, 2/, …). Keep every individual tweet under 280 characters. "
            "Aim for 5 - 10 tweets. Use plain text only, no markdown."
        ),
        scorer=quality_score.score_tweet_thread,
    ),
    "linkedin": Format(
        label="LinkedIn",
        system_prompt=(
            "You are a LinkedIn content strategist. Rewrite the blog post as a LinkedIn article. "
            "Use a compelling opening hook, short paragraphs, and a clear call to action at the end. "
            "Target 150-300 words. Plain text only. No markdown."
        ),
        scorer=quality_score.score_linkedin,
    ),
    EMAIL: Format(
        label="Email",
        system_prompt=(
            "You are an email newsletter writer. Convert the blog post into a newsletter email. "
            "Include a subject line on the first line prefixed with 'Subject:', followed by the body. "
            "Keep it scannable with short paragraphs. Target 200-400 words. Plain text only."
        ),
        scorer=quality_score.score_email,
    ),
    "tldr": Format(
        label="TL;DR",
        system_prompt=(
            "You are a summarisation assistant. Read the blog post and extract its "
            "3 to 5 most important points. Write exactly one bullet per point, each "
            "starting with '•'. Each bullet must be a single sentence under 20 words. "
            "Do not repeat the same point across multiple bullets. Do not include an "
            "introduction, conclusion, or any text outside the bullets. Plain text only, "
            "no markdown, no numbering."
        ),
        scorer=quality_score.score_tldr,
    ),
}

FORMAT_CHOICES = [(key, fmt.label) for key, fmt in FORMATS.items()]
