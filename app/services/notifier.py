"""알림 전송 로직.

Slack은 Incoming Webhook(SLACK_WEBHOOK_URL)이 설정돼 있으면 실제 전송하고,
없으면 콘솔 출력 스텁으로 동작한다. 이메일은 스텁이다.
"""
import httpx

from app.core.config import settings


def send_notification(channel: str, target: str, message: str) -> None:
    """지정한 채널로 알림을 전송한다. 실패 시 예외를 올려 호출부가 이력에 기록하게 한다."""
    channel = channel.lower()
    if channel == "slack":
        if settings.slack_webhook_url:
            resp = httpx.post(
                settings.slack_webhook_url, json={"text": message}, timeout=10
            )
            resp.raise_for_status()
        else:
            print(f"[SLACK:stub] {target} :: {message}")
    elif channel == "email":
        # TODO: smtplib 또는 이메일 서비스로 전송
        print(f"[EMAIL:stub] to={target} :: {message}")
    else:
        raise ValueError(f"지원하지 않는 채널: {channel}")
