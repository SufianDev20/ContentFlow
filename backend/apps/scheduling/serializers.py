from datetime import timedelta

from django.utils import timezone
from rest_framework import serializers

from apps.jobs.formats import EMAIL

from .models import ScheduledEmail

MAX_RECIPIENTS = 25
MAX_SCHEDULE_HORIZON_DAYS = 90


def validate_future_datetime(value):
    now = timezone.now()
    if value <= now:
        raise serializers.ValidationError("scheduled_for must be in the future.")
    if value > now + timedelta(days=MAX_SCHEDULE_HORIZON_DAYS):
        raise serializers.ValidationError(
            f"scheduled_for cannot be more than {MAX_SCHEDULE_HORIZON_DAYS} days out."
        )
    return value


def recipients_field(**kwargs):
    return serializers.ListField(
        child=serializers.EmailField(), min_length=1, max_length=MAX_RECIPIENTS, **kwargs
    )


class ScheduledEmailSerializer(serializers.ModelSerializer):

    class Meta:
        model = ScheduledEmail
        fields = [
            "id",
            "output",
            "recipients",
            "subject",
            "edited_content",
            "status",
            "scheduled_for",
            "sent_at",
            "error_message",
            "attempt_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class ScheduledEmailCreateSerializer(serializers.ModelSerializer):
    recipients = recipients_field()
    edited_content = serializers.CharField(required=False, allow_blank=True)

    class Meta:
        model = ScheduledEmail
        fields = ["output", "recipients", "subject", "edited_content", "scheduled_for"]

    def validate_output(self, output):
        request = self.context["request"]
        if output.job.user_id != request.user.id:
            raise serializers.ValidationError("Output not found.")
        if output.format != EMAIL:
            raise serializers.ValidationError(
                "Only email-format outputs can be scheduled."
            )
        return output

    validate_scheduled_for = staticmethod(validate_future_datetime)

    def create(self, validated_data):
        request = self.context["request"]
        output = validated_data["output"]
        if not validated_data.get("edited_content"):
            validated_data["edited_content"] = output.text
        validated_data["user"] = request.user
        validated_data["status"] = ScheduledEmail.Status.SCHEDULED
        return super().create(validated_data)


class ScheduledEmailUpdateSerializer(serializers.ModelSerializer):
    recipients = recipients_field(required=False)

    class Meta:
        model = ScheduledEmail
        fields = ["recipients", "subject", "edited_content", "scheduled_for"]

    def validate(self, attrs):
        if self.instance.status not in ScheduledEmail.EDITABLE_STATUSES:
            raise serializers.ValidationError(
                f"Cannot edit a {self.instance.status} scheduled email."
            )
        return attrs

    validate_scheduled_for = staticmethod(validate_future_datetime)
