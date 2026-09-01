# 风险策略与决策框架

本文档定义智能汽车服务风险决策平台（AutoCare Risk Intelligence Platform）的风险容忍度、决策标准、升级路径和人工复核机制。

## 1. 风险容忍度矩阵

| 风险等级 | 容忍度 | 业务含义 | 自动化处置 |
| --- | --- | --- | --- |
| `low_risk` | 高容忍 | 普通咨询、轻微体验问题，或证据足以排除安全风险 | 可自动信息回复（`information_reply`） |
| `mid_risk` | 中等容忍 | 明确异常或重复问题，需补采 / 工单 / 服务跟进 | 服务跟进、建工单或专家复核 + 抽样人工复核 |
| `high_risk` | 低容忍 | 可能影响人员、行车、高压或热安全 | 建议 `emergency_review`（人工确认，模型不直接控车） |

## 2. 决策标准（Decision Criteria）

### 2.1 风险等级判定（示意）

```
IF 对话语义与车辆侧证据互相印证 AND 涉及高压/热安全/行车安全:
    risk_level = high_risk
    event_judgment = risk_event
ELIF 存在明确异常 OR 重复未解决 OR 单侧证据较强:
    risk_level = mid_risk
ELIF 证据冲突或关键车辆侧证据缺失:
    event_judgment = insufficient_evidence
ELSE:
    risk_level = low_risk
    event_judgment = not_risk_event
```

### 2.2 动作建议映射

| risk_level | event_judgment | recommended_action |
| --- | --- | --- |
| high_risk | risk_event（证据充分） | emergency_review |
| high_risk | risk_event（证据不足） | expert_review / collect_more_evidence |
| mid_risk | risk_event | service_followup / create_work_order / expert_review |
| mid_risk | insufficient_evidence | collect_more_evidence |
| low_risk | not_risk_event | information_reply |
| * | insufficient_evidence | collect_more_evidence |

### 2.3 路由规则

| 条件 | 路由 | 原因 |
| --- | --- | --- |
| action = emergency_review | `review_queue` / `await_human_confirmation` | 强处置必须人工确认 |
| action = expert_review | `review_queue` / `await_expert_review` | 专家排查 |
| action = create_work_order | `work_order_queue` | 进入工单队列 |
| action = service_followup | `service_queue` | 服务跟进 |
| action = collect_more_evidence | `collect_evidence` | 补采证据 |
| action = information_reply | `information_flow` | 信息回复流 |
| parse / validation 异常 | `fallback_or_review` | 不信任模型裸输出 |
| 紧急动作缺车辆侧证据 | 降级为专家复核 / 补采 | 证据门禁优先于模型输出 |

## 3. 升级路径（Escalation）

### Level 1：自动路由

- 系统根据模型输出 + 后处理规则自动给出 `route` / `final_action`
- 覆盖信息回复、补采、服务跟进、建工单候选等低到中影响动作
- SLO：P95 延迟 <= 1200ms（展示目标）

### Level 2：人工 / 专家复核

- 触发条件：`emergency_review`、`expert_review`、解析异常、证据门禁失败
- SLA：高风险建议 30 分钟内复核；中风险建议 4 小时内复核（见 `configs/rollout.yaml`）
- 复核结果回写审计日志

### Level 3：安全 / 技术专家升级

- 触发条件：车主申诉、复核分歧、新型故障模式、救援复盘漏判
- SLA：24 小时内出结论
- 需要售后安全策略与技术专家介入

### Level 4：策略变更

- 触发条件：新法规 / 政策、大规模误判、模型 drift 告警
- 责任人：策略 PM + 算法负责人
- 产出：rubric 更新 → 标注 → 重训 → 灰度

## 4. 安全红线（Hard Rules）

以下规则优先级高于模型输出，在 postprocess 层强制执行：

| 规则 | 逻辑 | 原因 |
| --- | --- | --- |
| 紧急动作无车辆侧证据 | 不得仅凭对话文本维持 `emergency_review` | 防止无证据强处置；模型不直接控车 |
| 紧急动作缺少 `evidence_refs` | 门禁失败并转人工 / 专家路径 | 证据可追溯 |
| 模型输出紧急但 risk 非 high 或非 risk_event | 降级为 `expert_review` | 逻辑一致性 |
| 证据不足却输出紧急 | 改为 `collect_more_evidence` | 避免证据不足当紧急执行 |
| `not_risk_event` 却输出强处置 | 纠正为信息回复或服务跟进 | 防止误升级 |

## 5. 误判处理

### 5.1 误升级（False Positive）

- 车主申诉或服务经理驳回
- 人工复核后标记 `override: false_positive`
- 修正工单状态 + 记入 hard case 池
- hard case 池累积后触发一次模型评估

### 5.2 漏判（False Negative）

- 巡检、救援复盘或客诉发现
- 标记 `override: false_negative`
- 追加工单 / 复核 + 记入 hard case 池
- 若同类漏判集中出现，触发 Level 4 策略变更

## 6. 阈值管理

### 6.1 告警阈值

阈值以 `configs/default.yaml` 的 `alert_thresholds` 为准：

| 指标 | warn | critical | 行动 |
| --- | ---: | ---: | --- |
| `emergency_review_rate` | > 0.05 | > 0.08 | 暂停强处置自动流转，转人工确认 |
| `parse_non_ok_rate` | > 0.005 | > 0.02 | 检查模型输出格式，考虑回滚 |
| `missing_vehicle_evidence_rate` | > 0.08 | > 0.20 | 检查上游车辆 / 故障特征质量 |
| P95 延迟 | — | > 1200ms（rollout guardrail） | 扩容或降级为规则引擎 |

说明：`emergency_review_rate` 是紧急建议占全部请求的比例；与评测用的 `emergency_review_fpr`（gold 非紧急中被误判为紧急的比例）分母不同，勿混用。

### 6.2 阈值变更流程

1. 提出变更 PR，附带变更原因和影响分析
2. 策略 PM 审批
3. 灰度小流量验证
4. 全量生效 + 记录变更日志（见 [POLICY_CHANGELOG.md](POLICY_CHANGELOG.md)）

## 7. 风险权衡

误升级会带来复核成本与车主体验成本，漏判会带来行车 / 热安全风险。公开策略对 `mid_risk` 采用保守动作，对 `emergency_review` 强制人工确认，并通过 postprocess 证据门禁避免模型输出被无脑执行。
