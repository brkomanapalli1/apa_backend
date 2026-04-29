from celery import Celery
from app.core.config import settings

celery_app = Celery('paperwork', broker=settings.REDIS_URL, backend=settings.REDIS_URL)
celery_app.conf.task_track_started = True
celery_app.conf.task_serializer = 'json'
celery_app.conf.result_serializer = 'json'
celery_app.conf.accept_content = ['json']
celery_app.conf.timezone = 'UTC'
# Beat schedule is defined in app/worker/tasks.py — do not duplicate here