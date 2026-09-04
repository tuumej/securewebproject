"""수집기(collector) — 대상 서버에서 원시 데이터를 "어떻게" 가져오는지만 담당한다.

불변식: 모든 명령은 읽기 전용(조회)이다. 수집기를 추가할 때도 이 원칙을 지켜야 한다.
"무엇을 기대하는가/심각도"는 여기 없다 — 그건 YAML 규칙(app/services/diagnosis_rules.py)의
몫이다. 각 함수는 `run` 콜러블을 주입받을 수 있어 실제 SSH 없이도 단위 테스트가 가능하다
(app.services.diagnosis_ssh.run_command 와 동일한 시그니처: (client, command) -> (rc, out, err)).
"""
from dataclasses import dataclass
from typing import Callable

from app.services import diagnosis_ssh as ssh

RunCommand = Callable[[object, str], tuple[int, str, str]]

_EVIDENCE_LIMIT = 4000


@dataclass
class CollectorResult:
    value: str | list[str] | None
    evidence: str
    not_found: bool = False


def _truncate(text: str) -> str:
    text = text.strip() or "(빈 결과)"
    return text if len(text) <= _EVIDENCE_LIMIT else text[:_EVIDENCE_LIMIT] + "\n... (생략)"


def _strip_grep_prefix(line: str) -> str:
    """여러 파일을 대상으로 grep한 결과는 'path:content' 형태다 — 경로 접두어를 제거한다."""
    if line.startswith("/") and ":" in line:
        return line.split(":", 1)[1]
    return line


def sshd_config_value(client, param: str, *, run: RunCommand = ssh.run_command) -> CollectorResult:
    """param: sshd_config 키 이름 (예: PermitRootLogin)."""
    key = param.strip()
    cmd = f"grep -Ei '^\\s*{key}' /etc/ssh/sshd_config /etc/ssh/sshd_config.d/*.conf 2>/dev/null"
    _rc, out, _err = run(client, cmd)
    for raw in out.splitlines():
        line = _strip_grep_prefix(raw).strip()
        parts = line.split(None, 1)
        if len(parts) == 2 and parts[0].lower() == key.lower():
            return CollectorResult(value=parts[1].strip(), evidence=_truncate(out))
    return CollectorResult(value=None, evidence=_truncate(out))


def systemd_service_active(client, param: str, *, run: RunCommand = ssh.run_command) -> CollectorResult:
    """param: systemd 서비스명 (예: fail2ban, apparmor)."""
    service = param.strip()
    _rc, out, err = run(client, f"systemctl is-active {service} 2>&1")
    combined = out.strip() or err.strip()
    lowered = combined.lower()
    not_found = "could not be found" in lowered
    value = combined.splitlines()[0].strip().lower() if combined else None
    return CollectorResult(value=value, evidence=_truncate(combined), not_found=not_found)


def command_value(client, param: str, *, run: RunCommand = ssh.run_command) -> CollectorResult:
    """param: 실행할 셸 명령. 출력 전체를 trim한 단일 문자열 값으로 취급한다."""
    rc, out, err = run(client, param)
    not_found = rc == 127 or "command not found" in err.lower()
    value = out.strip() or None
    evidence = out.strip() + (("\n" + err.strip()) if err.strip() else "")
    return CollectorResult(value=value, evidence=_truncate(evidence), not_found=not_found)


def command_list_lines(client, param: str, *, run: RunCommand = ssh.run_command) -> CollectorResult:
    """param: 실행할 셸 명령. 결과의 비어있지 않은 각 줄을 위반 항목 리스트로 취급한다."""
    rc, out, err = run(client, param)
    lines = [line.strip() for line in out.splitlines() if line.strip()]
    not_found = rc == 127 or "command not found" in err.lower()
    evidence = "\n".join(lines) or err.strip()
    return CollectorResult(value=lines, evidence=_truncate(evidence), not_found=not_found)


_RISKY_PORTS = {
    "21": "FTP",
    "23": "Telnet",
    "69": "TFTP",
    "161": "SNMP",
    "512": "rexec",
    "513": "rlogin",
    "514": "rsh",
}


def risky_ports(client, param: str = "", *, run: RunCommand = ssh.run_command) -> CollectorResult:
    """param은 사용하지 않는다. ss -tuln 결과에서 위험 서비스 포트 노출 여부를 확인한다."""
    _rc, out, _err = run(client, "ss -tuln")
    found: list[str] = []
    for line in out.splitlines():
        for port, name in _RISKY_PORTS.items():
            if f":{port} " in line or line.rstrip().endswith(f":{port}"):
                tag = f"{name}({port})"
                if tag not in found:
                    found.append(tag)
    return CollectorResult(value=sorted(found), evidence=_truncate(out))


COLLECTORS: dict[str, Callable[..., CollectorResult]] = {
    "sshd_config_value": sshd_config_value,
    "systemd_service_active": systemd_service_active,
    "command_value": command_value,
    "command_list_lines": command_list_lines,
    "risky_ports": risky_ports,
}
