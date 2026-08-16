# 命令手册

本文档整理本项目常用命令，覆盖本地 demo、数据检查、评测、监控、告警、训练和部署。

## 本地 Demo

```bash
PYTHONPATH=src python3 -m im_guard_ml.cli --config configs/default.yaml summary data/local/input.jsonl

PYTHONPATH=src python3 -m im_guard_ml.cli --config configs/default.yaml predict data/local/input.jsonl \
  --with-route \
  --with-version \
  --audit-log-out outputs/demo_audit_logs.jsonl \
  --out outputs/demo_routed_predictions.jsonl

PYTHONPATH=src python3 -m im_guard_ml.cli --config configs/default.yaml eval outputs/demo_routed_predictions.jsonl
PYTHONPATH=src python3 -m im_guard_ml.cli --config configs/default.yaml eval-report outputs/demo_routed_predictions.jsonl --out outputs/offline_eval_report.md
PYTHONPATH=src python3 -m im_guard_ml.cli --config configs/default.yaml delivery-summary --out outputs/enterprise_delivery_summary.md
PYTHONPATH=src python3 -m im_guard_ml.cli --config configs/default.yaml readiness-check --out outputs/readiness_check.json
PYTHONPATH=src python3 -m im_guard_ml.cli --config configs/default.yaml monitor outputs/demo_routed_predictions.jsonl
PYTHONPATH=src python3 -m im_guard_ml.cli --config configs/default.yaml alerts outputs/demo_routed_predictions.jsonl
PYTHONPATH=src python3 -m im_guard_ml.cli --config configs/default.yaml window-alerts outputs/demo_routed_predictions.jsonl --window-size 100 --step-size 50
PYTHONPATH=src python3 -m im_guard_ml.cli --config configs/default.yaml drift-report outputs/demo_routed_predictions.jsonl --baseline-pred-jsonl outputs/demo_routed_predictions.jsonl --out outputs/drift_report.json
PYTHONPATH=src python3 -m im_guard_ml.cli --config configs/default.yaml ab-report --control outputs/demo_routed_predictions.jsonl --candidate outputs/demo_routed_predictions.jsonl --out outputs/ab_report.md --json-out outputs/ab_report.json
PYTHONPATH=src python3 -m im_guard_ml.cli --config configs/default.yaml api-contract --out outputs/openapi_contract.json --fail-on-missing
PYTHONPATH=src python3 -m im_guard_ml.cli --config configs/default.yaml production-preflight --env-file deploy/audit_service.prod.env.example --out outputs/production_preflight.json
PYTHONPATH=src python3 -m im_guard_ml.cli --config configs/default.yaml model-registry-check --registry configs/model_registry.yaml --out outputs/model_registry_check.json
PYTHONPATH=src python3 -m im_guard_ml.cli --config configs/default.yaml audit-data data/local/input.jsonl
```

## Makefile 快捷命令

```bash
make summary
make predict
make predict-route
make eval
make monitor
make alerts
make window-alerts
make drift-report
make ab-report
make api-contract
make production-preflight
make model-registry-check
make audit-data
make build-demo
make download-xguard
make build-xguard
make audit-xguard
make eval-report
make delivery-summary
make readiness-check
make enterprise-check
make compile
```

## 构造训练数据

下载 XGuard 公开安全训练集到本地忽略目录：

```bash
python3 scripts/download_xguard_dataset.py
```

将 XGuard 转换为本项目训练格式：

```bash
PYTHONPATH=src python3 -m im_guard_ml.build_dataset \
  --public-xguard data/external/xguard_train_open_200k.jsonl \
  --out data/train/xguard_public_train.jsonl \
  --split-out-dir data/train/xguard_splits
```

转换后做数据质量检查：

```bash
PYTHONPATH=src python3 -m im_guard_ml.cli audit-data data/train/xguard_public_train.jsonl
```

完整快捷命令：

```bash
make download-xguard
make build-xguard
make audit-xguard
```

```bash
PYTHONPATH=src python3 -m im_guard_ml.build_dataset \
  --internal data/raw/history_tickets.jsonl \
  --internal data/raw/synthetic_cases.jsonl \
  --internal data/raw/refinement_cases.jsonl \
  --public data/raw/public_binary_safety.jsonl \
  --public-xguard data/external/xguard_train_open_200k.jsonl \
  --out data/train/im_audit_train.jsonl
```

## 训练

```bash
pip install -e ".[train]"
im-guard --config configs/default.yaml train data/train/im_audit_train.jsonl
```

在 `configs/default.yaml` 中开启 LoRA：

```yaml
training:
  peft:
    enabled: true
```

## API 服务

```bash
pip install -e ".[serve]"
im-guard --config configs/default.yaml serve --port 8000
```

开启 Bearer Token 鉴权和审计落盘：

```bash
export IM_GUARD_API_TOKEN="replace-with-a-secret"
export IM_GUARD_AUDIT_LOG_PATH="outputs/api_audit_events.jsonl"
export IM_GUARD_CORS_ORIGINS="http://127.0.0.1:8000,http://localhost:8000"
export IM_GUARD_MAX_REQUEST_BYTES=262144
export IM_GUARD_RATE_LIMIT_PER_MINUTE=120
im-guard --config configs/default.yaml serve --port 8000
```

生产化展示建议改用 SHA-256 token hash，不在环境变量中保存明文 token：

```bash
export IM_GUARD_API_TOKEN_HASHES="$(python3 - <<'PY'
import hashlib
print(hashlib.sha256('replace-with-a-secret'.encode()).hexdigest() + ':admin')
PY
)"
```

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/ready
curl http://127.0.0.1:8000/config
curl http://127.0.0.1:8000/metrics
```

带 token 调用审核接口：

```bash
curl -X POST http://127.0.0.1:8000/judge \
  -H "Authorization: Bearer replace-with-a-secret" \
  -H "Content-Type: application/json" \
  -d '{"ticket_id":"demo-1","chat_evidence_list":["加微信稳赚，带你投资。"],"behavior_abnormal_list":["短时间高频私聊。"]}'
```

按 `ticket_id` 查询 API 审计事件：

```bash
curl http://127.0.0.1:8000/audit/tickets/demo-1 \
  -H "Authorization: Bearer replace-with-a-secret"
```

使用 SQLite 审计后端：

```bash
export IM_GUARD_AUDIT_BACKEND=sqlite
export IM_GUARD_AUDIT_LOG_PATH=outputs/api_audit_events.sqlite
```

容器启动：

```bash
docker build -f deploy/Dockerfile -t ai-im-guard-ml:latest .
docker run --rm -p 8000:8000 \
  --env-file deploy/audit_service.prod.env.example \
  -v "$PWD/outputs:/app/outputs" \
  ai-im-guard-ml:latest
```

K8s 模板：

```bash
kubectl apply -f deploy/k8s/configmap.yaml
kubectl apply -f deploy/k8s/secret.example.yaml
kubectl apply -f deploy/k8s/pvc.yaml
kubectl apply -f deploy/k8s/deployment.yaml
kubectl apply -f deploy/k8s/service.yaml
```

多 token 角色配置：

```bash
export IM_GUARD_API_TOKENS="writer-token:writer,reader-token:reader,audit-token:auditor"
```

多 token hash 角色配置：

```bash
export IM_GUARD_API_TOKEN_HASHES="<writer-token-64-hex-sha256>:writer,<reader-token-64-hex-sha256>:reader,<audit-token-64-hex-sha256>:auditor"
```

## 本地开发环境

```bash
export LANG=en_US.UTF-8
export LC_ALL=en_US.UTF-8
pip install -e ".[dev,serve]"
make test
```

生产化展示验收：

```bash
make enterprise-check
PYTHONPATH=src python3 -m im_guard_ml.cli readiness-check --project-root . --out outputs/readiness_check.json
```

`readiness-check` 会检查核心交付物、`.gitignore` 中的大数据忽略规则、本机 XGuard 下载与转换文件。仓库核心交付物缺失会返回失败；本机大数据文件缺失只返回 warn，因为这些文件不应提交到 git。

训练前检查：

```bash
make train-readiness
```

`train-readiness` 会生成 `outputs/training_readiness.json`，检查训练集、公开数据强处置污染、训练依赖和硬件条件。当前默认 7B 配置需要 GPU 训练环境；无 GPU 本机可以完成数据审计、训练前置验收和小模型完整链路训练，但不适合直接完成高质量 SFT。

本机 MPS Qwen LoRA：

```bash
LC_ALL=en_US.UTF-8 LANG=en_US.UTF-8 \
PYTHONPATH=src im-guard --config configs/local_mps_train.yaml train data/train/xguard_splits/train.jsonl
```

本机快速完整链路训练：

```bash
LC_ALL=en_US.UTF-8 LANG=en_US.UTF-8 \
PYTHONPATH=src im-guard --config configs/local_fast_full_train.yaml train data/train/xguard_splits/train.jsonl
```

快速配置会生成 checkpoint，但只用于验证训练工程链路，不用于证明模型精度。

## GitHub CI

仓库包含 `.github/workflows/ci.yml`，会在 push 和 pull request 时运行：

```bash
python -m pip install -e ".[dev,serve]"
make enterprise-check
```

CI 会上传 `outputs/openapi_contract.json`、`outputs/production_preflight.json`、`outputs/model_registry_check.json`、`outputs/enterprise_delivery_summary.md` 和 `outputs/readiness_check.json` 作为 artifact。workflow 使用 Node 24 兼容的官方 Actions major 版本，并显式启用 Node 24 运行时兼容开关，避免未来 runner 默认升级时门禁失效。CI 不下载 XGuard 大数据；大数据只保留在本地忽略目录。

## 轻量压力测试

先启动服务，再运行：

```bash
make serve
make benchmark-api
```

如果开启了 `IM_GUARD_API_TOKEN`：

```bash
python3 scripts/benchmark_api.py \
  --url http://127.0.0.1:8000/judge \
  --requests 100 \
  --token replace-with-a-secret \
  --out outputs/api_benchmark.json \
  --fail-on-non-2xx \
  --fail-on-p95-ms 1200
```

`make benchmark-api` 默认生成 `outputs/api_benchmark.json`，并通过 `BENCHMARK_REQUESTS` 和 `BENCHMARK_P95_MS` 覆盖请求量与 P95 门槛。

## SLO 与告警

Prometheus 告警规则模板：

```bash
kubectl apply -f deploy/prometheus/im_guard_alerts.yaml
```

说明见：[SLO_AND_ALERTING.md](SLO_AND_ALERTING.md)

离线回放或批量预测结果的滑动窗口异常检测：

```bash
PYTHONPATH=src python3 -m im_guard_ml.cli --config configs/default.yaml window-alerts \
  outputs/demo_routed_predictions.jsonl \
  --window-size 100 \
  --step-size 50
```

相对历史 baseline 的漂移检测：

```bash
PYTHONPATH=src python3 -m im_guard_ml.cli --config configs/default.yaml drift-report \
  outputs/current_predictions.jsonl \
  --baseline-pred-jsonl outputs/baseline_predictions.jsonl \
  --out outputs/drift_report.json
```

也可以先用 `monitor` 生成 baseline JSON，再传入 `--baseline-json`。

## vLLM

```bash
MODEL_PATH=outputs/im-audit-judge \
TP_SIZE=4 \
MAX_MODEL_LEN=8192 \
bash deploy/vllm_serve.sh
```
