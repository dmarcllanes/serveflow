FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.9 /uv /bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DATA_DIR=/app/data

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY *.py ./
COPY seeds ./seeds

RUN useradd --uid 1000 --create-home app && mkdir -p /app/data && chown -R app /app/data
USER app

EXPOSE 5001
HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:5001/healthz', timeout=2).status == 200 else 1)"

# one worker keeps RAM ~60-80 MB; run uvicorn directly (no uv wrapper process)
CMD [".venv/bin/uvicorn", "main:app", "--host", "0.0.0.0", "--port", "5001", "--workers", "1", \
     "--proxy-headers", "--forwarded-allow-ips", "*", "--no-server-header"]
