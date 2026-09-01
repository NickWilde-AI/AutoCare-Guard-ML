<div align="center">

# AutoCare-Guard-ML

**新能源汽车售后风险智能研判与工单路由**

把「用户怎么说」和「车辆当时怎样」放进同一个可审计的 Judge，输出结构化风险结论与工单路由建议。

[![Python](https://img.shields.io/badge/Python-3.11%2B-blue)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/API-FastAPI-009688)](https://fastapi.tiangolo.com/)
[![vLLM](https://img.shields.io/badge/Serving-vLLM-7c3aed)](https://github.com/vllm-project/vllm)
[![enterprise-check](https://github.com/NickWilde-AI/AutoCare-Guard-ML/actions/workflows/ci.yml/badge.svg)](https://github.com/NickWilde-AI/AutoCare-Guard-ML/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

[English](README_EN.md) · [快速开始](#快速开始) · [系统架构](#系统架构) · [输出协议](#输出协议) · [训练与评测](#训练与评测) · [企业级验收](#企业级验收) · [文档](#文档)

</div>

---

本仓库是 **AutoCare** 售后风险研判项目的脱敏工程实现：覆盖多证据样本构建、Qwen LoRA SFT、离线评测、推理服务、证据门禁、工单路由、审计与监控。

**公开边界**：不含原始工单、车主身份、故障码字典、生产模型权重和完整生产基础设施。效果评估需自备已授权且脱敏的数据与权重。

## 为什么做这个项目

很多售后系统只做文本分类：咨询 / 投诉 / 升级。

真实的车辆售后风险研判要同时回答：

| 问题 | 为什么难 |
| --- | --- |
| 这是不是车辆风险事件？ | 车主只说「充不上电」，可能是预约设置，也可能是高压告警伴随温升 |
| 风险有多高？ | 需要对话语义与车辆信号、故障证据、服务历史互相印证 |
| 下一步怎么走？ | 信息回复、补采证据、服务跟进、建工单、专家复核，还是紧急人工确认 |
| 证据不够怎么办？ | 不能当成「无风险」；应进入 `insufficient_evidence` 路径 |
| 如何可审计？ | 结构化证据引用、版本化决策、监控告警与样本回流 |

AutoCare-Guard-ML 把这些问题拆成可评审、可复现的工程链路：

```text
服务事件
  -> 对话证据 + 车辆信号摘要 + 故障证据 + 服务历史
  -> LLM Judge
  -> 结构化研判 JSON
  -> 后处理 / 车辆侧证据门禁
  -> 工单路由
  -> 审计 / 指标 / 样本回流
```

## 项目亮点

| 能力 | 已实现内容 |
| --- | --- |
| 多证据研判 | `conversation_evidence`、`vehicle_signal_summary`、`fault_evidence`、`service_history_summary` |
| LLM Judge | 本地规则基线；Transformers / SFT checkpoint；OpenAI 兼容 API |
| 训练链路 | completion-only SFT、LoRA/PEFT、公开数据字段级 loss mask |
| 决策安全 | JSON 兜底解析、标签校验、`emergency_review` 车辆证据门禁、策略路由 |
| API 服务 | FastAPI、request_id、Token/RBAC、CORS、限流、请求大小限制 |
| 审计追踪 | JSONL / SQLite、按 case 查询、版本化决策记录 |
| 监控告警 | Prometheus 指标、漂移报告、滑动窗口告警 |
| 模型治理 | 模型注册表、晋级红线、回滚目标、审批元数据 |
| 交付门禁 | `make enterprise-check`、OpenAPI 契约、preflight、readiness、CI |

## 当前状态

| 阶段 | 状态 | 说明 |
| --- | --- | --- |
| 工程框架 | 可公开验证 | CLI、API、数据转换、训练入口、评测、监控、审计、部署模板 |
| 规则基线 | 可公开验证 | 用于跑通解析 / 路由 / 服务流程，不代表模型效果 |
| tiny-gpt2 / 小模型 | 工程冒烟 | 只验证训练代码路径 |
| Qwen3-32B LoRA | 代码与配置公开 | 需自备合规数据、权重和匹配 GPU |
| 生产接入 | 不在公开范围 | 生产权重、内部数据和完整基础设施不公开 |

## 系统架构

更详细的设计见 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)。

```text
服务研判请求
  -> 证据构建：聚合对话、车辆信号、故障、服务历史
  -> Prompt / Feature 渲染
  -> LLM Judge：输出结构化研判 JSON
  -> JSON 解析与修复
  -> 后处理：标签校验 + 紧急动作证据门禁
  -> 工单路由：信息流 / 补采 / 服务队列 / 工单 / 复核 / 兜底
  -> 审计与监控：request_id、版本、指标、告警
  -> 样本回流：误判与灰区进入下一轮训练
```

| 层级 | 职责 | 关键文件 |
| --- | --- | --- |
| 接入层 | 请求、CLI、schema | `api.py` `cli.py` `schema.py` |
| 证据层 | 多证据渲染与审计 | `prompting.py` `data_audit.py` |
| 模型层 | 基线 / SFT / 推理 | `inference.py` `training.py` |
| 决策层 | 解析、门禁、路由 | `parsing.py` `postprocess.py` |
| 治理层 | 版本、审计、监控、注册表 | `versioning.py` `audit_store.py` `monitoring.py` `model_registry.py` |
| 闭环层 | 离线评测与难例回流 | `evaluation.py` `refinement.py` |

## 快速开始

本地不需要 GPU，也不需要微调 checkpoint。默认使用确定性规则基线 Judge，可立刻验证 API、路由、审计、监控和评测。

```bash
git clone https://github.com/NickWilde-AI/AutoCare-Guard-ML.git
cd AutoCare-Guard-ML

python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,serve]"

python -m pytest tests/ -q
python -m compileall -q src

# 准备本地脱敏 JSONL 后：
make predict-route INPUT=data/local/input.jsonl
make eval-report INPUT=data/local/input.jsonl
make readiness-check
```

启动 API：

```bash
PYTHONPATH=src autocare-guard --config configs/default.yaml serve --port 8000
```

提交研判请求：

```bash
curl -X POST http://127.0.0.1:8000/judge \
  -H "Content-Type: application/json" \
  -H "X-Request-ID: local-run-1" \
  -d '{
    "case_id": "local-run-1",
    "conversation_evidence": [
      {"role": "owner", "text": "充电中闻到焦糊味，车机提示高压异常。"}
    ],
    "vehicle_signal_summary": {
      "motion_state": "charging",
      "warning_lights": ["高压系统告警"],
      "thermal_status": "abnormal_rise",
      "data_freshness": "fresh"
    },
    "fault_evidence": [
      {"fault_domain": "hv_system", "severity_from_source": "critical", "occurrence_count": 2}
    ],
    "service_history_summary": {
      "open_work_orders": 0,
      "repeat_repair_count_90d": 0
    }
  }'
```

查看指标：

```bash
curl http://127.0.0.1:8000/metrics
```

## 输出协议

Judge 输出的是结构化研判结论，不是单个二分类标签：

```json
{
  "risk_level": "low_risk | mid_risk | high_risk",
  "event_topic": "动力电池与热安全 | 充电与高压系统异常 | ... | 无风险事件",
  "event_judgment": "risk_event | not_risk_event | insufficient_evidence",
  "recommended_action": "information_reply | collect_more_evidence | service_followup | create_work_order | expert_review | emergency_review",
  "evidence_refs": [
    {"source": "conversation_evidence", "index": 0, "field": "text"}
  ],
  "correlation_analysis": "对话与车辆证据如何互相支持或冲突",
  "uncertainty_reason": "缺失、冲突或不足以定论的原因",
  "service_escalation_flags": ["repeated_complaint", "unresolved_service_case", "public_opinion_risk"],
  "route": "information_flow | collect_evidence | service_queue | work_order_queue | review_queue | fallback_or_review",
  "final_action": "information_reply_candidate | request_more_evidence | ... | await_human_confirmation"
}
```

### 主题与动作

首期车辆风险主题（9 + 无风险事件）：

1. 动力电池与热安全  
2. 充电与高压系统异常  
3. 制动与转向异常  
4. 行驶中动力异常  
5. 智能驾驶与驾驶辅助反馈  
6. 车机、座舱和远程控车故障  
7. 重复维修与问题未解决  
8. 道路救援与人员安全  
9. 质保、零部件与服务争议  
10. 无风险事件  

处置建议：

| 动作 | 含义 |
| --- | --- |
| `information_reply` | 信息回复 / 引导自助 |
| `collect_more_evidence` | 补采对话、信号或故障证据 |
| `service_followup` | 服务跟进 |
| `create_work_order` | 创建售后工单 |
| `expert_review` | 技术专家复核 |
| `emergency_review` | 紧急人工确认（需车辆侧证据门禁；模型不直接控车） |

## 训练与评测

安装训练依赖：

```bash
pip install -e ".[train]"
```

训练前检查：

```bash
LC_ALL=en_US.UTF-8 LANG=en_US.UTF-8 \
PYTHONPATH=src autocare-guard --config configs/default.yaml \
  train-readiness data/train/xguard_splits/train.jsonl \
  --out outputs/training_readiness.json
```

效果训练（需自备 GPU 与数据）：

```bash
LC_ALL=en_US.UTF-8 LANG=en_US.UTF-8 \
PYTHONPATH=src autocare-guard --config configs/default.yaml \
  train data/train/xguard_splits/train.jsonl
```

本地冒烟可用 `configs/local_fast_full_train.yaml` 或 `configs/local_mps_train.yaml`。

训练设计：

- **completion-only SFT**：只对 assistant JSON 输出算 loss  
- **字段级 mask**：公开二分类数据不训练完整 `risk_level` / `recommended_action`，尤其不监督 `expert_review` / `emergency_review`  
- **保守公开标签**：公开风险样本最多映射到中等风险与服务跟进类动作  
- **统一 prompt**：训练与推理共用同一套渲染路径  

建议评测指标：

| 指标 | 用途 |
| --- | --- |
| `event_judgment` F1 | 事件判断主指标 |
| `risk_level` macro-F1 | 风险分级 |
| `recommended_action` macro-F1 | 处置建议 |
| `emergency_review` FPR | 紧急误报控制 |
| critical-event recall | 高影响事件召回 |

## 企业级验收

```bash
make enterprise-check
```

覆盖：单元测试、源码编译、OpenAPI 契约、生产配置 preflight、模型注册表、交付摘要、readiness。  
GitHub Actions 在 push / PR 时运行同一套检查。

## 项目结构

```text
.
├── configs/                 # 模型、训练、注册表、灰度、rubric
├── data/                    # 本地数据目录；业务数据默认不提交
├── deploy/                  # Docker、vLLM、K8s、Prometheus 示例
├── docs/                    # 架构、运维、训练、治理文档
├── scripts/                 # 数据下载、压测、demo
├── src/autocare_guard_ml/   # 核心 Python 包
├── static/                  # 本地看板
├── tests/                   # 单测、契约、readiness、治理回归
├── Makefile
├── pyproject.toml
└── README.md
```

## 文档

| 需求 | 入口 |
| --- | --- |
| 项目地图 | [docs/PROJECT_INDEX.md](docs/PROJECT_INDEX.md) |
| 架构说明 | [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) |
| 命令手册 | [docs/COMMANDS.md](docs/COMMANDS.md) |
| API 使用 | [docs/API_USAGE.md](docs/API_USAGE.md) |
| 训练与评测 | [docs/TRAINING_AND_EVALUATION.md](docs/TRAINING_AND_EVALUATION.md) |
| 标签与 Rubric | [docs/RUBRIC_AND_LABELING_GUIDE.md](docs/RUBRIC_AND_LABELING_GUIDE.md) |
| 风险策略 | [docs/RISK_STRATEGY.md](docs/RISK_STRATEGY.md) |
| 公开数据集 | [docs/PUBLIC_DATASET_XGUARD.md](docs/PUBLIC_DATASET_XGUARD.md) |
| 部署与运维 | [docs/DEPLOYMENT_AND_OPERATIONS.md](docs/DEPLOYMENT_AND_OPERATIONS.md) |
| SLO 与告警 | [docs/SLO_AND_ALERTING.md](docs/SLO_AND_ALERTING.md) |
| 模型治理 | [docs/MODEL_GOVERNANCE_PLAYBOOK.md](docs/MODEL_GOVERNANCE_PLAYBOOK.md) |

## 生产接入说明

公开仓库提供可运行骨架。进入真实业务环境时，通常需要接入或替换：

- 已脱敏的售后标注数据、工单反馈、安全复核样本和线上回流样本  
- 经过正式训练和评测的 Qwen 或同级 checkpoint  
- 企业网关、密钥轮换、集中审计仓库和人工确认平台  
- 灰度、A/B、回滚与持续监控流程  

部署文件只表示接口与拓扑参考，不证明已达到特定吞吐、延迟或可用性目标。模型输出是研判与路由建议，**不直接控制车辆**。

## License

MIT License. See [LICENSE](LICENSE).
