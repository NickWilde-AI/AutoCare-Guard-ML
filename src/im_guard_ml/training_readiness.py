from __future__ import annotations

import importlib.util
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .dataio import load_yaml


REQUIRED_TRAIN_MODULES = ["datasets", "torch", "transformers", "trl", "peft"]


def build_training_readiness_report(
    dataset_path: str | Path,
    *,
    config_path: str | Path = "configs/default.yaml",
    max_scan_rows: int | None = None,
) -> dict[str, Any]:
    """Build a machine-readable preflight report before launching SFT.

    The report intentionally does not import heavyweight ML libraries unless
    they are installed. This keeps the check useful on CI and laptops where
    the train extra is not present yet.
    """
    dataset = Path(dataset_path)
    cfg = load_yaml(config_path)
    checks: list[dict[str, Any]] = []

    def add(name: str, status: str, detail: str = "", **extra: Any) -> None:
        item: dict[str, Any] = {"name": name, "status": status}
        if detail:
            item["detail"] = detail
        item.update(extra)
        checks.append(item)

    add(
        "dataset_exists",
        "pass" if dataset.exists() else "fail",
        path=str(dataset),
    )
    dataset_stats = _scan_dataset(dataset, max_rows=max_scan_rows) if dataset.exists() else {}
    if dataset_stats:
        add("dataset_rows", "pass" if dataset_stats["rows"] > 0 else "fail", rows=dataset_stats["rows"])
        add(
            "public_binary_guardrail",
            "pass" if dataset_stats["public_strong_handling_count"] == 0 else "fail",
            detail="public_binary samples must not train limit_account or ban_account.",
            public_strong_handling_count=dataset_stats["public_strong_handling_count"],
        )
        add(
            "label_parse_errors",
            "pass" if dataset_stats["label_parse_errors"] == 0 else "fail",
            label_parse_errors=dataset_stats["label_parse_errors"],
        )

    module_status = _module_status(REQUIRED_TRAIN_MODULES)
    missing = [name for name, present in module_status.items() if not present]
    add(
        "train_dependencies",
        "pass" if not missing else "fail",
        detail="Install with `pip install -e \".[train]\"`." if missing else "",
        missing=missing,
    )

    hardware = _hardware_status(module_status.get("torch", False))
    add(
        "accelerator",
        hardware["status"],
        detail=hardware["detail"],
        device=hardware["device"],
    )

    model_name = str(cfg.get("model", {}).get("base_model", ""))
    add(
        "model_config",
        "warn" if "27B" in model_name.upper() and hardware["device"] in {"cpu", "none"} else "pass",
        detail="Qwen 27B SFT needs GPU-class training hardware; use LoRA/QLoRA on a GPU box or switch to a small smoke-test model."
        if "27B" in model_name.upper() and hardware["device"] in {"cpu", "none"}
        else "",
        base_model=model_name,
        max_seq_length=cfg.get("model", {}).get("max_seq_length"),
        peft=cfg.get("training", {}).get("peft", {}),
    )

    fail_count = sum(1 for check in checks if check["status"] == "fail")
    warn_count = sum(1 for check in checks if check["status"] == "warn")
    status = "fail" if fail_count else "warn" if warn_count else "pass"
    return {
        "status": status,
        "generated_at": datetime.now(UTC).isoformat(),
        "config_path": str(config_path),
        "dataset_path": str(dataset),
        "dataset": dataset_stats,
        "checks": checks,
        "summary": {
            "pass": sum(1 for check in checks if check["status"] == "pass"),
            "warn": warn_count,
            "fail": fail_count,
            "total": len(checks),
        },
        "recommended_commands": [
            'pip install -e ".[train]"',
            f"LC_ALL=en_US.UTF-8 LANG=en_US.UTF-8 im-guard --config {config_path} train {dataset}",
        ],
        "training_task": {
            "objective": "Learn structured IM-risk audit JSON outputs from multi-evidence inputs.",
            "primary_supervision": "final_judgment for public_binary samples; full risk/handling supervision only for internal or reviewed business samples.",
            "open_source_boundary": "XGuard is suitable for cold-start safety recognition and data-pipeline demonstration, not for claiming real IM production performance.",
        },
    }


def _module_status(names: list[str]) -> dict[str, bool]:
    return {name: importlib.util.find_spec(name) is not None for name in names}


def _hardware_status(torch_available: bool) -> dict[str, str]:
    if not torch_available:
        return {"status": "warn", "device": "none", "detail": "torch is not installed; hardware cannot be inspected."}
    try:
        import torch

        if torch.cuda.is_available():
            return {"status": "pass", "device": "cuda", "detail": "CUDA is available."}
        mps = getattr(torch.backends, "mps", None)
        if mps is not None and mps.is_available():
            return {"status": "warn", "device": "mps", "detail": "MPS is available; large LLM SFT is still likely impractical."}
        return {"status": "warn", "device": "cpu", "detail": "Only CPU is available; full LLM SFT is not practical."}
    except Exception as exc:  # pragma: no cover - defensive for broken torch installs.
        return {"status": "warn", "device": "unknown", "detail": f"torch import failed: {exc}"}


def _scan_dataset(path: Path, *, max_rows: int | None = None) -> dict[str, Any]:
    rows = 0
    public_rows = 0
    public_strong = 0
    label_parse_errors = 0
    task_types: dict[str, int] = {}
    final_judgments: dict[str, int] = {}
    handling: dict[str, int] = {}

    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            if max_rows is not None and rows >= max_rows:
                break
            rows += 1
            try:
                row = json.loads(line)
                label = row.get("label") or {}
                task_type = str(row.get("task_type") or row.get("source_type") or "")
                task_types[task_type] = task_types.get(task_type, 0) + 1
                final = str(label.get("final_judgment") or "")
                final_judgments[final] = final_judgments.get(final, 0) + 1
                action = str(label.get("handling_suggestion") or "")
                handling[action] = handling.get(action, 0) + 1
                if task_type == "public_binary":
                    public_rows += 1
                    if action in {"limit_account", "ban_account"}:
                        public_strong += 1
            except Exception:
                label_parse_errors += 1

    return {
        "rows": rows,
        "scanned_rows": rows,
        "max_scan_rows": max_rows,
        "public_binary_rows": public_rows,
        "public_strong_handling_count": public_strong,
        "label_parse_errors": label_parse_errors,
        "task_types": task_types,
        "final_judgments": final_judgments,
        "handling_suggestions": handling,
    }
