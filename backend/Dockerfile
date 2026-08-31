# syntax=docker/dockerfile:1.7
FROM python:3.11-slim@sha256:90744cff8f32887f075c47d747a173ff333e9e98801667af93c357fa9f5e28ff

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONHASHSEED=0

WORKDIR /app
RUN apt-get update \
    && apt-get install -y --no-install-recommends libzbar0 libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*
COPY requirements-base.lock.txt requirements-cpu.lock.txt ./
RUN --mount=type=cache,target=/root/.cache/pip \
    python -m pip install -r requirements-cpu.lock.txt
COPY . .
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=5s --start-period=30s --retries=12 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4).read()"]
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
