from config.throttles import WriteOnlyUserRateThrottle


class ScheduledEmailCreateThrottle(WriteOnlyUserRateThrottle):
    scope = "scheduled_email_create"
