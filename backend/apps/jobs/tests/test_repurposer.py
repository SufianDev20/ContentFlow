from unittest.mock import patch

import pytest

from apps.jobs.models import Job
from apps.jobs.services import repurposer
from apps.jobs.services.llm import Generation


def generation(text="generated", provider="gemini"):
    return Generation(
        text=text, provider=provider, latency_ms=500, tokens_generated=100, tokens_per_second=200.0
    )


@pytest.fixture
def generate():
    with patch("apps.jobs.services.repurposer.llm.generate") as m:
        yield m


def test_saves_outputs_with_metrics_provider_and_score(generate, make_job):
    generate.return_value = generation("1/ a\n2/ b\n3/ c\n4/ d", provider="gemini")
    job = make_job(formats=["tweet_thread"])

    repurposer.repurpose(job)

    output = job.outputs.get()
    assert output.format == "tweet_thread"
    assert output.provider == "gemini"
    assert (output.latency_ms, output.tokens_generated, output.tokens_per_second) == (500, 100, 200.0)
    assert output.quality_score == 100


def test_prompt_and_model_come_from_format_and_job(generate, make_job):
    generate.return_value = generation()
    job = make_job(formats=["email"], content="the post", model="vendor/model")

    repurposer.repurpose(job)

    model, system_prompt, content = generate.call_args.args
    assert (model, content) == ("vendor/model", "the post")
    assert "Subject:" in system_prompt


def test_markdown_bold_is_stripped(generate, make_job):
    generate.return_value = generation("a **key** point")
    job = make_job(formats=["tldr"])

    repurposer.repurpose(job)

    assert job.outputs.get().text == "a key point"


def test_status_is_complete_when_any_format_succeeds(generate, make_job):
    generate.side_effect = [RuntimeError("boom"), generation()]
    job = make_job(formats=["tweet_thread", "tldr"])

    outputs = repurposer.repurpose(job)

    job.refresh_from_db()
    assert job.status == Job.Status.COMPLETE
    assert [o.format for o in outputs] == ["tldr"]


def test_status_is_failed_when_nothing_is_generated(generate, make_job):
    generate.side_effect = RuntimeError("boom")
    job = make_job(formats=["tldr"])

    assert repurposer.repurpose(job) == []

    job.refresh_from_db()
    assert job.status == Job.Status.FAILED


def test_failure_is_logged_with_job_and_format(generate, make_job, caplog):
    generate.side_effect = RuntimeError("boom")
    job = make_job(formats=["email"])

    repurposer.repurpose(job)

    record = next(r for r in caplog.records if r.levelname == "ERROR")
    assert (record.job_id, record.format) == (str(job.id), "email")
