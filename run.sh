#!/usr/bin/env bash
# Start AOS detached, so it survives the agent session that launched it.
# Hermes kills background processes it owns; nohup + disown breaks that link.
cd "$(dirname "$0")" || exit 1

PORT=8077
PIDFILE=.aos.pid
LOG=aos.log

if [ "$(curl --max-time 2 -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:$PORT/?as=u_marketing" 2>/dev/null)" = "200" ]; then
  echo "already running -> http://127.0.0.1:$PORT/?as=u_marketing"
  exit 0
fi

AOS_ENV=development nohup python -m uvicorn web:app \
  --host 127.0.0.1 --port "$PORT" > "$LOG" 2>&1 &
echo $! > "$PIDFILE"
disown 2>/dev/null

for attempt in {1..30}; do
  if [ "$(curl --max-time 2 -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:$PORT/?as=u_marketing" 2>/dev/null)" = "200" ]; then
    echo "up -> http://127.0.0.1:$PORT/?as=u_marketing"
    exit 0
  fi
  sleep 1
done

echo "failed to start — see $LOG" >&2
exit 1
