from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .evaluation import eval_binary, eval_multi_field


REQUIRED_DELIVERY_FILES = {
    "公开数据接入说明": "docs/PUBLIC_DATASET_XGUARD.md",
    "公开实现边界评审": "docs/ENTERPRISE_READINESS_REVIEW.md",
    "训练与评测流程": "docs/TRAINING_AND_EVALUATION.md",
    "训练前 readiness": "src/im_guard_ml/training_readiness.py",
    "训练前 readiness 测试": "tests/test_training_readiness.py",
    "人审与灰度治理": "docs/HUMAN_REVIEW_AND_ROLLOUT.md",
    "SLO 与告警": "docs/SLO_AND_ALERTING.md",
    "部署和运维说明": "docs/DEPLOYMENT_AND_OPERATIONS.md",
    "API 使用说明": "docs/API_USAGE.md",
    "命令手册": "docs/COMMANDS.md",
    "策略变更记录": "docs/POLICY_CHANGELOG.md",
    "本地 UTF-8 环境根因": "docs/LOCAL_ENV_ROOT_CAUSE.md",
    "GitHub CI 质量门禁": ".github/workflows/ci.yml",
    "API 契约导出与校验": "src/im_guard_ml/api_contract.py",
    "生产环境 preflight 检查": "src/im_guard_ml/preflight.py",
    "模型注册表": "configs/model_registry.yaml",
    "模型注册表校验": "src/im_guard_ml/model_registry.py",
    "A/B 灰度对比实现": "src/im_guard_ml/rollout.py",
    "Dockerfile": "deploy/Dockerfile",
    "Docker Compose": "deploy/docker-compose.example.yml",
    "K8s 模板": "deploy/k8s/deployment.yaml",
    "部署模板测试": "tests/test_deployment_templates.py",
    "Prometheus 告警": "deploy/prometheus/im_guard_alerts.yaml",
    "XGuard 下载脚本": "scripts/download_xguard_dataset.py",
    "API 压测脚本": "scripts/benchmark_api.py",
    "API 压测脚本测试": "tests/test_benchmark_api.py",
}

EXPECTED_GITIGNORE_ENTRIES = ["data/external/", "data/train/", "outputs/"]

LOCAL_DATA_FILES = {
    "XGuard 原始公开数据": "data/external/xguard_train_open_200k.jsonl",
    "XGuard 转换后训练集": "data/train/xguard_public_train.jsonl",
    "XGuard train split": "data/train/xguard_splits/train.jsonl",
    "XGuard val split": "data/train/xguard_splits/val.jsonl",
    "XGuard test split": "data/train/xguard_splits/test.jsonl",
}


def build_offline_eval_report(rows: list[dict[str, Any]], *, title: str = "AI-IM-Guard-ML 离线评测报告") -> str:
    pairs = [row for row in rows if "label" in row and "prediction" in row]
    gold = [row["label"] for row in pairs]
    pred = [row["prediction"] for row in pairs]
    metas = [{"topic": row.get("label", {}).get("topic", "unknown")} for row in pairs]
    binary_targets = [1 if x["final_judgment"] == "exist_violation" else 0 for x in gold]
    binary_preds = [1 if x["final_judgment"] == "exist_violation" else 0 for x in pred]
    binary = eval_binary(binary_targets, binary_preds)
    multi = eval_multi_field(gold, pred, metas)
    versions = _collect_versions(pred)
    lines = [
        f"# {title}",
        "",
        f"- 生成时间：{datetime.now(UTC).isoformat()}",
        f"- 样本数：{len(pairs)}",
        "",
        "## 版本信息",
        "",
    ]
    if versions:
        lines.extend(f"- `{k}`：`{v}`" for k, v in sorted(versions.items()))
    else:
        lines.append("- 未在 prediction 中发现版本字段。")
    lines.extend(
        [
            "",
            "## 二分类指标",
            "",
            "| 指标 | 数值 |",
            "| --- | ---: |",
        ]
    )
    for key in ["accuracy", "precision", "recall", "f1", "fpr", "auprc"]:
        value = binary.get(key)
        lines.append(f"| {key} | {_fmt(value)} |")
    lines.extend(
        [
            "",
            "## 多字段指标",
            "",
            "| 指标 | 数值 |",
            "| --- | ---: |",
            f"| risk_macro_f1 | {_fmt(multi['risk_macro_f1'])} |",
            f"| handling_macro_f1 | {_fmt(multi['handling_macro_f1'])} |",
            "",
            "## 主题维度风险等级准确率",
            "",
            "| topic | accuracy |",
            "| --- | ---: |",
        ]
    )
    for topic, acc in sorted(multi.get("risk_per_topic_acc", {}).items()):
        lines.append(f"| {topic} | {_fmt(acc)} |")
    lines.extend(
        [
            "",
            "## 说明",
            "",
            "公开二分类数据只用于安全识别底座评估，不应单独证明 `limit_account` 或 `ban_account` 强处置能力。",
            "",
        ]
    )
    return "\n".join(lines)


def _collect_versions(preds: list[dict[str, Any]]) -> dict[str, str]:
    keys = ["model_version", "prompt_version", "rubric_version", "feature_schema_version", "postprocess_version"]
    versions: dict[str, str] = {}
    for pred in preds:
        for key in keys:
            if key in pred and key not in versions:
                versions[key] = str(pred[key])
    return versions


def _fmt(value: Any) -> str:
    if value is None:
        return "N/A"
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def build_delivery_summary(project_root: str | Path = ".") -> str:
    root = Path(project_root)
    lines = [
        "# AI-IM-Guard-ML 企业级生产化交付摘要",
        "",
        f"- 生成时间：{datetime.now(UTC).isoformat()}",
        "",
        "## 交付项检查",
        "",
        "| 交付项 | 路径 | 状态 |",
        "| --- | --- | --- |",
    ]
    for name, rel in REQUIRED_DELIVERY_FILES.items():
        status = "ok" if (root / rel).exists() else "missing"
        lines.append(f"| {name} | `{rel}` | {status} |")
    lines.extend(
        [
            "",
            "## 已覆盖能力",
            "",
            "- 公开安全训练数据下载、映射、去重、拆分和审计。",
            "- dev/serve 依赖、本地 UTF-8 环境说明和全量测试。",
            "- FastAPI 鉴权、最小 RBAC、请求大小限制、基础限流、结构化错误、ready 检查。",
            "- JSONL/SQLite 审计持久化、按 ticket 查询、输入摘要和 PII 脱敏。",
            "- Prometheus 指标、SLO、告警规则、轻量压测脚本。",
            "- API 契约门禁、生产 preflight、模型注册表校验和 API 轻量压测门禁。",
            "- Docker、Compose、K8s 模板、人审复核、灰度/A/B 和回滚治理文档。",
            "",
            "## 仍需真实生产平台补齐",
            "",
            "- 真实 IM 私聊、人审、申诉和客诉样本。",
            "- 生产网关、密钥轮换、集中权限和租户隔离。",
            "- PostgreSQL/日志平台集中审计、归档和合规留存。",
            "- 模型注册、审批、线上 A/B 平台和真实 K8s 灰度发布。",
            "",
        ]
    )
    return "\n".join(lines)


def build_readiness_check(project_root: str | Path = ".") -> dict[str, Any]:
    """Return a machine-readable production-demo readiness check."""
    root = Path(project_root)
    checks: list[dict[str, Any]] = []

    def add_check(name: str, status: str, category: str, *, detail: str = "", path: str | None = None) -> None:
        item: dict[str, Any] = {"name": name, "category": category, "status": status}
        if path:
            item["path"] = path
        if detail:
            item["detail"] = detail
        checks.append(item)

    for name, rel in REQUIRED_DELIVERY_FILES.items():
        exists = (root / rel).exists()
        add_check(name, "pass" if exists else "fail", "required_artifact", path=rel)

    gitignore = root / ".gitignore"
    if not gitignore.exists():
        add_check(".gitignore 存在", "fail", "repo_hygiene", path=".gitignore")
    else:
        text = gitignore.read_text(encoding="utf-8")
        for entry in EXPECTED_GITIGNORE_ENTRIES:
            add_check(
                f".gitignore 忽略 {entry}",
                "pass" if entry in text else "fail",
                "repo_hygiene",
                path=".gitignore",
            )

    for name, rel in LOCAL_DATA_FILES.items():
        exists = (root / rel).exists()
        add_check(
            name,
            "pass" if exists else "warn",
            "local_data",
            detail="本地数据文件不应提交到 git；缺失时请运行下载/转换命令。" if not exists else "",
            path=rel,
        )

    remaining_external_requirements = [
        "真实 IM 私聊、人审、申诉和客诉样本仍需来自业务闭环。",
        "生产网关、密钥轮换、集中权限和租户隔离需接入企业基础设施。",
        "集中审计存储、归档、合规留存和日志平台需在生产环境落地。",
        "模型注册、审批、线上 A/B 平台和真实 K8s 灰度发布需外部平台配合。",
    ]
    fail_count = sum(1 for check in checks if check["status"] == "fail")
    warn_count = sum(1 for check in checks if check["status"] == "warn")
    status = "fail" if fail_count else "warn" if warn_count else "pass"
    return {
        "status": status,
        "generated_at": datetime.now(UTC).isoformat(),
        "project_root": str(root),
        "summary": {
            "pass": sum(1 for check in checks if check["status"] == "pass"),
            "warn": warn_count,
            "fail": fail_count,
            "total": len(checks),
        },
        "checks": checks,
        "remaining_external_requirements": remaining_external_requirements,
    }
