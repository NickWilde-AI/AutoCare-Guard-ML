# 部署与运维说明

这份文档说明公开工程如何部署、配置、灰度和回滚。部署文件是参考模板，不代表完整生产环境或已经验证的容量结论。

## 1. 服务形态

生产建议拆成两层：

- `vLLM Judge Service`：只负责加载 SFT checkpoint 并生成模型原始输出。
- `Audit API Service`：负责组装 prompt、调用模型、解析 JSON、策略路由、版本追踪、审计日志和监控。

这样拆的好处是模型推理和业务后处理解耦。模型服务可以独立扩容，审核服务可以快速迭代策略和后处理。

## 2. 部署模式

| 模式 | 适用场景 | Judge 来源 | 审计后端 | 关键命令 |
| --- | --- | --- | --- | --- |
| 本地验证 | 开发自测、无 GPU 环境 | `HeuristicJudge` | JSONL | `make demo` / `im-guard serve --port 8000` |
| 单机服务 | 有 checkpoint 的单机验证、压测、容器展示 | `TransformersJudge` 或 API Judge | JSONL/SQLite | `docker compose -f deploy/docker-compose.example.yml up --build im-guard-api` |
| 生产部署 | 多实例、网关、监控、审计留存 | vLLM/API 模型服务 + Audit API | PostgreSQL/日志平台优先，SQLite 仅展示 | `kubectl apply -f deploy/k8s/` |

边界说明：

- 本地 demo 只证明工程链路、协议、后处理、监控和审计能跑通，不证明模型效果。
- 单机服务适合验证 checkpoint、请求限制、token 鉴权、SQLite 审计和基础压测。
- 生产部署必须接入企业网关、密钥系统、集中日志、集中审计库、模型注册和灰度平台。

## 3. vLLM 推理服务

示例脚本：[deploy/vllm_serve.sh](../deploy/vllm_serve.sh)

关键参数：

- `MODEL_PATH`：SFT 后的 checkpoint 路径。
- `TP_SIZE`：tensor parallel，一般按 GPU 数和模型大小设置。
- `MAX_MODEL_LEN=8192`：和训练上下文保持一致。
- `--enable-prefix-caching`：rubric、策略表、JSON Schema 是稳定前缀，可降低首 token 延迟。
- `GPU_MEMORY_UTILIZATION`：控制显存使用上限，避免 KV cache 把实例打爆。

示例：

```bash
MODEL_PATH=outputs/im-audit-judge \
TP_SIZE=4 \
MAX_MODEL_LEN=8192 \
bash deploy/vllm_serve.sh
```

## 4. 审核 API 服务

审核 API 负责业务链路，不只是推理。

职责：

- 接收 `audit_scene / chat_evidence_list / behavior_abnormal_list`。
- 根据主题选择 rubric。
- 调用 Judge。
- 解析和校验 JSON。
- 输出 `route / final_action`。
- 写审计日志。
- 暴露健康检查和配置查询。

本仓库提供 FastAPI 入口：

```bash
im-guard serve --model-path outputs/im-audit-judge --port 8000
```

单机容器构建：

```bash
docker build -f deploy/Dockerfile -t ai-im-guard-ml:latest .
docker run --rm -p 8000:8000 \
  --env-file deploy/audit_service.prod.env.example \
  -v "$PWD/outputs:/app/outputs" \
  ai-im-guard-ml:latest
```

Compose 启动：

```bash
docker compose -f deploy/docker-compose.example.yml up --build im-guard-api
docker compose -f deploy/docker-compose.example.yml logs -f im-guard-api
docker compose -f deploy/docker-compose.example.yml down
```

Compose 示例会在 `IM_GUARD_MODEL_PATH` 指向的文件或目录存在时加载 checkpoint；如果路径为空或不存在，则自动使用启发式 demo Judge，避免没有模型文件时服务无法启动。API 服务包含 `/ready` healthcheck。

`deploy/docker-compose.example.yml` 中的 `env_file` 相对 compose 文件所在目录解析，因此默认读取 `deploy/audit_service.env.example`；`../outputs:/app/outputs` 会把仓库根目录的 `outputs/` 挂到容器内审计输出目录。

生产化环境变量 preflight：

```bash
PYTHONPATH=src im-guard --config configs/default.yaml production-preflight \
  --env-file deploy/audit_service.prod.env.example \
  --out outputs/production_preflight.json
```

该检查会验证：

- API 鉴权是否开启。
- token hash 是否为合法 SHA-256 格式。
- CORS 是否不是 wildcard。
- 审计后端和审计路径是否配置。
- 请求大小限制和基础限流是否开启。

示例 `prod.env` 里的全零 hash 只用于模板占位，preflight 会返回 `warn`，真实部署前必须替换。

K8s 模板：

```bash
kubectl apply -f deploy/k8s/configmap.yaml
kubectl apply -f deploy/k8s/secret.example.yaml
kubectl apply -f deploy/k8s/pvc.yaml
kubectl apply -f deploy/k8s/deployment.yaml
kubectl apply -f deploy/k8s/service.yaml
```

说明：[deploy/k8s/README.md](../deploy/k8s/README.md)

服务同时提供 Prometheus 文本格式指标：

```bash
curl http://127.0.0.1:8000/metrics
```

## 5. 运维命令速查

### 本地 demo

```bash
make demo
make demo-stop
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/ready
curl http://127.0.0.1:8000/metrics
```

### 单机 API

```bash
PYTHONPATH=src im-guard --config configs/default.yaml serve --port 8000
IM_GUARD_API_TOKEN=replace-with-a-secret PYTHONPATH=src im-guard --config configs/default.yaml serve --port 8000
python3 scripts/benchmark_api.py --url http://127.0.0.1:8000/judge --requests 100 --token replace-with-a-secret
```

### Docker Compose

```bash
docker compose -f deploy/docker-compose.example.yml up --build -d im-guard-api
docker compose -f deploy/docker-compose.example.yml ps
docker compose -f deploy/docker-compose.example.yml logs -f im-guard-api
docker compose -f deploy/docker-compose.example.yml exec im-guard-api im-guard --config configs/default.yaml readiness-check --project-root /app
docker compose -f deploy/docker-compose.example.yml down
```

### K8s

```bash
kubectl rollout status deployment/im-guard-api
kubectl get pods -l app=im-guard-api
kubectl logs deploy/im-guard-api --tail=100
kubectl port-forward svc/im-guard-api 8000:8000
curl http://127.0.0.1:8000/ready
kubectl rollout restart deployment/im-guard-api
```

## 6. 故障排查

| 现象 | 首先检查 | 常见原因 | 处理 |
| --- | --- | --- | --- |
| Python 启动时报中文路径解码错误 | `echo $LANG $LC_ALL` | locale 为 `C` 或 ASCII | 设置 `LANG=en_US.UTF-8`、`LC_ALL=en_US.UTF-8`，详见 `docs/LOCAL_ENV_ROOT_CAUSE.md` |
| `/ready` 不通过 | 环境变量、审计路径、模型路径 | token/审计路径配置错误，checkpoint 不存在 | 先用启发式 demo 启动，再逐项打开模型和审计配置 |
| `/judge` 返回 401 | `Authorization` header | 设置了 `IM_GUARD_API_TOKEN`、`IM_GUARD_API_TOKENS` 或 `IM_GUARD_API_TOKEN_HASHES` | 使用 `Authorization: Bearer <token>`，确认角色有 `write` 权限 |
| `/judge` 返回 413 | 请求大小 | 聊天证据或行为证据过长 | 调整 `IM_GUARD_MAX_REQUEST_BYTES`，生产上游应做证据摘要 |
| `/judge` 返回 429 | 客户端 IP 请求频率 | 基础限流触发 | 调整 `IM_GUARD_RATE_LIMIT_PER_MINUTE` 或接入网关限流 |
| 解析失败率升高 | `/metrics`、`window-alerts`、`drift-report` | prompt、模型版本、输出截断变化 | 降级到人审/规则，回滚 prompt 或模型 |
| ban 占比异常升高 | `im_guard_requests_by_handling_total`、窗口告警 | 输入分布变化、rubric 或后处理变化 | 暂停自动 ban，全部进人审，做 drift 检测和事故复盘 |
| SQLite 审计查询慢 | 审计文件大小、多副本写入 | SQLite 只适合单机展示 | 生产迁移到 PostgreSQL 或日志平台 |

## 7. 环境变量

示例配置：[deploy/audit_service.env.example](../deploy/audit_service.env.example)

重要变量：

- `IM_GUARD_MODEL_PATH`：模型路径。
- `IM_GUARD_API_TOKEN`：可选 Bearer Token；为空时保持本地 demo 兼容，非空时业务接口必须带 `Authorization: Bearer <token>`。
- `IM_GUARD_API_TOKENS`：可选多 token 角色配置，格式为 `token:role,token2:role2`；角色支持 `admin / writer / reader / auditor`。
- `IM_GUARD_API_TOKEN_HASHES`：可选多 token 哈希角色配置，格式为 `sha256(token):role,sha256(token2):role2`；生产化展示优先使用，服务端使用常量时间比较校验。
- `IM_GUARD_CORS_ORIGINS`：允许跨域来源，多个来源用逗号分隔，默认 `*`。
- `IM_GUARD_AUDIT_BACKEND`：审计后端，支持 `jsonl` 和 `sqlite`；生产化展示建议使用 `sqlite`。
- `IM_GUARD_AUDIT_LOG_PATH`：API 审计落盘路径，默认 `outputs/api_audit_events.jsonl`；SQLite 示例为 `outputs/api_audit_events.sqlite`。
- `IM_GUARD_MAX_REQUEST_BYTES`：单次请求体大小上限，默认 `262144`。
- `IM_GUARD_RATE_LIMIT_PER_MINUTE`：按客户端 IP 的每分钟基础限流，默认 `120`；设为 `0` 可关闭。
- `IM_GUARD_P95_LATENCY_BUDGET_MS`：延迟红线，运行时覆盖 rollout guardrail `p95_latency_ms_max`（src/im_guard_ml/rollout.py）。
- `IM_GUARD_BAN_FPR_REDLINE`：ban 误杀红线，运行时覆盖 rollout guardrail `ban_account_fpr_max`（src/im_guard_ml/rollout.py）。

## 8. 灰度配置

灰度和 A/B 配置示例：[configs/rollout.yaml](../configs/rollout.yaml)

推荐灰度参数：

| 阶段 | 流量 | 模型动作 | 规则引擎 |
| --- | ---: | --- | --- |
| shadow | 1% | 只预测入库 | 主处置 |
| small | 10% | warning/limit 可进入策略，ban 人审 | 兜底 |
| ramp | 50% | 模型主链路 | 强规则兜底 |
| full | 100% | 模型主链路 | 异常兜底 |

每个阶段观察：

- `ban_account_rate`
- `ban_account FPR`
- 人审改判率
- 客诉率
- JSON 解析失败率
- P95/P99 延迟
- 上游行为特征分布
- `im_guard_requests_by_risk_total`
- `im_guard_requests_by_topic_total`
- `im_guard_requests_by_handling_total`
- `im_guard_requests_by_route_total`

## 9. 回滚策略

必须能快速回滚到上一版本。

触发条件：

- ban FPR 超过红线。
- 客诉率突增。
- 行为特征分布异常。
- JSON 解析失败率升高。
- P95 延迟超预算。
- 人审队列被 ban 样本打爆。

回滚动作：

- 流量切回规则引擎。
- 模型切回上一 checkpoint。
- 禁止 ban 自动流转，只保留人审。
- 固定当前日志和样本，做事故复盘。

## 10. 容量估算

粗略估算思路：

```text
所需实例数 = 峰值 QPS / 单实例稳定 QPS / 安全系数
```

如果单实例稳定 QPS 25-30，线上峰值 80-100 QPS，至少需要 4 个实例，并保留 30%-40% 余量。P99 延迟升高时，优先看 vLLM queue time、输入 token 长度和 KV cache 命中率。

## 11. 部署原则

模型推理和审核业务服务应解耦：vLLM 负责生成，审核服务负责 prompt、JSON 校验、策略路由、审计和监控。高影响动作进入人工复核；模型、prompt、rubric、特征 schema 和后处理版本应共同记录，便于追溯与回滚。
