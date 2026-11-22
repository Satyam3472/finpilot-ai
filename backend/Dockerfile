FROM python:3.12-slim-trixie@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b AS dependencies
ENV PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /build
COPY requirements.lock .
RUN python -m venv /opt/venv && /opt/venv/bin/pip install --no-cache-dir -r requirements.lock

FROM python:3.12-slim-trixie@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b
ENV PATH="/opt/venv/bin:$PATH" PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 FINPILOT_DATA_DIR=/data
RUN groupadd --gid 10001 finpilot && useradd --uid 10001 --gid 10001 --no-create-home finpilot \
    && install -d -m 0700 -o finpilot -g finpilot /data
WORKDIR /app
COPY --from=dependencies /opt/venv /opt/venv
COPY backend backend
COPY finance_agent finance_agent
COPY scripts scripts
USER 10001:10001
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--timeout-graceful-shutdown", "25", "--no-access-log", "--no-proxy-headers"]
