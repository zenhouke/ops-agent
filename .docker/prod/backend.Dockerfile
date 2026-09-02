FROM python:3.13.15-slim-bookworm@sha256:ed86c82274b3c69b52fb5820f358f0bd7df0b603332063cb5c6e32bd220c3e6e

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    OPS_AGENT_ENV=production \
    OPS_AGENT_DATA_DIR=/data

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl openssh-client \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 10001 ops-agent \
    && useradd --system --uid 10001 --gid 10001 --home-dir /nonexistent ops-agent

WORKDIR /app
COPY requirements.lock ./
RUN pip install --no-cache-dir --require-hashes -r requirements.lock
COPY src ./src
RUN install -d -m 0700 -o ops-agent -g ops-agent /data

USER 10001:10001
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "app.api:app", "--app-dir", "src", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--timeout-keep-alive", "15"]
