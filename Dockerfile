FROM python:3.11-slim AS base

WORKDIR /app

# System deps for asyncpg and browser-use
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps
COPY pyproject.toml README.md ./
COPY src/ src/
RUN pip install --no-cache-dir .

# Copy remaining source
COPY alembic/ alembic/

# Railway sets PORT; default to 8000
ENV PORT=8000
ENV STORAGE_BACKEND=sqlite
ENV SQLITE_PATH=/app/data/apron.db

# Create data dir for SQLite
RUN mkdir -p /app/data

EXPOSE ${PORT}

CMD uvicorn apron.main:app --host 0.0.0.0 --port ${PORT}
