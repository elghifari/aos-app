#!/usr/bin/env bash
cd "$(dirname "$0")" || exit 1
PORT=8077
PIDFILE=.aos.pid

# Kill by recorded pid, then sweep whatever is still listening on the port.
# The pidfile can go stale, so the port sweep is the real guarantee.
if [ -f "$PIDFILE" ]; then
  kill "$(cat "$PIDFILE")" 2>/dev/null && echo "stopped $(cat "$PIDFILE")"
  rm -f "$PIDFILE"
fi
uv run python -c "
import psutil
for p in psutil.process_iter():
    try:
        if any(c.laddr.port==$PORT for c in p.net_connections(kind='inet') if c.status=='LISTEN'):
            p.terminate(); print('swept listener', p.pid)
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass
" 2>/dev/null
