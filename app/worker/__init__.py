from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

celery_app = Celery('paperwork', broker=settings.REDIS_URL, backend=settings.REDIS_URL)
celery_app.conf.task_track_started = True
celery_app.conf.task_serializer = 'json'
celery_app.conf.result_serializer = 'json'
celery_app.conf.accept_content = ['json']
celery_app.conf.beat_schedule = {
    'dispatch-due-reminders-every-hour': {
        'task': 'app.worker.tasks.send_due_reminders_task',
        'schedule': crontab(minute=0),
    },
}
celery_app.conf.timezone = 'UTC'
