"""진단(Diagnosis) 모델 — 등록된 대상 서버, 진단 실행, 개별 점검 결과."""
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class DiagnosisTarget(Base):
    """진단 대상으로 등록된 서버. 자격증명은 암호화해 저장한다."""

    __tablename__ = "diagnosis_targets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    host: Mapped[str] = mapped_column(String(255))
    port: Mapped[int] = mapped_column(Integer, default=22)
    username: Mapped[str] = mapped_column(String(128))
    auth_type: Mapped[str] = mapped_column(String(16))  # password|private_key
    encrypted_secret: Mapped[str] = mapped_column(Text)
    # TOFU: 최초 접속 시 저장한 호스트키 지문. 이후 접속에서 값이 달라지면 접속 거부.
    host_key_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    scans: Mapped[list["DiagnosisScan"]] = relationship(
        back_populates="target", cascade="all, delete-orphan"
    )


class DiagnosisScan(Base):
    """대상 서버 1회 진단 실행 기록."""

    __tablename__ = "diagnosis_scans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    target_id: Mapped[int] = mapped_column(
        ForeignKey("diagnosis_targets.id", ondelete="CASCADE")
    )
    status: Mapped[str] = mapped_column(String(32), default="pending")  # pending|running|success|failed
    ruleset_id: Mapped[str] = mapped_column(String(64), default="")
    os_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    os_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # 폴링 중 진행 상황 표시용: connecting|os_identify|collecting|reporting|done
    phase: Mapped[str | None] = mapped_column(String(32), nullable=True)
    critical_count: Mapped[int] = mapped_column(Integer, default=0)
    high_count: Mapped[int] = mapped_column(Integer, default=0)
    medium_count: Mapped[int] = mapped_column(Integer, default=0)
    low_count: Mapped[int] = mapped_column(Integer, default=0)
    info_count: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    target: Mapped["DiagnosisTarget"] = relationship(back_populates="scans")
    findings: Mapped[list["DiagnosisFinding"]] = relationship(
        back_populates="scan", cascade="all, delete-orphan"
    )


class DiagnosisFinding(Base):
    """진단 실행 중 개별 점검 항목의 결과."""

    __tablename__ = "diagnosis_findings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    scan_id: Mapped[int] = mapped_column(ForeignKey("diagnosis_scans.id", ondelete="CASCADE"))
    check_id: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(255))
    severity: Mapped[str] = mapped_column(String(16))  # critical|high|medium|low|info
    status: Mapped[str] = mapped_column(String(16))  # pass|fail|unknown
    detail: Mapped[str] = mapped_column(Text)
    evidence: Mapped[str | None] = mapped_column(Text, nullable=True)  # 수집기 원시 출력(⑤ 증적 저장)
    recommendation: Mapped[str | None] = mapped_column(Text, nullable=True)

    scan: Mapped["DiagnosisScan"] = relationship(back_populates="findings")
