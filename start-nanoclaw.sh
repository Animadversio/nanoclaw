#!/bin/bash
# start-nanoclaw.sh — Start NanoClaw without systemd
# To stop: kill \$(cat /n/home12/binxuwang/nanoclaw/nanoclaw.pid)

set -euo pipefail

cd "/n/home12/binxuwang/nanoclaw"

# Stop existing instance if running
if [ -f "/n/home12/binxuwang/nanoclaw/nanoclaw.pid" ]; then
  OLD_PID=$(cat "/n/home12/binxuwang/nanoclaw/nanoclaw.pid" 2>/dev/null || echo "")
  if [ -n "$OLD_PID" ] && kill -0 "$OLD_PID" 2>/dev/null; then
    echo "Stopping existing NanoClaw (PID $OLD_PID)..."
    kill "$OLD_PID" 2>/dev/null || true
    sleep 2
  fi
fi

# GCC 12 libraries needed for better-sqlite3 native module
export LD_LIBRARY_PATH="/n/sw/helmod-rocky8/apps/Core/gcc/12.2.0-fasrc01/lib64:/n/sw/helmod-rocky8/apps/Core/gcc/12.2.0-fasrc01/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"

echo "Starting NanoClaw..."
nohup "/n/home12/binxuwang/.nvm/versions/node/v22.17.1/bin/node" "/n/home12/binxuwang/nanoclaw/dist/index.js" \
  >> "/n/home12/binxuwang/nanoclaw/logs/nanoclaw.log" \
  2>> "/n/home12/binxuwang/nanoclaw/logs/nanoclaw.error.log" &

echo $! > "/n/home12/binxuwang/nanoclaw/nanoclaw.pid"
echo "NanoClaw started (PID $!)"
echo "Logs: tail -f /n/home12/binxuwang/nanoclaw/logs/nanoclaw.log"
