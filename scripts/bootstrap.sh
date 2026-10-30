#!/usr/bin/env bash
# 克隆完先跑这个：把仓库里的东西摆到引擎能用的位置。
#   bash scripts/bootstrap.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
mkdir -p logs tmp engine
if [ -d engine-dlls ]; then
  n=0
  for f in engine-dlls/*.dll; do [ -e "$f" ] || continue; cp -p "$f" engine/ && n=$((n+1)); done
  echo "[ok] 已从 engine-dlls/ 复制 $n 个 DLL 到 engine/"
else
  echo "[warn] 没有 engine-dlls/，按 RESTORE.md §3.3 自己下 6 个 DLL"
fi
echo "[next] 把引擎 ninfer-serve-89.exe 放进 engine/，模型放进 models/，然后："
echo "       python tools/restore_check.py --deep     # 期望 18/18 OK"
echo "       bash scripts/switch.sh ninfer"