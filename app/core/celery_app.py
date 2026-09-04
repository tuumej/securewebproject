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
    # 결과는 전부 DB 폴링으로 조회하고 .get()/AsyncResult로 결과를 읽지 않으므로
    # 결과 백엔드 조회 자체를 끈다. 켜져 있으면 .delay() 호출 시마다 결과 백엔드에
    # pub/sub 구독을 시도하는데, 브로커가 응답 없이 죽어있으면(예: Redis 다운) 이
    # 구독 재연결 로직이 재시도 한도를 채울 때까지(수십~100초 이상) .delay()가
    # 반환되지 않아 스캔이 "pending"에 오래 멈춰 보이는 원인이 된다.
    task_ignore_result=True,
)

# 주기 작업
celery_app.conf.beat_schedule = {
    # 1시간마다 데일리시큐 긴급속보 갱신 → 신규 기사 저장 + Slack 알림
    "hourly-security-news": {
        "task": "app.tasks.jobs.fetch_security_news_task",
        "schedule": 3600.0,  # 초 단위 (1시간)
    },
}
