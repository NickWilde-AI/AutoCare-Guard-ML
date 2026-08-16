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
