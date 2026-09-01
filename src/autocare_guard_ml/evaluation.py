from __future__ import annotations

from collections import defaultdict
from typing import Any, Sequence

RISK_LABELS = ["low_risk", "mid_risk", "high_risk"]
HANDLING_LABELS = [
    "information_reply",
    "collect_more_evidence",
    "service_followup",
    "create_work_order",
    "expert_review",
    "emergency_review",
]
ACTION_LABELS = HANDLING_LABELS
JUDGMENT_LABELS = ["risk_event", "not_risk_event", "insufficient_evidence"]


def eval_binary(targets: list[int], preds: list[int], probs: list[float] | None = None) -> dict[str, float | None]:
    tp = sum(1 for t, p in zip(targets, preds) if t == 1 and p == 1)
    tn = sum(1 for t, p in zip(targets, preds) if t == 0 and p == 0)
    fp = sum(1 for t, p in zip(targets, preds) if t == 0 and p == 1)
    fn = sum(1 for t, p in zip(targets, preds) if t == 1 and p == 0)
    total = len(targets) or 1
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    fpr = fp / (fp + tn) if fp + tn else 0.0
    return {
        "accuracy": (tp + tn) / total,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "fpr": fpr,
        "auprc": auprc(targets, probs) if probs is not None else None,
    }


def macro_f1(targets: Sequence[str], preds: Sequence[str], labels: Sequence[str]) -> float:
    scores: list[float] = []
    for label in labels:
        tp = sum(1 for t, p in zip(targets, preds) if t == label and p == label)
        fp = sum(1 for t, p in zip(targets, preds) if t != label and p == label)
        fn = sum(1 for t, p in zip(targets, preds) if t == label and p != label)
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        scores.append(2 * precision * recall / (precision + recall) if precision + recall else 0.0)
    return sum(scores) / len(scores) if scores else 0.0


def confusion_matrix(targets: Sequence[str], preds: Sequence[str], labels: Sequence[str]) -> list[list[int]]:
    idx = {label: i for i, label in enumerate(labels)}
    matrix = [[0 for _ in labels] for _ in labels]
    for target, pred in zip(targets, preds):
        if target in idx and pred in idx:
            matrix[idx[target]][idx[pred]] += 1
    return matrix


def eval_multi_field(targets: list[dict[str, Any]], preds: list[dict[str, Any]], metas: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    metas = metas or [{} for _ in targets]

    def _action(d: dict[str, Any]) -> str:
        return d.get("recommended_action") or d.get("handling_suggestion", "")

    def _judgment(d: dict[str, Any]) -> str:
        return d.get("event_judgment") or d.get("final_judgment", "")

    def _topic(d: dict[str, Any]) -> str:
        return d.get("event_topic") or d.get("topic", "unknown")

    risk_t = [t["risk_level"] for t in targets]
    risk_p = [p["risk_level"] for p in preds]
    hand_t = [_action(t) for t in targets]
    hand_p = [_action(p) for p in preds]
    judg_t = [_judgment(t) for t in targets]
    judg_p = [_judgment(p) for p in preds]
    per_topic: dict[str, list[int]] = defaultdict(list)
    for tg, pd, meta in zip(targets, preds, metas):
        topic = meta.get("topic") or meta.get("event_topic") or _topic(tg)
        per_topic[topic].append(int(tg["risk_level"] == pd["risk_level"]))

    emergency_fp = sum(
        1
        for t, p in zip(targets, preds)
        if _action(t) != "emergency_review" and _action(p) == "emergency_review"
    )
    emergency_tn_like = sum(1 for t in targets if _action(t) != "emergency_review") or 1

    return {
        "risk_macro_f1": macro_f1(risk_t, risk_p, RISK_LABELS),
        "handling_macro_f1": macro_f1(hand_t, hand_p, ACTION_LABELS),
        "action_macro_f1": macro_f1(hand_t, hand_p, ACTION_LABELS),
        "judgment_macro_f1": macro_f1(judg_t, judg_p, JUDGMENT_LABELS),
        "emergency_review_fpr": emergency_fp / emergency_tn_like,
        "risk_confusion_matrix": confusion_matrix(risk_t, risk_p, RISK_LABELS),
        "handling_confusion_matrix": confusion_matrix(hand_t, hand_p, ACTION_LABELS),
        "risk_per_topic_acc": {k: sum(v) / len(v) for k, v in per_topic.items()},
    }


def auprc(targets: Sequence[int], probs: Sequence[float]) -> float:
    """Average precision (AUPRC) with tie-grouped scores.

    相同分数的样本按整组处理（组内同时更新 tp/fp），并列排序顺序不会影响结果：
    全并列的随机预测返回 0.5（旧实现把正样本排在并列组前面，会错误地返回 1.0）。
    口径为不插值的 average precision（AP），与 sklearn `average_precision_score` 语义一致。
    """
    if not targets:
        return 0.0
    positives = sum(1 for t in targets if t == 1)
    if positives == 0:
        return 0.0
    order = sorted(range(len(targets)), key=lambda i: float(probs[i]), reverse=True)
    ap = 0.0
    tp = 0
    fp = 0
    i = 0
    n = len(order)
    while i < n:
        j = i + 1
        score = float(probs[order[i]])
        while j < n and float(probs[order[j]]) == score:
            j += 1
        group_tp = 0
        group_fp = 0
        for k in range(i, j):
            if targets[order[k]] == 1:
                group_tp += 1
            else:
                group_fp += 1
        recall_delta = group_tp / positives
        precision = (tp + group_tp) / (tp + group_tp + fp + group_fp)
        ap += precision * recall_delta
        tp += group_tp
        fp += group_fp
        i = j
    return ap


def percentile(sorted_values: Sequence[float], p: float) -> float:
    """Linear-interpolation percentile on ascending-sorted values.

    全仓库统一的 P 分位口径：位置 (len-1)*p 线性插值，由 rollout/monitoring
    共用，避免"向下取整索引"与"quantiles 插值"两套算法并存（P2-50）。
    """
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return float(sorted_values[0])
    pos = (len(sorted_values) - 1) * p
    lo = int(pos)
    hi = min(lo + 1, len(sorted_values) - 1)
    frac = pos - lo
    return float(sorted_values[lo]) * (1.0 - frac) + float(sorted_values[hi]) * frac


def fleiss_kappa(matrix: Sequence[Sequence[int | float]]) -> float:
    rows = [list(map(float, row)) for row in matrix]
    if not rows:
        return 0.0
    n = sum(rows[0])
    if n <= 1:
        return 0.0
    # Fleiss Kappa 要求每个样本被相同数量的评估者评分；ragged 矩阵会算错，显式拒绝（P2-49）。
    for row in rows:
        if abs(sum(row) - n) > 1e-9:
            raise ValueError(
                "fleiss_kappa requires every item to be rated by the same number "
                "of raters (ragged matrices are unsupported)"
            )
    p_i = [(sum(x * x for x in row) - n) / (n * (n - 1)) for row in rows]
    p_bar = sum(p_i) / len(p_i)
    col_count = len(rows[0])
    p_j = [sum(row[j] for row in rows) / (len(rows) * n) for j in range(col_count)]
    p_e = sum(x * x for x in p_j)
    return (p_bar - p_e) / (1 - p_e + 1e-12)


def ordinal_krippendorff_alpha(annotations: Sequence[Sequence[float | None]]) -> float:
    """Krippendorff alpha with the interval (squared-difference) distance.

    口径声明（P2-48）：本实现为 interval 度量变体（d^2 距离 + 简化 D_e≈2*方差），
    用于有序风险标签的一致性评估，与标准 coincidence 矩阵实现存在可忽略的
    数值差异；文档中的 0.71 由数据与审核团队按标准口径产出，本函数仅作工程侧近似参考。
    """
    rows = [list(row) for row in annotations]
    if not rows or not rows[0]:
        return 0.0
    pairs: list[tuple[float, float]] = []
    for col in range(len(rows[0])):
        values = [row[col] for row in rows if row[col] is not None]
        for i, x in enumerate(values):
            for j, y in enumerate(values):
                if i != j:
                    pairs.append((float(x), float(y)))
    if not pairs:
        return 0.0
    d_o = sum((x - y) ** 2 for x, y in pairs) / len(pairs)
    flat = [float(x) for row in rows for x in row if x is not None]
    all_pairs = [(x, y) for x in flat for y in flat]
    d_e = sum((x - y) ** 2 for x, y in all_pairs) / len(all_pairs)
    return 1 - d_o / (d_e + 1e-12)

