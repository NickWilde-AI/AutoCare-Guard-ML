# 人审复核、灰度与 A/B 治理

## 人审复核原则

模型输出的是处置建议，不是最终处罚。`ban_account` 必须进入人审复核，不能由模型直接封号。

| route | final_action | 处理方式 |
| --- | --- | --- |
| `auto_close` | `ignore` | 自动关闭，抽样质检 |
| `auto_action` | `send_warning` | 可自动警示，低比例抽样复核 |
| `policy_action` | `limit_account_candidate` | 可按策略限号，建议抽样或重点主题复核 |
| `human_review_required` | `review_before_ban` | 强制人审复核 |

人审系统至少回写：

- `review_result`
- `final_action`
- `reviewer_id_hash`
- `reviewed_at`
- `appeal_result`
- `is_model_error`
- `error_type`

这些字段用于后续 hard sample refinement、ban FPR 统计和策略回滚。

## 灰度配置

配置文件：[configs/rollout.yaml](../configs/rollout.yaml)

推荐节奏：

| 阶段 | 流量 | 模型动作 | 回滚条件 |
| --- | ---: | --- | --- |
| shadow | 1% | 只入库不处置 | 任一 guardrail 触发 |
| small | 10% | warning/limit candidate，ban 人审 | 任一 guardrail 触发 |
| ramp | 50% | warning/limit candidate，ban 人审 | 任一 guardrail 触发 |
| full | 100% | 模型进入主链路，规则兜底 | 任一 guardrail 触发 |

核心 guardrail：

- `ban_account_fpr <= 0.03`
- `parse_non_ok_rate <= 0.02`
- `p95_latency_ms <= 1200`
- 人审改判率不高于上一稳定版本

## A/B 对比

A/B 不比较单一 accuracy，而比较业务可用性：

- `final_judgment_f1`
- `handling_macro_f1`
- `ban_account_fpr`
- `human_review_overturn_rate`
- P95/P99 latency

候选模型只有在主指标提升且 guardrail 不退化时才能进入下一阶段。

本仓库提供了一个最小可运行的离线 A/B replay 报告，用于比较 control 与 candidate 两份 prediction JSONL：

```bash
PYTHONPATH=src python3 -m im_guard_ml.cli --config configs/default.yaml ab-report \
  --control outputs/control_predictions.jsonl \
  --candidate outputs/candidate_predictions.jsonl \
  --out outputs/ab_report.md \
  --json-out outputs/ab_report.json
```

报告会按 `ticket_id` 对齐样本，输出：

- `final_judgment_f1`
- `handling_macro_f1`
- `ban_account_fpr`
- `parse_non_ok_rate`
- `p95_latency_ms`
- 可选 `human_review_overturn_rate`

如果候选模型主指标没有退化且 guardrail 全部通过，报告会给出 `promote`；如果误封、解析异常或延迟触发阈值，则给出 `hold`。

## 回滚动作

1. 切回上一稳定模型或规则引擎。
2. `ban_account` 全部转人审。
3. 冻结当前审计日志、模型版本、prompt 版本和 rubric 版本。
4. 导出事故样本，进入 hard sample refinement。
