# SLO 与告警规则

## SLO

| 指标 | 目标 | 说明 |
| --- | ---: | --- |
| `/judge` P95 延迟 | `<= 1200ms` | demo heuristic 会更低，真实模型以 vLLM 服务为准 |
| JSON 解析异常率 | `<= 2%` | 超过即进入 critical 排查 |
| `ban_account` 占比 | `<= 12%` | 超过说明策略或输入分布可能异常 |
| 服务可用性 | `>= 99.5%` | 展示目标，真实生产需接入网关和探针统计 |

## Prometheus 指标

API 暴露 `/metrics`，包含：

- `im_guard_requests_total`
- `im_guard_requests_by_risk_total`
- `im_guard_requests_by_topic_total`
- `im_guard_requests_by_handling_total`
- `im_guard_requests_by_route_total`
- `im_guard_parse_non_ok_total`
- `im_guard_latency_ms{quantile="avg|p50|p95|p99"}`

## 告警规则

规则模板：[deploy/prometheus/im_guard_alerts.yaml](../deploy/prometheus/im_guard_alerts.yaml)

接入示例：

```bash
kubectl apply -f deploy/prometheus/im_guard_alerts.yaml
```

如果使用普通 Prometheus，而不是 Prometheus Operator，可把 `groups` 内容合并到 Prometheus rule file。

## 滑动窗口异常检测

离线回放、批量预测或线上日志采样后，可以用 `window-alerts` 对连续窗口做异常检测：

```bash
PYTHONPATH=src python3 -m im_guard_ml.cli --config configs/default.yaml window-alerts \
  outputs/demo_routed_predictions.jsonl \
  --window-size 100 \
  --step-size 50
```

该命令会对每个窗口输出：

- `ban_account_rate`
- `parse_non_ok_rate`
- `empty_behavior_rate`
- 相对 baseline 的 `gift_total_value_mean_delta`
- 窗口级 `pass / warn / critical` 状态

默认 baseline 是整批数据的整体监控报告；也可以用 `--baseline-json` 传入固定历史 baseline。它适合做回放验收和问题定位，真实生产仍应接入 Prometheus、日志平台或流式监控系统。

## Drift 检测

`drift-report` 用 PSI、卡方检验和 KS 检验比较当前预测分布与历史 baseline：

```bash
PYTHONPATH=src python3 -m im_guard_ml.cli --config configs/default.yaml drift-report \
  outputs/current_predictions.jsonl \
  --baseline-pred-jsonl outputs/baseline_predictions.jsonl \
  --out outputs/drift_report.json
```

输出包括整体 `stable / drift_warning / drift_critical` 状态，以及每个字段的统计量、p-value、阈值和严重程度。当前覆盖 `risk_level`、`final_judgment`、`handling_suggestion` 和 `gift_total_value`。

## 处理建议

- `IMGuardHighParseErrorRate`：检查模型版本、prompt 版本、输出截断和后处理兜底。
- `IMGuardHighBanRate`：暂停强处置，`ban_account` 全部进人审，排查行为特征和 rubric 变更。
- `IMGuardP95LatencyHigh`：检查输入长度、vLLM queue、prefix cache、限流和实例容量。
- `IMGuardNoTraffic`：检查上游流量、Service/Ingress、指标抓取和认证配置。
