"""SSH 접속 계층 — TOFU 호스트키 고정, 접속/명령 실행/접속 테스트.

불변식: 이 모듈이 대상 서버에서 실행하는 것은 명령 실행뿐이며, 어떤 명령을 실행할지는
호출부(수집기/엔진)가 결정한다. 이 모듈 자체는 상태를 변경하는 동작을 하지 않는다.
"""
import hashlib
import io

import paramiko
from sqlalchemy.orm import Session

from app.models.diagnosis import DiagnosisTarget


class TofuHostKeyPolicy(paramiko.MissingHostKeyPolicy):
    """최초 접속 시 호스트키 지문을 저장하고, 이후 접속마다 비교한다(TOFU).

    지문이 달라지면 접속을 거부한다 — 대상 서버가 교체되었거나 MITM 가능성이 있다.
    """

    def __init__(self, target: DiagnosisTarget, db: Session):
        self.target = target
        self.db = db

    def missing_host_key(self, client, hostname, key):
        fingerprint = hashlib.sha256(key.asbytes()).hexdigest()
        if self.target.host_key_fingerprint is None:
            self.target.host_key_fingerprint = fingerprint
            self.db.commit()
        elif self.target.host_key_fingerprint != fingerprint:
            raise paramiko.SSHException(
                "호스트 키 변경이 감지되었습니다(MITM 가능성). 대상 서버 정보를 확인 후 재등록하세요."
            )


def _load_private_key(secret: str) -> paramiko.PKey:
    """패스프레이즈 없는 개인키만 지원한다. Ed25519/ECDSA/RSA 순으로 시도한다."""
    last_exc: Exception | None = None
    for key_cls in (paramiko.Ed25519Key, paramiko.ECDSAKey, paramiko.RSAKey):
        try:
            return key_cls.from_private_key(io.StringIO(secret))
        except paramiko.SSHException as exc:
            last_exc = exc
            continue
    raise ValueError("지원하지 않는 개인키 형식입니다(패스프레이즈 없는 키만 지원).") from last_exc


def connect(db: Session, target: DiagnosisTarget, secret: str) -> paramiko.SSHClient:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(TofuHostKeyPolicy(target, db))
    common = dict(
        hostname=target.host,
        port=target.port,
        username=target.username,
        timeout=10,
        banner_timeout=10,
        auth_timeout=10,
        look_for_keys=False,
        allow_agent=False,
    )
    if target.auth_type == "password":
        client.connect(password=secret, **common)
    else:
        client.connect(pkey=_load_private_key(secret), **common)
    return client


def run_command(client: paramiko.SSHClient, command: str, timeout: int = 15) -> tuple[int, str, str]:
    _stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    rc = stdout.channel.recv_exit_status()
    return rc, out, err


def test_connection(db: Session, target: DiagnosisTarget, secret: str) -> tuple[bool, str]:
    """접속만 시도하고 즉시 닫는다(점검 실행 없음). 진단 시작 전 자격증명/도달성 확인용."""
    try:
        client = connect(db, target, secret)
    except Exception as exc:  # noqa: BLE001 - 인증/네트워크/호스트키 오류를 사용자 메시지로 변환
        return False, f"접속 실패: {exc}"
    else:
        client.close()
        return True, "접속에 성공했습니다."
