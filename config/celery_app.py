import os

from celery import Celery
from celery.schedules import crontab

# set the default Django settings module for the 'celery' program.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")

app = Celery("aiagents_directory")

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
# - namespace='CELERY' means all celery-related configuration keys
#   should have a `CELERY_` prefix.
app.config_from_object("django.conf:settings", namespace="CELERY")

# Load task modules from all registered Django app configs.
app.autodiscover_tasks()


# ─────────────────────────────────────────────────────────────
# Celery Beat Schedule
# ─────────────────────────────────────────────────────────────

app.conf.beat_schedule = {
    # Daily agent sourcing - runs at 6:00 AM UTC every day
    "daily-agent-sourcing": {
        "task": "aiagents_directory.auto_directory.tasks.source_agents_task",
        "schedule": crontab(hour=6, minute=0),
        "kwargs": {
            "limit": 50,
            "auto_enrich": True,
            "auto_review": False,  # Set to True for fully automated pipeline
            "use_daily_queries": True,  # Rotating queries
            "tbs": "qdr:w",  # Past week only
        },
    },
}
