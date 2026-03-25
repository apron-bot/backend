FROM python:3.11-slim AS base

WORKDIR /app

# System deps for asyncpg + Chromium for browser-use
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    # Chromium dependencies for browser-use
    chromium \
    chromium-driver \
    fonts-liberation \
    libnss3 \
    libxss1 \
    libasound2 \
    libatk-bridge2.0-0 \
    libgtk-3-0 \
    libgbm1 \
    && rm -rf /var/lib/apt/lists/*

# Tell browser-use / playwright where Chromium is
ENV CHROME_PATH=/usr/bin/chromium
ENV CHROMIUM_PATH=/usr/bin/chromium
# Playwright needs this to find the system Chromium
ENV PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium
# Running as root in container — Chromium requires --no-sandbox
ENV CHROMIUM_FLAGS="--no-sandbox --disable-dev-shm-usage"

# Install Python deps
COPY pyproject.toml README.md ./
COPY src/ src/
RUN pip install --no-cache-dir .

# Install playwright browsers as fallback + browser-use setup
RUN python -m playwright install chromium 2>/dev/null || true
RUN python -m browser_use install || true

# Copy remaining source
COPY alembic/ alembic/

# Railway sets PORT; default to 8000
ENV PORT=8000
ENV STORAGE_BACKEND=sqlite
ENV SQLITE_PATH=/app/data/apron.db
ENV ENVIRONMENT=production

# Create data dir for SQLite (mount a Railway Volume here)
RUN mkdir -p /app/data

EXPOSE ${PORT}

CMD uvicorn apron.main:app --host 0.0.0.0 --port ${PORT}
