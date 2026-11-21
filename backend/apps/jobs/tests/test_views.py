from unittest.mock import patch

import pytest
import requests
from django.urls import reverse

from apps.jobs.models import Job, Output
from apps.jobs.services.llm import Generation

GENERATION = Generation(
    text="generated **bold** text",
    provider="openrouter",
    latency_ms=500,
    tokens_generated=100,
    tokens_per_second=200.0,
)


@pytest.fixture
def llm_generate():
    with patch("apps.jobs.services.repurposer.llm.generate", return_value=GENERATION) as m:
        yield m


class TestCreateJob:
    url = reverse("job-list-create")

    def test_generates_an_output_per_requested_format(self, api, user, llm_generate):
        response = api.post(
            self.url,
            {"content": "one two three", "formats": ["tweet_thread", "tldr"], "model": "m"},
            format="json",
        )

        assert response.status_code == 201
        assert response.data["status"] == "complete"
        assert sorted(o["format"] for o in response.data["outputs"]) == ["tldr", "tweet_thread"]
        job = Job.objects.get()
        assert job.user == user
        assert job.word_count == 3
        assert all(o["text"] == "generated bold text" for o in response.data["outputs"])

    def test_job_is_failed_when_every_generation_fails(self, api, llm_generate):
        llm_generate.side_effect = requests.exceptions.Timeout()

        response = api.post(
            self.url, {"content": "text", "formats": ["email"], "model": "m"}, format="json"
        )

        assert response.status_code == 201
        assert response.data["status"] == "failed"
        assert response.data["outputs"] == []

    def test_one_failing_format_does_not_stop_the_others(self, api, llm_generate):
        llm_generate.side_effect = [RuntimeError("down"), GENERATION]

        response = api.post(
            self.url,
            {"content": "text", "formats": ["tweet_thread", "linkedin"], "model": "m"},
            format="json",
        )

        assert response.data["status"] == "complete"
        assert [o["format"] for o in response.data["outputs"]] == ["linkedin"]

    def test_fetches_content_from_source_url_when_content_is_missing(self, api, llm_generate):
        with patch(
            "apps.jobs.serializers.scraper.fetch_from_url", return_value={"text": "page text"}
        ):
            response = api.post(
                self.url,
                {"source_url": "https://example.com/post", "formats": ["tldr"], "model": "m"},
                format="json",
            )

        assert response.status_code == 201
        assert Job.objects.get().content == "page text"

    def test_unfetchable_source_url_is_rejected(self, api, llm_generate):
        with patch(
            "apps.jobs.serializers.scraper.fetch_from_url", side_effect=ValueError("blocked")
        ):
            response = api.post(
                self.url,
                {"source_url": "https://example.com/post", "formats": ["tldr"], "model": "m"},
                format="json",
            )

        assert response.status_code == 400
        assert Job.objects.count() == 0

    @pytest.mark.parametrize(
        "payload",
        [
            {"formats": ["email"]},
            {"content": "text", "formats": []},
            {"content": "text", "formats": ["not_a_format"]},
            {"content": "text"},
        ],
    )
    def test_invalid_input_is_rejected(self, api, llm_generate, payload):
        assert api.post(self.url, payload, format="json").status_code == 400
        llm_generate.assert_not_called()

    def test_requires_authentication(self, client):
        assert client.post(self.url, {}).status_code == 401


class TestJobReadAndDelete:
    def test_list_contains_only_own_jobs_without_outputs(
        self, api, make_job, make_output, other_user
    ):
        mine = make_job()
        make_output(job=mine)
        make_job(owner=other_user)

        response = api.get(reverse("job-list-create"))

        assert [j["id"] for j in response.data["results"]] == [str(mine.id)]
        assert "outputs" not in response.data["results"][0]

    def test_detail_includes_outputs(self, api, make_job, make_output):
        job = make_job()
        make_output(job=job)

        response = api.get(reverse("job-detail", args=[job.id]))

        assert len(response.data["outputs"]) == 1

    def test_other_users_job_is_not_found(self, api, make_job, other_user):
        job = make_job(owner=other_user)

        assert api.get(reverse("job-detail", args=[job.id])).status_code == 404
        assert api.delete(reverse("job-detail", args=[job.id])).status_code == 404
        assert Job.objects.filter(id=job.id).exists()

    def test_delete_removes_job_and_its_outputs(self, api, make_job, make_output):
        job = make_job()
        make_output(job=job)

        assert api.delete(reverse("job-detail", args=[job.id])).status_code == 204
        assert not Output.objects.exists()


class TestOutputs:
    def test_list_is_scoped_to_user_and_filterable(
        self, api, make_job, make_output, other_user
    ):
        job = make_job(model="model-a")
        email = make_output(job=job, format="email")
        make_output(job=job, format="tldr")
        make_output(job=make_job(model="model-b"), format="email")
        make_output(job=make_job(owner=other_user), format="email")
        url = reverse("output-list")

        assert api.get(url).data["count"] == 3
        filtered = api.get(url, {"format": "email", "model": "model-a"}).data["results"]
        assert [o["id"] for o in filtered] == [str(email.id)]

    def test_rating_is_saved(self, api, make_output):
        output = make_output()

        response = api.patch(reverse("output-rate", args=[output.id]), {"user_rating": 4})

        assert response.status_code == 200
        output.refresh_from_db()
        assert output.user_rating == 4

    @pytest.mark.parametrize("rating", [0, 6])
    def test_out_of_range_rating_is_rejected(self, api, make_output, rating):
        output = make_output()

        response = api.patch(reverse("output-rate", args=[output.id]), {"user_rating": rating})

        assert response.status_code == 400

    def test_cannot_rate_other_users_output(self, api, make_job, make_output, other_user):
        output = make_output(job=make_job(owner=other_user))

        response = api.patch(reverse("output-rate", args=[output.id]), {"user_rating": 3})

        assert response.status_code == 404


class TestScrape:
    url = reverse("scrape")

    def test_returns_extracted_page(self, api):
        page = {"title": "T", "text": "body", "word_count": 1}
        with patch("apps.jobs.views.fetch_from_url", return_value=page):
            response = api.post(self.url, {"url": "https://example.com"})

        assert response.status_code == 200
        assert response.data == page

    def test_unusable_url_is_a_client_error(self, api):
        with patch("apps.jobs.views.fetch_from_url", side_effect=ValueError("blocked")):
            response = api.post(self.url, {"url": "https://example.com"})

        assert response.status_code == 400

    def test_upstream_failure_is_a_bad_gateway(self, api):
        with patch("apps.jobs.views.fetch_from_url", side_effect=requests.exceptions.Timeout()):
            response = api.post(self.url, {"url": "https://example.com"})

        assert response.status_code == 502


def test_available_models_are_listed_per_provider(api):
    by_provider = {"openrouter": ["a:free"], "gemini": ["gemini-2.5-flash"]}
    with patch("apps.jobs.views.llm.available_models", return_value=by_provider):
        response = api.get(reverse("models-available"))

    assert response.data == by_provider
