#!/usr/bin/env bash
# Start AOS detached, so it survives the agent session that launched it.
# Hermes kills background processes it owns; nohup + disown breaks that link.
cd "$(dirname "$0")" || exit 1

PORT=8077
PIDFILE=.aos.pid
LOG=aos.log

if [ -f "$PIDFILE" ] && kill -0 "$(cat $PIDFILE)" 2>/dev/null; then
  echo "already running (pid $(cat $PIDFILE)) -> http://127.0.0.1:$PORT/"
  exit 0
fi

AOS_ENV=development nohup python -m uvicorn web:app \
  --host 127.0.0.1 --port "$PORT" > "$LOG" 2>&1 &
echo $! > "$PIDFILE"
disown 2>/dev/null

sleep 4
if [ "$(curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:$PORT/?as=u_marketing")" = "200" ]; then
  echo "up (pid $(cat $PIDFILE)) -> http://127.0.0.1:$PORT/?as=u_marketing"
else
  echo "failed to start — see $LOG"
  tail -5 "$LOG"
fi
