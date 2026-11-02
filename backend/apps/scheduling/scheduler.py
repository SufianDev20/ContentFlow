"""
In-process background scheduler (APScheduler), started once from
SchedulingConfig.ready(). Runs inside the same Django process — no
separate worker/beat process, no broker. Single-server only: if this
app is ever deployed across multiple instances/processes, each would
run its own scheduler and could double-poll (mitigated in tasks.py by
select_for_update + a status re-check, not eliminated).
"""

import logging

from apscheduler.schedulers.background import BackgroundScheduler

logger = logging.getLogger(__name__)

_scheduler = None


def start():
    global _scheduler
    if _scheduler is not None:
        return

    from . import tasks

    scheduler = BackgroundScheduler(timezone="UTC")
    scheduler.add_job(
        tasks.poll_due_scheduled_emails,
        trigger="interval",
        seconds=60,
        id="poll_due_scheduled_emails",
        max_instances=1,
        misfire_grace_time=30,
    )
    scheduler.start()
    logger.info("Scheduling background scheduler started.")
    _scheduler = scheduler
