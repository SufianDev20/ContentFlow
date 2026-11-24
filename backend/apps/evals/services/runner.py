import logging
import re

from django.utils import timezone

from apps.jobs.formats import FORMATS
from apps.jobs.services import llm
from apps.evals.models import EvalArticle, EvalRun, EvalResult
from apps.evals.services.judge import judge_output

logger = logging.getLogger(__name__)


def _strip_bold(text: str) -> str:
    return re.sub(r"\*\*(.+?)\*\*", r"\1", text)


def run_eval(model: str, judge_model: str, articles=None, formats=None, stdout=None):
    """
    Execute a full evaluation run with real LLM calls.

    Args:
        model: The generation model to evaluate.
        judge_model: The model used as LLM-as-judge.
        articles: QuerySet of EvalArticle (defaults to all).
        formats: List of format keys (defaults to all four).
        stdout: Optional write() callable for progress output.

    Returns the completed EvalRun.
    """
    if articles is None:
        articles = EvalArticle.objects.all()
    if formats is None:
        formats = list(FORMATS.keys())

    def log(msg):
        if stdout:
            stdout(msg)
        logger.info(msg)

    run = EvalRun.objects.create(
        model=model,
        judge_model=judge_model,
        status=EvalRun.Status.RUNNING,
        started_at=timezone.now(),
    )

    total = 0
    passed = 0
    article_list = list(articles)

    log(f"\nStarting eval run {run.id}")
    log(f"  Model: {model} | Judge: {judge_model}")
    log(f"  Articles: {len(article_list)} | Formats: {', '.join(formats)}\n")

    for i, article in enumerate(article_list, 1):
        log(f"[{i}/{len(article_list)}] {article.title}")

        for fmt_key in formats:
            spec = FORMATS[fmt_key]

            # Skip if already evaluated in this run (resume support)
            if EvalResult.objects.filter(run=run, article=article, format=fmt_key).exists():
                log(f"  {fmt_key}: already evaluated, skipping")
                continue

            # Step 1: Generate content
            try:
                generation = llm.generate(model, spec.system_prompt, article.source_text)
                generated_text = _strip_bold(generation.text)
            except Exception as exc:
                log(f"  {fmt_key}: GENERATION FAILED ({exc})")
                EvalResult.objects.create(
                    run=run, article=article, format=fmt_key,
                    generated_text="", factual_errors=-1, passed=False,
                    judge_raw_response=f"Generation failed: {exc}",
                )
                total += 1
                continue

            # Step 2: Judge the output
            try:
                result = judge_output(
                    source_text=article.source_text,
                    key_facts=article.key_facts,
                    generated_text=generated_text,
                    judge_model=judge_model,
                )
            except Exception as exc:
                log(f"  {fmt_key}: JUDGE FAILED ({exc})")
                EvalResult.objects.create(
                    run=run, article=article, format=fmt_key,
                    generated_text=generated_text,
                    generation_latency_ms=generation.latency_ms,
                    generation_provider=generation.provider,
                    factual_errors=-1, passed=False,
                    judge_raw_response=f"Judge failed: {exc}",
                )
                total += 1
                continue

            # Step 3: Save the result
            eval_result = EvalResult.objects.create(
                run=run,
                article=article,
                format=fmt_key,
                generated_text=generated_text,
                generation_latency_ms=generation.latency_ms,
                generation_provider=generation.provider,
                claims_checked=result["claims"],
                invented_facts=result["invented_facts"],
                factual_errors=result["factual_errors"],
                passed=result["passed"],
                judge_raw_response=result["judge_raw_response"],
            )

            total += 1
            if eval_result.passed:
                passed += 1

            status = "PASS" if eval_result.passed else f"FAIL ({eval_result.factual_errors} errors)"
            log(f"  {fmt_key}: {status}")

    # Finalize the run
    run.total_outputs = total
    run.passed_outputs = passed
    run.status = EvalRun.Status.COMPLETE if total > 0 else EvalRun.Status.FAILED
    run.completed_at = timezone.now()
    run.save()

    log(f"\n{'=' * 60}")
    log(f"RESULT: {run.summary_line}")
    log(f"{'=' * 60}\n")

    return run
