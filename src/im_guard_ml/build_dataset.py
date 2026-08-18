from __future__ import annotations

import argparse
import hashlib
import json
import random
from pathlib import Path
from typing import Any

from .dataio import read_jsonl, write_jsonl
from .schema import TOPICS


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
    raw_topic_text = str(row.get("topic") or row.get("category") or "")
    final = row.get("final_judgment") or row.get("harm_label") or row.get("label")
    final_judgment = "not_exist_violation" if str(final).lower() in {"safe", "0", "false", "not_exist_violation"} else "exist_violation"
    fallback_topic = "无主题" if final_judgment == "not_exist_violation" else "虚假信息"
    mapped_topic = PUBLIC_TOPIC_MAP.get(raw_topic_text.lower())
    # P2-19：未映射的原始主题字符串不再直接透传，避免产生 TOPICS 之外的 topic。
    if mapped_topic:
        topic = mapped_topic
    elif raw_topic_text in TOPICS:
        topic = raw_topic_text
    else:
        topic = fallback_topic
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
    """按工单 ID 隔离的 train/val/test 拆分（P1-17）。

    同一 ticket_id 的多行作为一个整体随机打乱后整组分配，保证任何工单
    不会同时落入训练集与评测集（主文档 5.4/5.5 口径）。比例按行数目标
    贪心分配，逐组选择"距离目标最远"的集合，保持近似比例。
    """
    total_ratio = train_ratio + val_ratio + test_ratio
    if total_ratio <= 0:
        raise ValueError("split ratios must sum to a positive value")
    train_ratio, val_ratio, test_ratio = (train_ratio / total_ratio, val_ratio / total_ratio, test_ratio / total_ratio)

    by_ticket: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        ticket_id = str(row.get("ticket_id", ""))
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
