"""알림 전송 로직.

- send_to_type(type, config, message): 특정 채널 타입에 직접 전송
- send_to_all_enabled(message): DB에 저장된 활성화된 모든 대상에 전송
- send_notification(channel, target, message): 기존 호환용 (크롤링/이력 등에서 사용)
"""
import json

import httpx

from app.core.config import settings

_TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


def send_to_type(target_type: str, config: dict, message: str) -> None:
    """config dict를 받아 해당 채널로 전송한다. 실패 시 예외 발생."""
    t = target_type.lower()
    if t == "slack":
        webhook_url = config.get("webhook_url", "")
        if not webhook_url:
            raise ValueError("Slack webhook_url이 설정되지 않았습니다.")
        try:
            resp = httpx.post(webhook_url, json={"text": message}, timeout=10)
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise ValueError(f"Slack API 오류: {exc.response.status_code} {exc.response.text[:200]}") from exc
    elif t == "telegram":
        token = config.get("bot_token", "")
        chat_id = config.get("chat_id", "")
        if not token or not chat_id:
            raise ValueError("Telegram bot_token 또는 chat_id가 설정되지 않았습니다.")
        url = _TELEGRAM_API.format(token=token)
        try:
            resp = httpx.post(url, json={"chat_id": chat_id, "text": message}, timeout=10)
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            try:
                detail = exc.response.json().get("description") or str(exc)
            except Exception:
                detail = str(exc)
            raise ValueError(f"Telegram API 오류: {detail}") from exc
    else:
        raise ValueError(f"지원하지 않는 채널: {target_type}")


def send_to_all_enabled(message: str) -> list[dict]:
    """DB에서 활성화된 모든 알림 대상을 조회하고 순서대로 전송한다.
    결과: [{"id": ..., "name": ..., "ok": bool, "error": str|None}]
    """
    from app.core.crypto import decrypt_secret
    from app.core.database import SessionLocal
    from app.models.notification_target import NotificationTarget
    from sqlalchemy import select

    db = SessionLocal()
    results = []
    try:
        targets = list(db.scalars(select(NotificationTarget).where(NotificationTarget.enabled.is_(True))))
        for t in targets:
            try:
                config = json.loads(decrypt_secret(t.config_encrypted))
                send_to_type(t.type, config, message)
                results.append({"id": t.id, "name": t.name, "ok": True, "error": None})
            except Exception as exc:  # noqa: BLE001
                results.append({"id": t.id, "name": t.name, "ok": False, "error": str(exc)})
    finally:
        db.close()
    return results


def send_telegram(message: str, chat_id: str | None = None) -> None:
    """텔레그램으로 직접 메시지를 전송하는 편의 함수 (단일 설정 기반)."""
    from app.services.app_settings import get_telegram_config
    token, default_chat = get_telegram_config()
    effective_chat = chat_id or default_chat
    if token and effective_chat:
        send_to_type("telegram", {"bot_token": token, "chat_id": effective_chat}, message)
    else:
        print(f"[TELEGRAM:stub] {message}")


def send_notification(channel: str, target: str, message: str) -> None:
    """기존 호환용. 크롤링/이력 등 레거시 코드에서 사용."""
    channel = channel.lower()
    if channel == "slack":
        if settings.slack_webhook_url:
            resp = httpx.post(settings.slack_webhook_url, json={"text": message}, timeout=10)
            resp.raise_for_status()
        else:
            print(f"[SLACK:stub] {target} :: {message}")
    elif channel == "telegram":
        send_telegram(message, target or None)
    elif channel == "email":
        print(f"[EMAIL:stub] to={target} :: {message}")
    else:
        raise ValueError(f"지원하지 않는 채널: {channel}")
