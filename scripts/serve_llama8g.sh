#!/usr/bin/env bash
# serve_llama8g.sh —— llama.cpp 分叉 professorpalmer/bonsai-ada-surgery 的 8G 起服骨架
#
# 目标：RTX 4060 Ti 8G（8188 MiB）上 -c 262144（或 204800）+ KV 前 N 个位置放显存
#       （--kv-vram-cells），其余 KV 全量放 pinned RAM 走 PCIe，KV 用 q3_0/q4_0 + MTP head。
#
# 现状（2026-10-30）：**bundle 还没落地，所有 flag 都还没跟 --help 核对过**，所以本脚本：
#   - 只保证 --probe 能打印「将要执行的命令行」，不真起服；
#   - 真起服必须 RUN=1 显式开启，避免误占 8G 卡把别人的实验打断；
#   - 所有可疑 flag 都放在变量 / TBD 标记处，bundle 落地后只改这一处。
#
# 用法：
#   bash scripts/serve_llama8g.sh --probe              # 只打印命令行
#   bash scripts/serve_llama8g.sh --probe -c 204800 --kv-cells 12345
#   MODEL=/path/to/model.gguf RUN=1 bash scripts/serve_llama8g.sh
#
# 环境变量（都有默认值）：MODEL CTX PORT HOST NGL KV_TYPE KV_VRAM_CELLS MTP_HEAD
#                        THREADS BATCH UBATCH BIN RUN

set -u

BIN="${BIN:-./llama-server.exe}"
MODEL="${MODEL:-}"
CTX="${CTX:-262144}"
PORT="${PORT:-8089}"
HOST="${HOST:-127.0.0.1}"
NGL="${NGL:-99}"
KV_TYPE="${KV_TYPE:-q3_0}"
KV_VRAM_CELLS="${KV_VRAM_CELLS:-}"
MTP_HEAD="${MTP_HEAD:-}"
THREADS="${THREADS:-8}"
BATCH="${BATCH:-2048}"
UBATCH="${UBATCH:-512}"
RUN="${RUN:-0}"

MODE="serve"

usage() {
  sed -n "2,20p" "$0"
}

while [ $# -gt 0 ]; do
  case "$1" in
    --probe) MODE="probe" ;;
    -c|--ctx) shift; CTX="$1" ;;
    --kv-cells) shift; KV_VRAM_CELLS="$1" ;;
    --kv-type) shift; KV_TYPE="$1" ;;
    --model) shift; MODEL="$1" ;;
    --port) shift; PORT="$1" ;;
    --bin) shift; BIN="$1" ;;
    -h|--help) usage; exit 0 ;;
    *) echo "未知参数：$1（用 --help 看用法）" >&2; exit 2 ;;
  esac
  shift
done

# ---------------------------------------------------------------- 命令行拼装
# TBD-1  --kv-vram-cells：分叉特有，名字可能是 --kv-vram-cells / --n-vram-cells / --kv-cells。
# TBD-2  -ctk/-ctv（或 --cache-type-k/-v）：q3_0 / q4_0 的合法值以 --help 为准（不同版本叫 q3_0/ q3_0）。
# TBD-3  --mtp-head：MTP 投机头文件路径，分叉可能叫 --draft-mtp / --mtp-model / -md。
# TBD-4  -fa：flash attention 开关形式在新版本是 -fa on|off|auto。
# 这四处不动逻辑，只改参数名，bundle 落地后按 --help 校对。
CMD=("$BIN"
  -m "$MODEL"
  -c "$CTX"
  --host "$HOST"
  --port "$PORT"
  -ngl "$NGL"
  -fa on
  -ctk "$KV_TYPE"
  -ctv "$KV_TYPE"
  -b "$BATCH"
  -ub "$UBATCH"
  -t "$THREADS"
  --mlock
  --cont-batching
)

# 可选：KV 显存放多少个位置（不填 = 引擎自己按空闲显存决定，前提是分叉实现了 auto）
if [ -n "$KV_VRAM_CELLS" ]; then
  CMD+=(--kv-vram-cells "$KV_VRAM_CELLS")
fi
if [ -n "$MTP_HEAD" ]; then
  CMD+=(--mtp-head "$MTP_HEAD")
fi

# ---------------------------------------------------------------- 预算提示
print_budget() {
  echo "[budget] 卡 8188 MiB；CTX=$CTX；KV_TYPE=$KV_TYPE；NGL=$NGL"
  if [ -n "$KV_VRAM_CELLS" ]; then
    echo "[budget] KV 显存位置 = $KV_VRAM_CELLS 个（其余走 pinned RAM，按 PCIe 带宽换算速度）"
  else
    echo "[budget] KV 显存位置 = 未指定（若分叉不实现 auto，需要手算：cells ≈ (空闲显存 MiB × 1048576) / 每位置字节数）"
    echo "[budget] 每位置字节数要先跑一次 --help / 日志里的 KV 台账才能定；本骨架不猜数字。"
  fi
  if [ -z "$MODEL" ]; then
    echo "[budget] 警告：MODEL 未设置（-m 空）—— 真起服前必须给 MODEL=/path/to.gguf"
  fi
}

# ---------------------------------------------------------------- 两种模式
if [ "$MODE" = "probe" ]; then
  echo "[probe] 只打印，不执行。TBD 的四处见脚本头注释。"
  print_budget
  echo "[probe] 命令行："
  for a in "${CMD[@]}"; do
    printf " %q" "$a"
  done
  echo
  echo "[probe] 落地核对清单："
  echo "  1) $BIN --help | grep -iE vram.cells|kv.cache|mtp|flash"
  echo "  2) 起一次最小 -c 4096 看日志里的 KV 台账（每位置字节数 / host 部分大小）"
  echo "  3) 再按 8G 预算填 --kv-cells，或确认 auto 生效"
  exit 0
fi

if [ "$RUN" != "1" ]; then
  echo "[serve] 骨架阶段不真起服：bundle 未落地、flag 未核对。" >&2
  echo "[serve] 先跑 --probe 看命令行；确认无误后 RUN=1 再执行。" >&2
  exit 3
fi

print_budget
echo "[serve] 执行："
for a in "${CMD[@]}"; do printf " %q" "$a"; done
echo
exec "${CMD[@]}"
