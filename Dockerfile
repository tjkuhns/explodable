FROM python:3.12-slim

WORKDIR /app

# System dependencies for psycopg[binary]
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY pyproject.toml ./
RUN pip install --no-cache-dir .

# Copy application code
COPY src/ ./src/
COPY scripts/ ./scripts/

# Config is mounted as a volume — not baked into the image
# COPY config/ ./config/

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app
