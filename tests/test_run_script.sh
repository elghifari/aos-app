#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORK="$(mktemp -d "$HOME/AppData/Local/hermes/cache/scratch/aos-run.XXXXXX")"
trap 'cd "$ROOT"; rm -rf "$WORK" 2>/dev/null || true' EXIT
cp "$ROOT/run.sh" "$WORK/run.sh"
printf '999999\n' > "$WORK/.aos.pid"
cd "$WORK"
printf '#!/usr/bin/env bash\n: > launched\n' > uv
chmod +x uv
export PATH="$WORK:$PATH"
curl() { printf 200; }
sleep() { :; }
export -f curl sleep
output="$(bash run.sh)"
if [[ "$output" != *"already running"* ]] || [[ -e launched ]]; then
  printf 'FAIL: running app with stale PID launched a duplicate: %s\n' "$output" >&2
  exit 1
fi
printf 'PASS: healthy listener avoids duplicate start\n'

rm -f .aos.pid launched
printf '0\n' > calls
curl() {
  n="$(<calls)"
  n=$((n + 1))
  printf '%s\n' "$n" > calls
  if (( n < 3 )); then printf 000; else printf 200; fi
}
export -f curl
output="$(bash run.sh)"
for attempt in {1..20}; do
  [[ -e launched ]] && break
  command sleep .05
done
if [[ "$output" != *"up ->"* ]] || [[ ! -e launched ]]; then
  printf 'FAIL: delayed app startup reported failure: %s; log: %s\n' "$output" "$(<aos.log)" >&2
  exit 1
fi
printf 'PASS: delayed listener is given time to become ready\n'
