FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8

WORKDIR /app

COPY pyproject.toml README.md LICENSE ./
COPY src ./src
COPY configs ./configs
COPY static ./static

RUN pip install --no-cache-dir -e ".[serve]"

EXPOSE 8000

# P2-09：AUTOCARE_GUARD_CONFIG/HOST/PORT 环境变量真正生效（k8s configmap 注入），
# 未设置时保持原默认值。
CMD ["sh", "-c", "autocare-guard --config \"${AUTOCARE_GUARD_CONFIG:-configs/default.yaml}\" serve --host \"${AUTOCARE_GUARD_HOST:-0.0.0.0}\" --port \"${AUTOCARE_GUARD_PORT:-8000}\""]
