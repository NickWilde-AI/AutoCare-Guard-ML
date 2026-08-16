"""Public benchmark evaluation for cross-domain capability monitoring.

Evaluates the fine-tuned Judge on three public benchmarks to verify that
IM-specific training does not degrade general text moderation capability:

  1. ToxicChat (~2.85K): Real user-model interactions, response binary classification
  2. HarmBench (~0.4K): Adversarial prompts, verifies resistance to jailbreak
  3. XSTest (~0.45K): Safe-looking-but-actually-safe, monitors false positive rate

These public benchmarks complement user-provided IM-specific evaluation data.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .evaluation import eval_binary
from .parsing import parse_judge_output

logger = logging.getLogger(__name__)


@dataclass
class BenchmarkResult:
    """Evaluation result for a single benchmark."""
    name: str
    num_samples: int
    accuracy: float
    precision: float
    recall: float
    f1: float
    fpr: float
    auprc: float | None = None
    per_category: dict[str, float] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Benchmark loaders
# ---------------------------------------------------------------------------


def load_toxicchat(path: str | Path) -> list[dict[str, Any]]:
    """Load ToxicChat dataset.

    Expected format: JSONL with fields:
      - text / user_input: the conversation text
      - toxicity / label: 0 (safe) or 1 (toxic)
    """
    samples = _load_jsonl(path)
    normalized: list[dict[str, Any]] = []
    for row in samples:
        text = row.get("text") or row.get("user_input") or row.get("conv", "")
        label = row.get("toxicity") or row.get("label") or 0
        normalized.append({
            "content": text,
            "gold_label": int(label),
            "task_type": "response_binary",
            "source": "ToxicChat",
        })
    return normalized


def load_harmbench(path: str | Path) -> list[dict[str, Any]]:
    """Load HarmBench dataset.

    Expected format: JSONL with fields:
      - prompt: adversarial prompt
      - response: model response
      - harm_label: "safe" or "unsafe"
    """
    samples = _load_jsonl(path)
    normalized: list[dict[str, Any]] = []
    for row in samples:
        text = row.get("response") or row.get("prompt") or ""
        label_str = str(row.get("harm_label", "safe")).lower()
        label = 0 if label_str in ("safe", "0", "false") else 1
        normalized.append({
            "content": text,
            "gold_label": label,
            "task_type": "response_binary",
            "source": "HarmBench",
        })
    return normalized


def load_xstest(path: str | Path) -> list[dict[str, Any]]:
    """Load XSTest dataset (contrast set for false positive monitoring).

    Expected format: JSONL with fields:
      - prompt / text: the test prompt
      - label: "safe" or "unsafe"
      - type: "contrast" or "base" (optional)
    """
    samples = _load_jsonl(path)
    normalized: list[dict[str, Any]] = []
    for row in samples:
        text = row.get("prompt") or row.get("text") or ""
        label_str = str(row.get("label", "safe")).lower()
        label = 0 if label_str in ("safe", "0", "false") else 1
        normalized.append({
            "content": text,
            "gold_label": label,
            "task_type": "safe_unsafe",
            "source": "XSTest",
            "subset": row.get("type", "base"),
        })
    return normalized


# ---------------------------------------------------------------------------
# Evaluation pipeline
# ---------------------------------------------------------------------------


def evaluate_benchmark(
    samples: list[dict[str, Any]],
    predict_fn: Any,
    benchmark_name: str,
) -> BenchmarkResult:
    """Evaluate a predict function on a loaded benchmark.

    Args:
        samples: Loaded and normalized benchmark samples.
        predict_fn: Callable that takes a case dict and returns a prediction dict
                    with at least 'final_judgment' field.
        benchmark_name: Name for reporting.

    Returns:
        BenchmarkResult with all metrics.
    """
    targets: list[int] = []
    preds: list[int] = []
    probs: list[float] = []

    for sample in samples:
        # Build a minimal audit case for the predictor
        case = _sample_to_audit_case(sample)
        pred = predict_fn(case)

        gold = sample["gold_label"]
        pred_label = 1 if pred.get("final_judgment") == "exist_violation" else 0

        targets.append(gold)
        preds.append(pred_label)

        # Use risk_level as a proxy for violation probability
        risk = pred.get("risk_level", "low_risk")
        prob = {"high_risk": 0.9, "mid_risk": 0.6, "low_risk": 0.1}.get(risk, 0.1)
        probs.append(prob)

    metrics = eval_binary(targets, preds, probs)

    return BenchmarkResult(
        name=benchmark_name,
        num_samples=len(samples),
        accuracy=metrics["accuracy"],
        precision=metrics["precision"],
        recall=metrics["recall"],
        f1=metrics["f1"],
        fpr=metrics["fpr"],
        auprc=metrics.get("auprc"),
    )


def run_all_benchmarks(
    predict_fn: Any,
    data_dir: str | Path,
    output_path: str | Path | None = None,
) -> dict[str, BenchmarkResult]:
    """Run evaluation on all available public benchmarks.

    Looks for benchmark files in data_dir:
      - toxicchat.jsonl
      - harmbench.jsonl
      - xstest.jsonl

    Returns dict of benchmark_name -> BenchmarkResult.
    """
    data_dir = Path(data_dir)
    results: dict[str, BenchmarkResult] = {}

    benchmark_configs = [
        ("ToxicChat", "toxicchat.jsonl", load_toxicchat),
        ("HarmBench", "harmbench.jsonl", load_harmbench),
        ("XSTest", "xstest.jsonl", load_xstest),
    ]

    for name, filename, loader in benchmark_configs:
        filepath = data_dir / filename
        if not filepath.exists():
            logger.warning("Benchmark file not found: %s, skipping %s", filepath, name)
            continue

        logger.info("Evaluating %s (%s)...", name, filepath)
        samples = loader(filepath)
        result = evaluate_benchmark(samples, predict_fn, name)
        results[name] = result
        logger.info(
            "%s: F1=%.3f, FPR=%.3f, AUPRC=%s",
            name, result.f1, result.fpr,
            f"{result.auprc:.3f}" if result.auprc else "N/A",
        )

    if output_path:
        _save_results(results, output_path)

    return results


# ---------------------------------------------------------------------------
# Internal evaluation (IM-specific test sets)
# ---------------------------------------------------------------------------


def evaluate_im_test_set(
    test_data: list[dict[str, Any]],
    predict_fn: Any,
) -> dict[str, Any]:
    """Evaluate on a user-provided IM audit test set.

    Returns comprehensive metrics including:
      - final_judgment binary metrics
      - risk_level macro-F1
      - handling_suggestion macro-F1
      - per-topic accuracy
    """
    from .evaluation import eval_multi_field

    targets: list[dict[str, Any]] = []
    preds_list: list[dict[str, Any]] = []
    metas: list[dict[str, Any]] = []
    binary_targets: list[int] = []
    binary_preds: list[int] = []

    for case in test_data:
        gold = case.get("label", {})
        pred = predict_fn(case)

        targets.append(gold)
        preds_list.append(pred)
        metas.append({"topic": gold.get("topic", "无主题")})

        binary_targets.append(1 if gold.get("final_judgment") == "exist_violation" else 0)
        binary_preds.append(1 if pred.get("final_judgment") == "exist_violation" else 0)

    binary_metrics = eval_binary(binary_targets, binary_preds)
    multi_metrics = eval_multi_field(targets, preds_list, metas)

    return {
        "final_judgment": binary_metrics,
        "risk_level_macro_f1": multi_metrics["risk_macro_f1"],
        "handling_macro_f1": multi_metrics["handling_macro_f1"],
        "risk_per_topic_acc": multi_metrics.get("risk_per_topic_acc", {}),
        "num_samples": len(test_data),
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sample_to_audit_case(sample: dict[str, Any]) -> dict[str, Any]:
    """Convert a public benchmark sample to a minimal audit case format."""
    return {
        "audit_scene": {
            "chat_type": "public_text",
            "user_intimacy": "unknown",
            "behavior_key_summary": {},
        },
        "chat_evidence_list": [
            {
                "original_content": sample.get("content", ""),
                "risk_point": "公开评测集样本。",
            }
        ],
        "behavior_abnormal_list": [],
        "hint_topic": "__default__",
    }


def _load_jsonl(path: str | Path) -> list[dict[str, Any]]:
    """Load a JSONL file with error handling."""
    path = Path(path)
    samples: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                samples.append(json.loads(line))
            except json.JSONDecodeError:
                logger.warning("Skipping malformed line %d in %s", line_num, path)
    return samples


def _save_results(results: dict[str, BenchmarkResult], path: str | Path) -> None:
    """Save benchmark results to JSON."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    output = {}
    for name, result in results.items():
        output[name] = {
            "num_samples": result.num_samples,
            "accuracy": round(result.accuracy, 4),
            "precision": round(result.precision, 4),
            "recall": round(result.recall, 4),
            "f1": round(result.f1, 4),
            "fpr": round(result.fpr, 4),
            "auprc": round(result.auprc, 4) if result.auprc else None,
        }
    with path.open("w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    logger.info("Results saved to %s", path)
