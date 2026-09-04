"""진단(Diagnosis) API 입출력 스키마."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class DiagnosisTargetCreate(BaseModel):
    name: str
    host: str
    port: int = 22
    username: str
    auth_type: Literal["password", "private_key"]
    secret: str  # 비밀번호 또는 개인키 원문(패스프레이즈 없음) — 저장 시 암호화, 응답에는 포함하지 않음


class DiagnosisTargetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    host: str
    port: int
    username: str
    auth_type: str
    created_at: datetime


class ConnectionTestResult(BaseModel):
    ok: bool
    message: str


class ScanStartRequest(BaseModel):
    ruleset_id: str


class DiagnosisFindingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    check_id: str
    title: str
    severity: str
    status: str
    detail: str
    evidence: str | None = None
    recommendation: str | None = None


class DiagnosisScanOut(BaseModel):
    id: int
    target_id: int
    target_name: str
    status: str
    ruleset_id: str
    os_id: str | None = None
    os_version: str | None = None
    phase: str | None = None
    critical_count: int
    high_count: int
    medium_count: int
    low_count: int
    info_count: int
    error: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None


class DiagnosisScanDetailOut(DiagnosisScanOut):
    findings: list[DiagnosisFindingOut] = []


class ScanQueuedOut(BaseModel):
    scan_id: int
    task_id: str
    status: str


class RulesetOut(BaseModel):
    id: str
    name: str
    description: str
    os: list[str]
    rule_count: int


class RulesetDetailOut(RulesetOut):
    yaml_text: str


class RulesetCreateRequest(BaseModel):
    id: str
    name: str
    description: str = ""


class RulesetUpdateRequest(BaseModel):
    yaml_text: str


class RulesetValidationErrorOut(BaseModel):
    errors: list[str]
