from __future__ import annotations

from collections import defaultdict
from typing import Any, Sequence

RISK_LABELS = ["low_risk", "mid_risk", "high_risk"]
HANDLING_LABELS = ["ignore", "warning", "limit_account", "ban_account"]


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
    risk_t = [t["risk_level"] for t in targets]
    risk_p = [p["risk_level"] for p in preds]
    hand_t = [t["handling_suggestion"] for t in targets]
    hand_p = [p["handling_suggestion"] for p in preds]
    per_topic: dict[str, list[int]] = defaultdict(list)
    for tg, pd, meta in zip(targets, preds, metas):
        topic = meta.get("topic", tg.get("topic", "unknown"))
        per_topic[topic].append(int(tg["risk_level"] == pd["risk_level"]))
    return {
        "risk_macro_f1": macro_f1(risk_t, risk_p, RISK_LABELS),
        "handling_macro_f1": macro_f1(hand_t, hand_p, HANDLING_LABELS),
        "risk_confusion_matrix": confusion_matrix(risk_t, risk_p, RISK_LABELS),
        "handling_confusion_matrix": confusion_matrix(hand_t, hand_p, HANDLING_LABELS),
        "risk_per_topic_acc": {k: sum(v) / len(v) for k, v in per_topic.items()},
    }


def auprc(targets: Sequence[int], probs: Sequence[float]) -> float:
    pairs = sorted(zip(probs, targets), reverse=True)
    positives = sum(targets)
    if positives == 0:
        return 0.0
    tp = 0
    fp = 0
    points: list[tuple[float, float]] = [(1.0, 0.0)]
    for _score, target in pairs:
        if target == 1:
            tp += 1
        else:
            fp += 1
        precision = tp / (tp + fp)
        recall = tp / positives
        points.append((precision, recall))
    area = 0.0
    for (p0, r0), (p1, r1) in zip(points, points[1:]):
        area += (r1 - r0) * ((p0 + p1) / 2)
    return area


def fleiss_kappa(matrix: Sequence[Sequence[int | float]]) -> float:
    rows = [list(map(float, row)) for row in matrix]
    if not rows:
        return 0.0
    n = sum(rows[0])
    if n <= 1:
        return 0.0
    p_i = [(sum(x * x for x in row) - n) / (n * (n - 1)) for row in rows]
    p_bar = sum(p_i) / len(p_i)
    col_count = len(rows[0])
    p_j = [sum(row[j] for row in rows) / (len(rows) * n) for j in range(col_count)]
    p_e = sum(x * x for x in p_j)
    return (p_bar - p_e) / (1 - p_e + 1e-12)


def ordinal_krippendorff_alpha(annotations: Sequence[Sequence[float | None]]) -> float:
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

