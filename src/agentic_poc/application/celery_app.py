import os
from celery import Celery
from celery.schedules import crontab
from src.agentic_poc.config import settings

# Initialize Celery App
app = Celery("agentic_poc", include=["src.agentic_poc.application.worker_tasks"])

# Configuration
app.conf.update(
    broker_url=settings.REDIS_URL,
    result_backend=settings.REDIS_URL,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Seoul",
    enable_utc=True,
    task_always_eager=settings.CELERY_TASK_ALWAYS_EAGER,
    task_eager_propagates=settings.CELERY_TASK_ALWAYS_EAGER,
    # Idempotency safeguards
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1, # Don't fetch multiple tasks if concurrency=1 to reduce risks
)

# Setup Celery Beat
app.conf.beat_schedule = {
    "cleanup-stale-artifacts-daily": {
        "task": "src.agentic_poc.application.worker_tasks.cleanup_artifacts_task",
        "schedule": crontab(hour=3, minute=0), # Run daily at 3 AM
    },
}
