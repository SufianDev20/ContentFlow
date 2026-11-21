from rest_framework.throttling import AnonRateThrottle

from config.throttles import WriteOnlyUserRateThrottle


class AuthRateThrottle(AnonRateThrottle):
    scope = "auth"


class AccountActionThrottle(WriteOnlyUserRateThrottle):
    scope = "account_action"
