#!/usr/bin/env bash
# 本地模型项目「一键卸载」助手 —— 恢复到没装过高位模型之前的状态。
# 用法： bash 删除-本地模型.sh          # 只演算（dry-run，不动任何文件）
#        bash 删除-本地模型.sh apply    # 真删（先做配置备份，再删）
set -u
MODE="${1:-dry}"
ROOT=/c/Project/local_model
HERE="$(cd "$(dirname "$0")" && pwd)"
DOWN=/c/Users/Administrator/Downloads
WS=/c/Users/Administrator/Documents/deepseek-harness/default-workspace
LAP="${LOCALAPPDATA:-/c/Users/Administrator/AppData/Local}"
TOTAL=0

say() { printf "\n== %s\n" "$1"; }

# $1=路径 … 删除或统计
del() {
  for p in "$@"; do
    if [ ! -e "$p" ]; then printf "  [skip] 不存在  %s\n" "$p"; continue; fi
    sz=$(du -sb "$p" 2>/dev/null | awk "{print \$1}")
    [ -z "${sz:-}" ] && sz=0
    TOTAL=$((TOTAL + sz))
    if [ "$MODE" = "apply" ]; then
      rm -rf "$p" && printf "  [del ] %-10s %s\n" "$(numfmt --to=iec $sz 2>/dev/null || echo ${sz}B)" "$p"
    else
      printf "  [will] %-10s %s\n" "$(numfmt --to=iec $sz 2>/dev/null || echo ${sz}B)" "$p"
    fi
  done
}

say "0. 前置检查"
echo "  模式：$MODE   项目根：$ROOT"
if [ "$MODE" != "apply" ]; then echo "  （dry-run：只统计，不删除。确认无误后加参数 apply 执行）"; fi

say "1. 停掉 4 个进程（引擎 8091 / 网关 8081 / 分片代理 8086 / 控制台 8090）"
# 只按「监听端口」找 PID，避免误杀自身或别的 python
for port in 8091 8081 8086 8090; do
  pid=$(netstat -ano | grep "127.0.0.1:${port} .*LISTENING" | awk "{print \$5}" | head -1)
  if [ -z "${pid:-}" ]; then echo "  [skip] ${port} 没在听"; continue; fi
  nm=$(powershell -NoProfile -Command "(Get-Process -Id ${pid} -ErrorAction SilentlyContinue).ProcessName" 2>/dev/null | tr -d "\r")
  if [ "$MODE" = "apply" ]; then taskkill //F //PID "$pid" >/dev/null 2>&1 && echo "  [kill] ${port} pid=${pid} (${nm})";
  else echo "  [will] kill ${port} pid=${pid} (${nm})"; fi
done
# 引擎兜底：按镜像名再清一次（它只会跑在 8091）
if [ "$MODE" = "apply" ]; then taskkill //F //IM ninfer-serve-89.exe >/dev/null 2>&1 && echo "  [kill] 兜底 ninfer-serve-89.exe"; fi

say "2. DSH 配置：删 3 个 provider + 默认模型回退到 wb/deepseek-v4.1-flash + 删 2 个凭据键"
if [ "$MODE" = "apply" ]; then (cd "$HERE" && python dsh_uninstall.py --apply); else (cd "$HERE" && python dsh_uninstall.py); fi

say "3. 桌面快捷方式"
del "/c/Users/Administrator/Desktop/本地模型控制台.lnk"

say "4. AppData 残留"
del "$LAP/ninfer"
del "$LAP/ai.strata.desktop"

say "5. 临时目录残留"
for d in /c/Users/Administrator/AppData/Local/Temp/llama-longctx-selftest-*; do del "$d"; done
del /c/Users/Administrator/AppData/Local/Temp/mockllama.log

say "6. Downloads 里本项目的 6 个下载件（11.0 GB）"
del "$DOWN/③超低显存档（llama+KVMem）.zip"
del "$DOWN/infer-27b-kv-stream-3arch-20261019-r3.zip"
del "$DOWN/engine-pack-sm89"
del "$DOWN/04-卡死与循环的防治.md"
del "$DOWN/Strata-本地硬件适配指南-20261013"
del "$DOWN/方案-工具调用与死循环-20261013"

say "7. 项目主目录（39.06 GiB / 27,199 文件）"
del "$ROOT"

say "8. 工作区刮下来的垃圾（约 1.5 GB；保留 reports/ 里的小报告）"
for d in "$WS/tmp" "$WS/work" "$WS/recon" "$WS/repos" "$WS/_recon" "$WS/scratch" "$WS/src" "$WS/bili_subs" "$WS/.tmp-st"; do del "$d"; done

say "9. 收尾校验"
if [ "$MODE" = "apply" ]; then
  echo "  -- 端口是否还在听："
  for p in 8091 8081 8086 8090; do netstat -ano | grep -q "127.0.0.1:$p .*LISTENING" && echo "     !! $p 还在听" || echo "     ok  $p 已关闭"; done
  echo "  -- 项目目录：" ; [ -e "$ROOT" ] && echo "     !! 还在" || echo "     ok 已删除"
  echo "  -- C 盘可用：" ; df -h /c | tail -1
else
  echo "  （dry-run 不做校验）"
fi

printf "\n合计：%.2f GiB\n" "$(awk -v t=$TOTAL "BEGIN{print t/1024/1024/1024}")"
[ "$MODE" = "apply" ] && echo "完成。请重启 DSH 应用与宿主，默认模型会回到 wb / deepseek-v4.1-flash。" || echo "以上为演算结果。"