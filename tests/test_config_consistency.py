"""口径一致性测试：锁定 2026-08-18 定稿口径，防止旧口径回流。

统一口径：
- 主模型 Qwen3-32B，LoRA 多任务 SFT；
- 学习率 1e-4；Epoch 2；全局 Batch Size 64；max_seq 8192；BF16；
- LoRA r=16 / alpha=32 / dropout=0.05 / target=[q_proj, k_proj, v_proj, o_proj]；
- 11 类一级违规主题 + 无主题。
"""

from pathlib import Path

import yaml

from im_guard_ml.config import DEFAULT_CONFIG
from im_guard_ml.schema import TOPICS

ROOT = Path(__file__).resolve().parents[1]

FINALIZED_TOPICS = [
    "代刷/包榜",
    "色情诱导",
    "诈骗引流",
    "私下交易",
    "政治敏感",
    "辱骂攻击",
    "未成年保护",
    "版权侵犯",
    "虚假信息",
    "自伤诱导",
    "违禁品交易",
    "无主题",
]

# P2-24：补齐旧口径标记覆盖面（35B/Qwen3.6/qwen35-27b/im-judge-qwen27b 等）。
OLD_MODEL_MARKERS = [
    "27B", "27b", "35B", "35b",
    "Qwen3.5", "qwen3.5", "Qwen3.6", "qwen3.6",
    "qwen35-27b", "im-judge-qwen27b", "Qwen2.5-7B",
]
OLD_LEARNING_RATES = [0.000002, 0.000001, 2e-6, 1e-6, 2.0e-5]


def _load_default_yaml() -> dict:
    return yaml.safe_load((ROOT / "configs" / "default.yaml").read_text(encoding="utf-8"))


def test_default_yaml_matches_finalized_model_config():
    cfg = _load_default_yaml()

    assert cfg["model"]["base_model"] == "Qwen/Qwen3-32B"
    assert cfg["model"]["max_seq_length"] == 8192
    assert cfg["model"]["max_new_tokens"] == 384
    assert cfg["model"]["do_sample"] is False


def test_default_yaml_matches_finalized_training_config():
    training = _load_default_yaml()["training"]

    assert training["learning_rate"] == 0.0001
    assert training["num_train_epochs"] == 2
    # P2-24：锁乘积的同时锁住各自的值，防止 8x8=64 这类同乘积替换。
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


def test_default_yaml_topics_match_finalized_11_topics():
    assert _load_default_yaml()["labels"]["topics"] == FINALIZED_TOPICS


def _collapse(value: str) -> str:
    # 忽略全部空白差异（YAML 块标量会在"；"后保留换行/空格）。
    return "".join(value.split())


def test_default_config_mirrors_default_yaml():
    cfg = _load_default_yaml()

    assert DEFAULT_CONFIG["model"] == cfg["model"]
    assert DEFAULT_CONFIG["training"] == cfg["training"]
    assert DEFAULT_CONFIG["labels"] == cfg["labels"]
    # rubrics 为 YAML 块标量，与 Python 默认值仅在换行/缩进上不同，按压缩空白比较。
    assert {k: _collapse(v) for k, v in DEFAULT_CONFIG["rubrics"].items()} == {
        k: _collapse(v) for k, v in cfg["rubrics"].items()
    }


def test_no_old_model_markers_in_code_defaults():
    # P2-24：不只扫 default.yaml，把内置配置与注册表也纳入扫描。
    for rel in ("configs/default.yaml", "configs/model_registry.yaml", "configs/rollout.yaml"):
        text = (ROOT / rel).read_text(encoding="utf-8")
        for marker in OLD_MODEL_MARKERS:
            assert marker not in text, f"旧模型口径 {marker} 不应出现在 {rel}"

    assert DEFAULT_CONFIG["model"]["base_model"] == "Qwen/Qwen3-32B"
    training = DEFAULT_CONFIG["training"]
    assert training["learning_rate"] not in OLD_LEARNING_RATES
    assert training["learning_rate"] == 0.0001


def test_no_gambling_topic_in_rubrics():
    rubrics = yaml.safe_load((ROOT / "configs" / "rubrics.yaml").read_text(encoding="utf-8"))
    assert "赌博引流" not in rubrics["topics"]
    assert len(rubrics["topics"]) == 11  # 定稿 11 类一级主题，均有 rubric 细则


def test_schema_topics_equal_finalized_and_config_topics():
    # P2-24：schema.TOPICS 精确锁定，并与 default.yaml 的 labels.topics 对拍。
    assert TOPICS == FINALIZED_TOPICS
    assert _load_default_yaml()["labels"]["topics"] == list(TOPICS)


def test_model_version_unified_heuristic_public_v0():
    # P2-24：model_version 全 tests 此前零断言，现在锁死统一版本名。
    assert _load_default_yaml()["versions"]["model_version"] == "heuristic-public-v0"
    assert DEFAULT_CONFIG["versions"]["model_version"] == "heuristic-public-v0"
    registry = yaml.safe_load((ROOT / "configs" / "model_registry.yaml").read_text(encoding="utf-8"))
    assert registry["current_stable"] == "heuristic-public-v0"
    rollout = yaml.safe_load((ROOT / "configs" / "rollout.yaml").read_text(encoding="utf-8"))
    assert rollout["ab_test"]["control_model_version"] == "heuristic-public-v0"


def test_rubrics_subtopic_count_is_representative_44():
    # P1-06：公开 rubrics.yaml 为 44 个代表性子类（11 主题 x 4），
    # 完整 47 子类以内部定版 rubric 为准（文件头部注释已声明）。
    rubrics = yaml.safe_load((ROOT / "configs" / "rubrics.yaml").read_text(encoding="utf-8"))
    subtopic_total = sum(len(entry.get("subtopics", [])) for entry in rubrics["topics"].values())
    assert subtopic_total == 44
    text = (ROOT / "configs" / "rubrics.yaml").read_text(encoding="utf-8")
    assert "47" in text and "代表性" in text
