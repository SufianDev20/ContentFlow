"""
apps/jobs/tests/test_models.py

Covers Job (PRD 8.2) and Output (PRD 8.3, moved to apps.stats.models per your
Option B decision — imported here for the FK relationship test only).
"""

from django.test import TestCase
from apps.users.models import User
from apps.jobs.models import Job
from apps.stats.models import Output


class JobModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="jane@example.com", password="pass123", full_name="Jane Doe"
        )

    def test_id_is_uuid(self):
        job = Job.objects.create(
            user=self.user, content="some text", model="openai/gpt-4o"
        )
        self.assertEqual(len(str(job.id)), 36)

    def test_status_defaults_to_processing(self):
        job = Job.objects.create(
            user=self.user, content="some text", model="openai/gpt-4o"
        )
        self.assertEqual(job.status, "processing")

    def test_status_choices_restricted_to_prd_values(self):
        field = Job._meta.get_field("status")
        choice_values = [choice[0] for choice in field.choices]
        self.assertIn("processing", choice_values)
        self.assertIn("complete", choice_values)
        self.assertIn("failed", choice_values)

    def test_word_count_calculated_from_content_on_save(self):
        job = Job.objects.create(
            user=self.user, content="one two three four five", model="openai/gpt-4o"
        )
        self.assertEqual(job.word_count, 5)

    def test_word_count_recalculates_on_content_update(self):
        job = Job.objects.create(
            user=self.user, content="one two", model="openai/gpt-4o"
        )
        job.content = "one two three four"
        job.save()
        self.assertEqual(job.word_count, 4)

    def test_source_url_is_optional(self):
        job = Job.objects.create(
            user=self.user, content="some text", model="openai/gpt-4o"
        )
        self.assertIsNone(job.source_url)

    def test_deleting_user_deletes_their_jobs(self):
        Job.objects.create(user=self.user, content="some text", model="openai/gpt-4o")
        self.user.delete()
        self.assertEqual(Job.objects.count(), 0)

    def test_created_at_is_set_automatically(self):
        job = Job.objects.create(
            user=self.user, content="some text", model="openai/gpt-4o"
        )
        self.assertIsNotNone(job.created_at)

    def test_model_field_stores_openrouter_string(self):
        job = Job.objects.create(
            user=self.user, content="text", model="anthropic/claude-3.5-sonnet"
        )
        self.assertEqual(job.model, "anthropic/claude-3.5-sonnet")


class OutputModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="jane@example.com", password="pass123", full_name="Jane Doe"
        )
        self.job = Job.objects.create(
            user=self.user, content="some text", model="openai/gpt-4o"
        )

    def test_id_is_uuid(self):
        output = Output.objects.create(job=self.job, format="email", text="body text")
        self.assertEqual(len(str(output.id)), 36)

    def test_format_choices_restricted_to_prd_values(self):
        field = Output._meta.get_field("format")
        choice_values = [choice[0] for choice in field.choices]
        for expected in ["tweet_thread", "linkedin", "email", "tldr"]:
            self.assertIn(expected, choice_values)

    def test_character_count_calculated_from_text_on_save(self):
        output = Output.objects.create(job=self.job, format="email", text="12345")
        self.assertEqual(output.character_count, 5)

    def test_character_count_recalculates_on_text_update(self):
        output = Output.objects.create(job=self.job, format="email", text="12345")
        output.text = "1234567890"
        output.save()
        self.assertEqual(output.character_count, 10)

    def test_metrics_default_to_zero_before_scoring(self):
        output = Output.objects.create(job=self.job, format="email", text="body")
        self.assertEqual(output.latency_ms, 0)
        self.assertEqual(output.tokens_generated, 0)
        self.assertEqual(output.tokens_per_second, 0.0)
        self.assertEqual(output.quality_score, 0)

    def test_user_rating_is_null_until_rated(self):
        output = Output.objects.create(job=self.job, format="email", text="body")
        self.assertIsNone(output.user_rating)

    def test_user_rating_accepts_value_1_to_5(self):
        output = Output.objects.create(
            job=self.job, format="email", text="body", user_rating=4
        )
        self.assertEqual(output.user_rating, 4)

    def test_deleting_job_deletes_its_outputs(self):
        Output.objects.create(job=self.job, format="email", text="body")
        self.job.delete()
        self.assertEqual(Output.objects.count(), 0)

    def test_created_at_is_set_automatically(self):
        output = Output.objects.create(job=self.job, format="email", text="body")
        self.assertIsNotNone(output.created_at)
