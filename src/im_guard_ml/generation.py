"""Level-specific synthetic data generation pipeline.

Implements the 3-generator architecture described in the design doc:
  - Each risk_level (low/mid/high) has a dedicated generator fine-tuned on ~240
    seed cases from the ticket pool.
  - Generators produce controlled (audit_scene, chat_evidence_list,
    behavior_abnormal_list) triplets conditioned on topic + evidence combination.
  - Generated samples pass JSON Schema validation and rubric consistency checks
    before entering the training pool.

Usage:
    # Prepare seeds
    seeds = prepare_seeds(ticket_pool, per_level=240)

    # Train generators (one per risk_level)
    for level in ["low_risk", "mid_risk", "high_risk"]:
        train_generator(seeds[level], output_dir=f"ckpt/gen-{level}", ...)

    # Generate synthetic samples
    samples = generate_synthetic_batch(generator_path, topic, level, n=500)
"""

from __future__ import annotations

import json
import logging
import random
from collections import defaultdict
from typing import Any

from .schema import TOPICS, RiskLevel, validate_label

logger = logging.getLogger(__name__)

# Evidence combination types for controlled generation
EVIDENCE_COMBOS = [
    "semantic_heavy_behavior_heavy",   # 语义重 + 行为重
    "semantic_only",                    # 仅语义
    "behavior_only",                    # 仅行为
    "semantic_light_behavior_heavy",    # 语义淡 + 行为重 (灰区)
]

# Generation prompt template for the level-specific generator
GENERATOR_PROMPT = """你是一个 IM 私聊审核案例生成器。请根据以下条件生成一条完整的审核案例。

<生成条件>
目标风险等级: {risk_level}
目标违规主题: {topic}
证据组合类型: {evidence_combo}
</生成条件>

<风险等级 rubric>
{rubric}
</风险等级 rubric>

请生成一条包含以下字段的 JSON 案例：
- audit_scene: 审核场景（含 behavior_key_summary）
- chat_evidence_list: 聊天证据列表
- behavior_abnormal_list: 行为异常列表
- label: 标签（risk_level, topic, final_judgment, handling_suggestion, correlation_analysis, judgment_basis）

要求：
1. 证据内容必须符合目标风险等级的 rubric 定义
2. 证据组合类型决定语义和行为的强弱分布
3. 输出严格 JSON 格式"""


def prepare_seeds(
    ticket_pool: list[dict[str, Any]],
    per_level: int = 240,
    seed: int = 42,
) -> dict[str, list[dict[str, Any]]]:
    """Stratified sampling of seed cases for each risk_level.

    Ensures each level's seeds cover all 11 topics and multiple evidence
    combinations, providing diverse conditioning for the generator.
    """
    rng = random.Random(seed)
    by_level: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for case in ticket_pool:
        label = case.get("label", {})
        level = label.get("risk_level")
        if level in {r.value for r in RiskLevel}:
            by_level[level].append(case)

    seeds: dict[str, list[dict[str, Any]]] = {}
    for level in [r.value for r in RiskLevel]:
        pool = by_level.get(level, [])
        if not pool:
            logger.warning("No tickets for level %s, skipping seed preparation", level)
            seeds[level] = []
            continue

        # Stratify by topic to ensure coverage
        by_topic: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for case in pool:
            topic = case.get("label", {}).get("topic", "无主题")
            by_topic[topic].append(case)

        selected: list[dict[str, Any]] = []
        topics_with_data = [t for t in TOPICS if by_topic[t]]
        per_topic = max(1, per_level // max(len(topics_with_data), 1))

        for topic in topics_with_data:
            candidates = by_topic[topic]
            rng.shuffle(candidates)
            selected.extend(candidates[:per_topic])

        # Fill remaining quota from any topic
        remaining = per_level - len(selected)
        if remaining > 0:
            all_remaining = [c for c in pool if c not in selected]
            rng.shuffle(all_remaining)
            selected.extend(all_remaining[:remaining])

        seeds[level] = selected[:per_level]
        logger.info("Prepared %d seeds for %s (%d topics covered)",
                    len(seeds[level]), level, len(topics_with_data))

    return seeds


def build_generator_training_data(
    seeds: list[dict[str, Any]],
    rubrics: dict[str, str],
) -> list[dict[str, str]]:
    """Convert seed cases into (prompt, completion) pairs for generator SFT.

    Each seed becomes a training example where:
      - prompt = generation conditions (level, topic, evidence combo, rubric)
      - completion = the full case JSON
    """
    training_pairs: list[dict[str, str]] = []

    for case in seeds:
        label = case.get("label", {})
        level = label.get("risk_level", "mid_risk")
        topic = label.get("topic", "无主题")

        # Infer evidence combination from case structure
        has_chat = bool(case.get("chat_evidence_list"))
        has_behavior = bool(case.get("behavior_abnormal_list"))
        if has_chat and has_behavior:
            combo = "semantic_heavy_behavior_heavy"
        elif has_chat:
            combo = "semantic_only"
        elif has_behavior:
            combo = "behavior_only"
        else:
            combo = "semantic_only"

        rubric_text = rubrics.get(topic, rubrics.get("__default__", ""))

        prompt = GENERATOR_PROMPT.format(
            risk_level=level,
            topic=topic,
            evidence_combo=combo,
            rubric=rubric_text,
        )

        # The completion is the full case as JSON
        completion = json.dumps(case, ensure_ascii=False, indent=2)

        training_pairs.append({"prompt": prompt, "completion": completion})

    return training_pairs


def validate_generated_case(case: dict[str, Any]) -> tuple[bool, list[str]]:
    """Validate a generated case against schema and rubric consistency.

    Returns (is_valid, list_of_errors).
    """
    errors: list[str] = []

    # Required fields
    if not case.get("audit_scene"):
        errors.append("missing audit_scene")
    if not isinstance(case.get("chat_evidence_list"), list):
        errors.append("missing or invalid chat_evidence_list")
    if not isinstance(case.get("behavior_abnormal_list"), list):
        errors.append("missing or invalid behavior_abnormal_list")

    label = case.get("label")
    if not isinstance(label, dict):
        errors.append("missing label")
        return False, errors

    # Label validation
    label_errors = validate_label(label)
    errors.extend(label_errors)

    # Evidence-label consistency checks
    has_behavior = bool(case.get("behavior_abnormal_list"))
    handling = label.get("handling_suggestion")
    risk = label.get("risk_level")

    # ban_account should have behavior evidence
    if handling == "ban_account" and not has_behavior:
        errors.append("ban_account without behavior evidence")

    # high_risk should have at least some evidence
    if risk == "high_risk":
        has_chat = bool(case.get("chat_evidence_list"))
        if not has_chat and not has_behavior:
            errors.append("high_risk without any evidence")

    return len(errors) == 0, errors


def filter_generated_batch(
    cases: list[dict[str, Any]],
    target_level: str,
    target_topic: str | None = None,
) -> list[dict[str, Any]]:
    """Filter and validate a batch of generated cases.

    Removes cases that:
      - Fail schema validation
      - Don't match the target risk_level
      - Have evidence-label inconsistencies
    """
    valid: list[dict[str, Any]] = []
    rejected = 0

    for case in cases:
        is_valid, errors = validate_generated_case(case)
        if not is_valid:
            rejected += 1
            continue

        label = case.get("label", {})
        if label.get("risk_level") != target_level:
            rejected += 1
            continue

        if target_topic and label.get("topic") != target_topic:
            rejected += 1
            continue

        valid.append(case)

    if rejected:
        logger.info("Filtered %d/%d generated cases (%.1f%% pass rate)",
                    rejected, len(cases), 100 * len(valid) / max(len(cases), 1))

    return valid


def assign_synthetic_metadata(
    cases: list[dict[str, Any]],
    level: str,
    round_id: int = 1,
) -> list[dict[str, Any]]:
    """Assign ticket_id, source, and task_type metadata to synthetic cases."""
    enriched: list[dict[str, Any]] = []
    for i, case in enumerate(cases):
        case = dict(case)
        case["ticket_id"] = f"synthetic-{level[:3]}-r{round_id}-{i:06d}"
        case["source"] = f"level_generator_{level}"
        case["task_type"] = "multi_label"
        enriched.append(case)
    return enriched
