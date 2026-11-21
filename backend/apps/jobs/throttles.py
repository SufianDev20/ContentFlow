from config.throttles import WriteOnlyUserRateThrottle


class JobCreateBurstThrottle(WriteOnlyUserRateThrottle):
    scope = "jobs_create_burst"


class JobCreateDailyThrottle(WriteOnlyUserRateThrottle):
    scope = "jobs_create_daily"


class ScrapeThrottle(WriteOnlyUserRateThrottle):
    scope = "scrape"
