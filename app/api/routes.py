"""API 엔드포인트 — 크롤링/알림 작업 등록, 이력 조회, 보안뉴스/알림."""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.history import CrawlRecord, NotificationLog
from app.models.news import SecurityNews
from app.schemas.history import (
    CrawlRecordOut,
    CrawlRequest,
    NotificationLogOut,
    NotificationRequest,
)
from app.schemas.news import RefreshResult, SecurityNewsOut, UnreadCount
from app.services.security_news import refresh_security_news
from app.tasks.jobs import crawl_url_task, send_notification_task

router = APIRouter(prefix="/api", tags=["core"])

KST = timezone(timedelta(hours=9))


# ── 크롤링 ────────────────────────────────────────────
@router.post("/crawl", status_code=202)
def enqueue_crawl(req: CrawlRequest) -> dict[str, str]:
    """크롤링 작업을 백그라운드 큐에 등록한다."""
    task = crawl_url_task.delay(str(req.url))
    return {"task_id": task.id, "status": "queued"}


@router.post("/notify", status_code=202)
def enqueue_notification(req: NotificationRequest) -> dict[str, str]:
    """알림 전송 작업을 백그라운드 큐에 등록한다."""
    task = send_notification_task.delay(req.channel, req.target, req.message)
    return {"task_id": task.id, "status": "queued"}


# ── 이력 ──────────────────────────────────────────────
@router.get("/history/crawls", response_model=list[CrawlRecordOut])
def list_crawls(db: Session = Depends(get_db)) -> list[CrawlRecord]:
    stmt = select(CrawlRecord).order_by(CrawlRecord.created_at.desc()).limit(50)
    return list(db.scalars(stmt))


@router.get("/history/notifications", response_model=list[NotificationLogOut])
def list_notifications(db: Session = Depends(get_db)) -> list[NotificationLog]:
    stmt = select(NotificationLog).order_by(NotificationLog.created_at.desc()).limit(50)
    return list(db.scalars(stmt))


# ── 보안뉴스 (데일리시큐 긴급속보) ────────────────────
def _query_security_news(db: Session, today_only: bool) -> list[SecurityNews]:
    stmt = select(SecurityNews).order_by(SecurityNews.published_at.desc().nullslast())
    if today_only:
        start = datetime.now(KST).replace(hour=0, minute=0, second=0, microsecond=0)
        stmt = stmt.where(SecurityNews.published_at >= start)
    return list(db.scalars(stmt.limit(100)))


@router.get("/security-news", response_model=list[SecurityNewsOut])
def list_security_news(
    today_only: bool = True,
    auto_refresh: bool = False,
    fallback_recent: bool = False,
    db: Session = Depends(get_db),
) -> list[SecurityNews]:
    """긴급속보 기사 목록. 기본은 오늘자만.

    - auto_refresh=true: 결과가 비어 있으면(수집 전) 데일리시큐에서 즉시 한 번 갱신한
      뒤 다시 조회한다. Celery/Redis 없이도 화면이 채워지도록 한다.
    - fallback_recent=true: 오늘자 기사가 없으면 최신 긴급속보로 대체 조회한다. 최신
      기사가 전날인 경우에도 목록이 비지 않게 한다.
    """
    rows = _query_security_news(db, today_only)
    if auto_refresh and not rows:
        try:
            refresh_security_news(db)
        except Exception:  # noqa: BLE001 - 네트워크 실패 시 빈 목록 반환
            pass
        rows = _query_security_news(db, today_only)
    # 오늘자가 없으면 최신 긴급속보로 대체(요청 시)
    if fallback_recent and today_only and not rows:
        rows = _query_security_news(db, today_only=False)
    return rows


@router.post("/security-news/refresh", response_model=RefreshResult)
def refresh_now(db: Session = Depends(get_db)) -> RefreshResult:
    """긴급속보를 지금 즉시 동기 갱신한다(수동 새로고침 / Celery 없이 사용 가능)."""
    new_items = refresh_security_news(db)
    return RefreshResult(new_count=len(new_items))


# ── 알림 (종 배지) ────────────────────────────────────
@router.get("/alerts/unread-count", response_model=UnreadCount)
def unread_count(db: Session = Depends(get_db)) -> UnreadCount:
    """미확인 알림 수(읽지 않은 긴급속보) — 종 모양 배지에 사용."""
    n = db.scalar(select(func.count()).select_from(SecurityNews).where(~SecurityNews.is_read))
    return UnreadCount(count=n or 0)


@router.get("/alerts", response_model=list[SecurityNewsOut])
def list_alerts(db: Session = Depends(get_db)) -> list[SecurityNews]:
    """최근 알림(긴급속보) 목록 — 종 클릭 시 표시."""
    stmt = select(SecurityNews).order_by(SecurityNews.created_at.desc()).limit(50)
    return list(db.scalars(stmt))


@router.post("/alerts/read", response_model=UnreadCount)
def mark_alerts_read(db: Session = Depends(get_db)) -> UnreadCount:
    """모든 알림을 읽음 처리한다 → 배지 초기화."""
    db.execute(update(SecurityNews).where(~SecurityNews.is_read).values(is_read=True))
    db.commit()
    return UnreadCount(count=0)
