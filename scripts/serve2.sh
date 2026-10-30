#!/usr/bin/env bash
# serve2.sh v2 - 4060 Ti 8GB launcher, calibrated against measured arms.
# Every profile below was measured on this card on 2026-10-30 (see reports/).
#   PROFILE=ctx40  current best (2026-10-30 late): pool 40,000 / host-kv 6,144, draft4+win8,
#                  slots0, no cuda graph => peak 7,469 MiB, 97-98 counting / 45.7 prose tok/s,
#                  37K-token prompt: prefill 963 tok/s, zero "prompt exceeds the resident" warnings.
#                  Pool ceiling measured on this card: 52,000 starts but prefill collapses to ~180 tok/s,
#                  56,000 refuses to start (runtime reservation 1,092,297,216 B vs 1,037,041,664 B).
#   PROFILE=fast   N7 winner: pool 16000, rk2v4-e8, draft4+win8, slots0, no cuda graph
#                  => peak 7,141 MiB, 98.1 counting / 45.7 prose tok/s, ctx cap 16,000
#   PROFILE=ctx20  N8: same but pool 20,032 / host-kv 5,120 (peak 7,197, 97.6 tok/s)
#   PROFILE=long   author 8g-long: no MTP, cuda graph on, pool 51,200 (peak 7,353, 32 tok/s)
#   PROFILE=legacy our pre-2026-10-30 recipe (pool 32,000, draft4, window 0) for A/B only
# Knobs: CHUNK=512 saves ~74 MiB but costs ~5 tok/s | GW=1 starts gateway on 8081
#        FORCE=1 bypasses the VRAM gate | EXTRA="..." appends raw engine flags
set -u
ROOT=/c/Project/local_model
MODEL=${MODEL:-$ROOT/models/bonsai2_27b_ternary_ptq1_native_mtp.ninfer}
PORT=${PORT:-8091}
# [DSH] models[].id 会原样发成请求的 model 字段，引擎按 --model-id 逐字强校验：
# 对不上直接 404 model_not_found（经 8081 网关变 502）。这里的默认值必须与
# ~/.dsh/profiles/desktop/cordis.patch.yml 里 ninfer provider 的 models[].id 一致。
# 命名规范：模型族+尺寸+量化+关键配置，见 reports/DSH配置与验收.md
MODELID_SET=${MODELID:-}          # 用户显式给的 model id（空 = 按 profile 取默认）
MODELID=${MODELID:-bonsai27b-ptq1-mtp-rk2v4-40k}
PROFILE=${PROFILE:-fast}
GW=${GW:-0}
GWPORT=${GWPORT:-8081}
CHUNK=${CHUNK:-}   # per-profile default; set in the case below

case "$PROFILE" in
  max)  # 2026-10-30 极限档 (task-17): CUDA Graph ON + MTP + chunk 1536
    POOL=${POOL:-40000}; KV=${KV:-rk2v4-e8}; HOSTKV=${HOSTKV:-6144}; WINDOW=${WINDOW:-16384}
    SPEC="--spec mtp --draft-tokens 4 --mtp-attention-window 8"; MTPFLAG=--mtp
    CGFLAG="--cuda-graph-allowance-mib 16 --ngram-draft-tokens 0"; STATE="--device-state-slots 0"; EFFORT=none
    CHUNK=${CHUNK:-1536} ;;
  ctx40)
    CHUNK=${CHUNK:-1024}
    POOL=${POOL:-40000}; KV=${KV:-rk2v4-e8}; HOSTKV=${HOSTKV:-6144}; WINDOW=${WINDOW:-16384}
    SPEC="--spec mtp --draft-tokens 4 --mtp-attention-window 8"; MTPFLAG=--mtp
    CGFLAG=--no-cuda-graph; STATE="--device-state-slots 0"; EFFORT=none ;;
  fast)
    CHUNK=${CHUNK:-1024}
    POOL=${POOL:-16000}; KV=${KV:-rk2v4-e8}; HOSTKV=${HOSTKV:-4096}; WINDOW=${WINDOW:-16384}
    SPEC="--spec mtp --draft-tokens 4 --mtp-attention-window 8"; MTPFLAG=--mtp
    CGFLAG=--no-cuda-graph; STATE="--device-state-slots 0"; EFFORT=none ;;
  ctx20)
    CHUNK=${CHUNK:-1024}
    POOL=${POOL:-20032}; KV=${KV:-rk2v4-e8}; HOSTKV=${HOSTKV:-5120}; WINDOW=${WINDOW:-16384}
    SPEC="--spec mtp --draft-tokens 4 --mtp-attention-window 8"; MTPFLAG=--mtp
    CGFLAG=--no-cuda-graph; STATE="--device-state-slots 0"; EFFORT=none ;;
  long)
    CHUNK=${CHUNK:-1024}
    POOL=${POOL:-51200}; KV=${KV:-rk2v4-e8}; HOSTKV=${HOSTKV:-2816}; WINDOW=${WINDOW:-10240}
    SPEC=""; MTPFLAG=""; CGFLAG=""; STATE=""; EFFORT=none ;;
  long64)  # 长文档档 2026-10-30 实测：池 64,000 起服后 free 349 MiB；prompt <= 池 才可信（引擎 warning 口径）
    CHUNK=${CHUNK:-1024}
    POOL=${POOL:-64000}; KV=${KV:-rk2v4-e8}; HOSTKV=${HOSTKV:-8192}; WINDOW=${WINDOW:-16384}
    SPEC=""; MTPFLAG=""; CGFLAG="--no-cuda-graph"; STATE="--device-state-slots 0"; EFFORT=none
    MODELID=${MODELID_SET:-bonsai27b-ptq1-nomtp-rk2v4-64k} ;;
  long72)  # 同 long64 但池 72,000：起服后只剩 243 MiB（先关 OBS/游戏）；80,000 剩 137、88,000 剩 33、96,000 起不来
    CHUNK=${CHUNK:-1024}
    POOL=${POOL:-72000}; KV=${KV:-rk2v4-e8}; HOSTKV=${HOSTKV:-8192}; WINDOW=${WINDOW:-16384}
    SPEC=""; MTPFLAG=""; CGFLAG="--no-cuda-graph"; STATE="--device-state-slots 0"; EFFORT=none
    MODELID=${MODELID_SET:-bonsai27b-ptq1-nomtp-rk2v4-72k} ;;
  long80)  # 极限档：池 80,000，起服后剩 137 MiB（务必先关 OBS/QQNT/GameViewer），88,000 只剩 33 MiB
    CHUNK=${CHUNK:-1024}
    POOL=${POOL:-80000}; KV=${KV:-rk2v4-e8}; HOSTKV=${HOSTKV:-8192}; WINDOW=${WINDOW:-16384}
    SPEC=""; MTPFLAG=""; CGFLAG="--no-cuda-graph"; STATE="--device-state-slots 0"; EFFORT=none
    MODELID=${MODELID_SET:-bonsai27b-ptq1-nomtp-rk2v4-80k} ;;
  legacy)
    CHUNK=${CHUNK:-1024}
    POOL=${POOL:-32000}; KV=${KV:-rk2v4-e8}; HOSTKV=${HOSTKV:-8192}; WINDOW=${WINDOW:-16384}
    SPEC="--spec mtp --draft-tokens 4 --mtp-attention-window 8"; MTPFLAG=--mtp; CGFLAG=--no-cuda-graph; STATE="--device-state-slots 0"; EFFORT=none ;;
  *) echo "unknown PROFILE=$PROFILE (max|ctx40|fast|ctx20|long|legacy)" >&2; exit 64 ;;
esac

CARD=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits | head -1 | tr -d " \r")
python "$ROOT/scripts/plan.py" --card "$CARD" --dtype "$KV" --pool "$POOL" $MTPFLAG
GATE_RC=$?
echo "[serve2] profile=$PROFILE pool=$POOL kv=$KV hostkv=$HOSTKV window=$WINDOW chunk=$CHUNK card=${CARD}MiB gate_rc=$GATE_RC"
if [ "$GATE_RC" -ne 0 ] && [ "${FORCE:-0}" != "1" ]; then
  python "$ROOT/scripts/plan.py" --card "$CARD" --dtype "$KV" --fit $MTPFLAG >&2
  echo "[serve2] over redline -> refusing to start (FORCE=1 to override)" >&2
  exit 2
fi

# env must live in the shell that starts the engine
export NINFER_KV_WINDOW=$WINDOW
# 2026-10-30 实测：这支引擎在 prompt > 池 且 NINFER_KV_RETRIEVE **未设** 时会 AUTO-ENABLED：
#   [ring] retrieve AUTO-ENABLED: prompt 1204 pages > pool 1000 pages and NINFER_KV_RETRIEVE is unset
#        -> budget 500 pages (skeleton 4, restore-slack 4)
# 我们过去写死 8192 ⇒ 只有 128 页证据（比 auto 少 3.9 倍）。默认改成不设；要固定就 RETRIEVE=<tokens>。
if [ "${RETRIEVE:-auto}" = "auto" ]; then unset NINFER_KV_RETRIEVE; else export NINFER_KV_RETRIEVE=$RETRIEVE; fi
export NINFER_HOST_PAGEABLE=1
export NINFER_KV_REUSE_HOSTBACKED=1
export NINFER_TERNARY_PTQ1_FAST=1

if [ "$GW" = "1" ]; then
  # 一个网关只能有一个：旧网关的 --pool-tokens 是旧档的值，留着会把新档的长提示裁到旧池。
  for pid in $(netstat -ano 2>/dev/null | grep ":$GWPORT .*LISTENING" | awk '{print $5}' | sort -u); do
    [ -n "$pid" ] && taskkill //F //PID "$pid" >/dev/null 2>&1
  done
  sleep 2
  ( python "$ROOT/tools/chat_gateway.py" --port "$GWPORT" --engine "http://127.0.0.1:$PORT" \
      --pool-tokens "$POOL" --headroom-tokens 1024 > "$ROOT/logs/gateway-$GWPORT.log" 2>&1 & )
  echo "[serve2] gateway -> http://127.0.0.1:$GWPORT/v1 (pool=$POOL)"
fi

exec "$ROOT/engine/ninfer-serve-89.exe" "$MODEL" \
  --host 127.0.0.1 --port "$PORT" --model-id "$MODELID" \
  --max-context 262144 --kv-capacity "$POOL" --kv-dtype "$KV" --host-kv-mib "$HOSTKV" \
  --max-concurrency 1 --max-shared-prefixes 0 --derive-session-keys \
  --prefill-chunk "$CHUNK" $CGFLAG $STATE --gdn-state-fp16 $SPEC ${EXTRA:-} \
  --presence-penalty 0 --temperature 0.7 --top-p 0.9 --top-k 20 \
  --default-reasoning-effort "$EFFORT" --default-max-tokens 8192 \
  --log-stats-interval-ms 5000 --log-colours off
