from __future__ import annotations

from pathlib import Path
from typing import Any

DEFAULT_RUBRICS_FILE = "configs/rubrics.yaml"

DEFAULT_CONFIG = {
    "model": {
        # 统一模型口径（2026-08-18 定稿）：主模型 Qwen3-32B，LoRA 多任务 SFT。
        "base_model": "Qwen/Qwen3-32B",
        "max_seq_length": 8192,
        "max_new_tokens": 384,
        "do_sample": False,
    },
    "versions": {
        # 与 configs/model_registry.yaml 的 current_stable 保持一致。
        "model_version": "heuristic-public-v0",
        "prompt_version": "prompt-v1",
        "rubric_version": "rubric-v1",
        "feature_schema_version": "feature-schema-v1",
        "postprocess_version": "postprocess-v1",
    },
    "alert_thresholds": {
        "ban_account_rate_warn": 0.08,
        "ban_account_rate_critical": 0.12,
        "parse_non_ok_rate_warn": 0.005,
        "parse_non_ok_rate_critical": 0.02,
        "empty_behavior_rate_warn": 0.05,
        "empty_behavior_rate_critical": 0.15,
        "gift_total_value_mean_delta_warn": 1000.0,
        "gift_total_value_mean_delta_critical": 3000.0,
    },
    "training": {
        "output_dir": "outputs/im-audit-judge",
        "num_train_epochs": 2,
        # 统一模型口径（2026-08-18 定稿）：LoRA 学习率 1e-4，全局 Batch Size 64（4 x 16）。
        "learning_rate": 0.0001,
        "per_device_train_batch_size": 4,
        "gradient_accumulation_steps": 16,
        "warmup_ratio": 0.03,
        "bf16": True,
        "gradient_checkpointing": True,
        "completion_only": True,
        "enable_field_loss_mask": True,
        "peft": {
            "enabled": True,
            "method": "lora",
            "r": 16,
            "lora_alpha": 32,
            "lora_dropout": 0.05,
            # 统一模型口径（2026-08-18 定稿）：仅注意力线性层。
            "target_modules": ["q_proj", "k_proj", "v_proj", "o_proj"],
            "qlora_4bit": False,
        },
    },
    "labels": {
        "risk_levels": ["low_risk", "mid_risk", "high_risk"],
        "judgments": ["not_exist_violation", "exist_violation"],
        "handling_suggestions": ["ignore", "warning", "limit_account", "ban_account"],
        "topics": [
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
        ],
    },
    "rubrics": {
        "__default__": "low_risk: 风险极低，日常社交或证据不足；mid_risk: 中等风险，语义或行为存在倾向但证据链不完整；high_risk: 高风险，语义和行为双证据链完整，或属于明确禁止类目。",
        "代刷/包榜": "low_risk: 仅讨论榜单玩法或正常送礼，无代刷意向；mid_risk: 暗示冲榜、返利、互送或老规矩，但金额、时间、对象不完整；high_risk: 明确约定金额、榜单位次或时间，且行为侧出现突发大额打赏。",
        "诈骗引流": "low_risk: 普通社交联系方式交换，无收益承诺或欺骗要素；mid_risk: 出现外部联系方式、项目收益暗示或批量投递迹象；high_risk: 明确诱导转外部平台并承诺收益、索取本金、押金或敏感信息。",
        "私下交易": "low_risk: 平台内正常消费咨询；mid_risk: 试探私下折扣、外部结算或规避平台抽成；high_risk: 明确达成平台外交易、收款方式、金额或交付安排。",
    },
}


def merge_rubrics_file(
    cfg: dict[str, Any], rubrics_path: str | Path = DEFAULT_RUBRICS_FILE
) -> dict[str, Any]:
    """把 configs/rubrics.yaml 的逐主题 rubric 合并进配置（P1-07）。

    此前 rubrics.yaml 全仓库零引用、运行时 8/11 主题回退 __default__；
    现在 cli 与 api 加载配置后统一调用本函数，11 类主题均获得细分 rubric。
    文件缺失时保留原配置（rubrics.yaml 为可选的公开代表性子集）。
    """
    from .dataio import load_yaml

    rubrics_file = load_yaml(rubrics_path)
    topics_rubrics = rubrics_file.get("topics") if isinstance(rubrics_file, dict) else None
    if isinstance(topics_rubrics, dict):
        merged = dict(cfg.get("rubrics", {}))
        for topic, entry in topics_rubrics.items():
            if isinstance(entry, dict):
                # rubrics.yaml 的主题条目为 {subtopics, low/mid/high_risk} 结构，
                # 渲染成与 default.yaml 一致的文本 rubric 再合并。
                merged[topic] = (
                    f"low_risk: {entry.get('low_risk', '')}；"
                    f"mid_risk: {entry.get('mid_risk', '')}；"
                    f"high_risk: {entry.get('high_risk', '')}"
                )
            elif isinstance(entry, str):
                merged[topic] = entry
        cfg = dict(cfg)
        cfg["rubrics"] = merged
    return cfg
