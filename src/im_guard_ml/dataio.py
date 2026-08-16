from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable


def read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    with Path(path).open("r", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                items.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL at {path}:{line_no}: {exc}") from exc
    return items


def write_jsonl(path: str | Path, rows: Iterable[dict[str, Any]]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def load_yaml(path: str | Path) -> dict[str, Any]:
    try:
        import yaml
    except ModuleNotFoundError:
        from .config import DEFAULT_CONFIG

        if Path(path).name == "default.yaml":
            return DEFAULT_CONFIG
        raise
    with Path(path).open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def stratified_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    summary: dict[str, Any] = {"total": len(rows), "by_source": {}, "by_topic": {}, "by_label": {}}
    for row in rows:
        label = row.get("label", {})
        source = row.get("source", "unknown")
        topic = label.get("topic", "无主题")
        final = label.get("final_judgment", "unknown")
        summary["by_source"][source] = summary["by_source"].get(source, 0) + 1
        summary["by_topic"][topic] = summary["by_topic"].get(topic, 0) + 1
        summary["by_label"][final] = summary["by_label"].get(final, 0) + 1
    return summary
