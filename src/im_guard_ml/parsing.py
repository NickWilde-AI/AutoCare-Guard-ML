from __future__ import annotations

import json
import re
from typing import Any

from .schema import AuditLabel, HandlingSuggestion, RiskLevel, validate_label


ENUM_PATTERNS = {
    "risk_level": r"(low_risk|mid_risk|high_risk)",
    "final_judgment": r"(not_exist_violation|exist_violation)",
    "handling_suggestion": r"(ignore|warning|limit_account|ban_account)",
}


def _extract_json_object(text: str) -> str | None:
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    in_str = False
    escaped = False
    for idx in range(start, len(text)):
        ch = text[idx]
        if in_str:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : idx + 1]
    return None


def parse_judge_output(text: str, strict: bool = False) -> dict[str, Any]:
    default = AuditLabel.safe_default().to_dict()
    parsed: dict[str, Any] | None = None
    json_text = _extract_json_object(text)
    if json_text:
        try:
            obj = json.loads(json_text)
            if isinstance(obj, dict):
                parsed = {**default, **obj}
        except json.JSONDecodeError:
            parsed = None
    if parsed is None:
        parsed = dict(default)
        for field, pattern in ENUM_PATTERNS.items():
            match = re.search(pattern, text)
            if match:
                parsed[field] = match.group(1)
    errors = validate_label(parsed)
    if errors and strict:
        raise ValueError("; ".join(errors))
    if errors:
        if parsed.get("handling_suggestion") == HandlingSuggestion.BAN_ACCOUNT.value:
            parsed["handling_suggestion"] = HandlingSuggestion.LIMIT_ACCOUNT.value
        if parsed.get("final_judgment") == "not_exist_violation":
            parsed["risk_level"] = RiskLevel.LOW.value
            parsed["handling_suggestion"] = HandlingSuggestion.IGNORE.value
    return parsed

