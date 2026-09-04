"""6단계 진단 엔진 단위 테스트 — 가짜 client/collector 결과를 주입해 SSH 없이 검증한다."""
from app.services import diagnosis_engine as engine
from app.services.diagnosis_collectors import CollectorResult
from app.services.diagnosis_rules import Rule


def _rule(**overrides) -> Rule:
    base = dict(
        rule_id="U-TEST", name="테스트 규칙", target="command_value:echo x",
        compare="equals_any", expected=["ok"], severity="HIGH",
        needs_sudo=False, on_missing="fail", recommendation="조치하세요.",
    )
    base.update(overrides)
    return Rule(**base)


def test_compare_equals_any() -> None:
    rule = _rule(compare="equals_any", expected=["ok"])
    assert engine._compare(CollectorResult(value="ok", evidence=""), rule) is True
    assert engine._compare(CollectorResult(value="bad", evidence=""), rule) is False


def test_compare_not_equals_any() -> None:
    rule = _rule(compare="not_equals_any", expected=["REQUIRED"])
    assert engine._compare(CollectorResult(value="NOT_REQUIRED", evidence=""), rule) is True
    assert engine._compare(CollectorResult(value="REQUIRED", evidence=""), rule) is False


def test_compare_list_empty() -> None:
    rule = _rule(compare="list_empty", expected=[])
    assert engine._compare(CollectorResult(value=[], evidence=""), rule) is True
    assert engine._compare(CollectorResult(value=["x"], evidence=""), rule) is False


def test_judge_not_found_is_unknown_info_regardless_of_compare() -> None:
    rule = _rule(severity="CRITICAL")
    status, severity = engine._judge(CollectorResult(value=None, evidence="", not_found=True), rule)
    assert (status, severity) == ("unknown", "info")


def test_judge_missing_value_uses_on_missing_fail_by_default() -> None:
    rule = _rule(on_missing="fail", severity="HIGH")
    status, severity = engine._judge(CollectorResult(value=None, evidence=""), rule)
    assert (status, severity) == ("fail", "high")


def test_judge_missing_value_on_missing_pass() -> None:
    rule = _rule(on_missing="pass", severity="HIGH")
    status, _ = engine._judge(CollectorResult(value=None, evidence=""), rule)
    assert status == "pass"


def test_judge_missing_value_on_missing_unknown() -> None:
    rule = _rule(on_missing="unknown")
    status, severity = engine._judge(CollectorResult(value=None, evidence=""), rule)
    assert (status, severity) == ("unknown", "info")


def test_judge_pass_and_fail_from_compare() -> None:
    rule = _rule(compare="equals_any", expected=["ok"], severity="LOW")
    pass_status, _ = engine._judge(CollectorResult(value="ok", evidence=""), rule)
    fail_status, _ = engine._judge(CollectorResult(value="bad", evidence=""), rule)
    assert pass_status == "pass"
    assert fail_status == "fail"


def test_judge_list_empty_pass_when_no_violations() -> None:
    rule = _rule(compare="list_empty", expected=[])
    status, _ = engine._judge(CollectorResult(value=[], evidence=""), rule)
    assert status == "pass"


def test_to_finding_omits_recommendation_when_pass() -> None:
    rule = _rule()
    finding = engine._to_finding(rule, CollectorResult(value="ok", evidence="ev"), "pass", "high")
    assert finding.recommendation is None
    assert finding.evidence == "ev"


def test_to_finding_includes_recommendation_when_fail() -> None:
    rule = _rule()
    finding = engine._to_finding(rule, CollectorResult(value="bad", evidence="ev"), "fail", "high")
    assert finding.recommendation == "조치하세요."


def test_collect_needs_sudo_wraps_command_with_sudo(monkeypatch) -> None:
    rule = _rule(needs_sudo=True, target="command_value:whoami")
    calls: list[str] = []

    def fake_command_value(client, param, *, run):
        calls.append(param)
        return run(client, param)

    monkeypatch.setattr(engine, "COLLECTORS", {"command_value": fake_command_value})

    def fake_run_command(client, command):
        calls.append(command)
        return 0, "root\n", ""

    monkeypatch.setattr(engine.ssh, "run_command", fake_run_command)
    engine._collect(None, rule, sudo_ok=True)
    assert calls[-1] == "sudo -n whoami"


def test_collect_needs_sudo_without_sudo_access_returns_not_found() -> None:
    rule = _rule(needs_sudo=True)
    result = engine._collect(None, rule, sudo_ok=False)
    assert result.not_found


def test_collect_unknown_collector_returns_not_found() -> None:
    rule = _rule(target="no_such_collector:x")
    result = engine._collect(None, rule, sudo_ok=True)
    assert result.not_found


def test_run_diagnosis_builds_report(monkeypatch) -> None:
    class FakeClient:
        def close(self) -> None:
            pass

    monkeypatch.setattr(engine.ssh, "connect", lambda db, target, secret: FakeClient())

    def fake_run_command(client, command):
        if "os-release" in command:
            return 0, 'ID=ubuntu\nVERSION_ID="24.04"\n', ""
        if "sudo -n true" in command:
            return 0, "", ""
        if "PermitRootLogin" in command:
            return 0, "PermitRootLogin no\n", ""
        return 0, "", ""

    monkeypatch.setattr(engine.ssh, "run_command", fake_run_command)

    rule = _rule(rule_id="U-01", target="sshd_config_value:PermitRootLogin", expected=["no"])

    class FakeRuleset:
        ruleset_id = "fake"
        name = "가짜 기준"
        os = ["ubuntu"]
        rules = [rule]

    monkeypatch.setattr(engine, "load_ruleset", lambda ruleset_id: FakeRuleset())

    phases: list[str] = []
    result = engine.run_diagnosis(
        None, target=object(), secret="x", ruleset_id="fake", on_phase=phases.append
    )

    assert result.os_id == "ubuntu"
    assert result.os_version == "24.04"
    assert phases == [
        engine.PHASE_CONNECTING,
        engine.PHASE_OS_IDENTIFY,
        engine.PHASE_COLLECTING,
        engine.PHASE_REPORTING,
        engine.PHASE_DONE,
    ]
    assert len(result.findings) == 1
    assert result.findings[0].status == "pass"


def test_run_diagnosis_flags_os_mismatch(monkeypatch) -> None:
    class FakeClient:
        def close(self) -> None:
            pass

    monkeypatch.setattr(engine.ssh, "connect", lambda db, target, secret: FakeClient())
    monkeypatch.setattr(
        engine.ssh, "run_command",
        lambda client, command: (0, "ID=centos\n", "") if "os-release" in command else (0, "", ""),
    )

    class FakeRuleset:
        ruleset_id = "fake"
        name = "가짜 기준"
        os = ["ubuntu"]
        rules: list[Rule] = []

    monkeypatch.setattr(engine, "load_ruleset", lambda ruleset_id: FakeRuleset())

    result = engine.run_diagnosis(None, target=object(), secret="x", ruleset_id="fake")
    assert result.findings[0].rule_id == "_os_mismatch"


def test_run_diagnosis_connection_failure_is_tagged(monkeypatch) -> None:
    def fail_connect(db, target, secret):
        raise RuntimeError("auth failed")

    monkeypatch.setattr(engine.ssh, "connect", fail_connect)

    try:
        engine.run_diagnosis(None, target=object(), secret="x", ruleset_id="fake")
        raise AssertionError("예외가 발생해야 합니다")
    except RuntimeError as exc:
        assert "[SSH 접속 확인]" in str(exc)
