#!/usr/bin/env bash
# scan-pool.sh - 逐个试 --kv-capacity，记录能否起服 + 起服后 free 显存
set -u
cd /c/Project/local_model
for P in "$@"; do
  powershell -NoProfile -ExecutionPolicy Bypass -File scripts/kill-engines.ps1 > /dev/null 2>&1
  sleep 2
  errtag="pool$P"
  powershell -NoProfile -ExecutionPolicy Bypass -File scripts/exp-start.ps1 -Port 8092 -Pool "$P" -Hostkv 8192 -Dtype rk2v4-e8 -MaxCtx 262144 -Window 16384 -Chunk 1024 -Tag "$errtag" -Retrieve "" > /dev/null 2>&1
  ok=no
  for i in $(seq 1 30); do
    if grep -q "listening on" "logs/exp-$errtag.err" 2>/dev/null; then ok=yes; break; fi
    if grep -qE "refuses|out of memory|CUDA error|failed|Error" "logs/exp-$errtag.err" 2>/dev/null; then break; fi
    sleep 3
  done
  if [ "$ok" = yes ]; then
    line=$(grep "capacity |" "logs/exp-$errtag.err" | tail -1)
    echo "POOL=$P START_OK | $line"
  else
    reason=$(grep -iE "refuses|reservation|out of memory|CUDA error|failed" "logs/exp-$errtag.err" | tail -2 | tr "\n" " ")
    echo "POOL=$P START_FAIL | $reason"
  fi
  powershell -NoProfile -ExecutionPolicy Bypass -File scripts/kill-engines.ps1 > /dev/null 2>&1
  sleep 2
done
nvidia-smi --query-gpu=memory.used --format=csv,noheader