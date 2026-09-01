<div align="center">

# AutoCare-Guard-ML

**智能汽车服务风险决策平台** · AutoCare Risk Intelligence Platform

把「用户怎么说」与「车辆当时怎样」融合进同一套可审计 Judge，输出结构化风险结论与服务路由建议。

[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/API-FastAPI-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![vLLM](https://img.shields.io/badge/Serving-vLLM-111111)](https://github.com/vllm-project/vllm)
[![CI](https://github.com/NickWilde-AI/AutoCare-Guard-ML/actions/workflows/ci.yml/badge.svg)](https://github.com/NickWilde-AI/AutoCare-Guard-ML/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/License-MIT-2ea44f)](LICENSE)

[English](README_EN.md) · [快速开始](#快速开始) · [架构](#系统架构) · [协议](#输出协议) · [训练](#训练与评测) · [文档](#文档)

</div>

---

本仓库是 **智能汽车服务风险决策平台**（AutoCare Risk Intelligence Platform）的脱敏工程实现，公开仓库为 [AutoCare-Guard-ML](https://github.com/NickWilde-AI/AutoCare-Guard-ML)；包名 / CLI 为 `autocare_guard_ml` / `autocare-guard`。覆盖多证据样本构建、Qwen LoRA SFT、离线评测、推理服务、证据门禁、工单路由、审计与监控。

> **公开边界** — 不含原始工单、车主身份、故障码字典、生产权重与完整生产基础设施；效果评估需自备已授权且脱敏的数据与模型。

---

## 为什么需要它

多数售后系统只做文本分类：咨询 / 投诉 / 升级。  
真实服务风险决策要同时回答五件事：

| 决策问题 | 难点 |
| :--- | :--- |
| 是否构成车辆风险事件？ | 「充不上电」可能是预约设置，也可能是高压告警伴随温升 |
| 风险等级有多高？ | 对话语义必须与车辆信号、故障证据、服务历史互证 |
| 下一步如何处置？ | 信息回复 → 补采证据 → 服务跟进 → 建工单 → 专家复核 → 紧急确认 |
| 证据不足怎么办？ | 不能当成无风险，应进入 `insufficient_evidence` |
| 如何可审计可回滚？ | 证据引用、版本化决策、监控告警与样本回流 |

```text
服务事件
   │
   ▼
对话证据 + 车辆信号摘要 + 故障证据 + 服务历史
   │
   ▼
LLM Judge  ──►  结构化研判 JSON
   │
   ▼
后处理 / 车辆侧证据门禁
   │
   ▼
工单路由  ──►  审计 · 指标 · 样本回流
```

---

## 能力一览

| 模块 | 内容 |
| :--- | :--- |
| 多证据研判 | `conversation_evidence` · `vehicle_signal_summary` · `fault_evidence` · `service_history_summary` |
| LLM Judge | 规则基线 · Transformers / SFT · OpenAI 兼容 API |
| 训练链路 | completion-only SFT · LoRA/PEFT · 公开数据字段级 loss mask |
| 决策安全 | JSON 兜底 · 标签校验 · `emergency_review` 证据门禁 · 策略路由 |
| 服务治理 | FastAPI · request_id · Token/RBAC · 限流 · JSONL/SQLite 审计 |
| 监控交付 | Prometheus · 漂移报告 · 模型注册表 · `make enterprise-check` |

### 当前状态

| 阶段 | 状态 |
| :--- | :--- |
| 工程框架 / 规则基线 | 可公开验证 |
| tiny-gpt2 / 小模型冒烟 | 仅验证训练路径 |
| Qwen3-32B LoRA | 代码与配置公开，需自备数据与 GPU |
| 生产接入 | 不在公开范围 |

---

## 系统架构

完整设计见 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)。

```text
服务研判请求
  → 证据构建
  → Prompt / Feature 渲染
  → LLM Judge
  → JSON 解析与修复
  → 后处理（标签校验 + 紧急动作门禁）
  → 工单路由
  → 审计与监控
  → 难例回流
```

| 层级 | 职责 | 关键文件 |
| :--- | :--- | :--- |
| 接入层 | 请求 · CLI · schema | `api.py` `cli.py` `schema.py` |
| 证据层 | 多证据渲染与审计 | `prompting.py` `data_audit.py` |
| 模型层 | 基线 · SFT · 推理 | `inference.py` `training.py` |
| 决策层 | 解析 · 门禁 · 路由 | `parsing.py` `postprocess.py` |
| 治理层 | 版本 · 审计 · 监控 · 注册表 | `versioning.py` `audit_store.py` `monitoring.py` |
| 闭环层 | 离线评测 · 难例回流 | `evaluation.py` `refinement.py` |

---

## 快速开始

本地**无需 GPU**，默认规则基线即可跑通 API、路由、审计与评测。

```bash
git clone https://github.com/NickWilde-AI/AutoCare-Guard-ML.git
cd AutoCare-Guard-ML

python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,serve]"

python -m pytest tests/ -q
make readiness-check
```

**启动服务**

```bash
PYTHONPATH=src autocare-guard --config configs/default.yaml serve --port 8000
```

**提交研判**

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

```bash
curl http://127.0.0.1:8000/metrics
```

---

## 输出协议

Judge 输出**结构化决策结论**，而非单一二分类标签。

```json
{
  "risk_level": "low_risk | mid_risk | high_risk",
  "event_topic": "动力电池与热安全 | ... | 无风险事件",
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

### 风险主题（首期）

| # | 主题 |
| :---: | :--- |
| 1 | 动力电池与热安全 |
| 2 | 充电与高压系统异常 |
| 3 | 制动与转向异常 |
| 4 | 行驶中动力异常 |
| 5 | 智能驾驶与驾驶辅助反馈 |
| 6 | 车机、座舱和远程控车故障 |
| 7 | 重复维修与问题未解决 |
| 8 | 道路救援与人员安全 |
| 9 | 质保、零部件与服务争议 |
| 10 | 无风险事件 |

### 处置建议

| 动作 | 含义 |
| :--- | :--- |
| `information_reply` | 信息回复 / 引导自助 |
| `collect_more_evidence` | 补采对话、信号或故障证据 |
| `service_followup` | 服务跟进 |
| `create_work_order` | 创建售后工单 |
| `expert_review` | 技术专家复核 |
| `emergency_review` | 紧急人工确认（需车辆侧证据门禁；**模型不直接控车**） |

---

## 训练与评测

```bash
pip install -e ".[train]"

# 训练前检查
PYTHONPATH=src autocare-guard --config configs/default.yaml \
  train-readiness data/train/xguard_splits/train.jsonl \
  --out outputs/training_readiness.json

# 效果训练（需自备 GPU 与数据）
PYTHONPATH=src autocare-guard --config configs/default.yaml \
  train data/train/xguard_splits/train.jsonl
```

本地冒烟可用 `configs/local_fast_full_train.yaml` 或 `configs/local_mps_train.yaml`。

| 设计点 | 说明 |
| :--- | :--- |
| completion-only SFT | 只对 assistant JSON 输出算 loss |
| 字段级 mask | 公开数据不监督 `expert_review` / `emergency_review` |
| 保守公开标签 | 公开风险样本最多映射到中等风险与服务跟进 |
| 统一 prompt | 训练与推理共用渲染路径 |

| 建议指标 | 用途 |
| :--- | :--- |
| `event_judgment` F1 | 事件判断 |
| `risk_level` macro-F1 | 风险分级 |
| `recommended_action` macro-F1 | 处置建议 |
| `emergency_review` FPR | 紧急误报控制 |
| critical-event recall | 高影响事件召回 |

---

## 企业级验收

```bash
make enterprise-check
```

覆盖单元测试、源码编译、OpenAPI 契约、生产 preflight、模型注册表、交付摘要与 readiness。  
GitHub Actions 在 push / PR 时运行同一套检查。

---

## 项目结构

```text
AutoCare-Guard-ML/
├── configs/                  # 模型 · 训练 · 注册表 · 灰度 · rubric
├── data/                     # 本地数据（业务数据默认不提交）
├── deploy/                   # Docker · vLLM · K8s · Prometheus
├── docs/                     # 架构 · 运维 · 训练 · 治理
├── scripts/                  # 下载 · 压测 · demo
├── src/autocare_guard_ml/    # 核心 Python 包
├── static/                   # 本地看板
├── tests/                    # 单测 · 契约 · 回归
├── Makefile
├── pyproject.toml
└── README.md
```

---

## 文档

| 主题 | 文档 |
| :--- | :--- |
| 项目地图 | [PROJECT_INDEX](docs/PROJECT_INDEX.md) |
| 架构 | [ARCHITECTURE](docs/ARCHITECTURE.md) |
| 命令 | [COMMANDS](docs/COMMANDS.md) |
| API | [API_USAGE](docs/API_USAGE.md) |
| 训练评测 | [TRAINING_AND_EVALUATION](docs/TRAINING_AND_EVALUATION.md) |
| 标签 Rubric | [RUBRIC_AND_LABELING_GUIDE](docs/RUBRIC_AND_LABELING_GUIDE.md) |
| 风险策略 | [RISK_STRATEGY](docs/RISK_STRATEGY.md) |
| 部署运维 | [DEPLOYMENT_AND_OPERATIONS](docs/DEPLOYMENT_AND_OPERATIONS.md) |
| SLO 告警 | [SLO_AND_ALERTING](docs/SLO_AND_ALERTING.md) |
| 模型治理 | [MODEL_GOVERNANCE_PLAYBOOK](docs/MODEL_GOVERNANCE_PLAYBOOK.md) |

---

## 生产接入

公开仓库提供可运行骨架。真实业务通常还需：

- 脱敏售后标注、工单反馈、安全复核与回流样本  
- 正式训练评测后的 Qwen 或同级 checkpoint  
- 企业网关、密钥轮换、集中审计与人工确认平台  
- 灰度、A/B、回滚与持续监控  

部署模板仅作接口与拓扑参考，不代表已达到特定吞吐或可用性目标。

---

<div align="center">

MIT License · [LICENSE](LICENSE)

</div>
