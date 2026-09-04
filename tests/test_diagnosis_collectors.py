"""수집기(collector) 단위 테스트 — 실제 SSH 없이 가짜 명령 실행기를 주입한다."""
from app.services.diagnosis_collectors import (
    command_list_lines,
    command_value,
    risky_ports,
    sshd_config_value,
    systemd_service_active,
)


def _fake_run(rc: int, out: str, err: str = ""):
    def run(_client, _command):
        return rc, out, err
    return run


def test_sshd_config_value_found() -> None:
    out = "/etc/ssh/sshd_config:PermitRootLogin no\n"
    result = sshd_config_value(None, "PermitRootLogin", run=_fake_run(0, out))
    assert result.value == "no"
    assert not result.not_found


def test_sshd_config_value_missing() -> None:
    result = sshd_config_value(None, "PermitRootLogin", run=_fake_run(0, ""))
    assert result.value is None
    assert not result.not_found


def test_systemd_service_active() -> None:
    result = systemd_service_active(None, "fail2ban", run=_fake_run(0, "active\n"))
    assert result.value == "active"


def test_systemd_service_not_found() -> None:
    err = "Unit foo.service could not be found.\n"
    result = systemd_service_active(None, "foo", run=_fake_run(4, "", err))
    assert result.not_found


def test_command_value_trims_output() -> None:
    result = command_value(None, "echo hi", run=_fake_run(0, "hi\n"))
    assert result.value == "hi"


def test_command_value_not_found() -> None:
    result = command_value(None, "nosuchcmd", run=_fake_run(127, "", "bash: nosuchcmd: command not found\n"))
    assert result.not_found


def test_command_list_lines_lists_nonempty_lines() -> None:
    out = "line1\n\nline2\n"
    result = command_list_lines(None, "grep ...", run=_fake_run(0, out))
    assert result.value == ["line1", "line2"]


def test_command_list_lines_empty() -> None:
    result = command_list_lines(None, "grep ...", run=_fake_run(0, ""))
    assert result.value == []


def test_risky_ports_detects_telnet() -> None:
    out = "Netid  State   Recv-Q  Send-Q  Local Address:Port\ntcp    LISTEN  0       128     0.0.0.0:23\n"
    result = risky_ports(None, "", run=_fake_run(0, out))
    assert result.value == ["Telnet(23)"]


def test_risky_ports_clean() -> None:
    out = "Netid  State   Recv-Q  Send-Q  Local Address:Port\ntcp    LISTEN  0       128     0.0.0.0:22\n"
    result = risky_ports(None, "", run=_fake_run(0, out))
    assert result.value == []
