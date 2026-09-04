"""백그라운드 태스크 — 크롤링과 알림을 웹 요청과 분리해 실행한다."""
from datetime import datetime, timezone

from app.core.celery_app import celery_app
from app.core.crypto import decrypt_secret
from app.core.database import SessionLocal
from app.models.diagnosis import DiagnosisFinding, DiagnosisScan, DiagnosisTarget
from app.models.history import CrawlRecord, NotificationLog
from app.services.crawler import fetch_page
from app.services.diagnosis_engine import run_diagnosis
from app.services.notifier import send_notification
from app.services.security_news import refresh_security_news


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


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


@celery_app.task(name="app.tasks.jobs.run_diagnosis_scan_task")
def run_diagnosis_scan_task(scan_id: int) -> int:
    """등록된 대상 서버에 SSH로 접속해 6단계 진단 파이프라인을 수행하고 결과를 저장한다.

    scan 행은 API에서 이미 생성돼 있다(폴링 레이스를 피하기 위함) — 여기서는
    상태와 phase만 갱신한다. 접속 자체가 실패하면 scan.status를 failed로 만들고 개별
    finding은 남기지 않는다: 점검을 하나도 수행하지 못했기 때문이다.
    """
    db = SessionLocal()
    scan = db.get(DiagnosisScan, scan_id)
    scan.status = "running"
    scan.started_at = _utcnow()
    db.commit()

    def on_phase(phase: str) -> None:
        scan.phase = phase
        db.commit()

    try:
        target = db.get(DiagnosisTarget, scan.target_id)
        secret = decrypt_secret(target.encrypted_secret)
        result = run_diagnosis(db, target, secret, scan.ruleset_id, on_phase=on_phase)
        scan.os_id = result.os_id
        scan.os_version = result.os_version
        for finding in result.findings:
            db.add(
                DiagnosisFinding(
                    scan_id=scan.id,
                    check_id=finding.rule_id,
                    title=finding.name,
                    severity=finding.severity,
                    status=finding.status,
                    detail=finding.detail,
                    evidence=finding.evidence,
                    recommendation=finding.recommendation,
                )
            )
        for severity in ("critical", "high", "medium", "low", "info"):
            count = sum(1 for f in result.findings if f.severity == severity)
            setattr(scan, f"{severity}_count", count)
        scan.status = "success"
    except Exception as exc:  # noqa: BLE001 - 접속 실패 등은 스캔 전체를 failed로 처리
        scan.status = "failed"
        scan.error = str(exc)
    finally:
        scan.finished_at = _utcnow()
        db.commit()
        db.close()
    return scan_id
