# SLO 与告警规则

## SLO

| 指标 | 目标 | 说明 |
| --- | ---: | --- |
| `/judge` P95 延迟 | `<= 1200ms` | demo heuristic 会更低，真实模型以 vLLM 服务为准 |
| JSON 解析异常率 | `<= 2%` | 超过即进入 critical 排查；warn 阈值见 `configs/default.yaml` |
| `emergency_review_rate` | warn `> 0.05` / critical `> 0.08` | 紧急建议占全部请求比例；与 FPR 分母不同 |
| 服务可用性 | `>= 99.5%` | 展示目标，真实生产需接入网关和探针统计 |

## Prometheus 指标

API 暴露 `/metrics`，包含：

- `autocare_guard_requests_total`
- `autocare_guard_requests_by_risk_total`
- `autocare_guard_requests_by_topic_total`
- `autocare_guard_requests_by_action_total`
- `autocare_guard_requests_by_handling_total`（legacy 标签名，值同 recommended_action）
- `autocare_guard_requests_by_route_total`
- `autocare_guard_parse_non_ok_total`
- `autocare_guard_latency_ms{quantile="avg|p50|p95|p99"}`

## 告警规则

规则模板：[deploy/prometheus/autocare_guard_alerts.yaml](../deploy/prometheus/autocare_guard_alerts.yaml)

接入示例：

```bash
kubectl apply -f deploy/prometheus/autocare_guard_alerts.yaml
```

如果使用普通 Prometheus，而不是 Prometheus Operator，可把 `groups` 内容合并到 Prometheus rule file。

建议关注的告警语义：

| 语义 | 触发条件（示意） | 处理 |
| --- | --- | --- |
| 解析异常率过高 | `parse_non_ok_total / requests_total > 0.02` | 检查模型版本、prompt 版本、输出截断和后处理兜底 |
| 紧急动作占比过高 | 紧急动作计数 / 请求总量超过策略阈值 | 暂停强处置，全部进人工确认，排查车辆特征与 rubric 变更 |
| P95 延迟过高 | `autocare_guard_latency_ms{quantile="p95"} > 1200` | 检查输入长度、vLLM queue、prefix cache、限流和实例容量 |
| 长时间无流量 | `requests_total == 0` 持续一段时间 | 检查上游流量、Service/Ingress、指标抓取和认证配置 |

离线告警阈值以 `configs/default.yaml` 的 `alert_thresholds` 为准：

- `emergency_review_rate_warn / critical`
- `parse_non_ok_rate_warn / critical`
- `missing_vehicle_evidence_rate_warn / critical`
- `missing_vehicle_evidence_mean_delta_warn / critical`

## 滑动窗口异常检测

离线回放、批量预测或线上日志采样后，可以用 `window-alerts` 对连续窗口做异常检测：

```bash
PYTHONPATH=src python3 -m autocare_guard_ml.cli --config configs/default.yaml window-alerts \
  outputs/demo_routed_predictions.jsonl \
  --window-size 100 \
  --step-size 50
```

该命令会对每个窗口输出：

- `emergency_review_rate`
- `parse_non_ok_rate`
- `missing_vehicle_evidence_rate`
- 相对 baseline 的 `missing_vehicle_evidence_mean_delta`
- 窗口级 `pass / warn / critical` 状态

默认 baseline 是整批数据的整体监控报告；也可以用 `--baseline-json` 传入固定历史 baseline。它适合做回放验收和问题定位，真实生产仍应接入 Prometheus、日志平台或流式监控系统。

## Drift 检测

`drift-report` 用 PSI、卡方检验和 KS 检验比较当前预测分布与历史 baseline：

```bash
PYTHONPATH=src python3 -m autocare_guard_ml.cli --config configs/default.yaml drift-report \
  outputs/current_predictions.jsonl \
  --baseline-pred-jsonl outputs/baseline_predictions.jsonl \
  --out outputs/drift_report.json
```

输出包括整体 `stable / drift_warning / drift_critical` 状态，以及每个字段的统计量、p-value、阈值和严重程度。当前覆盖 `risk_level`、`event_judgment`、`recommended_action` 和车辆侧证据缺失相关字段。

## 处理建议

- 解析异常：检查模型版本、prompt 版本、输出截断和后处理兜底。
- 紧急动作占比异常：暂停强处置，全部进人工确认，排查车辆特征和 rubric 变更。
- P95 延迟：检查输入长度、vLLM queue、prefix cache、限流和实例容量。
- 无流量：检查上游流量、Service/Ingress、指标抓取和认证配置。
