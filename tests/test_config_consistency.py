"""口径一致性测试：锁定 AutoCare 领域口径，防止 IM 旧口径回流。

统一口径：
- 主模型 Qwen3-32B，LoRA 多任务 SFT；
- 学习率 1e-4；Epoch 2；全局 Batch Size 64；max_seq 8192；BF16；
- LoRA r=16 / alpha=32 / dropout=0.05 / target=[q_proj, k_proj, v_proj, o_proj]；
- 9 类车辆风险主题 + 无风险事件。
"""

from pathlib import Path

import yaml

from im_guard_ml.config import DEFAULT_CONFIG
from im_guard_ml.schema import EVENT_TOPICS, TOPICS

ROOT = Path(__file__).resolve().parents[1]

FINALIZED_TOPICS = [
    "动力电池与热安全",
    "充电与高压系统异常",
    "制动与转向异常",
    "行驶中动力异常",
    "智能驾驶与驾驶辅助反馈",
    "车机、座舱和远程控车故障",
    "重复维修与问题未解决",
    "道路救援与人员安全",
    "质保、零部件与服务争议",
    "无风险事件",
]

OLD_MODEL_MARKERS = [
    "27B", "27b", "35B", "35b",
    "Qwen3.5", "qwen3.5", "Qwen3.6", "qwen3.6",
    "qwen35-27b", "im-judge-qwen27b", "Qwen2.5-7B",
]
OLD_LEARNING_RATES = [0.000002, 0.000001, 2e-6, 1e-6, 2.0e-5]
IM_TOPIC_MARKERS = ["代刷/包榜", "色情诱导", "诈骗引流", "ban_account", "exist_violation"]


def _load_default_yaml() -> dict:
    return yaml.safe_load((ROOT / "configs" / "default.yaml").read_text(encoding="utf-8"))


def test_default_yaml_matches_finalized_model_config():
    cfg = _load_default_yaml()

    assert cfg["model"]["base_model"] == "Qwen/Qwen3-32B"
    assert cfg["model"]["max_seq_length"] == 8192
    assert cfg["model"]["max_new_tokens"] == 512
    assert cfg["model"]["do_sample"] is False


def test_default_yaml_matches_finalized_training_config():
    training = _load_default_yaml()["training"]

    assert training["learning_rate"] == 0.0001
    assert training["num_train_epochs"] == 2
    assert training["per_device_train_batch_size"] == 4
    assert training["gradient_accumulation_steps"] == 16
    assert training["per_device_train_batch_size"] * training["gradient_accumulation_steps"] == 64
    assert training["warmup_ratio"] == 0.03
    assert training["bf16"] is True
    assert training["gradient_checkpointing"] is True
    assert training["completion_only"] is True
    assert training["enable_field_loss_mask"] is True


def test_default_yaml_lora_matches_finalized_config():
    peft = _load_default_yaml()["training"]["peft"]

    assert peft["enabled"] is True
    assert peft["method"] == "lora"
    assert peft["r"] == 16
    assert peft["lora_alpha"] == 32
    assert peft["lora_dropout"] == 0.05
    assert peft["target_modules"] == ["q_proj", "k_proj", "v_proj", "o_proj"]
    assert peft["qlora_4bit"] is False


def test_default_yaml_topics_match_autocare():
    labels = _load_default_yaml()["labels"]
    assert labels["event_topics"] == FINALIZED_TOPICS
    assert labels["topics"] == FINALIZED_TOPICS
    assert labels["recommended_actions"] == [
        "information_reply",
        "collect_more_evidence",
        "service_followup",
        "create_work_order",
        "expert_review",
        "emergency_review",
    ]


def _collapse(value: str) -> str:
    return "".join(value.split())


def test_default_config_mirrors_default_yaml():
    cfg = _load_default_yaml()

    assert DEFAULT_CONFIG["model"] == cfg["model"]
    assert DEFAULT_CONFIG["training"] == cfg["training"]
    assert DEFAULT_CONFIG["labels"] == cfg["labels"]
    assert {k: _collapse(v) for k, v in DEFAULT_CONFIG["rubrics"].items()} == {
        k: _collapse(v) for k, v in cfg["rubrics"].items()
    }


def test_no_old_model_markers_in_code_defaults():
    for rel in ("configs/default.yaml", "configs/model_registry.yaml", "configs/rollout.yaml"):
        text = (ROOT / rel).read_text(encoding="utf-8")
        for marker in OLD_MODEL_MARKERS:
            assert marker not in text, f"旧模型口径 {marker} 不应出现在 {rel}"
        for marker in IM_TOPIC_MARKERS:
            assert marker not in text, f"IM 旧口径 {marker} 不应出现在 {rel}"

    assert DEFAULT_CONFIG["model"]["base_model"] == "Qwen/Qwen3-32B"
    training = DEFAULT_CONFIG["training"]
    assert training["learning_rate"] not in OLD_LEARNING_RATES
    assert training["learning_rate"] == 0.0001


def test_no_im_topics_in_rubrics():
    rubrics = yaml.safe_load((ROOT / "configs" / "rubrics.yaml").read_text(encoding="utf-8"))
    assert "赌博引流" not in rubrics["topics"]
    assert "代刷/包榜" not in rubrics["topics"]
    assert "动力电池与热安全" in rubrics["topics"]


def test_schema_topics_equal_finalized_and_config_topics():
    assert TOPICS == FINALIZED_TOPICS
    assert EVENT_TOPICS == FINALIZED_TOPICS
    assert _load_default_yaml()["labels"]["event_topics"] == list(TOPICS)


def test_model_version_unified_heuristic_public_v0():
    assert _load_default_yaml()["versions"]["model_version"] == "heuristic-public-v0"
    assert DEFAULT_CONFIG["versions"]["model_version"] == "heuristic-public-v0"
    registry = yaml.safe_load((ROOT / "configs" / "model_registry.yaml").read_text(encoding="utf-8"))
    assert registry["current_stable"] == "heuristic-public-v0"
    rollout = yaml.safe_load((ROOT / "configs" / "rollout.yaml").read_text(encoding="utf-8"))
    assert rollout["ab_test"]["control_model_version"] == "heuristic-public-v0"
    assert "emergency_review_fpr" in rollout["ab_test"]["success_metrics"]
    assert "emergency_review_fpr_max" in rollout["ab_test"]["guardrails"]


def test_alert_thresholds_use_emergency_not_ban():
    thresholds = _load_default_yaml()["alert_thresholds"]
    assert "emergency_review_rate_warn" in thresholds
    assert "missing_vehicle_evidence_rate_warn" in thresholds
    assert "missing_vehicle_evidence_mean_delta_warn" in thresholds
    assert "unsupported_evidence_rate_warn" not in thresholds
    assert "ban_account_rate_warn" not in thresholds


def test_gitignore_blocks_private_and_outputs_directories():
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "private/" in gitignore
    assert "outputs/" in gitignore
    assert "data/local/" in gitignore
