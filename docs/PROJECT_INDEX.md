# 技术文档索引

本目录只保留公开工程实现所需的技术资料。非公开材料、原始实验记录和旧历史备份保存在本地 `private/`，该目录不会进入 Git。

## 项目与术语

| 项 | 取值 |
| --- | --- |
| 项目名 | AutoCare-Guard-ML |
| 包名 / CLI | `autocare_guard_ml` / `autocare-guard` |
| 领域 | 新能源汽车售后风险智能研判与工单路由 |
| 环境变量前缀 | `AUTOCARE_GUARD_*` |

| 术语 | 含义 |
| --- | --- |
| 服务事件 / `case_id` | 一次售后研判请求的主键（legacy 输入字段 `ticket_id` 仍兼容） |
| 多证据输入 | `conversation_evidence`、`vehicle_signal_summary`、`fault_evidence`、`service_history_summary` |
| `event_judgment` | `risk_event` / `not_risk_event` / `insufficient_evidence` |
| `recommended_action` | `information_reply` / `collect_more_evidence` / `service_followup` / `create_work_order` / `expert_review` / `emergency_review` |
| 工单路由 | 后处理 + 证据门禁后的 `route` / `final_action` |

## 核心流程

1. [ARCHITECTURE.md](ARCHITECTURE.md)：多证据研判架构与模块边界。
2. [DATA_INGESTION.md](DATA_INGESTION.md)：输入字段、脱敏和接入约束。
3. [TRAINING_AND_EVALUATION.md](TRAINING_AND_EVALUATION.md)：数据转换、SFT、LoRA 与离线评测。
4. [API_USAGE.md](API_USAGE.md)：FastAPI 接口、鉴权和审计查询。
5. [HUMAN_REVIEW_AND_ROLLOUT.md](HUMAN_REVIEW_AND_ROLLOUT.md)：策略分流、人工复核和灰度接口。

## 工程治理

- [DATA_QUALITY_AND_AUDIT.md](DATA_QUALITY_AND_AUDIT.md)：数据质量和泄漏检查。
- [RUBRIC_AND_LABELING_GUIDE.md](RUBRIC_AND_LABELING_GUIDE.md)：公开标签 Schema 与标注方法。
- [RISK_STRATEGY.md](RISK_STRATEGY.md)：风险容忍度与决策框架。
- [DEPLOYMENT_AND_OPERATIONS.md](DEPLOYMENT_AND_OPERATIONS.md)：部署参考和运维边界。
- [MODEL_GOVERNANCE_PLAYBOOK.md](MODEL_GOVERNANCE_PLAYBOOK.md)：模型版本、候选与回滚接口。
- [SLO_AND_ALERTING.md](SLO_AND_ALERTING.md)：指标和告警配置方法。
- [INCIDENT_RUNBOOK.md](INCIDENT_RUNBOOK.md)：异常处置和复盘模板。
- [LIMITATIONS_AND_ROADMAP.md](LIMITATIONS_AND_ROADMAP.md)：公开实现的已知限制。
- [POLICY_CHANGELOG.md](POLICY_CHANGELOG.md)：策略与版本变更记录。
- [PUBLIC_DATASET_XGUARD.md](PUBLIC_DATASET_XGUARD.md)：公开安全识别底座说明。
- [COMMANDS.md](COMMANDS.md)：常用命令手册。
- [LOCAL_ENV_ROOT_CAUSE.md](LOCAL_ENV_ROOT_CAUSE.md)：本地 UTF-8 locale 问题说明。
- [ENTERPRISE_READINESS_REVIEW.md](ENTERPRISE_READINESS_REVIEW.md)：企业级成熟度评审。

## 常用命令

```bash
python -m pytest tests/ -q
python -m compileall -q src
make enterprise-check
```

数据文件、模型权重、checkpoint、运行输出和内部实验环境均不随仓库发布。
