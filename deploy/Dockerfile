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

CMD ["im-guard", "--config", "configs/default.yaml", "serve", "--host", "0.0.0.0", "--port", "8000"]
