"""진단 기준(YAML) 파싱/검증 테스트 — 실제 파일시스템 대신 텍스트로 검증한다."""
import pytest

from app.services.diagnosis_rules import RulesetValidationError, _parse_ruleset, validate_ruleset_yaml

VALID_YAML = """
meta:
  name: "테스트 기준"
  description: "설명"
  os: ["ubuntu"]
rules:
  U-01:
    name: "root 원격 로그인 제한"
    target: "sshd_config_value:PermitRootLogin"
    compare: equals_any
    expected: ["no"]
    severity: CRITICAL
"""


def test_valid_yaml_has_no_errors() -> None:
    assert validate_ruleset_yaml(VALID_YAML) == []


def test_parse_valid_yaml_builds_rule() -> None:
    ruleset = _parse_ruleset("test", VALID_YAML)
    assert ruleset.name == "테스트 기준"
    assert ruleset.os == ["ubuntu"]
    assert len(ruleset.rules) == 1
    rule = ruleset.rules[0]
    assert rule.rule_id == "U-01"
    assert rule.on_missing == "fail"  # 기본값
    assert rule.needs_sudo is False  # 기본값
    assert rule.parse_target() == ("sshd_config_value", "PermitRootLogin")


def test_rule_target_param_may_contain_colon() -> None:
    yaml_text = VALID_YAML.replace(
        'target: "sshd_config_value:PermitRootLogin"',
        'target: "command_value:echo a:b"',
    )
    ruleset = _parse_ruleset("test", yaml_text)
    assert ruleset.rules[0].parse_target() == ("command_value", "echo a:b")


def test_missing_meta_name_is_error() -> None:
    errors = validate_ruleset_yaml("meta: {}\nrules: {U-01: {}}\n")
    assert any("meta.name" in e for e in errors)


def test_unknown_collector_is_error() -> None:
    yaml_text = VALID_YAML.replace("sshd_config_value", "no_such_collector")
    errors = validate_ruleset_yaml(yaml_text)
    assert any("no_such_collector" in e for e in errors)


def test_invalid_compare_is_error() -> None:
    yaml_text = VALID_YAML.replace("compare: equals_any", "compare: bogus")
    errors = validate_ruleset_yaml(yaml_text)
    assert any("compare" in e for e in errors)


def test_missing_expected_for_equals_any_is_error() -> None:
    yaml_text = VALID_YAML.replace('    expected: ["no"]\n', "")
    errors = validate_ruleset_yaml(yaml_text)
    assert any("expected" in e for e in errors)


def test_list_empty_does_not_require_expected() -> None:
    yaml_text = (
        VALID_YAML.replace("compare: equals_any", "compare: list_empty")
        .replace('    expected: ["no"]\n', "")
    )
    assert validate_ruleset_yaml(yaml_text) == []


def test_invalid_severity_is_error() -> None:
    yaml_text = VALID_YAML.replace("severity: CRITICAL", "severity: SUPER_BAD")
    errors = validate_ruleset_yaml(yaml_text)
    assert any("severity" in e for e in errors)


def test_syntax_error_reported() -> None:
    errors = validate_ruleset_yaml("meta: [this is not: valid")
    assert len(errors) == 1
    assert "YAML" in errors[0]


def test_parse_invalid_yaml_raises_ruleset_validation_error() -> None:
    with pytest.raises(RulesetValidationError):
        _parse_ruleset("test", "meta: {}\nrules: {}\n")
