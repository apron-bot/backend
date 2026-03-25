#!/bin/bash
set -e

# Pre-start Chromium with CDP debugging port so browser-use can connect instantly
CHROME_PORT=9222
CHROME_DATA_DIR=$(mktemp -d /tmp/chrome-profile-XXXXXX)

echo "Starting Chromium on CDP port $CHROME_PORT..."
chromium \
  --headless=new \
  --no-sandbox \
  --disable-gpu \
  --disable-gpu-sandbox \
  --disable-setuid-sandbox \
  --disable-dev-shm-usage \
  --no-zygote \
  --disable-extensions \
  --remote-debugging-port=$CHROME_PORT \
  --remote-debugging-address=0.0.0.0 \
  --user-data-dir="$CHROME_DATA_DIR" \
  --disable-background-networking \
  --disable-default-apps \
  --disable-sync \
  --no-first-run \
  &

# Wait for Chromium to be ready
echo "Waiting for Chromium CDP..."
for i in $(seq 1 30); do
  if curl -sf http://127.0.0.1:$CHROME_PORT/json/version > /dev/null 2>&1; then
    echo "Chromium ready on port $CHROME_PORT"
    break
  fi
  sleep 1
done

# Export the CDP URL for browser-use
export CHROME_CDP_URL="http://127.0.0.1:$CHROME_PORT"

# Start the app
exec uvicorn apron.main:app --host 0.0.0.0 --port ${PORT:-8000}
