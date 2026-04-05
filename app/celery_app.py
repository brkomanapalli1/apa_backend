from celery import Celery

from app.core.config import settings

celery_app = Celery('paperwork', broker=settings.REDIS_URL, backend=settings.REDIS_URL)
