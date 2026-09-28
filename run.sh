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
disown 2>/dev/null

# Do not trust $! for the pidfile. On Windows git-bash the `python` launcher
# re-execs the real runtime python as a child, so $! points at an intermediate
# that exits immediately. Resolve the real listener once the port is up.
for attempt in {1..30}; do
  if [ "$(curl --max-time 2 -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:$PORT/?as=u_marketing" 2>/dev/null)" = "200" ]; then
    python -c "import psutil,sys; print(next(p.pid for p in psutil.process_iter() if any(c.laddr.port==$PORT for c in p.net_connections(kind='inet') if c.status=='LISTEN')))" > "$PIDFILE" 2>/dev/null
    echo "up -> http://127.0.0.1:$PORT/?as=u_marketing (pid $(cat "$PIDFILE"))"
    exit 0
  fi
  sleep 1
done

echo "failed to start — see $LOG" >&2
exit 1
