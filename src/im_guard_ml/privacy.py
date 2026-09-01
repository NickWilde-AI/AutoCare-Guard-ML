from __future__ import annotations

import hashlib
import json
import re
from typing import Any


REDACTION_PATTERNS = {
    "email": re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"),
    "phone_cn": re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"),
    "id_card_cn": re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)"),
}


def redact_text(text: str) -> tuple[str, list[str]]:
    pii_types: list[str] = []
    redacted = text
    for name, pattern in REDACTION_PATTERNS.items():
        if pattern.search(redacted):
            pii_types.append(name)
            redacted = pattern.sub(f"[REDACTED_{name.upper()}]", redacted)
    return redacted, pii_types


def build_input_summary(case: dict[str, Any], *, sample_chars: int = 160) -> dict[str, Any]:
    evidence_texts = _evidence_texts(case)
    conversation = case.get("conversation_evidence") or case.get("chat_evidence_list") or []
    faults = case.get("fault_evidence") or []
    payload_hash = hashlib.sha256(
        json.dumps(case, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    pii_seen: set[str] = set()
    redacted_samples: list[str] = []
    for text in evidence_texts[:3]:
        redacted, pii_types = redact_text(text)
        pii_seen.update(pii_types)
        redacted_samples.append(redacted[:sample_chars])
    conversation_n = len(conversation) if isinstance(conversation, list) else 0
    fault_n = len(faults) if isinstance(faults, list) else 0
    behavior_legacy = case.get("behavior_abnormal_list") or []
    behavior_n = len(behavior_legacy) if isinstance(behavior_legacy, list) and behavior_legacy else fault_n
    return {
        "payload_sha256": payload_hash,
        "conversation_evidence_count": conversation_n,
        "fault_evidence_count": fault_n,
        # 兼容旧审计字段名（无 behavior_abnormal_list 时回退 fault 计数）
        "chat_evidence_count": conversation_n,
        "behavior_abnormal_count": behavior_n,
        "hint_topic": case.get("hint_topic"),
        "pii_types": sorted(pii_seen),
        "redacted_evidence_samples": redacted_samples,
    }


def _evidence_texts(case: dict[str, Any]) -> list[str]:
    texts: list[str] = []
    for item in case.get("conversation_evidence") or case.get("chat_evidence_list") or []:
        if isinstance(item, dict):
            for key in ("content", "original_content", "text", "risk_point", "utterance"):
                if item.get(key):
                    texts.append(str(item[key]))
        elif item:
            texts.append(str(item))
    return texts
