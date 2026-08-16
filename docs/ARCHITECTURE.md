# AI-IM-Guard-ML 架构说明

AI-IM-Guard-ML 是一个面向 IM 私聊风险审核场景的企业级 AI/ML 工程框架。它将模型判断、输出校验、业务路由、可观测性和样本回流拆成相互独立但可组合的模块。

## 设计目标

- 融合聊天语义证据和结构化行为证据。
- 输出机器可解析的审核结论。
- 对高影响处置提供生产保护机制。
- 支持离线评测、监控、告警和审计日志。
- 支持从本地启发式 demo 平滑切换到微调 checkpoint 部署。

## 数据流

```text
审核请求
  -> schema 校验
  -> prompt 渲染
  -> Judge 推理
  -> JSON 解析
  -> 后处理
  -> 策略路由
  -> 版本化审计日志
  -> 监控 / 告警
```

## 核心组件

| 模块 | 文件 | 职责 |
| --- | --- | --- |
| Schema | `src/im_guard_ml/schema.py` | 标签、枚举、字段一致性检查 |
| Prompting | `src/im_guard_ml/prompting.py` | 审核 prompt 和 chat template 渲染 |
| Training | `src/im_guard_ml/training.py` | SFT 与 LoRA 训练入口 |
| Inference | `src/im_guard_ml/inference.py` | 启发式 demo Judge 和 Transformers Judge |
| Parsing | `src/im_guard_ml/parsing.py` | JSON 提取和兜底解析 |
| Postprocess | `src/im_guard_ml/postprocess.py` | 生产保护和策略路由 |
| Evaluation | `src/im_guard_ml/evaluation.py` | 分类指标和一致性指标 |
| Data Audit | `src/im_guard_ml/data_audit.py` | 数据质量和泄漏检查 |
| Monitoring | `src/im_guard_ml/monitoring.py` | 预测分布和输入分布报告 |
| Alerting | `src/im_guard_ml/alerting.py` | pass/warn/critical 告警判断 |
| Versioning | `src/im_guard_ml/versioning.py` | 模型、prompt、rubric、后处理版本元数据 |
| API | `src/im_guard_ml/api.py` | FastAPI 服务和 Prometheus 指标 |

## 训练策略

训练入口面向 completion-only SFT。公开二分类安全数据会被保守归一，避免向模型注入重处置标签，例如 `limit_account` 或 `ban_account`。

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
- **Audit API Service**：负责 prompt 渲染、解析、后处理、策略路由、日志和指标。

仓库提供：

- `deploy/vllm_serve.sh`
- `deploy/audit_service.env.example`
- `deploy/docker-compose.example.yml`

## 可观测性

API 提供 Prometheus 文本格式指标：

```text
im_guard_requests_total
im_guard_ban_total
im_guard_parse_non_ok_total
```

离线监控报告：

```bash
im-guard monitor outputs/demo_routed_predictions.jsonl
im-guard alerts outputs/demo_routed_predictions.jsonl
```

## 安全边界

本框架有意将模型设计为“决策支持组件”。高影响处置不应直接由模型裸输出执行，而应经过策略系统或人工复核。

