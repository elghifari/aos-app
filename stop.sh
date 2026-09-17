#!/usr/bin/env bash
cd "$(dirname "$0")" || exit 1
PIDFILE=.aos.pid
if [ -f "$PIDFILE" ]; then
  kill "$(cat $PIDFILE)" 2>/dev/null && echo "stopped $(cat $PIDFILE)"
  rm -f "$PIDFILE"
else
  echo "no pidfile; nothing tracked"
fi
