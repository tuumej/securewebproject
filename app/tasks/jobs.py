"""백그라운드 태스크 — 크롤링과 알림을 웹 요청과 분리해 실행한다."""
from app.core.celery_app import celery_app
from app.core.database import SessionLocal
from app.models.history import CrawlRecord, NotificationLog
from app.services.crawler import fetch_page
from app.services.notifier import send_notification
from app.services.security_news import refresh_security_news


@celery_app.task(name="app.tasks.jobs.crawl_url_task")
def crawl_url_task(url: str) -> int:
    """URL을 크롤링하고 결과를 이력에 저장한다. 저장된 레코드 id 반환."""
    db = SessionLocal()
    record = CrawlRecord(url=url, status="pending")
    db.add(record)
    db.commit()
    db.refresh(record)
    try:
        result = fetch_page(url)
        record.title = result["title"]
        record.content = result["content"]
        record.status = "success"
    except Exception as exc:  # noqa: BLE001 - 이력에 실패 사유를 남긴다
        record.status = "failed"
        record.error = str(exc)
    finally:
        db.commit()
        record_id = record.id
        db.close()
    return record_id


@celery_app.task(name="app.tasks.jobs.send_notification_task")
def send_notification_task(channel: str, target: str, message: str) -> int:
    """알림을 전송하고 발송 이력을 저장한다. 저장된 레코드 id 반환."""
    db = SessionLocal()
    log = NotificationLog(channel=channel, target=target, message=message, status="pending")
    db.add(log)
    db.commit()
    db.refresh(log)
    try:
        send_notification(channel, target, message)
        log.status = "sent"
    except Exception as exc:  # noqa: BLE001
        log.status = "failed"
    finally:
        db.commit()
        log_id = log.id
        db.close()
    return log_id


@celery_app.task(name="app.tasks.jobs.fetch_security_news_task")
def fetch_security_news_task() -> int:
    """긴급속보를 갱신한다(1시간 주기). 새로 추가된 기사 수를 반환한다."""
    db = SessionLocal()
    try:
        new_items = refresh_security_news(db)
        return len(new_items)
    finally:
        db.close()
