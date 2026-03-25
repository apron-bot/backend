FROM python:3.11-slim AS base

WORKDIR /app

# System deps for asyncpg + Chromium for browser-use (CDP-based, not Playwright)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    curl \
    # Chromium + all required dependencies for headless operation
    chromium \
    fonts-liberation \
    fonts-dejavu-core \
    fonts-freefont-ttf \
    libnss3 \
    libxss1 \
    libasound2 \
    libatk-bridge2.0-0 \
    libgtk-3-0 \
    libgbm1 \
    libdrm2 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    libcups2 \
    && rm -rf /var/lib/apt/lists/*

# CRITICAL: Tell browser-use it's running in Docker
# (auto-adjusts sandbox, paths, and container-specific behavior)
ENV IN_DOCKER=True
ENV CHROME_PATH=/usr/bin/chromium
ENV CHROMIUM_PATH=/usr/bin/chromium

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
ENV ENVIRONMENT=production
ENV PYTHONUNBUFFERED=1

# Create data dir for SQLite (mount a Railway Volume here)
RUN mkdir -p /app/data

EXPOSE ${PORT}

CMD uvicorn apron.main:app --host 0.0.0.0 --port ${PORT}
