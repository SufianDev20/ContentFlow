from rest_framework.throttling import UserRateThrottle


class ScheduledEmailCreateThrottle(UserRateThrottle):
    """Prevents rapid-fire POST requests to schedule emails."""

    scope = "scheduled_email_create"

    def allow_request(self, request, view):
        # Only POST creates; the list GET on the same view must not eat the budget.
        if request.method != "POST":
            return True
        return super().allow_request(request, view)
