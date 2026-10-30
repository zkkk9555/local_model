#!/bin/bash
# llama.cpp 分叉：故意把 VRAM 内 KV cell 钉小，逼 30K 文档走 host-tail 注意力，验真值。
set -u
B=/c/Project/local_model/llama8g/bundle
cd "$B" || exit 1
export BONSAI_8GB=1
export BONSAI_CTX=${CTX:-36864}
export BONSAI_PORT=${PORT:-8089}
export BONSAI_SPARSE=1
export BONSAI_SPEC=${SPEC:-0}
if [ -n "${CELLS:-}" ]; then export BONSAI_KV_VRAM_CELLS="$CELLS"; else unset BONSAI_KV_VRAM_CELLS; fi
exec powershell -NoProfile -ExecutionPolicy Bypass -File ./start-server.ps1