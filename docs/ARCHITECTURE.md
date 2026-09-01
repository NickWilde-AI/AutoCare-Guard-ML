# AutoCare-Guard-ML 架构说明

AutoCare-Guard-ML 是面向新能源汽车售后风险智能研判与工单路由的企业级 AI/ML 工程框架。它将模型研判、输出校验、工单路由、可观测性和样本回流拆成相互独立但可组合的模块。

## 设计目标

- 融合服务对话语义与车辆侧结构化证据（信号摘要、故障证据、服务历史）。
- 输出机器可解析的结构化研判结论。
- 对 `emergency_review` 等高影响动作提供车辆侧证据门禁与人工确认保护（模型不直接控车）。
- 支持离线评测、监控、告警和审计日志。
- 支持从本地规则基线平滑切换到微调 checkpoint 部署。

## 数据流

```text
服务研判请求
  -> schema 校验
  -> prompt / feature 渲染
  -> Judge 推理
  -> JSON 解析
  -> 后处理（标签校验 + 证据门禁）
  -> 工单路由
  -> 版本化审计日志
  -> 监控 / 告警
```

## 核心组件

| 模块 | 文件 | 职责 |
| --- | --- | --- |
| Schema | `src/autocare_guard_ml/schema.py` | 标签、枚举、字段一致性检查 |
| Prompting | `src/autocare_guard_ml/prompting.py` | 研判 prompt 和 chat template 渲染 |
| Training | `src/autocare_guard_ml/training.py` | SFT 与 LoRA 训练入口 |
| Inference | `src/autocare_guard_ml/inference.py` | 规则基线 Judge 和 Transformers Judge |
| Parsing | `src/autocare_guard_ml/parsing.py` | JSON 提取和兜底解析 |
| Postprocess | `src/autocare_guard_ml/postprocess.py` | 证据门禁和策略路由 |
| Evaluation | `src/autocare_guard_ml/evaluation.py` | 分类指标和一致性指标 |
| Data Audit | `src/autocare_guard_ml/data_audit.py` | 数据质量和泄漏检查 |
| Monitoring | `src/autocare_guard_ml/monitoring.py` | 预测分布和输入分布报告 |
| Alerting | `src/autocare_guard_ml/alerting.py` | pass/warn/critical 告警判断 |
| Versioning | `src/autocare_guard_ml/versioning.py` | 模型、prompt、rubric、后处理版本元数据 |
| API | `src/autocare_guard_ml/api.py` | FastAPI 服务和 Prometheus 指标 |

## 训练策略

训练入口面向 completion-only SFT。公开二分类安全数据会被保守归一，避免向模型注入 `expert_review` 或 `emergency_review` 等强处置标签。

LoRA 可以在 `configs/default.yaml` 中开启：

```yaml
training:
  peft:
    enabled: true
    method: lora
    r: 16
    lora_alpha: 32
    lora_dropout: 0.05
```

## 部署策略

推荐将生产部署拆成两层：

- **Judge Service**：基于 vLLM 的模型推理服务。
- **Audit API Service**：负责 prompt 渲染、解析、后处理、工单路由、日志和指标。

仓库提供：

- `deploy/vllm_serve.sh`
- `deploy/audit_service.env.example`
- `deploy/docker-compose.example.yml`

## 可观测性

API 提供 Prometheus 文本格式指标：

```text
autocare_guard_requests_total
autocare_guard_requests_by_action_total
autocare_guard_parse_non_ok_total
autocare_guard_latency_ms
```

离线监控报告：

```bash
autocare-guard monitor outputs/demo_routed_predictions.jsonl
autocare-guard alerts outputs/demo_routed_predictions.jsonl
```

告警阈值见 `configs/default.yaml` 的 `alert_thresholds`（如 `emergency_review_rate_*`、`missing_vehicle_evidence_rate_*`）。

## 安全边界

本框架有意将模型设计为“决策支持组件”。`emergency_review` 等高影响动作是人工确认建议，不是不可逆的最终处置；模型不直接控车。高影响动作应经过车辆侧证据门禁、策略系统或人工复核。
