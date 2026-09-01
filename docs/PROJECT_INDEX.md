# 技术文档索引

> **领域迁移说明（2026-09-01）**：公开工程已从 IM 私聊风控迁移为 **AutoCare 新能源汽车售后风险智能研判与工单路由**。仓库名 `AI-IM-Guard-ML`、包名 `im_guard_ml`、CLI `im-guard` 保留历史命名；核心术语请以 AutoCare 口径为准（`event_judgment` / `recommended_action` / `case_id` / 车辆证据等）。旧 IM 字段在 API 与测试中仍兼容。

本目录只保留公开工程实现所需的技术资料。非公开材料、原始实验记录和旧历史备份保存在本地 `private/`，该目录不会进入 Git。

## 核心术语（AutoCare）

| 术语 | 含义 |
| --- | --- |
| 服务事件 / `case_id` | 一次售后研判请求的主键（兼容 `ticket_id`） |
| 多证据输入 | `conversation_evidence`、`vehicle_signal_summary`、`fault_evidence`、服务历史等 |
| `event_judgment` | `risk_event` / `not_risk_event` / `insufficient_evidence` |
| `recommended_action` | 信息回复、补采、跟进、建工单、专家复核、紧急复核 |
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
- [DEPLOYMENT_AND_OPERATIONS.md](DEPLOYMENT_AND_OPERATIONS.md)：部署参考和运维边界。
- [MODEL_GOVERNANCE_PLAYBOOK.md](MODEL_GOVERNANCE_PLAYBOOK.md)：模型版本、候选与回滚接口。
- [SLO_AND_ALERTING.md](SLO_AND_ALERTING.md)：指标和告警配置方法。
- [INCIDENT_RUNBOOK.md](INCIDENT_RUNBOOK.md)：异常处置和复盘模板。
- [LIMITATIONS_AND_ROADMAP.md](LIMITATIONS_AND_ROADMAP.md)：公开实现的已知限制。
- [POLICY_CHANGELOG.md](POLICY_CHANGELOG.md)：策略与版本变更记录。

## 常用命令

```bash
python -m pytest tests/ -q
python -m compileall -q src
make enterprise-check
```

数据文件、模型权重、checkpoint、运行输出和内部实验环境均不随仓库发布。
