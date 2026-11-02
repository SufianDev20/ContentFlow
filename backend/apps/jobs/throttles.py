from rest_framework.throttling import UserRateThrottle


class JobCreateBurstThrottle(UserRateThrottle):
    """Prevents rapid-fire POST requests to create jobs (minute-level)."""

    scope = "jobs_create_burst"


class JobCreateDailyThrottle(UserRateThrottle):
    """Prevents a single user from draining daily API quotas (day-level)."""

    scope = "jobs_create_daily"


class ScrapeThrottle(UserRateThrottle):
    """Limits outbound URL scraping calls."""

    scope = "scrape"
