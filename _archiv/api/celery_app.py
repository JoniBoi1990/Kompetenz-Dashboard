from celery import Celery
from config import settings

celery = Celery(
    "kompetenz",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["tasks.pdf_task"],
)

celery.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Europe/Berlin",
    enable_utc=True,
)
