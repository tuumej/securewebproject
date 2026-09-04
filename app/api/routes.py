"""API 엔드포인트 — 크롤링/알림 작업 등록, 이력 조회, 보안뉴스/알림, 진단."""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, selectinload

import json

from app.core.crypto import decrypt_secret, encrypt_secret
from app.core.database import get_db
from app.models.diagnosis import DiagnosisScan, DiagnosisTarget
from app.models.history import CrawlRecord, NotificationLog
from app.models.news import SecurityNews
from app.models.notification_target import NotificationTarget
from app.schemas.diagnosis import (
    ConnectionTestResult,
    DiagnosisScanDetailOut,
    DiagnosisScanOut,
    DiagnosisTargetCreate,
    DiagnosisTargetOut,
    RulesetCreateRequest,
    RulesetDetailOut,
    RulesetOut,
    RulesetUpdateRequest,
    ScanQueuedOut,
    ScanStartRequest,
)
from app.schemas.history import (
    CrawlRecordOut,
    CrawlRequest,
    NotificationLogOut,
    NotificationRequest,
)
from app.schemas.news import RefreshResult, SecurityNewsOut, UnreadCount
from app.services import diagnosis_rules
from app.services.app_settings import get_telegram_config, set_setting
from app.services.notifier import send_telegram, send_to_type
from app.services.diagnosis_rules import RulesetValidationError
from app.services.diagnosis_ssh import test_connection
from app.services.security_news import refresh_security_news
from app.tasks.jobs import crawl_url_task, run_diagnosis_scan_task, send_notification_task

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


@router.get("/security-news/archived", response_model=list[SecurityNewsOut])
def list_archived_news(db: Session = Depends(get_db)) -> list[SecurityNews]:
    """보관된 기사 목록."""
    stmt = select(SecurityNews).where(SecurityNews.is_archived.is_(True)).order_by(SecurityNews.published_at.desc().nullslast())
    return list(db.scalars(stmt))


@router.post("/security-news/{news_id}/archive", response_model=SecurityNewsOut)
def archive_news(news_id: int, db: Session = Depends(get_db)) -> SecurityNews:
    """기사를 보관함에 저장한다."""
    item = db.get(SecurityNews, news_id)
    if item is None:
        raise HTTPException(status_code=404, detail="기사를 찾을 수 없습니다.")
    item.is_archived = True
    db.commit()
    db.refresh(item)
    return item


@router.delete("/security-news/{news_id}/archive", status_code=204)
def unarchive_news(news_id: int, db: Session = Depends(get_db)) -> None:
    """기사를 보관함에서 삭제한다."""
    item = db.get(SecurityNews, news_id)
    if item is None:
        raise HTTPException(status_code=404, detail="기사를 찾을 수 없습니다.")
    item.is_archived = False
    db.commit()


@router.post("/security-news/refresh", response_model=RefreshResult)
def refresh_now(db: Session = Depends(get_db)) -> RefreshResult:
    """긴급속보를 지금 즉시 동기 갱신한다(수동 새로고침 / Celery 없이 사용 가능)."""
    new_items = refresh_security_news(db)
    return RefreshResult(new_count=len(new_items))


@router.get("/settings/telegram")
def get_telegram_settings() -> dict[str, str]:
    """현재 저장된 텔레그램 설정 반환 (토큰은 마스킹)."""
    token, chat_id = get_telegram_config()
    masked = ("*" * (len(token) - 6) + token[-6:]) if len(token) > 6 else ("*" * len(token))
    return {"bot_token_masked": masked if token else "", "chat_id": chat_id, "configured": str(bool(token and chat_id))}


@router.post("/settings/telegram")
def save_telegram_settings(body: dict, db: Session = Depends(get_db)) -> dict[str, str]:
    """텔레그램 Bot Token과 Chat ID를 DB에 저장한다."""
    token = (body.get("bot_token") or "").strip()
    chat_id = (body.get("chat_id") or "").strip()
    if token:
        set_setting(db, "telegram_bot_token", token)
    if chat_id:
        set_setting(db, "telegram_chat_id", chat_id)
    return {"status": "saved"}


@router.post("/notifications/telegram/test")
def test_telegram_notification() -> dict[str, str]:
    """텔레그램 알림 테스트 메시지를 전송한다."""
    try:
        send_telegram("[securewebproject] 텔레그램 알림 연동 테스트 메시지입니다.")
        return {"status": "ok"}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


# ── 알림 대상 관리 (다중 채널 목록) ──────────────────────
@router.get("/settings/notifications")
def list_notification_targets(db: Session = Depends(get_db)) -> list[dict]:
    """등록된 알림 대상 목록 반환 (config는 복호화 후 일부만 노출)."""
    targets = list(db.scalars(select(NotificationTarget).order_by(NotificationTarget.created_at)))
    result = []
    for t in targets:
        try:
            cfg = json.loads(decrypt_secret(t.config_encrypted))
        except Exception:
            cfg = {}
        masked: dict = {}
        if t.type == "slack":
            url = cfg.get("webhook_url", "")
            masked["webhook_url_masked"] = url[:30] + "..." if len(url) > 30 else url
        elif t.type == "telegram":
            token = cfg.get("bot_token", "")
            masked["bot_token_masked"] = ("*" * (len(token) - 6) + token[-6:]) if len(token) > 6 else "*" * len(token)
            masked["chat_id"] = cfg.get("chat_id", "")
        result.append({
            "id": t.id,
            "type": t.type,
            "name": t.name,
            "enabled": t.enabled,
            "created_at": t.created_at.isoformat(),
            **masked,
        })
    return result


@router.post("/settings/notifications", status_code=201)
def create_notification_target(body: dict, db: Session = Depends(get_db)) -> dict:
    """새 알림 대상을 등록한다."""
    target_type = (body.get("type") or "").lower()
    name = (body.get("name") or "").strip()
    if target_type not in ("slack", "telegram"):
        raise HTTPException(status_code=422, detail="type은 'slack' 또는 'telegram'이어야 합니다.")
    if not name:
        raise HTTPException(status_code=422, detail="name은 필수입니다.")

    cfg: dict = {}
    if target_type == "slack":
        webhook_url = (body.get("webhook_url") or "").strip()
        if not webhook_url:
            raise HTTPException(status_code=422, detail="Slack webhook_url이 필요합니다.")
        cfg = {"webhook_url": webhook_url}
    elif target_type == "telegram":
        bot_token = (body.get("bot_token") or "").strip()
        chat_id = (body.get("chat_id") or "").strip()
        if not bot_token or not chat_id:
            raise HTTPException(status_code=422, detail="Telegram bot_token과 chat_id가 필요합니다.")
        cfg = {"bot_token": bot_token, "chat_id": chat_id}

    nt = NotificationTarget(
        type=target_type,
        name=name,
        config_encrypted=encrypt_secret(json.dumps(cfg)),
        enabled=True,
    )
    db.add(nt)
    db.commit()
    db.refresh(nt)
    return {"id": nt.id, "type": nt.type, "name": nt.name, "enabled": nt.enabled}


@router.patch("/settings/notifications/{target_id}")
def toggle_notification_target(target_id: int, body: dict, db: Session = Depends(get_db)) -> dict:
    """알림 대상 활성/비활성 토글 (또는 name 변경)."""
    nt = db.get(NotificationTarget, target_id)
    if nt is None:
        raise HTTPException(status_code=404, detail="알림 대상을 찾을 수 없습니다.")
    if "enabled" in body:
        nt.enabled = bool(body["enabled"])
    if "name" in body and body["name"]:
        nt.name = str(body["name"]).strip()
    db.commit()
    return {"id": nt.id, "enabled": nt.enabled, "name": nt.name}


@router.delete("/settings/notifications/{target_id}", status_code=204)
def delete_notification_target(target_id: int, db: Session = Depends(get_db)) -> None:
    """알림 대상을 삭제한다."""
    nt = db.get(NotificationTarget, target_id)
    if nt is None:
        raise HTTPException(status_code=404, detail="알림 대상을 찾을 수 없습니다.")
    db.delete(nt)
    db.commit()


@router.post("/settings/notifications/{target_id}/test")
def test_notification_target(target_id: int, db: Session = Depends(get_db)) -> dict:
    """특정 알림 대상으로 테스트 메시지를 전송한다."""
    nt = db.get(NotificationTarget, target_id)
    if nt is None:
        raise HTTPException(status_code=404, detail="알림 대상을 찾을 수 없습니다.")
    try:
        cfg = json.loads(decrypt_secret(nt.config_encrypted))
        send_to_type(nt.type, cfg, "[securewebproject] 알림 연동 테스트 메시지입니다.")
        return {"status": "ok"}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


# ── 알림 (종 배지) ────────────────────────────────────
@router.get("/alerts/unread-count", response_model=UnreadCount)
def unread_count(db: Session = Depends(get_db)) -> UnreadCount:
    """미확인 알림 수(읽지 않은 긴급속보) — 종 모양 배지에 사용."""
    n = db.scalar(select(func.count()).select_from(SecurityNews).where(~SecurityNews.is_read))
    return UnreadCount(count=n or 0)


@router.get("/alerts", response_model=list[SecurityNewsOut])
def list_alerts(db: Session = Depends(get_db)) -> list[SecurityNews]:
    """미확인 알림 목록 — is_read=False인 것만 반환."""
    stmt = select(SecurityNews).where(~SecurityNews.is_read).order_by(SecurityNews.published_at.desc().nullslast()).limit(50)
    return list(db.scalars(stmt))


@router.post("/alerts/{news_id}/read", response_model=UnreadCount)
def mark_alert_read(news_id: int, db: Session = Depends(get_db)) -> UnreadCount:
    """단건 알림을 읽음 처리한다."""
    db.execute(update(SecurityNews).where(SecurityNews.id == news_id).values(is_read=True))
    db.commit()
    n = db.scalar(select(func.count()).select_from(SecurityNews).where(~SecurityNews.is_read))
    return UnreadCount(count=n or 0)


@router.post("/alerts/read", response_model=UnreadCount)
def mark_alerts_read(db: Session = Depends(get_db)) -> UnreadCount:
    """모든 알림을 읽음 처리한다 → 배지 초기화."""
    db.execute(update(SecurityNews).where(~SecurityNews.is_read).values(is_read=True))
    db.commit()
    return UnreadCount(count=0)


@router.delete("/alerts/read", status_code=204)
def delete_read_alerts(db: Session = Depends(get_db)) -> None:
    """읽은 알림(is_read=True)을 DB에서 삭제한다. 보관된 기사는 유지."""
    db.execute(
        SecurityNews.__table__.delete().where(
            (SecurityNews.is_read == True) & (SecurityNews.is_archived == False)  # noqa: E712
        )
    )
    db.commit()


# ── 진단 (Diagnosis) ──────────────────────────────────
def _scan_out(scan: DiagnosisScan, target_name: str) -> DiagnosisScanOut:
    return DiagnosisScanOut(
        id=scan.id,
        target_id=scan.target_id,
        target_name=target_name,
        status=scan.status,
        ruleset_id=scan.ruleset_id,
        os_id=scan.os_id,
        os_version=scan.os_version,
        phase=scan.phase,
        critical_count=scan.critical_count,
        high_count=scan.high_count,
        medium_count=scan.medium_count,
        low_count=scan.low_count,
        info_count=scan.info_count,
        error=scan.error,
        created_at=scan.created_at,
        started_at=scan.started_at,
        finished_at=scan.finished_at,
    )


@router.post("/diagnosis/targets", response_model=DiagnosisTargetOut, status_code=201)
def create_diagnosis_target(req: DiagnosisTargetCreate, db: Session = Depends(get_db)) -> DiagnosisTarget:
    """진단 대상 서버를 등록한다. 비밀번호/개인키는 암호화해 저장하고 응답에는 포함하지 않는다."""
    target = DiagnosisTarget(
        name=req.name,
        host=req.host,
        port=req.port,
        username=req.username,
        auth_type=req.auth_type,
        encrypted_secret=encrypt_secret(req.secret),
    )
    db.add(target)
    db.commit()
    db.refresh(target)
    return target


@router.get("/diagnosis/targets", response_model=list[DiagnosisTargetOut])
def list_diagnosis_targets(db: Session = Depends(get_db)) -> list[DiagnosisTarget]:
    stmt = select(DiagnosisTarget).order_by(DiagnosisTarget.created_at.desc())
    return list(db.scalars(stmt))


@router.delete("/diagnosis/targets/{target_id}", status_code=204)
def delete_diagnosis_target(target_id: int, db: Session = Depends(get_db)) -> None:
    target = db.get(DiagnosisTarget, target_id)
    if target is None:
        raise HTTPException(status_code=404, detail="대상을 찾을 수 없습니다.")
    db.delete(target)
    db.commit()


@router.post("/diagnosis/targets/{target_id}/test-connection", response_model=ConnectionTestResult)
def test_diagnosis_connection(target_id: int, db: Session = Depends(get_db)) -> ConnectionTestResult:
    """SSH 접속만 시도하고 즉시 닫는다(점검 실행 없음). 진단 시작 전 자격증명/도달성 확인용."""
    target = db.get(DiagnosisTarget, target_id)
    if target is None:
        raise HTTPException(status_code=404, detail="대상을 찾을 수 없습니다.")
    secret = decrypt_secret(target.encrypted_secret)
    ok, message = test_connection(db, target, secret)
    return ConnectionTestResult(ok=ok, message=message)


@router.post("/diagnosis/targets/{target_id}/scan", response_model=ScanQueuedOut, status_code=202)
def start_diagnosis_scan(
    target_id: int, req: ScanStartRequest, db: Session = Depends(get_db)
) -> ScanQueuedOut:
    """진단 스캔 행을 즉시 생성한 뒤 Celery 큐에 등록한다. 적용할 진단 기준(ruleset)은
    실행마다 선택한다.

    스캔 행을 태스크 내부가 아니라 여기서 먼저 만드는 이유: UI가 응답을 받는 즉시
    /api/diagnosis/scans/{scan_id} 폴링을 시작해도 404가 나지 않게 하기 위함이다.
    """
    target = db.get(DiagnosisTarget, target_id)
    if target is None:
        raise HTTPException(status_code=404, detail="대상을 찾을 수 없습니다.")
    try:
        diagnosis_rules.load_ruleset(req.ruleset_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    scan = DiagnosisScan(target_id=target.id, status="pending", ruleset_id=req.ruleset_id)
    db.add(scan)
    db.commit()
    db.refresh(scan)
    try:
        task = run_diagnosis_scan_task.delay(scan.id)
    except Exception as exc:  # noqa: BLE001 - 브로커(Redis) 연결 실패 등, "pending"에 영원히 멈추지 않게 한다
        scan.status = "failed"
        scan.error = f"작업 큐 등록 실패: {exc}"
        scan.finished_at = datetime.now(timezone.utc)
        db.commit()
        raise HTTPException(
            status_code=503,
            detail="진단 작업을 큐에 등록하지 못했습니다(Redis/Celery 워커 연결 실패). 워커가 실행 중인지 확인하세요.",
        ) from exc
    return ScanQueuedOut(scan_id=scan.id, task_id=task.id, status=scan.status)


@router.get("/diagnosis/scans", response_model=list[DiagnosisScanOut])
def list_diagnosis_scans(db: Session = Depends(get_db)) -> list[DiagnosisScanOut]:
    stmt = (
        select(DiagnosisScan)
        .options(selectinload(DiagnosisScan.target))
        .order_by(DiagnosisScan.created_at.desc())
        .limit(50)
    )
    scans = list(db.scalars(stmt))
    return [_scan_out(scan, scan.target.name) for scan in scans]


@router.get("/diagnosis/scans/{scan_id}", response_model=DiagnosisScanDetailOut)
def get_diagnosis_scan(scan_id: int, db: Session = Depends(get_db)) -> DiagnosisScanDetailOut:
    stmt = (
        select(DiagnosisScan)
        .options(selectinload(DiagnosisScan.target), selectinload(DiagnosisScan.findings))
        .where(DiagnosisScan.id == scan_id)
    )
    scan = db.scalars(stmt).first()
    if scan is None:
        raise HTTPException(status_code=404, detail="스캔을 찾을 수 없습니다.")
    base = _scan_out(scan, scan.target.name)
    return DiagnosisScanDetailOut(**base.model_dump(), findings=list(scan.findings))


@router.get("/diagnosis/scans/{scan_id}/report")
def download_diagnosis_report(scan_id: int, db: Session = Depends(get_db)) -> Response:
    """스캔 결과를 텍스트 리포트 파일로 다운로드한다(⑥ 결과 리포트 생성)."""
    stmt = (
        select(DiagnosisScan)
        .options(selectinload(DiagnosisScan.target), selectinload(DiagnosisScan.findings))
        .where(DiagnosisScan.id == scan_id)
    )
    scan = db.scalars(stmt).first()
    if scan is None:
        raise HTTPException(status_code=404, detail="스캔을 찾을 수 없습니다.")

    lines = [
        f"진단 리포트 - 대상: {scan.target.name} ({scan.target.host})",
        f"기준(ruleset): {scan.ruleset_id}",
        f"OS: {scan.os_id or '(확인불가)'} {scan.os_version or ''}".strip(),
        f"상태: {scan.status}",
        f"실행: {scan.started_at} ~ {scan.finished_at}",
        f"요약: CRITICAL {scan.critical_count} / HIGH {scan.high_count} / "
        f"MEDIUM {scan.medium_count} / LOW {scan.low_count} / INFO {scan.info_count}",
        "",
        "항목별 결과",
        "-" * 60,
    ]
    for finding in scan.findings:
        lines.append(f"[{finding.check_id}] {finding.title}")
        lines.append(f"  상태: {finding.status} / 심각도: {finding.severity}")
        lines.append(f"  상세: {finding.detail}")
        if finding.recommendation:
            lines.append(f"  권고: {finding.recommendation}")
        lines.append("")

    body = "\n".join(lines)
    return Response(
        content=body,
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="diagnosis-report-{scan_id}.txt"'},
    )


# ── 진단 기준(Ruleset) 편집 ───────────────────────────
@router.get("/diagnosis/rulesets", response_model=list[RulesetOut])
def list_rulesets() -> list[RulesetOut]:
    rulesets = diagnosis_rules.list_rulesets()
    return [
        RulesetOut(
            id=rs.ruleset_id, name=rs.name, description=rs.description, os=rs.os,
            rule_count=len(rs.rules),
        )
        for rs in rulesets
    ]


@router.get("/diagnosis/rulesets/{ruleset_id}", response_model=RulesetDetailOut)
def get_ruleset(ruleset_id: str) -> RulesetDetailOut:
    try:
        rs = diagnosis_rules.load_ruleset(ruleset_id)
        yaml_text = diagnosis_rules.read_ruleset_yaml(ruleset_id)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return RulesetDetailOut(
        id=rs.ruleset_id, name=rs.name, description=rs.description, os=rs.os,
        rule_count=len(rs.rules), yaml_text=yaml_text,
    )


@router.post("/diagnosis/rulesets", response_model=RulesetDetailOut, status_code=201)
def create_ruleset(req: RulesetCreateRequest) -> RulesetDetailOut:
    try:
        rs = diagnosis_rules.create_ruleset(req.id, req.name, req.description)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    yaml_text = diagnosis_rules.read_ruleset_yaml(rs.ruleset_id)
    return RulesetDetailOut(
        id=rs.ruleset_id, name=rs.name, description=rs.description, os=rs.os,
        rule_count=len(rs.rules), yaml_text=yaml_text,
    )


@router.put("/diagnosis/rulesets/{ruleset_id}", response_model=RulesetDetailOut)
def update_ruleset(ruleset_id: str, req: RulesetUpdateRequest) -> RulesetDetailOut:
    try:
        rs = diagnosis_rules.save_ruleset_yaml(ruleset_id, req.yaml_text)
    except RulesetValidationError as exc:
        raise HTTPException(status_code=422, detail={"errors": exc.errors}) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={"errors": [str(exc)]}) from exc
    yaml_text = diagnosis_rules.read_ruleset_yaml(ruleset_id)
    return RulesetDetailOut(
        id=rs.ruleset_id, name=rs.name, description=rs.description, os=rs.os,
        rule_count=len(rs.rules), yaml_text=yaml_text,
    )


@router.delete("/diagnosis/rulesets/{ruleset_id}", status_code=204)
def delete_ruleset(ruleset_id: str) -> None:
    diagnosis_rules.delete_ruleset(ruleset_id)
