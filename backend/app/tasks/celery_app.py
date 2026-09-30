from celery import Celery

from app.core.config import settings

broker = settings.CELERY_BROKER_URL or settings.REDIS_URL or "memory://"
celery_app = Celery("pragati", broker=broker, backend=settings.CELERY_RESULT_BACKEND or None, include=["app.tasks.jobs"])
celery_app.conf.update(task_serializer="json", accept_content=["json"], result_serializer="json", timezone="UTC",
                       enable_utc=True, task_time_limit=1800, broker_connection_retry_on_startup=True)
celery_app.conf.beat_schedule = {
    "calculate_project_risk": {"task": "pragati.calculate_project_risk", "schedule": 6 * 3600.0},
}
