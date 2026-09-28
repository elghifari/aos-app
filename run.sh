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

if ! command -v uv >/dev/null 2>&1; then
  echo "uv not found. Install it from https://docs.astral.sh/uv/ and rerun." >&2
  exit 1
fi

# uv creates .venv from uv.lock on first run, so PATH order never picks the interpreter.
AOS_ENV=development nohup uv run python -m uvicorn web:app \
  --host 127.0.0.1 --port "$PORT" > "$LOG" 2>&1 &
disown 2>/dev/null

# $! is uv, not the server, so resolve the real listener once the port is up.
for attempt in {1..60}; do
  if [ "$(curl --max-time 2 -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:$PORT/?as=u_marketing" 2>/dev/null)" = "200" ]; then
    uv run python -c "import psutil; print(next(p.pid for p in psutil.process_iter() if any(c.laddr.port==$PORT for c in p.net_connections(kind='inet') if c.status=='LISTEN')))" > "$PIDFILE" 2>/dev/null
    echo "up -> http://127.0.0.1:$PORT/?as=u_marketing (pid $(cat "$PIDFILE"))"
    exit 0
  fi
  sleep 1
done

echo "failed to start, see $LOG" >&2
exit 1
