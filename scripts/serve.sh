#!/usr/bin/env bash
# Launch the NInfer KVMem engine for the 8 GB tier.
#   PROFILE=fast  (default) MTP draft-4 + explicit 32k pool  -> ~98 tok/s on predictable text, ~44 on prose
#   PROFILE=long           no speculation + explicit 64k pool -> ~31 tok/s, dependable context 64k
set -u
ROOT=/c/Project/local_model
MODEL=${MODEL:-$ROOT/models/bonsai2_27b_ternary_ptq1_native_mtp.ninfer}
PORT=${PORT:-8091}
PROFILE=${PROFILE:-fast}
CTX=${CTX:-262144}
KV=${KV:-rk2v4-e8}
RETRIEVE=${RETRIEVE:-8192}

if [ "$PROFILE" = "long" ]; then
  WINDOW=${WINDOW:-16384}
  POOL=${POOL:-64000}
  HOSTKV=${HOSTKV:-3072}
  SPEC=${SPEC:-}
else
  WINDOW=${WINDOW:-16384}
  POOL=${POOL:-32000}
  HOSTKV=${HOSTKV:-8192}
  SPEC=${SPEC:---spec mtp --draft-tokens 4}
fi
HEADROOM=${HEADROOM:-512}

export NINFER_KV_WINDOW=$WINDOW
export NINFER_KV_RETRIEVE=$RETRIEVE
export NINFER_HOST_PAGEABLE=1
export NINFER_KV_REUSE_HOSTBACKED=1
export NINFER_TERNARY_PTQ1_FAST=1

HR=""
if [ "$POOL" = "auto" ]; then HR="--kv-headroom-mib $HEADROOM"; fi

echo "profile=$PROFILE model=$MODEL ctx=$CTX pool=$POOL kv=$KV hostkv=$HOSTKV window=$WINDOW retrieve=$RETRIEVE spec=[$SPEC]"
exec "$ROOT/engine/ninfer-serve-89.exe" "$MODEL" \
  --host 127.0.0.1 --port "$PORT" \
  --max-context "$CTX" --max-concurrency 1 --max-shared-prefixes 0 \
  --derive-session-keys --prefill-chunk 1024 \
  --kv-capacity "$POOL" $HR --kv-dtype "$KV" --host-kv-mib "$HOSTKV" \
  ${CGFLAG:---no-cuda-graph} --gdn-state-fp16 ${SPEC:-} ${EXTRA:-} \
  --default-reasoning-effort none --default-max-tokens 8192 \
  --log-stats-interval-ms 5000 --log-colours off
