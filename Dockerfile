FROM python:3.12-slim AS base

# Keep the image lean and predictable: no .pyc cache, unbuffered stdout so
# logs show up immediately in `docker logs`, no pip cache left behind.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src ./src

# Data and logs are volume-mounted in docker-compose.yml so they survive
# container recreation - see DB_PATH / LOG_PATH in .env.
RUN mkdir -p /app/data /app/logs

# Runs as non-root; the mounted volumes below must be writable by this uid.
RUN useradd --create-home --uid 1000 botuser && chown -R botuser:botuser /app
USER botuser

CMD ["python", "-m", "src.main"]
