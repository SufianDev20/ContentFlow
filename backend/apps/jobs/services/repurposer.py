"""
Turns a Job's content into one Output per requested format and settles the
Job's status.
"""

import logging
import re

from apps.jobs.formats import FORMATS
from apps.jobs.models import Job, Output

from . import llm

logger = logging.getLogger(__name__)


def _strip_bold_markdown(text: str) -> str:
    return re.sub(r"\*\*(.*?)\*\*", r"\1", text)


def repurpose(job: Job) -> list[Output]:
    """
    Generate and save an Output for each format in job.formats, then mark the
    job complete (at least one output) or failed (none).

    A format whose generation fails is logged and skipped; it never aborts the
    others.
    """
    outputs = []
    for fmt in job.formats:
        try:
            outputs.append(_generate_output(job, fmt))
        except Exception:
            logger.exception(
                "Generation failed for job %s format %s",
                job.id,
                fmt,
                extra={"job_id": str(job.id), "format": fmt},
            )

    job.status = Job.Status.COMPLETE if outputs else Job.Status.FAILED
    job.save(update_fields=["status"])
    return outputs


def _generate_output(job: Job, fmt: str) -> Output:
    spec = FORMATS[fmt]
    generation = llm.generate(job.model, spec.system_prompt, job.content)
    text = _strip_bold_markdown(generation.text)
    return Output.objects.create(
        job=job,
        format=fmt,
        text=text,
        provider=generation.provider,
        latency_ms=generation.latency_ms,
        tokens_generated=generation.tokens_generated,
        tokens_per_second=generation.tokens_per_second,
        quality_score=spec.score(text),
    )
