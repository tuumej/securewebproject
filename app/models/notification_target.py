"""알림 대상 모델 — Slack/Telegram 등 여러 채널을 목록으로 관리한다."""
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class NotificationTarget(Base):
    __tablename__ = "notification_targets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    type: Mapped[str] = mapped_column(String(32))        # "slack" | "telegram"
    name: Mapped[str] = mapped_column(String(128))       # 사용자 지정 레이블
    config_encrypted: Mapped[str] = mapped_column(Text)  # JSON 암호화 저장
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
