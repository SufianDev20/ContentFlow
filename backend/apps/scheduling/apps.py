from django.apps import AppConfig


class SchedulingConfig(AppConfig):
    name = "apps.scheduling"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        import os
        import sys
        from django.conf import settings

        # Never start the background scheduler under pytest or `manage.py
        # migrate`/`test` — those run against a DB that may not be ready,
        # and a live BackgroundScheduler thread holding a DB connection
        # open has been observed to hang pytest-django's test-database
        # teardown. Add other management commands here only if one is
        # actually observed hitting the same problem.
        if "pytest" in sys.modules:
            return
        if {"migrate", "test"}.intersection(sys.argv):
            return

        # Under `runserver`'s autoreloader, Django imports this app twice: once
        # in the watcher process and once in the reloaded child (RUN_MAIN=true).
        # Only start in the child so the scheduler doesn't run twice.
        if settings.DEBUG and os.environ.get("RUN_MAIN") != "true":
            return

        from . import scheduler

        scheduler.start()
