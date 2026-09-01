# Rubric 与标注规范

这份文档说明公开示例中的车辆风险主题如何拆分，以及标注者如何稳定给出 `risk_level / event_judgment / recommended_action`。

## 1. 标注输入

每条样本必须给标注员看到多类证据：

- `service_context` / `vehicle_context`：渠道、车型摘要等上下文。
- `conversation_evidence`：服务对话、角色、关键表述。
- `vehicle_signal_summary`：行驶 / 充电状态、告警摘要、热状态等。
- `fault_evidence`：故障域、严重度、次数等。
- `service_history_summary`：重复维修、未结工单等。
- `missing_and_conflicts`：已知缺失与冲突。

标注员不能只看对话文本，也不能只看车辆告警；必须判断语义与车辆侧证据是否构成同一条证据链。

## 2. 标注输出

每条样本标注以下字段：

- `event_topic`：车辆风险主题之一；无风险为 `无风险事件`。
- `risk_level`：`low_risk / mid_risk / high_risk`。
- `event_judgment`：`risk_event / not_risk_event / insufficient_evidence`。
- `recommended_action`：`information_reply / collect_more_evidence / service_followup / create_work_order / expert_review / emergency_review`。
- `evidence_refs`：结构化证据引用（source / index / field）。
- `correlation_analysis`：对话与车辆侧证据如何关联。
- `uncertainty_reason`：缺失、冲突或不确定说明。
- `service_escalation_flags`：如 `repeated_complaint`、`unresolved_service_case`、`public_opinion_risk`。

## 3. 总体判定原则

`low_risk`：

- 普通咨询、轻微体验问题，或已有证据明确不构成安全风险。
- 车辆侧无告警，对话也无安全风险迹象。
- 通常对应 `not_risk_event + information_reply`。

`mid_risk`：

- 存在明确异常或重复问题，需要补采、工单或专家排查。
- 对话与车辆侧仅单侧印证，或证据链不完整。
- 通常对应 `risk_event` + `service_followup / create_work_order / expert_review`，或 `insufficient_evidence + collect_more_evidence`。

`high_risk`：

- 可能影响人员、行车、高压或热安全，且证据链相对完整。
- 对话语义与车辆侧告警 / 故障互相印证。
- 通常对应 `risk_event + emergency_review`（人工确认，不直接控车）。

## 4. 动作档位原则

`information_reply`：无风险或风险极低，信息回复即可。

`collect_more_evidence`：证据不足或冲突，先补采再研判。

`service_followup`：需要服务跟进，但不一定立刻建工单。

`create_work_order`：需要进入售后工单队列处理。

`expert_review`：技术 / 安全专家复核。

`emergency_review`：高风险且证据充分时的紧急人工确认建议；生产上必须人审，模型不直接控车。

## 5. 主题 rubric

详细配置见 `configs/default.yaml` 的 `rubrics`（以及可选的 `configs/rubrics.yaml`）。这些规则是公开工程示例，不应视为任何公司的完整内部策略。

### 5.1 动力电池与热安全

- low：续航咨询或正常温升范围内的体验问题。
- mid：出现电池相关告警或异常温差，但车辆已安全停放且无人员暴露。
- high：焦糊味、冒烟、热失控迹象或行驶 / 充电中伴随严重热安全证据。

### 5.2 充电与高压系统异常

- low：预约充电设置、桩兼容性等使用咨询。
- mid：多次充电中断或高压告警，当前无立即现场危险。
- high：充电中断伴随高压 / 热安全证据，或存在人员暴露风险。

### 5.3 制动与转向异常

- low：轻微异响咨询且车辆侧无告警。
- mid：重复制动 / 转向告警，车辆可控停放。
- high：行驶中制动失效 / 转向异常等行车风险证据。

### 5.4 行驶中动力异常

- low：动力体感咨询且无告警。
- mid：动力中断或跛行告警，但已停放。
- high：行驶中动力突然中断并伴随安全风险证据。

### 5.5 智能驾驶与驾驶辅助反馈

- low：功能体验吐槽，无同期车辆告警。
- mid：误制动 / 突然减速等描述且有功能状态摘要印证。
- high：行驶中智驾异常并存在人身或行车风险的车辆侧证据。

### 5.6 车机、座舱和远程控车故障

- low：车机卡顿、账号登录等体验问题。
- mid：远程控车失败或重复故障影响服务。
- high：远程控车异常与车辆安全状态冲突且证据充分（仍不直接控车）。

### 5.7 重复维修与问题未解决

- low：首次咨询历史工单进度。
- mid：同类问题重复出现，需工单或专家排查。
- high：重复未解决且当前存在安全相关车辆证据。

### 5.8 道路救援与人员安全

- low：救援流程咨询。
- mid：需要道路救援但人员已脱离危险。
- high：人员或行车安全正在受影响，需紧急人工确认。

### 5.9 质保、零部件与服务争议

- low：质保政策咨询。
- mid：争议需服务升级标记与工单跟进。
- high：争议同时伴随明确车辆安全证据（安全与客诉分流处理）。

### 5.10 无风险事件

- low：明确无风险或证据足以排除安全风险。
- mid / high：不适用。

其他边界案例可按同一原则：先看语义强度，再看车辆侧印证，再看动作代价。

## 6. 标注一致性流程

推荐流程：

1. 每条样本由 3 名标注员独立标注。
2. 完全一致直接采纳。
3. 两人一致取多数票。
4. 三人分歧进入仲裁。
5. 每周抽样复盘分歧样本，更新 rubric。

一致性指标：

- `Fleiss Kappa`：多标注员一致性。
- `ordinal Krippendorff alpha`：适合 `risk_level` 这种有序等级。
- `Cohen's Kappa`：成对一致性校验。

## 7. 分歧样本怎么处理

常见分歧：

- 对话描述严重但车辆侧无告警：通常 `insufficient_evidence` 或 mid，动作不宜直接 `emergency_review`。
- 车辆告警强但对话很淡：看告警强度与时间关联，通常 mid 或 high。
- 高风险主题但证据不完整：risk 可高，但 `recommended_action` 要保守（专家复核 / 补采）。
- 重大客诉但不构成车辆安全事件：走 `service_escalation_flags`，不要硬塞进安全主题。

处理原则：宁可把强处置交给人审，也不要让模型在缺车辆侧证据时扩大紧急动作。

## 8. 一致性原则

标注者应同时查看对话证据、车辆信号、故障证据和服务历史，独立标注风险等级、事件研判与动作建议。分歧样本可采用多数票或仲裁，并使用 Fleiss Kappa、ordinal Krippendorff alpha 等指标检查一致性。
