# 技术文档索引

本目录只保留公开工程实现所需的技术资料。非公开材料、原始实验记录和旧历史备份保存在本地 `private/`，该目录不会进入 Git。

## 核心流程

1. [ARCHITECTURE.md](ARCHITECTURE.md)：多证据审核架构与模块边界。
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

## 常用命令

```bash
python -m pytest tests/ -q
python -m compileall -q src
make enterprise-check
```

数据文件、模型权重、checkpoint、运行输出和内部实验环境均不随仓库发布。
