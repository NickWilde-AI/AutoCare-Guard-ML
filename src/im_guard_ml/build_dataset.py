from __future__ import annotations

import argparse
import hashlib
import json
import random
from pathlib import Path
from typing import Any

from .dataio import read_jsonl, write_jsonl


PUBLIC_TOPIC_MAP = {
    "violence": "违禁品交易",
    "illegal": "违禁品交易",
    "sexual": "色情诱导",
    "harassment": "辱骂攻击",
    "hate": "辱骂攻击",
    "self_harm": "自伤诱导",
    "politics": "政治敏感",
}

XGUARD_TOPIC_MAP = {
    "pc": "色情诱导",
    "ec": "诈骗引流",
    "fin": "诈骗引流",
    "dc": "违禁品交易",
    "dw": "违禁品交易",
    "ter": "违禁品交易",
    "ac": "辱骂攻击",
    "def": "辱骂攻击",
    "ti": "辱骂攻击",
    "cy": "辱骂攻击",
    "mh": "自伤诱导",
    "cm": "未成年保护",
    "ma": "未成年保护",
    "md": "未成年保护",
    "pi": "版权侵犯",
    "sd": "政治敏感",
    "ext": "政治敏感",
}


def normalize_internal(row: dict[str, Any], source: str) -> dict[str, Any]:
    obj = dict(row)
    obj.setdefault("ticket_id", stable_id(source, row))
    obj.setdefault("source", source)
    obj.setdefault("audit_scene", {})
    obj.setdefault("chat_evidence_list", [])
    obj.setdefault("behavior_abnormal_list", [])
    return obj


def normalize_public(row: dict[str, Any], source: str) -> dict[str, Any]:
    content = row.get("content") or row.get("prompt") or row.get("response") or row.get("text") or ""
    raw_topic = row.get("topic") or row.get("category") or ""
    final = row.get("final_judgment") or row.get("harm_label") or row.get("label")
    final_judgment = "not_exist_violation" if str(final).lower() in {"safe", "0", "false", "not_exist_violation"} else "exist_violation"
    topic = PUBLIC_TOPIC_MAP.get(str(raw_topic).lower(), row.get("topic", "无主题" if final_judgment == "not_exist_violation" else "虚假信息"))
    return {
        "ticket_id": stable_id(source, row),
        "audit_scene": {
            "chat_type": "public_text",
            "user_intimacy": "unknown",
            "behavior_key_summary": {},
        },
        "chat_evidence_list": [{"original_content": content, "risk_point": "公开安全数据文本侧监督样本。"}],
        "behavior_abnormal_list": [],
        "label": {
            "risk_level": "low_risk" if final_judgment == "not_exist_violation" else "mid_risk",
            "topic": topic,
            "correlation_analysis": "",
            "final_judgment": final_judgment,
            "judgment_basis": "公开数据集二分类金标。",
            "handling_suggestion": "ignore" if final_judgment == "not_exist_violation" else "warning",
        },
        "source": source,
        "task_type": "public_binary",
    }


def normalize_xguard(row: dict[str, Any], source: str = "xguard_train_open_200k") -> dict[str, Any]:
    label_token = str(row.get("label", "")).strip().lower()
    final_judgment = "not_exist_violation" if label_token == "sec" else "exist_violation"
    topic = "无主题" if final_judgment == "not_exist_violation" else XGUARD_TOPIC_MAP.get(label_token, "虚假信息")
    content = xguard_content(row)
    explanation = str(row.get("explanation", "") or "").strip()
    risk_point = "XGuard 公开安全护栏训练样本。"
    if explanation:
        risk_point = f"{risk_point} 原始解释: {explanation}"
    return {
        "ticket_id": stable_id(source, row),
        "audit_scene": {
            "chat_type": "public_safety_guardrail",
            "user_intimacy": "unknown",
            "behavior_key_summary": {},
            "source_dataset": "Alibaba-AAIG/XGuard-Train-Open-200K",
            "xguard_stage": row.get("stage", ""),
            "xguard_sample_type": row.get("sample_type", ""),
            "xguard_label": label_token,
        },
        "chat_evidence_list": [{"original_content": content, "risk_point": risk_point}],
        "behavior_abnormal_list": [],
        "label": {
            "risk_level": "low_risk" if final_judgment == "not_exist_violation" else "mid_risk",
            "topic": topic,
            "correlation_analysis": "公开安全数据仅提供文本侧监督，不作为强处置证据。",
            "final_judgment": final_judgment,
            "judgment_basis": f"XGuard 原始类别: {label_token or 'unknown'}。",
            "handling_suggestion": "ignore" if final_judgment == "not_exist_violation" else "warning",
        },
        "source": source,
        "task_type": "public_binary",
    }


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
                "audit_scene": row.get("audit_scene", {}),
                "chat_evidence_list": row.get("chat_evidence_list", []),
                "behavior_abnormal_list": row.get("behavior_abnormal_list", []),
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
    total_ratio = train_ratio + val_ratio + test_ratio
    if total_ratio <= 0:
        raise ValueError("split ratios must sum to a positive value")
    train_ratio, val_ratio, test_ratio = (train_ratio / total_ratio, val_ratio / total_ratio, test_ratio / total_ratio)
    shuffled = list(rows)
    random.Random(seed).shuffle(shuffled)
    train_end = int(len(shuffled) * train_ratio)
    val_end = train_end + int(len(shuffled) * val_ratio)
    return {
        "train": shuffled[:train_end],
        "val": shuffled[train_end:val_end],
        "test": shuffled[val_end:],
    }


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
