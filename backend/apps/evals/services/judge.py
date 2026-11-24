import json
import logging
import re

from apps.jobs.services import llm
from apps.evals.prompts import JUDGE_SYSTEM_PROMPT, format_judge_user_message

logger = logging.getLogger(__name__)


def _extract_json(text: str) -> dict:
    """Extract JSON from LLM response, handling markdown code fences."""
    cleaned = re.sub(r"```(?:json)?\s*", "", text).strip().rstrip("`")
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            return json.loads(match.group())
        raise


def judge_output(source_text: str, key_facts: list[str], generated_text: str,
                 judge_model: str) -> dict:
    """
    Call the LLM judge to evaluate factual accuracy of generated_text
    against source_text and key_facts.

    Returns dict with keys: claims, invented_facts, factual_errors, passed,
    judge_raw_response.
    """
    user_message = format_judge_user_message(source_text, key_facts, generated_text)

    generation = llm.generate(
        judge_model,
        JUDGE_SYSTEM_PROMPT,
        user_message,
        temperature=0.0,
        max_tokens=2048,
    )

    raw_response = generation.text

    try:
        parsed = _extract_json(raw_response)
    except (json.JSONDecodeError, ValueError):
        logger.error("Failed to parse judge response: %s", raw_response[:500])
        return {
            "claims": [],
            "invented_facts": [],
            "factual_errors": -1,
            "passed": False,
            "judge_raw_response": raw_response,
        }

    claims = parsed.get("claims", [])
    invented_facts = parsed.get("invented_facts", [])

    missing_or_wrong = sum(
        1 for c in claims
        if not c.get("present") or c.get("correct") is False
    )
    invented_count = len(invented_facts)
    factual_errors = missing_or_wrong + invented_count

    return {
        "claims": claims,
        "invented_facts": invented_facts,
        "factual_errors": factual_errors,
        "passed": factual_errors == 0,
        "judge_raw_response": raw_response,
    }
