from __future__ import annotations

import argparse
import hashlib
import json
import random
from pathlib import Path
from typing import Any

from .dataio import read_jsonl, write_jsonl
from .schema import EVENT_TOPICS, TOPICS


# 公开安全语料 → AutoCare 主题的弱映射（仅演示冷启动，不做生产主张）
PUBLIC_TOPIC_MAP = {
    "violence": "道路救援与人员安全",
    "illegal": "质保、零部件与服务争议",
    "sexual": "无风险事件",
    "harassment": "无风险事件",
    "hate": "无风险事件",
    "self_harm": "道路救援与人员安全",
    "politics": "无风险事件",
}

XGUARD_TOPIC_MAP = {
    "pc": "无风险事件",
    "ec": "质保、零部件与服务争议",
    "fin": "质保、零部件与服务争议",
    "dc": "道路救援与人员安全",
    "dw": "道路救援与人员安全",
    "ter": "道路救援与人员安全",
    "ac": "无风险事件",
    "def": "无风险事件",
    "ti": "无风险事件",
    "cy": "车机、座舱和远程控车故障",
    "mh": "道路救援与人员安全",
    "cm": "无风险事件",
    "ma": "无风险事件",
    "md": "无风险事件",
    "pi": "无风险事件",
    "sd": "无风险事件",
    "ext": "无风险事件",
}


def normalize_internal(row: dict[str, Any], source: str) -> dict[str, Any]:
    """Normalize internal rows into ServiceCase shape (minimal mapping)."""
    obj = dict(row)
    case_id = obj.get("case_id") or obj.get("ticket_id") or stable_id(source, row)
    obj["case_id"] = str(case_id)
    obj.setdefault("ticket_id", obj["case_id"])
    obj.setdefault("source", source)
    obj.setdefault("service_context", obj.get("audit_scene") or {})
    obj.setdefault("vehicle_context", {})
    obj.setdefault(
        "conversation_evidence",
        obj.get("chat_evidence_list") or [],
    )
    obj.setdefault("vehicle_signal_summary", {})
    obj.setdefault("fault_evidence", obj.get("behavior_abnormal_list") or [])
    obj.setdefault("service_history_summary", {})
    obj.setdefault("missing_and_conflicts", {})
    obj.setdefault("data_provenance", {})
    if isinstance(obj.get("label"), dict):
        obj["label"] = _normalize_label_fields(obj["label"])
    return obj


def normalize_public(row: dict[str, Any], source: str) -> dict[str, Any]:
    content = row.get("content") or row.get("prompt") or row.get("response") or row.get("text") or ""
    raw_topic_text = str(row.get("topic") or row.get("category") or row.get("event_topic") or "")
    final = row.get("event_judgment") or row.get("final_judgment") or row.get("harm_label") or row.get("label")
    is_safe = str(final).lower() in {
        "safe",
        "0",
        "false",
        "not_exist_violation",
        "not_risk_event",
    }
    event_judgment = "not_risk_event" if is_safe else "risk_event"
    fallback_topic = "无风险事件" if is_safe else "质保、零部件与服务争议"
    mapped_topic = PUBLIC_TOPIC_MAP.get(raw_topic_text.lower())
    if mapped_topic:
        topic = mapped_topic
    elif raw_topic_text in EVENT_TOPICS or raw_topic_text in TOPICS:
        topic = raw_topic_text
    else:
        topic = fallback_topic
    case_id = stable_id(source, row)
    return {
        "case_id": case_id,
        "ticket_id": case_id,
        "service_context": {
            "channel": "public_text",
            "source_dataset": source,
        },
        "vehicle_context": {},
        "conversation_evidence": [
            {"content": content, "role": "user", "note": "公开安全数据文本侧监督样本。"}
        ],
        "vehicle_signal_summary": {},
        "fault_evidence": [],
        "service_history_summary": {},
        "missing_and_conflicts": {},
        "data_provenance": {"task_type": "public_binary"},
        "label": {
            "risk_level": "low_risk" if is_safe else "mid_risk",
            "event_topic": topic,
            "event_judgment": event_judgment,
            "recommended_action": "information_reply" if is_safe else "service_followup",
            "correlation_analysis": "",
            "uncertainty_reason": "公开数据集二分类金标。",
            "evidence_refs": [],
            "service_escalation_flags": [],
        },
        "source": source,
        "task_type": "public_binary",
    }


def normalize_xguard(row: dict[str, Any], source: str = "xguard_train_open_200k") -> dict[str, Any]:
    label_token = str(row.get("label", "")).strip().lower()
    is_safe = label_token == "sec"
    event_judgment = "not_risk_event" if is_safe else "risk_event"
    topic = "无风险事件" if is_safe else XGUARD_TOPIC_MAP.get(label_token, "质保、零部件与服务争议")
    content = xguard_content(row)
    explanation = str(row.get("explanation", "") or "").strip()
    note = "XGuard 公开安全护栏训练样本。"
    if explanation:
        note = f"{note} 原始解释: {explanation}"
    case_id = stable_id(source, row)
    return {
        "case_id": case_id,
        "ticket_id": case_id,
        "service_context": {
            "channel": "public_safety_guardrail",
            "source_dataset": "Alibaba-AAIG/XGuard-Train-Open-200K",
            "xguard_stage": row.get("stage", ""),
            "xguard_sample_type": row.get("sample_type", ""),
            "xguard_label": label_token,
        },
        "vehicle_context": {},
        "conversation_evidence": [{"content": content, "role": "user", "note": note}],
        "vehicle_signal_summary": {},
        "fault_evidence": [],
        "service_history_summary": {},
        "missing_and_conflicts": {},
        "data_provenance": {"task_type": "public_binary"},
        "label": {
            "risk_level": "low_risk" if is_safe else "mid_risk",
            "event_topic": topic,
            "event_judgment": event_judgment,
            "recommended_action": "information_reply" if is_safe else "service_followup",
            "correlation_analysis": "公开安全数据仅提供文本侧监督，不作为紧急/专家处置证据。",
            "uncertainty_reason": f"XGuard 原始类别: {label_token or 'unknown'}。",
            "evidence_refs": [],
            "service_escalation_flags": [],
        },
        "source": source,
        "task_type": "public_binary",
    }


def _normalize_label_fields(label: dict[str, Any]) -> dict[str, Any]:
    out = dict(label)
    if "event_topic" not in out and "topic" in out:
        out["event_topic"] = out["topic"]
    if "event_judgment" not in out and "final_judgment" in out:
        judgment_map = {
            "exist_violation": "risk_event",
            "not_exist_violation": "not_risk_event",
        }
        out["event_judgment"] = judgment_map.get(out["final_judgment"], out["final_judgment"])
    if "recommended_action" not in out and "handling_suggestion" in out:
        action_map = {
            "ignore": "information_reply",
            "warning": "service_followup",
            "limit_account": "create_work_order",
            "ban_account": "emergency_review",
        }
        out["recommended_action"] = action_map.get(
            out["handling_suggestion"], out["handling_suggestion"]
        )
    if out.get("event_topic") == "无主题":
        out["event_topic"] = "无风险事件"
    return out


def xguard_content(row: dict[str, Any]) -> str:
    prompt = str(row.get("prompt", "") or "").strip()
    response = str(row.get("response", "") or "").strip()
    stage = str(row.get("stage", "") or "").strip().lower()
    if stage == "qr":
        return f"[User Query] {prompt}\n\n[LLM Response] {response}".strip()
    if stage == "r":
        return response
    return prompt


def stable_id(source: str, row: dict[str, Any]) -> str:
    payload = json.dumps(row, ensure_ascii=False, sort_keys=True)
    digest = hashlib.sha1(payload.encode("utf-8")).hexdigest()[:12]
    return f"{source}-{digest}"


def dedupe_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for row in rows:
        key = json.dumps(
            {
                "service_context": row.get("service_context") or row.get("audit_scene", {}),
                "conversation_evidence": row.get("conversation_evidence")
                or row.get("chat_evidence_list", []),
                "fault_evidence": row.get("fault_evidence") or row.get("behavior_abnormal_list", []),
                "label": row.get("label", {}),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped


def split_rows(
    rows: list[dict[str, Any]],
    *,
    train_ratio: float = 0.8,
    val_ratio: float = 0.1,
    test_ratio: float = 0.1,
    seed: int = 42,
) -> dict[str, list[dict[str, Any]]]:
    """按工单 ID 隔离的 train/val/test 拆分。"""
    total_ratio = train_ratio + val_ratio + test_ratio
    if total_ratio <= 0:
        raise ValueError("split ratios must sum to a positive value")
    train_ratio, val_ratio, test_ratio = (
        train_ratio / total_ratio,
        val_ratio / total_ratio,
        test_ratio / total_ratio,
    )

    by_ticket: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        ticket_id = str(row.get("case_id") or row.get("ticket_id", ""))
        by_ticket.setdefault(ticket_id, []).append(row)
    groups = list(by_ticket.values())
    rng = random.Random(seed)
    rng.shuffle(groups)

    targets = [
        int(round(len(rows) * train_ratio)),
        int(round(len(rows) * val_ratio)),
        int(round(len(rows) * test_ratio)),
    ]
    splits: list[list[dict[str, Any]]] = [[], [], []]
    counts = [0, 0, 0]

    for group in groups:
        deficits = [targets[i] - counts[i] for i in range(3)]
        idx = deficits.index(max(deficits))
        splits[idx].extend(group)
        counts[idx] += len(group)

    return {"train": splits[0], "val": splits[1], "test": splits[2]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m im_guard_ml.build_dataset")
    parser.add_argument("--internal", action="append", default=[], help="Internal JSONL path, can be repeated.")
    parser.add_argument("--public", action="append", default=[], help="Public binary JSONL path, can be repeated.")
    parser.add_argument("--public-xguard", action="append", default=[], help="XGuard JSONL path, can be repeated.")
    parser.add_argument("--out", required=True)
    parser.add_argument("--split-out-dir", help="Optional directory for train/val/test JSONL splits.")
    parser.add_argument("--train-ratio", type=float, default=0.8)
    parser.add_argument("--val-ratio", type=float, default=0.1)
    parser.add_argument("--test-ratio", type=float, default=0.1)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args(argv)
    rows: list[dict[str, Any]] = []
    for path in args.internal:
        source = Path(path).stem
        rows.extend(normalize_internal(row, source) for row in read_jsonl(path))
    for path in args.public:
        source = Path(path).stem
        rows.extend(normalize_public(row, source) for row in read_jsonl(path))
    for path in args.public_xguard:
        source = Path(path).stem
        rows.extend(normalize_xguard(row, source) for row in read_jsonl(path))
    rows = dedupe_rows(rows)
    write_jsonl(args.out, rows)
    if args.split_out_dir:
        split_dir = Path(args.split_out_dir)
        for name, split in split_rows(
            rows,
            train_ratio=args.train_ratio,
            val_ratio=args.val_ratio,
            test_ratio=args.test_ratio,
            seed=args.seed,
        ).items():
            write_jsonl(split_dir / f"{name}.jsonl", split)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
