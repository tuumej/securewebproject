"""Celery 애플리케이션 및 주기 스케줄(Celery Beat) 설정."""
from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "securewebproject",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.tasks.jobs"],
)

celery_app.conf.update(
    task_track_started=True,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Seoul",
    enable_utc=True,
)

# 주기 작업
celery_app.conf.beat_schedule = {
    # 1시간마다 데일리시큐 긴급속보 갱신 → 신규 기사 저장 + Slack 알림
    "hourly-security-news": {
        "task": "app.tasks.jobs.fetch_security_news_task",
        "schedule": 3600.0,  # 초 단위 (1시간)
    },
}
