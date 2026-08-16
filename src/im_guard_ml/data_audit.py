from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from typing import Any

from .schema import validate_label


REQUIRED_FIELDS = ["ticket_id", "audit_scene", "chat_evidence_list", "behavior_abnormal_list", "label"]
PII_PATTERNS = {
    "email": re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"),
    "phone_cn": re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"),
    "id_card_cn": re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)"),
}


def audit_dataset(rows: list[dict[str, Any]]) -> dict[str, Any]:
    missing: Counter[str] = Counter()
    label_errors: list[dict[str, Any]] = []
    duplicate_ids: list[str] = []
    duplicate_payloads: list[str] = []
    source_counter: Counter[str] = Counter()
    source_type_counter: Counter[str] = Counter()
    topic_counter: Counter[str] = Counter()
    risk_counter: Counter[str] = Counter()
    judgment_counter: Counter[str] = Counter()
    handling_counter: Counter[str] = Counter()
    seen_ids: set[str] = set()
    seen_hashes: dict[str, str] = {}
    public_multitask_leaks: list[str] = []
    pii_counter: Counter[str] = Counter()
    pii_samples: list[dict[str, Any]] = []

    for idx, row in enumerate(rows):
        for field in REQUIRED_FIELDS:
            if field not in row:
                missing[field] += 1
        ticket_id = str(row.get("ticket_id", f"row-{idx}"))
        if ticket_id in seen_ids:
            duplicate_ids.append(ticket_id)
        seen_ids.add(ticket_id)
        payload_hash = _case_hash(row)
        if payload_hash in seen_hashes:
            duplicate_payloads.append(ticket_id)
        seen_hashes[payload_hash] = ticket_id
        source = str(row.get("source", "unknown"))
        source_counter[source] += 1
        source_type_counter[_source_type(row)] += 1
        label = row.get("label", {})
        topic_counter[str(label.get("topic", "missing"))] += 1
        risk_counter[str(label.get("risk_level", "missing"))] += 1
        judgment_counter[str(label.get("final_judgment", "missing"))] += 1
        handling_counter[str(label.get("handling_suggestion", "missing"))] += 1
        errors = validate_label(label) if isinstance(label, dict) else ["label must be an object"]
        if errors:
            label_errors.append({"ticket_id": ticket_id, "errors": errors})
        if row.get("task_type") == "public_binary":
            if label.get("handling_suggestion") not in {"ignore", "warning"}:
                public_multitask_leaks.append(ticket_id)
        pii_hits = detect_pii_types(row)
        if pii_hits:
            for pii_type in pii_hits:
                pii_counter[pii_type] += 1
            if len(pii_samples) < 20:
                pii_samples.append({"ticket_id": ticket_id, "pii_types": pii_hits})

    return {
        "total": len(rows),
        "missing_required_fields": dict(missing),
        "duplicate_ticket_ids": duplicate_ids[:50],
        "duplicate_payloads": duplicate_payloads[:50],
        "label_error_count": len(label_errors),
        "label_errors_sample": label_errors[:20],
        "public_multitask_leak_count": len(public_multitask_leaks),
        "public_multitask_leaks_sample": public_multitask_leaks[:20],
        "pii_risk_count": sum(pii_counter.values()),
        "pii_risk_by_type": dict(sorted(pii_counter.items())),
        "pii_risk_sample": pii_samples,
        "by_source": dict(sorted(source_counter.items())),
        "by_source_type": dict(sorted(source_type_counter.items())),
        "by_topic": dict(sorted(topic_counter.items())),
        "by_risk_level": dict(sorted(risk_counter.items())),
        "by_final_judgment": dict(sorted(judgment_counter.items())),
        "by_handling_suggestion": dict(sorted(handling_counter.items())),
        "distribution_warnings": _distribution_warnings(
            len(rows),
            {
                "source_type": source_type_counter,
                "topic": topic_counter,
                "risk_level": risk_counter,
                "final_judgment": judgment_counter,
                "handling_suggestion": handling_counter,
            },
        ),
        "quality_status": _quality_status(missing, duplicate_ids, duplicate_payloads, label_errors, public_multitask_leaks),
    }


def split_leakage_report(train_rows: list[dict[str, Any]], eval_rows: list[dict[str, Any]]) -> dict[str, Any]:
    train_ids = {str(row.get("ticket_id", "")) for row in train_rows}
    eval_ids = {str(row.get("ticket_id", "")) for row in eval_rows}
    train_hashes = {_case_hash(row): str(row.get("ticket_id", "")) for row in train_rows}
    overlap_ids = sorted(train_ids & eval_ids)
    overlap_hashes: list[dict[str, str]] = []
    for row in eval_rows:
        h = _case_hash(row)
        if h in train_hashes:
            overlap_hashes.append({"eval_ticket_id": str(row.get("ticket_id", "")), "train_ticket_id": train_hashes[h]})
    return {
        "ticket_id_overlap_count": len(overlap_ids),
        "ticket_id_overlap_sample": overlap_ids[:50],
        "payload_overlap_count": len(overlap_hashes),
        "payload_overlap_sample": overlap_hashes[:20],
        "quality_status": "fail" if overlap_ids or overlap_hashes else "pass",
}


def detect_pii_types(row: dict[str, Any]) -> list[str]:
    text = "\n".join(_text_fragments(row))
    return [name for name, pattern in PII_PATTERNS.items() if pattern.search(text)]


def _source_type(row: dict[str, Any]) -> str:
    task_type = str(row.get("task_type", "")).strip()
    if task_type:
        return task_type
    source = str(row.get("source", "")).lower()
    if "hard" in source or "refinement" in source:
        return "hard_case"
    if "synthetic" in source or "generator" in source:
        return "synthetic"
    if "public" in source or "xguard" in source:
        return "public_binary"
    if source and source != "unknown":
        return "internal"
    return "unknown"


def _distribution_warnings(total: int, counters: dict[str, Counter[str]], *, dominance_threshold: float = 0.95) -> list[dict[str, Any]]:
    if total < 20:
        return []
    warnings: list[dict[str, Any]] = []
    for field, counter in counters.items():
        if not counter:
            continue
        label, count = counter.most_common(1)[0]
        ratio = count / total
        if ratio >= dominance_threshold:
            warnings.append(
                {
                    "field": field,
                    "dominant_value": label,
                    "ratio": round(ratio, 4),
                    "message": f"{field} is dominated by {label}; verify sampling or split strategy before training.",
                }
            )
    return warnings


def _text_fragments(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        parts: list[str] = []
        for item in value.values():
            parts.extend(_text_fragments(item))
        return parts
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            parts.extend(_text_fragments(item))
        return parts
    return []


def _case_hash(row: dict[str, Any]) -> str:
    content = {
        "audit_scene": row.get("audit_scene", {}),
        "chat_evidence_list": row.get("chat_evidence_list", []),
        "behavior_abnormal_list": row.get("behavior_abnormal_list", []),
        "label": row.get("label", {}),
    }
    payload = json.dumps(content, ensure_ascii=False, sort_keys=True)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def _quality_status(
    missing: Counter[str],
    duplicate_ids: list[str],
    duplicate_payloads: list[str],
    label_errors: list[dict[str, Any]],
    public_multitask_leaks: list[str],
) -> str:
    if missing or duplicate_ids or duplicate_payloads or label_errors or public_multitask_leaks:
        return "fail"
    return "pass"
