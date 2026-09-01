# API 使用说明

本文档说明 FastAPI 售后风险研判服务的接口、鉴权、错误码、审计查询和运维检查方式。它面向生产化展示和接入评审，不替代真实生产网关、密钥系统或集中权限平台。

领域口径为 AutoCare（新能源汽车售后风险研判与工单路由）。项目名 `AutoCare-Guard-ML`，包名 `autocare_guard_ml`，CLI `autocare-guard`。请求与响应同时接受 legacy 输入字段兼容（如 `ticket_id`、`chat_evidence_list`、`final_judgment`、`handling_suggestion`）。

## 启动

本地 demo：

```bash
PYTHONPATH=src autocare-guard --config configs/default.yaml serve --port 8000
```

开启 token、审计、请求大小限制和限流：

```bash
export AUTOCARE_GUARD_API_TOKEN_HASHES="$(python3 - <<'PY'
import hashlib
print(hashlib.sha256('replace-with-a-secret'.encode()).hexdigest() + ':admin')
PY
)"
export AUTOCARE_GUARD_AUDIT_BACKEND=jsonl
export AUTOCARE_GUARD_AUDIT_LOG_PATH=outputs/api_audit_events.jsonl
export AUTOCARE_GUARD_CORS_ORIGINS="http://127.0.0.1:8000,http://localhost:8000"
export AUTOCARE_GUARD_MAX_REQUEST_BYTES=262144
export AUTOCARE_GUARD_RATE_LIMIT_PER_MINUTE=120
PYTHONPATH=src autocare-guard --config configs/default.yaml serve --port 8000
```

## 鉴权与角色

默认不设置 `AUTOCARE_GUARD_API_TOKEN`、`AUTOCARE_GUARD_API_TOKENS` 或 `AUTOCARE_GUARD_API_TOKEN_HASHES` 时，接口保持本地 demo 可访问。设置 token 后，业务接口必须带：

```text
Authorization: Bearer <token>
```

单 token：

```bash
export AUTOCARE_GUARD_API_TOKEN="replace-with-a-secret"
```

多 token + 最小角色权限：

```bash
export AUTOCARE_GUARD_API_TOKENS="writer-token:writer,reader-token:reader,audit-token:auditor"
```

生产化展示推荐只在环境变量里保存 SHA-256 token hash，格式为 `sha256(token):role`：

```bash
export AUTOCARE_GUARD_API_TOKEN_HASHES="a2b...64位hex...9f:writer,0f3...64位hex...1c:auditor"
```

服务端会对请求 Bearer token 做 SHA-256 摘要，并用常量时间比较匹配 hash。`AUTOCARE_GUARD_API_TOKEN` 和 `AUTOCARE_GUARD_API_TOKENS` 仍保留，用于本地 demo 或临时验证。

| 角色 | 可访问能力 |
| --- | --- |
| `admin` | 全部接口 |
| `writer` | `/judge` |
| `reader` | `/dashboard/data`、`/config`、模拟器配置读取 |
| `auditor` | `/audit/tickets/{ticket_id}` |

## 接口表

| 方法 | 路径 | 鉴权权限 | 说明 |
| --- | --- | --- | --- |
| `GET` | `/health` | 无 | 存活检查 |
| `GET` | `/ready` | 无 | 就绪检查和生产 guard 配置摘要 |
| `GET` | `/config` | `config` | 配置摘要（治理权限，最低为 admin） |
| `POST` | `/judge` | `write` | 提交售后服务事件研判 |
| `GET` | `/dashboard/data?window=5m|1h|all` | `read` | 监控大盘数据 |
| `GET` | `/metrics` | 无 | Prometheus 文本指标 |
| `GET` | `/audit/tickets/{ticket_id}` | `audit` | 按 case/ticket 查询审计事件 |
| `GET` | `/simulator/config` | `config` | 读取模拟器配置 |
| `POST` | `/simulator/speed` | `config` | 设置模拟器速度 |

## API 契约

FastAPI 会自动生成 OpenAPI schema。本仓库额外提供 `api-contract` 命令，把关键业务接口作为契约门禁：

```bash
PYTHONPATH=src python3 -m autocare_guard_ml.cli --config configs/default.yaml api-contract \
  --out outputs/openapi_contract.json \
  --fail-on-missing
```

契约要求至少包含：

- `GET /health`
- `GET /ready`
- `GET /config`
- `POST /judge`
- `GET /dashboard/data`
- `GET /metrics`
- `GET /audit/tickets/{ticket_id}`

`make enterprise-check` 和 GitHub Actions 会运行这个检查，防止核心接口被误删或改名。

## 请求 ID

客户端可以传入：

```text
X-Request-ID: req-20260606-0001
```

服务会在响应 header、`/judge` 响应体和审计日志中复用同一个 `request_id`。如果客户端不传，服务自动生成 UUID。

## `/judge` 示例

请求（推荐 AutoCare 字段）：

```bash
curl -X POST http://127.0.0.1:8000/judge \
  -H "Authorization: Bearer replace-with-a-secret" \
  -H "X-Request-ID: req-demo-1" \
  -H "Content-Type: application/json" \
  -d '{
    "case_id": "demo-1",
    "conversation_evidence": [
      {"role": "owner", "text": "充电中闻到焦糊味，车机提示高压异常。"}
    ],
    "vehicle_signal_summary": {
      "motion_state": "charging",
      "alert_summary": ["高压系统告警"],
      "thermal_status": "abnormal_rise"
    },
    "fault_evidence": [
      {"domain": "hv_system", "severity": "critical", "count": 2}
    ],
    "service_history_summary": {
      "repeat_repair_count": 0,
      "open_work_orders": 0
    }
  }'
```

制动场景示例：

```bash
curl -X POST http://127.0.0.1:8000/judge \
  -H "Authorization: Bearer replace-with-a-secret" \
  -H "Content-Type: application/json" \
  -d '{
    "case_id": "demo-brake-1",
    "conversation_evidence": [
      {"role": "owner", "text": "高速上刹车感觉变软，仪表有制动告警。"}
    ],
    "vehicle_signal_summary": {
      "motion_state": "driving",
      "alert_summary": ["制动系统告警"],
      "speed_kph": 80
    },
    "fault_evidence": [
      {"domain": "brake", "severity": "high", "count": 1}
    ]
  }'
```

legacy 输入字段仍兼容，例如可用 `ticket_id` 代替 `case_id`、`chat_evidence_list` 代替 `conversation_evidence`；响应中也会回填部分兼容键名以便过渡。

响应字段：

| 字段 | 说明 |
| --- | --- |
| `risk_level` | `low_risk / mid_risk / high_risk` |
| `event_topic` | 车辆风险主题（如 `动力电池与热安全`）；兼容键 `topic` |
| `event_judgment` | `risk_event / not_risk_event / insufficient_evidence`；兼容键 `final_judgment` |
| `recommended_action` | `information_reply / collect_more_evidence / service_followup / create_work_order / expert_review / emergency_review`；兼容键 `handling_suggestion` |
| `evidence_refs` | 结构化证据引用（source / index / field） |
| `correlation_analysis` | 对话与车辆侧证据关联分析 |
| `uncertainty_reason` | 缺失、冲突或不确定说明 |
| `service_escalation_flags` | 服务升级标记（如 `repeated_complaint`） |
| `route` | 策略路由（如 `information_flow` / `work_order_queue` / `review_queue`） |
| `final_action` | 最终动作建议（候选态，非不可逆执行） |
| `requires_human_review` | 是否进入人工复核 |
| `request_id` / `case_id` | 请求追踪 ID；`ticket_id` 在审计侧兼容回填 |
| `model_version` 等版本字段 | 模型、prompt、rubric、schema、后处理版本 |

## 错误结构

所有生产 guard 和 HTTP 异常使用结构化错误：

```json
{
  "error": {
    "code": "unauthorized",
    "message": "missing or invalid bearer token",
    "request_id": "req-demo-1"
  }
}
```

| HTTP 状态 | `error.code` | 触发条件 |
| --- | --- | --- |
| `401` | `unauthorized` | token 缺失、错误或角色权限不足 |
| `413` | `request_too_large` | 请求体超过 `AUTOCARE_GUARD_MAX_REQUEST_BYTES` |
| `429` | `rate_limited` | 单 IP 每分钟请求数超过 `AUTOCARE_GUARD_RATE_LIMIT_PER_MINUTE` |
| `422` | `validation_error` | FastAPI 请求校验失败 |
| 其他 | `http_error` | 通用 HTTP 异常 |

## 审计查询

JSONL 审计：

```bash
export AUTOCARE_GUARD_AUDIT_BACKEND=jsonl
export AUTOCARE_GUARD_AUDIT_LOG_PATH=outputs/api_audit_events.jsonl
```

SQLite 审计：

```bash
export AUTOCARE_GUARD_AUDIT_BACKEND=sqlite
export AUTOCARE_GUARD_AUDIT_LOG_PATH=outputs/api_audit_events.sqlite
```

查询 case/ticket：

```bash
curl http://127.0.0.1:8000/audit/tickets/demo-1 \
  -H "Authorization: Bearer replace-with-a-secret"
```

审计事件记录版本、风险结果、route、latency、request_id 和 `input_summary`。`input_summary` 包含 payload hash、证据数量、PII 类型和脱敏样例，不保存完整明文证据列表。路径参数仍叫 `ticket_id`，值可使用 `case_id`。

## 监控接口

```bash
curl http://127.0.0.1:8000/dashboard/data?window=5m \
  -H "Authorization: Bearer replace-with-a-secret"

curl http://127.0.0.1:8000/metrics
```

Prometheus 指标包含请求总量、风险等级、主题、动作建议（`recommended_action`）、route、解析异常数和延迟分位数。

## 压测

先启动服务：

```bash
make serve
```

然后运行轻量压测门禁：

```bash
make benchmark-api
```

默认会请求 `/judge` 100 次，生成 `outputs/api_benchmark.json`，并在出现非 2xx 响应或 P95 超过 1200ms 时返回失败。请求量和阈值可以通过 Makefile 变量覆盖：

```bash
BENCHMARK_REQUESTS=300 BENCHMARK_P95_MS=1500 make benchmark-api
```

也可以直接运行脚本：

```bash
python3 scripts/benchmark_api.py \
  --url http://127.0.0.1:8000/judge \
  --requests 100 \
  --token replace-with-a-secret \
  --out outputs/api_benchmark.json \
  --fail-on-non-2xx \
  --fail-on-p95-ms 1200
```

压测脚本用于展示级基准，不替代真实生产压测。生产压测应覆盖多实例、网关、模型队列、长输入、失败重试和审计写入压力。

## 生产接入边界

- Bearer token + SHA-256 hash 配置是生产化展示增强；真实生产仍应使用网关、密钥轮换、租户隔离和集中权限。
- SQLite 适合单机展示；多实例生产应使用 PostgreSQL、日志平台或审计平台。
- `/metrics` 提供指标出口；真实告警应接入 Prometheus、日志平台和 on-call 流程。
- `emergency_review` 等强处置应经过车辆侧证据门禁与人工确认，不应只依赖公开训练数据直接自动执行；模型不直接控车。
