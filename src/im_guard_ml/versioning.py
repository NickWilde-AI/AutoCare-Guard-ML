from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from .privacy import build_input_summary


@dataclass(slots=True)
class VersionInfo:
    model_version: str = "heuristic-demo-v0"
    prompt_version: str = "prompt-v1"
    rubric_version: str = "rubric-v1"
    feature_schema_version: str = "feature-schema-v1"
    postprocess_version: str = "postprocess-v1"

    def to_dict(self) -> dict[str, str]:
        return {
            "model_version": self.model_version,
            "prompt_version": self.prompt_version,
            "rubric_version": self.rubric_version,
            "feature_schema_version": self.feature_schema_version,
            "postprocess_version": self.postprocess_version,
        }


def version_info_from_config(config: dict[str, Any], model_path: str | None = None) -> VersionInfo:
    versions = config.get("versions", {})
    return VersionInfo(
        model_version=versions.get("model_version") or (model_path or "heuristic-demo-v0"),
        prompt_version=versions.get("prompt_version", "prompt-v1"),
        rubric_version=versions.get("rubric_version", "rubric-v1"),
        feature_schema_version=versions.get("feature_schema_version", "feature-schema-v1"),
        postprocess_version=versions.get("postprocess_version", "postprocess-v1"),
    )


def build_audit_log(
    case: dict[str, Any],
    prediction: dict[str, Any],
    versions: VersionInfo,
    latency_ms: float | None = None,
) -> dict[str, Any]:
    return {
        "request_id": case.get("request_id") or case.get("ticket_id", ""),
        "ticket_id": case.get("ticket_id", ""),
        "created_at": datetime.now(UTC).isoformat(),
        **versions.to_dict(),
        "latency_ms": latency_ms,
        "input_summary": build_input_summary(case),
        "prediction": prediction,
    }
