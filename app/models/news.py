"""보안뉴스 모델 — 데일리시큐/보안뉴스/KCERT 기사를 저장한다."""
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SecurityNews(Base):
    """보안 기사. (source, idxno) 조합으로 중복을 판별하고, is_read로 종 배지를 계산한다.

    여러 출처(데일리시큐 긴급속보 · 보안뉴스 사건사고 · KCERT 보안공지)를 저장하므로
    사이트별로 idxno가 겹칠 수 있어 source와의 복합 유니크로 중복을 관리한다.
    """

    __tablename__ = "security_news"
    __table_args__ = (UniqueConstraint("source", "idxno", name="uq_source_idxno"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(32), index=True, default="dailysecu")
    idxno: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(512))
    url: Mapped[str] = mapped_column(String(2048))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
