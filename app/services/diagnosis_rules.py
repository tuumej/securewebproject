"""진단 기준(YAML) 로딩/검증/저장 — "무엇을 기대하는가"는 코드가 아니라 여기 데이터로만
존재한다. app/diagnosis_rules/*.yaml 파일 하나가 하나의 ruleset이며, 파일명(확장자 제외)이
ruleset id다.

이 모듈은 규칙의 "값"만 다룬다. 규칙을 실제로 수집·비교·판정하는 것은
app/services/diagnosis_engine.py 다.
"""
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from app.services.diagnosis_collectors import COLLECTORS

RULES_DIR = Path(__file__).resolve().parent.parent / "diagnosis_rules"

_ID_PATTERN = re.compile(r"^[a-z0-9_-]+$")
COMPARATORS = {"equals_any", "not_equals_any", "list_empty"}
SEVERITIES = {"CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"}
ON_MISSING_VALUES = {"fail", "pass", "unknown"}


class RulesetValidationError(ValueError):
    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


@dataclass(frozen=True)
class Rule:
    rule_id: str
    name: str
    target: str
    compare: str
    expected: list[str]
    severity: str
    needs_sudo: bool
    on_missing: str
    recommendation: str | None

    def parse_target(self) -> tuple[str, str]:
        if ":" in self.target:
            collector_id, param = self.target.split(":", 1)
        else:
            collector_id, param = self.target, ""
        return collector_id.strip(), param


@dataclass(frozen=True)
class Ruleset:
    ruleset_id: str
    name: str
    description: str
    os: list[str]
    rules: list[Rule]


def _ruleset_path(ruleset_id: str) -> Path:
    if not _ID_PATTERN.match(ruleset_id):
        raise ValueError("기준 id는 영문 소문자/숫자/-/_ 만 사용할 수 있습니다.")
    return RULES_DIR / f"{ruleset_id}.yaml"


def validate_ruleset_yaml(yaml_text: str) -> list[str]:
    """스키마 오류 목록을 반환한다(비어 있으면 유효)."""
    try:
        data = yaml.safe_load(yaml_text)
    except yaml.YAMLError as exc:
        return [f"YAML 문법 오류: {exc}"]
    if not isinstance(data, dict):
        return ["최상위는 meta/rules를 담은 mapping이어야 합니다."]

    errors: list[str] = []
    meta = data.get("meta")
    if not isinstance(meta, dict) or not meta.get("name"):
        errors.append("meta.name은 필수입니다.")

    rules = data.get("rules")
    if not isinstance(rules, dict) or not rules:
        errors.append("rules는 최소 1개 이상의 항목이 있는 mapping이어야 합니다.")
        return errors

    for rule_id, spec in rules.items():
        prefix = f"규칙 '{rule_id}'"
        if not isinstance(spec, dict):
            errors.append(f"{prefix}: mapping이어야 합니다.")
            continue
        if not spec.get("name"):
            errors.append(f"{prefix}: name은 필수입니다.")

        target = spec.get("target")
        if not target or not isinstance(target, str):
            errors.append(f"{prefix}: target은 필수입니다.")
        else:
            collector_id = target.split(":", 1)[0].strip()
            if collector_id not in COLLECTORS:
                names = ", ".join(sorted(COLLECTORS))
                errors.append(f"{prefix}: collector '{collector_id}'는 등록되지 않은 수집기입니다({names} 중 하나).")

        compare = spec.get("compare")
        if compare not in COMPARATORS:
            errors.append(f"{prefix}: compare는 {sorted(COMPARATORS)} 중 하나여야 합니다.")
        elif compare != "list_empty":
            expected = spec.get("expected")
            if not expected or not isinstance(expected, list):
                errors.append(f"{prefix}: compare가 '{compare}'이면 expected(리스트)가 필요합니다.")

        severity = spec.get("severity")
        if severity not in SEVERITIES:
            errors.append(f"{prefix}: severity는 {sorted(SEVERITIES)} 중 하나여야 합니다.")

        on_missing = spec.get("on_missing", "fail")
        if on_missing not in ON_MISSING_VALUES:
            errors.append(f"{prefix}: on_missing은 {sorted(ON_MISSING_VALUES)} 중 하나여야 합니다.")

    return errors


def _parse_ruleset(ruleset_id: str, yaml_text: str) -> Ruleset:
    errors = validate_ruleset_yaml(yaml_text)
    if errors:
        raise RulesetValidationError(errors)
    data = yaml.safe_load(yaml_text)
    meta = data.get("meta") or {}
    rules = [
        Rule(
            rule_id=str(rule_id),
            name=spec["name"],
            target=spec["target"],
            compare=spec["compare"],
            expected=[str(v) for v in (spec.get("expected") or [])],
            severity=spec["severity"],
            needs_sudo=bool(spec.get("needs_sudo", False)),
            on_missing=spec.get("on_missing", "fail"),
            recommendation=spec.get("recommendation"),
        )
        for rule_id, spec in data["rules"].items()
    ]
    return Ruleset(
        ruleset_id=ruleset_id,
        name=meta.get("name", ruleset_id),
        description=meta.get("description", ""),
        os=[str(v) for v in (meta.get("os") or [])],
        rules=rules,
    )


def list_rulesets() -> list[Ruleset]:
    RULES_DIR.mkdir(parents=True, exist_ok=True)
    result = []
    for path in sorted(RULES_DIR.glob("*.yaml")):
        try:
            result.append(_parse_ruleset(path.stem, path.read_text(encoding="utf-8")))
        except RulesetValidationError:
            continue  # 손상된 파일은 목록에서 건너뛴다(개별 격리)
    return result


def load_ruleset(ruleset_id: str) -> Ruleset:
    return _parse_ruleset(ruleset_id, read_ruleset_yaml(ruleset_id))


def read_ruleset_yaml(ruleset_id: str) -> str:
    path = _ruleset_path(ruleset_id)
    if not path.exists():
        raise FileNotFoundError(f"진단 기준 '{ruleset_id}'을 찾을 수 없습니다.")
    return path.read_text(encoding="utf-8")


def save_ruleset_yaml(ruleset_id: str, yaml_text: str) -> Ruleset:
    """검증 후 저장한다. 유효하지 않으면 RulesetValidationError(오류 목록 포함)."""
    ruleset = _parse_ruleset(ruleset_id, yaml_text)  # 검증도 함께 수행됨
    path = _ruleset_path(ruleset_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml_text, encoding="utf-8")
    return ruleset


def create_ruleset(ruleset_id: str, name: str, description: str = "") -> Ruleset:
    path = _ruleset_path(ruleset_id)
    if path.exists():
        raise ValueError(f"진단 기준 '{ruleset_id}'은 이미 존재합니다.")
    template = yaml.safe_dump(
        {
            "meta": {"name": name, "description": description, "os": []},
            "rules": {
                "EXAMPLE-01": {
                    "name": "예시 규칙 - 필요에 맞게 수정하거나 삭제하세요",
                    "target": "command_value:echo ok",
                    "compare": "equals_any",
                    "expected": ["ok"],
                    "severity": "LOW",
                    "needs_sudo": False,
                    "on_missing": "fail",
                    "recommendation": None,
                }
            },
        },
        allow_unicode=True,
        sort_keys=False,
    )
    return save_ruleset_yaml(ruleset_id, template)


def delete_ruleset(ruleset_id: str) -> None:
    path = _ruleset_path(ruleset_id)
    if path.exists():
        path.unlink()
