from django.apps import AppConfig


class SchedulingConfig(AppConfig):
    name = "apps.scheduling"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        import os
        import sys
        from django.conf import settings

        # A live scheduler thread holding a DB connection has been observed to
        # hang pytest-django's test-database teardown, and migrate/test run
        # against a DB that may not be ready.
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
