PYTHON ?= $(shell [ -f .venv/bin/python ] && echo .venv/bin/python || echo python3)
PYTHONPATH := src
CONFIG ?= configs/default.yaml
INPUT ?= data/local/input.jsonl
OUT_DIR ?= outputs
PORT ?= 8000
API_MODEL ?= qwen-plus
SIM_INTERVAL ?= 1
XGUARD_RAW ?= data/external/xguard_train_open_200k.jsonl
XGUARD_TRAIN ?= data/train/xguard_public_train.jsonl
XGUARD_SPLITS ?= data/train/xguard_splits
BENCHMARK_REQUESTS ?= 100
BENCHMARK_CONCURRENCY ?= 1
BENCHMARK_P95_MS ?= 1200

.PHONY: summary predict predict-route eval monitor alerts window-alerts drift-report ab-report api-contract production-preflight model-registry-check audit-data build-demo download-xguard build-xguard audit-xguard train-readiness eval-report delivery-summary readiness-check benchmark-api benchmark-stress enterprise-check compile clean serve simulator demo test

summary:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m im_guard_ml.cli --config $(CONFIG) summary $(INPUT)

predict:
	mkdir -p $(OUT_DIR)
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m im_guard_ml.cli --config $(CONFIG) predict $(INPUT) --out $(OUT_DIR)/demo_predictions.jsonl

predict-route:
	mkdir -p $(OUT_DIR)
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m im_guard_ml.cli --config $(CONFIG) predict $(INPUT) --with-route --with-version --audit-log-out $(OUT_DIR)/demo_audit_logs.jsonl --out $(OUT_DIR)/demo_routed_predictions.jsonl

eval: predict
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m im_guard_ml.cli --config $(CONFIG) eval $(OUT_DIR)/demo_predictions.jsonl

monitor: predict-route
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m im_guard_ml.cli --config $(CONFIG) monitor $(OUT_DIR)/demo_routed_predictions.jsonl

alerts: predict-route
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m im_guard_ml.cli --config $(CONFIG) alerts $(OUT_DIR)/demo_routed_predictions.jsonl

window-alerts: predict-route
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m im_guard_ml.cli --config $(CONFIG) window-alerts $(OUT_DIR)/demo_routed_predictions.jsonl --window-size 20 --step-size 10

drift-report: predict-route
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m im_guard_ml.cli --config $(CONFIG) drift-report $(OUT_DIR)/demo_routed_predictions.jsonl --baseline-pred-jsonl $(OUT_DIR)/demo_routed_predictions.jsonl --out $(OUT_DIR)/drift_report.json

ab-report: predict-route
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m im_guard_ml.cli --config configs/rollout.yaml ab-report --control $(OUT_DIR)/demo_routed_predictions.jsonl --candidate $(OUT_DIR)/demo_routed_predictions.jsonl --out $(OUT_DIR)/ab_report.md --json-out $(OUT_DIR)/ab_report.json

api-contract:
	mkdir -p $(OUT_DIR)
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m im_guard_ml.cli --config $(CONFIG) api-contract --out $(OUT_DIR)/openapi_contract.json --fail-on-missing

production-preflight:
	mkdir -p $(OUT_DIR)
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m im_guard_ml.cli --config $(CONFIG) production-preflight --env-file deploy/audit_service.prod.env.example --out $(OUT_DIR)/production_preflight.json

model-registry-check:
	mkdir -p $(OUT_DIR)
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m im_guard_ml.cli --config $(CONFIG) model-registry-check --registry configs/model_registry.yaml --out $(OUT_DIR)/model_registry_check.json

audit-data:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m im_guard_ml.cli --config $(CONFIG) audit-data $(INPUT)

build-demo:
	mkdir -p $(OUT_DIR)
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m im_guard_ml.build_dataset --internal $(INPUT) --out $(OUT_DIR)/built_train.jsonl

download-xguard:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) scripts/download_xguard_dataset.py --out $(XGUARD_RAW)

build-xguard:
	mkdir -p data/train
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m im_guard_ml.build_dataset --public-xguard $(XGUARD_RAW) --out $(XGUARD_TRAIN) --split-out-dir $(XGUARD_SPLITS)

audit-xguard:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m im_guard_ml.cli --config $(CONFIG) audit-data $(XGUARD_TRAIN)

train-readiness:
	mkdir -p $(OUT_DIR)
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m im_guard_ml.cli --config $(CONFIG) train-readiness $(XGUARD_SPLITS)/train.jsonl --out $(OUT_DIR)/training_readiness.json

eval-report: predict-route
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m im_guard_ml.cli --config $(CONFIG) eval-report $(OUT_DIR)/demo_routed_predictions.jsonl --out $(OUT_DIR)/offline_eval_report.md

delivery-summary:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m im_guard_ml.cli --config $(CONFIG) delivery-summary --project-root . --out $(OUT_DIR)/enterprise_delivery_summary.md

readiness-check:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m im_guard_ml.cli --config $(CONFIG) readiness-check --project-root . --out $(OUT_DIR)/readiness_check.json

benchmark-api:
	mkdir -p $(OUT_DIR)
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) scripts/benchmark_api.py --url http://127.0.0.1:$(PORT)/judge --requests $(BENCHMARK_REQUESTS) --concurrency $(BENCHMARK_CONCURRENCY) --out $(OUT_DIR)/api_benchmark.json --fail-on-non-2xx --fail-on-p95-ms $(BENCHMARK_P95_MS)

benchmark-stress:
	mkdir -p $(OUT_DIR)
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) scripts/benchmark_api.py --url http://127.0.0.1:$(PORT)/judge --requests 200 --concurrency 50 --warmup 5 --out $(OUT_DIR)/api_stress_test.json --fail-on-p95-ms $(BENCHMARK_P95_MS)

enterprise-check: test compile api-contract production-preflight model-registry-check delivery-summary readiness-check

compile:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m compileall -q src

clean:
	rm -rf $(OUT_DIR) **/__pycache__ .pytest_cache *.egg-info

# === 服务与演示 ===

serve:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m im_guard_ml.cli --config $(CONFIG) serve --port $(PORT)

serve-api:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m im_guard_ml.cli --config $(CONFIG) serve --port $(PORT) --api --api-model $(API_MODEL)

simulator:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m im_guard_ml.simulator --port $(PORT) --interval $(SIM_INTERVAL)

demo:
	@echo "启动审核服务 (端口 $(PORT))..."
	@PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m im_guard_ml.cli --config $(CONFIG) serve --port $(PORT) &
	@sleep 2
	@echo "启动数据模拟器 (间隔 $(SIM_INTERVAL)秒)..."
	@PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m im_guard_ml.simulator --port $(PORT) --interval $(SIM_INTERVAL) &
	@sleep 1
	@echo "打开监控大盘..."
	@open static/Guard-ML.html
	@echo ""
	@echo "=== 演示已启动 ==="
	@echo "  监控大盘: static/Guard-ML.html"
	@echo "  审核接口: http://127.0.0.1:$(PORT)/judge"
	@echo "  健康检查: http://127.0.0.1:$(PORT)/health"
	@echo "  指标接口: http://127.0.0.1:$(PORT)/metrics"
	@echo "  数据接口: http://127.0.0.1:$(PORT)/dashboard/data"
	@echo ""
	@echo "按 Ctrl+C 停止所有服务"
	@wait

demo-stop:
	@pkill -f "im_guard_ml.simulator" 2>/dev/null || true
	@pkill -f "im_guard_ml.cli.*serve" 2>/dev/null || true
	@echo "所有服务已停止"

test:
	$(PYTHON) -m pytest tests/ -v
