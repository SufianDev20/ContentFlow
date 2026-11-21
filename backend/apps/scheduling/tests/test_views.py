from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.scheduling.models import ScheduledEmail

Status = ScheduledEmail.Status
LIST_URL = reverse("scheduled-email-list-create")


def in_hours(hours):
    return (timezone.now() + timedelta(hours=hours)).isoformat()


@pytest.fixture
def email_output(make_output):
    return make_output(format="email", text="Newsletter body")


@pytest.fixture
def payload(email_output):
    return {
        "output": str(email_output.id),
        "recipients": ["reader@example.com"],
        "subject": "Weekly update",
        "scheduled_for": in_hours(1),
    }


@pytest.fixture
def make_scheduled(user, email_output):
    def make(owner=None, **overrides):
        fields = dict(
            output=email_output,
            user=owner or user,
            recipients=["a@example.com"],
            subject="mine",
            edited_content="body",
            status=Status.SCHEDULED,
            scheduled_for=timezone.now() + timedelta(hours=1),
        )
        fields.update(overrides)
        return ScheduledEmail.objects.create(**fields)

    return make


class TestSchedule:
    def test_creates_a_scheduled_email_defaulting_content_to_the_output_text(
        self, api, user, payload
    ):
        response = api.post(LIST_URL, payload, format="json")

        assert response.status_code == 201
        scheduled = ScheduledEmail.objects.get()
        assert (scheduled.status, scheduled.user) == (Status.SCHEDULED, user)
        assert scheduled.edited_content == "Newsletter body"

    def test_explicit_content_overrides_the_output_text(self, api, payload):
        api.post(LIST_URL, {**payload, "edited_content": "my edit"}, format="json")

        assert ScheduledEmail.objects.get().edited_content == "my edit"

    def test_rejects_non_email_outputs(self, api, payload, make_output):
        payload["output"] = str(make_output(format="tweet_thread").id)

        assert api.post(LIST_URL, payload, format="json").status_code == 400
        assert not ScheduledEmail.objects.exists()

    def test_rejects_other_users_outputs(self, api, payload, make_job, make_output, other_user):
        payload["output"] = str(make_output(job=make_job(owner=other_user), format="email").id)

        assert api.post(LIST_URL, payload, format="json").status_code == 400
        assert not ScheduledEmail.objects.exists()

    @pytest.mark.parametrize(
        "overrides",
        [
            {"scheduled_for": in_hours(-1)},
            {"scheduled_for": in_hours(24 * 91)},
            {"recipients": []},
            {"recipients": ["not-an-email"]},
            {"recipients": [f"r{i}@example.com" for i in range(26)]},
        ],
    )
    def test_rejects_invalid_time_or_recipients(self, api, payload, overrides):
        assert api.post(LIST_URL, {**payload, **overrides}, format="json").status_code == 400
        assert not ScheduledEmail.objects.exists()

    def test_requires_authentication(self, client, payload):
        assert client.post(LIST_URL, payload, content_type="application/json").status_code == 401


class TestList:
    def test_lists_only_own_emails_and_filters_by_status(self, api, make_scheduled, other_user):
        mine = make_scheduled()
        make_scheduled(status=Status.CANCELLED)
        make_scheduled(owner=other_user)

        assert api.get(LIST_URL).data["count"] == 2
        only_scheduled = api.get(LIST_URL, {"status": "scheduled"}).data["results"]
        assert [e["id"] for e in only_scheduled] == [str(mine.id)]


class TestCancel:
    def test_cancels_a_scheduled_email(self, api, make_scheduled):
        scheduled = make_scheduled()

        response = api.post(reverse("scheduled-email-cancel", args=[scheduled.id]))

        assert response.status_code == 200
        scheduled.refresh_from_db()
        assert scheduled.status == Status.CANCELLED

    @pytest.mark.parametrize("status", [Status.SENT, Status.FAILED, Status.CANCELLED])
    def test_cannot_cancel_a_finished_email(self, api, make_scheduled, status):
        scheduled = make_scheduled(status=status)

        response = api.post(reverse("scheduled-email-cancel", args=[scheduled.id]))

        assert response.status_code == 400
        scheduled.refresh_from_db()
        assert scheduled.status == status

    def test_other_users_email_is_not_found(self, api, make_scheduled, other_user):
        scheduled = make_scheduled(owner=other_user)

        response = api.post(reverse("scheduled-email-cancel", args=[scheduled.id]))

        assert response.status_code == 404
        scheduled.refresh_from_db()
        assert scheduled.status == Status.SCHEDULED


class TestUpdate:
    def url(self, scheduled):
        return reverse("scheduled-email-update", args=[scheduled.id])

    def test_edits_content_before_it_is_sent(self, api, make_scheduled):
        scheduled = make_scheduled()

        response = api.patch(self.url(scheduled), {"edited_content": "revised"})

        assert response.status_code == 200
        scheduled.refresh_from_db()
        assert scheduled.edited_content == "revised"

    @pytest.mark.parametrize("status", [Status.SENT, Status.FAILED, Status.CANCELLED])
    def test_finished_emails_cannot_be_edited(self, api, make_scheduled, status):
        scheduled = make_scheduled(status=status)

        response = api.patch(self.url(scheduled), {"edited_content": "revised"})

        assert response.status_code == 400
        scheduled.refresh_from_db()
        assert scheduled.edited_content == "body"

    def test_rescheduling_to_the_past_is_rejected(self, api, make_scheduled):
        scheduled = make_scheduled()

        response = api.patch(self.url(scheduled), {"scheduled_for": in_hours(-1)})

        assert response.status_code == 400

    def test_other_users_email_is_not_found(self, api, make_scheduled, other_user):
        scheduled = make_scheduled(owner=other_user)

        assert api.patch(self.url(scheduled), {"subject": "hijack"}).status_code == 404
