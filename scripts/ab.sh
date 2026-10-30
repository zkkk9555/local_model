#!/usr/bin/env bash
# One A/B arm: boot engine with given config, run the standard bench, tear down.
set -u
ROOT=/c/Users/Administrator/Documents/deepseek-harness/default-workspace
cd "$ROOT" || exit 1
TAG=$1; shift
export WINDOW=$1 CTX=$2 POOL=$3 KV=$4 HOSTKV=$5 SPEC=$6 EXTRA=$7
taskkill //F //IM ninfer-serve-89.exe >/dev/null 2>&1
sleep 2
LOG=logs/ab_$TAG.log
nohup bash scripts/serve.sh > "$LOG" 2>&1 &
for i in $(seq 1 40); do
  if grep -q "listening on" "$LOG"; then break; fi
  if grep -qiE "fatal error|out of memory|CUDA error" "$LOG"; then echo "== $TAG BOOT FAILED"; tail -3 "$LOG"; exit 1; fi
  sleep 5
done
echo "== $TAG : $(grep -oE 'capacity \| KV [0-9,]+ tokens[^|]*\| .*free [0-9.]+ MiB' "$LOG" | tail -1)"
echo "   $(grep -oE '\[spec\] backend=.*' "$LOG" | tail -1)"
PYTHONIOENCODING=utf-8 python scripts/speed_ab.py 2>&1 | tail -4
sleep 1
