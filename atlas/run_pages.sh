#!/bin/bash
# Unattended run of the breakthrough page passes, for days if need be.
#
#   atlas/run_pages.sh MODEL EFFORT LOGFILE [extra args for both passes, e.g. --workers 3]
#
# Loops: `atlas.page define --missing`, then `atlas.page results --missing`. When a pass exits
# with 75 (a provider reported exhaustion) it sleeps 30 minutes and tries again. It stops when
# both passes report "Nothing to do". A loop never starts sooner than a minute after the last.
# Every line is written, timestamped, to LOGFILE. The whole run is wrapped in `caffeinate -i`.
# Each pass commits atlas/core as it goes; stopping this script (kill its process) is safe.

set -u
if [ $# -lt 3 ]; then
  echo "usage: $0 MODEL EFFORT LOGFILE [extra args]" >&2
  exit 2
fi
MODEL=$1
EFFORT=$2
LOG=$3
shift 3
case "$LOG" in /*) ;; *) LOG="$PWD/$LOG" ;; esac

if [ -z "${ATLAS_CAFFEINATED:-}" ]; then
  ATLAS_CAFFEINATED=1 exec caffeinate -i "$0" "$MODEL" "$EFFORT" "$LOG" "$@"
fi

cd "$(dirname "$0")/.." || exit 1
PYTHON=${PYTHON:-python3}
OUTPUT=$(mktemp -t atlas-pages)
EXHAUSTED=75

log() {
  echo "$(date '+%Y-%m-%dT%H:%M:%S%z') $*" >> "$LOG"
}

# run_pass define|results [extra args]: runs one pass; its exit code is in PASS_CODE.
run_pass() {
  pass=$1
  shift
  log "start $pass --missing --model $MODEL --effort $EFFORT $*"
  "$PYTHON" -m atlas.page "$pass" --missing --model "$MODEL" --effort "$EFFORT" "$@" 2>&1 \
    | while IFS= read -r line; do
        echo "$line" >> "$OUTPUT"
        log "$pass: $line"
      done
  PASS_CODE=${PIPESTATUS[0]}
  log "end $pass (exit $PASS_CODE)"
}

log "runner started: model $MODEL, effort $EFFORT, extra args: $*"
while true; do
  started=$(date +%s)
  idle=0
  exhausted=0
  for pass in define results; do
    : > "$OUTPUT"
    run_pass "$pass" "$@"
    if [ "$PASS_CODE" -eq "$EXHAUSTED" ]; then
      exhausted=1
      break
    fi
    if grep -q '^Nothing to do' "$OUTPUT"; then
      idle=$((idle + 1))
    fi
  done
  if [ "$exhausted" -eq 1 ]; then
    log "a provider reported exhaustion; sleeping 30 minutes"
    sleep 1800
    continue
  fi
  if [ "$idle" -eq 2 ]; then
    log "nothing left to do; runner stopped"
    break
  fi
  elapsed=$(($(date +%s) - started))
  if [ "$elapsed" -lt 60 ]; then
    sleep $((60 - elapsed))
  fi
done
rm -f "$OUTPUT"
