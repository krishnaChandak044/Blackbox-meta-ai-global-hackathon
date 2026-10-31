"""Celery application for durable media processing."""

import os

from celery import Celery
from dotenv import load_dotenv

load_dotenv()

app = Celery("blackbox", broker=os.getenv("REDIS_URL", "redis://localhost:6379/0"))
app.conf.task_always_eager = os.getenv("CELERY_TASK_ALWAYS_EAGER", "false").lower() == "true"
app.conf.task_eager_propagates = True
app.conf.task_track_started = True
app.conf.imports = (
    "services.worker.jobs.ingest",
    "services.worker.jobs.tracking",
    "services.worker.jobs.transcription",
    "services.worker.jobs.claim_extraction",
)
