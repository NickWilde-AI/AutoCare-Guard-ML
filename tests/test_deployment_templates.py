from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def _load_yaml(rel: str) -> dict:
    return yaml.safe_load((ROOT / rel).read_text(encoding="utf-8"))


def test_k8s_sqlite_showcase_defaults_to_single_replica():
    deployment = _load_yaml("deploy/k8s/deployment.yaml")
    configmap = _load_yaml("deploy/k8s/configmap.yaml")
    pvc = _load_yaml("deploy/k8s/pvc.yaml")

    assert configmap["data"]["IM_GUARD_AUDIT_BACKEND"] == "sqlite"
    assert deployment["spec"]["replicas"] == 1
    assert pvc["spec"]["accessModes"] == ["ReadWriteOnce"]


def test_k8s_probes_cover_ready_and_health_endpoints():
    deployment = _load_yaml("deploy/k8s/deployment.yaml")
    container = deployment["spec"]["template"]["spec"]["containers"][0]

    assert container["readinessProbe"]["httpGet"] == {"path": "/ready", "port": 8000}
    assert container["livenessProbe"]["httpGet"] == {"path": "/health", "port": 8000}


def test_compose_api_service_keeps_demo_safe_defaults():
    compose = _load_yaml("deploy/docker-compose.example.yml")
    api = compose["services"]["im-guard-api"]

    assert api["build"] == {"context": "..", "dockerfile": "deploy/Dockerfile"}
    assert api["env_file"] == ["audit_service.env.example"]
    assert "../outputs:/app/outputs" in api["volumes"]
    assert api["ports"] == ["8000:8000"]
    assert "/ready" in " ".join(str(part) for part in api["healthcheck"]["test"])

    command = api["command"]
    assert "IM_GUARD_MODEL_PATH" in command
    assert "--model-path" in command
    assert "else" in command
    assert "serve --host" in command


def test_compose_vllm_service_is_separate_gpu_profile_target():
    compose = _load_yaml("deploy/docker-compose.example.yml")
    vllm = compose["services"]["vllm-judge"]

    assert vllm["image"] == "vllm/vllm-openai:latest"
    assert vllm["environment"]["SERVED_MODEL_NAME"] == "im-audit-judge"
    assert vllm["ports"] == ["8001:8001"]
    devices = vllm["deploy"]["resources"]["reservations"]["devices"]
    assert devices == [{"capabilities": ["gpu"]}]


def test_configmap_covers_redline_envs_and_prod_env_keys():
    # P2-39：k8s configmap 必须包含 prod.env.example 中除密钥外的全部键，
    # 特别是 2026-08-19 补的两个红线变量，防止"改了不生效"回流。
    configmap = _load_yaml("deploy/k8s/configmap.yaml")["data"]
    prod_env = (ROOT / "deploy" / "audit_service.prod.env.example").read_text(encoding="utf-8")
    prod_keys = {
        line.split("=", 1)[0].strip()
        for line in prod_env.splitlines()
        if "=" in line and not line.strip().startswith("#")
    }
    # 密钥类走 secret 文件；权重路径由 volume/镜像管理，均不在 configmap 中要求。
    excluded_keys = {
        "IM_GUARD_API_TOKEN", "IM_GUARD_API_TOKENS", "IM_GUARD_API_TOKEN_HASHES",
        "IM_GUARD_MODEL_PATH",
    }
    assert set(configmap) == prod_keys - excluded_keys
    assert configmap["IM_GUARD_P95_LATENCY_BUDGET_MS"] == "1200"
    assert configmap["IM_GUARD_BAN_FPR_REDLINE"] == "0.03"


def test_dockerfile_respects_env_overrides():
    # P2-09：Dockerfile CMD 必须消费 IM_GUARD_CONFIG/HOST/PORT 环境变量。
    dockerfile = (ROOT / "deploy" / "Dockerfile").read_text(encoding="utf-8")
    assert "IM_GUARD_CONFIG" in dockerfile
    assert "IM_GUARD_HOST" in dockerfile
    assert "IM_GUARD_PORT" in dockerfile
