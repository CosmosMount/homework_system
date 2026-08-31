FROM python:3.12.13-alpine3.23@sha256:601d3d3797e90e2534782e69c85fafb7971b43f24c7b1b079b7e48dd435e458d AS builder

ENV PATH="/opt/venv/bin:$PATH"
RUN python -m venv /opt/venv
COPY requirements.lock /tmp/requirements.lock
RUN pip install --no-cache-dir --requirement /tmp/requirements.lock

FROM python:3.12.13-alpine3.23@sha256:601d3d3797e90e2534782e69c85fafb7971b43f24c7b1b079b7e48dd435e458d AS runtime

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN addgroup -g 10001 -S appgroup \
    && adduser -S -D -H -u 10001 -G appgroup appuser
WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY --chown=appuser:appgroup alembic.ini ./
COPY --chown=appuser:appgroup migrations ./migrations
COPY --chown=appuser:appgroup app ./app
RUN chmod -R a=rX alembic.ini migrations app

USER appuser
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health/live', timeout=3)"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4", "--no-access-log"]
