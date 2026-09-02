"""이력관리 모델 — 크롤링 결과와 알림 발송 기록을 저장한다."""
from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class CrawlRecord(Base):
    """크롤링 실행 및 결과 이력."""

    __tablename__ = "crawl_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    url: Mapped[str] = mapped_column(String(2048), index=True)
    status: Mapped[str] = mapped_column(String(32), default="pending")  # pending|success|failed
    title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class NotificationLog(Base):
    """알림 전송 이력."""

    __tablename__ = "notification_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    channel: Mapped[str] = mapped_column(String(32))  # email|slack|...
    target: Mapped[str] = mapped_column(String(512))
    message: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="pending")  # pending|sent|failed
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
