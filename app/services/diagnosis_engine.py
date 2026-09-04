"""6단계 진단 파이프라인 — ①OS 식별 ②진단 항목 수집 ③기준값과 비교 ④양호/취약 판정
⑤증적 저장 ⑥결과 리포트 생성.

이 모듈은 "규칙을 어떻게 실행하는가"만 안다. 규칙의 값(기대값/심각도)은
diagnosis_rules(YAML)에, 값을 어떻게 가져오는가(SSH 명령)는 diagnosis_collectors에,
SSH 연결 자체는 diagnosis_ssh에 있다.

접속 자체 실패는 예외로 올려 호출부(Celery 태스크)가 스캔 전체를 failed로 처리하게
한다. 개별 규칙 처리 중 오류는 여기서 잡아 unknown/info finding으로 격리한다(스캔은
계속 진행).
"""
from dataclasses import dataclass
from typing import Callable

from app.models.diagnosis import DiagnosisTarget
from app.services import diagnosis_ssh as ssh
from app.services.diagnosis_collectors import COLLECTORS, CollectorResult
from app.services.diagnosis_rules import Rule, load_ruleset

PHASE_CONNECTING = "connecting"
PHASE_OS_IDENTIFY = "os_identify"
PHASE_COLLECTING = "collecting"
PHASE_REPORTING = "reporting"
PHASE_DONE = "done"

OnPhase = Callable[[str], None]


@dataclass
class FindingResult:
    rule_id: str
    name: str
    status: str  # pass|fail|unknown
    severity: str  # critical|high|medium|low|info
    detail: str
    evidence: str | None
    recommendation: str | None


@dataclass
class EngineResult:
    os_id: str | None
    os_version: str | None
    ruleset_id: str
    ruleset_name: str
    findings: list[FindingResult]


def _noop_phase(_phase: str) -> None:
    pass


def _identify_os(client) -> tuple[str | None, str | None]:
    _rc, out, _err = ssh.run_command(client, "cat /etc/os-release 2>/dev/null")
    os_id = None
    os_version = None
    for line in out.splitlines():
        if line.startswith("ID="):
            os_id = line.split("=", 1)[1].strip().strip('"').lower()
        elif line.startswith("VERSION_ID="):
            os_version = line.split("=", 1)[1].strip().strip('"')
    return os_id, os_version


def _check_sudo(client) -> bool:
    rc, _out, _err = ssh.run_command(client, "sudo -n true 2>/dev/null")
    return rc == 0


def _collect(client, rule: Rule, sudo_ok: bool) -> CollectorResult:
    collector_id, param = rule.parse_target()
    collector = COLLECTORS.get(collector_id)
    if collector is None:
        return CollectorResult(value=None, evidence=f"알 수 없는 수집기: {collector_id}", not_found=True)
    if rule.needs_sudo and not sudo_ok:
        return CollectorResult(value=None, evidence="sudo 비대화식 권한이 없어 확인할 수 없습니다.", not_found=True)
    run = (lambda c, cmd: ssh.run_command(c, f"sudo -n {cmd}")) if rule.needs_sudo else ssh.run_command
    try:
        return collector(client, param, run=run)
    except Exception as exc:  # noqa: BLE001 - 개별 규칙 실패를 격리해 스캔 전체는 계속되게 한다
        return CollectorResult(value=None, evidence=f"수집 오류: {exc}", not_found=True)


def _compare(raw: CollectorResult, rule: Rule) -> bool:
    """True == 기준을 만족(양호)."""
    if rule.compare == "list_empty":
        return not raw.value
    values = raw.value if isinstance(raw.value, list) else [raw.value]
    if rule.compare == "equals_any":
        return any(v in rule.expected for v in values)
    if rule.compare == "not_equals_any":
        return all(v not in rule.expected for v in values)
    raise ValueError(f"알 수 없는 compare 연산자: {rule.compare}")


def _judge(raw: CollectorResult, rule: Rule) -> tuple[str, str]:
    if raw.not_found:
        return "unknown", "info"
    if raw.value is None:
        if rule.on_missing == "pass":
            return "pass", rule.severity.lower()
        if rule.on_missing == "unknown":
            return "unknown", "info"
        return "fail", rule.severity.lower()
    ok = _compare(raw, rule)
    return ("pass" if ok else "fail"), rule.severity.lower()


def _detail_for(raw: CollectorResult, status: str) -> str:
    if status == "unknown":
        return raw.evidence or "확인할 수 없습니다."
    if isinstance(raw.value, list):
        return ", ".join(raw.value) if raw.value else "(해당 항목 없음)"
    return str(raw.value) if raw.value is not None else "(값 없음)"


def _to_finding(rule: Rule, raw: CollectorResult, status: str, severity: str) -> FindingResult:
    return FindingResult(
        rule_id=rule.rule_id,
        name=rule.name,
        status=status,
        severity=severity,
        detail=_detail_for(raw, status),
        evidence=raw.evidence,
        recommendation=None if status == "pass" else rule.recommendation,
    )


def run_diagnosis(
    db,
    target: DiagnosisTarget,
    secret: str,
    ruleset_id: str,
    on_phase: OnPhase = _noop_phase,
) -> EngineResult:
    on_phase(PHASE_CONNECTING)  # 0. SSH 접속 확인
    try:
        client = ssh.connect(db, target, secret)
    except Exception as exc:
        raise RuntimeError(f"[SSH 접속 확인] {exc}") from exc

    try:
        on_phase(PHASE_OS_IDENTIFY)  # ① OS 식별
        try:
            os_id, os_version = _identify_os(client)
        except Exception as exc:
            raise RuntimeError(f"[OS 식별] {exc}") from exc

        try:
            ruleset = load_ruleset(ruleset_id)
        except Exception as exc:
            raise RuntimeError(f"[진단 기준 로드] {exc}") from exc

        sudo_ok = _check_sudo(client)

        on_phase(PHASE_COLLECTING)  # ②~⑤ 항목별 수집/비교/판정/증적
        findings: list[FindingResult] = []
        if ruleset.os and os_id and os_id not in ruleset.os:
            findings.append(
                FindingResult(
                    rule_id="_os_mismatch",
                    name="OS 불일치",
                    status="unknown",
                    severity="info",
                    detail=(
                        f"이 기준은 {ruleset.os} 대상이지만 식별된 OS는 '{os_id}'입니다. "
                        "결과가 부정확할 수 있습니다."
                    ),
                    evidence=None,
                    recommendation=None,
                )
            )
        for rule in ruleset.rules:
            raw = _collect(client, rule, sudo_ok)  # ② 진단 항목 수집
            status, severity = _judge(raw, rule)  # ③ 기준값과 비교 + ④ 양호/취약 판정
            findings.append(_to_finding(rule, raw, status, severity))  # ⑤ 증적 저장

        on_phase(PHASE_REPORTING)  # ⑥ 결과 리포트 생성
        result = EngineResult(
            os_id=os_id,
            os_version=os_version,
            ruleset_id=ruleset.ruleset_id,
            ruleset_name=ruleset.name,
            findings=findings,
        )
        on_phase(PHASE_DONE)
        return result
    finally:
        client.close()
