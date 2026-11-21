from rest_framework.permissions import SAFE_METHODS
from rest_framework.throttling import UserRateThrottle


class WriteOnlyUserRateThrottle(UserRateThrottle):
    """Counts only requests that change state, so reading never uses up the budget."""

    def allow_request(self, request, view):
        if request.method in SAFE_METHODS:
            return True
        return super().allow_request(request, view)
