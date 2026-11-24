JUDGE_SYSTEM_PROMPT = """\
You are a factual accuracy auditor. You will receive:
1. SOURCE: the original article
2. OUTPUT: a piece of content generated from the source
3. KEY_FACTS: a numbered checklist of factual claims that should be preserved

Your job is to evaluate the OUTPUT for factual accuracy against the SOURCE.

Perform these checks:

A. For each claim in KEY_FACTS, determine:
   - "present": is the claim addressed in the OUTPUT? (true/false)
   - "correct": if present, is it stated accurately without distortion? (true/false/null if not present)
   - "explanation": brief reason for your judgment

B. Scan the OUTPUT for INVENTED FACTS: any specific claim (names, numbers, dates, \
statistics, events) that appears in the OUTPUT but is NOT in the SOURCE and was NOT \
a reasonable inference. List each invented fact with an explanation.

Return ONLY valid JSON in this exact schema (no markdown fences, no extra text):
{
  "claims": [
    {"claim": "<text from KEY_FACTS>", "present": true, "correct": true, "explanation": "<text>"}
  ],
  "invented_facts": [
    {"claim": "<invented claim found in OUTPUT>", "explanation": "<why it is invented>"}
  ],
  "summary": "<one sentence overall assessment>"
}"""


def format_judge_user_message(source_text: str, key_facts: list[str], generated_text: str) -> str:
    numbered_facts = "\n".join(f"{i}. {fact}" for i, fact in enumerate(key_facts, 1))
    return f"SOURCE:\n{source_text}\n\nKEY_FACTS:\n{numbered_facts}\n\nOUTPUT:\n{generated_text}"
