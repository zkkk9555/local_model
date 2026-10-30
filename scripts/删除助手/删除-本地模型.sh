#!/usr/bin/env bash
# 本地模型项目「一键卸载」助手 —— 恢复到没装过本地模型之前的状态。
# 用法： bash 删除-本地模型.sh            # 只演算（dry-run，不动任何文件）
#        bash 删除-本地模型.sh apply      # 真删（先备份配置，再按顺序删）
#        ALL=1 bash 删除-本地模型.sh apply # 连 4 件「存疑项」一起删，见 §5/§6
# 依据：C:/Project/删除清单-本地模型-20261031.md（v3）+ 三份交叉审计（A/B/C）
set -u
MODE="${1:-dry}"
ALL="${ALL:-0}"
ROOT=/c/Project/local_model
HERE="$(cd "$(dirname "$0")" && pwd)"
HOME_W=/c/Users/Administrator
DOWN=$HOME_W/Downloads
WS=$HOME_W/Documents/deepseek-harness/default-workspace
LAP="${LOCALAPPDATA:-$HOME_W/AppData/Local}"
TMPD="${TMP:-$LAP/Temp}"
TOTAL=0
say() { printf "\n== %s\n" "$1"; }

# $1=路径 … 统计或删除
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

# 按端口找 PID 并杀（不要按进程名杀 python —— bili-duty 的两个 python 要留）
kill_port() {
  port="$1"
  pid=$(netstat -ano | grep "127.0.0.1:${port} .*LISTENING" | awk "{print \$5}" | head -1)
  if [ -z "${pid:-}" ]; then echo "  [skip] ${port} 没在听"; return; fi
  nm=$(powershell -NoProfile -Command "(Get-Process -Id ${pid} -ErrorAction SilentlyContinue).ProcessName" 2>/dev/null | tr -d "\r")
  if [ "$MODE" = "apply" ]; then
    taskkill //F //PID "$pid" >/dev/null 2>&1 && echo "  [kill] ${port} pid=${pid} (${nm})"
  else echo "  [will] kill ${port} pid=${pid} (${nm})"; fi
}

# 按命令行精确匹配杀（只认 cwd 落在项目里的 DSH 宿主；排除自己与父进程）
kill_cmd() {
  needle="$1"; label="$2"
  pids=$(powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { \$_.CommandLine -and \$_.CommandLine.Contains(\"${needle}\") } | Select-Object -ExpandProperty ProcessId" 2>/dev/null | tr -d "\r")
  [ -z "${pids:-}" ] && { echo "  [skip] 没有 ${label}"; return; }
  for pid in $pids; do
    [ "$pid" = "$$" ] && continue
    [ "$pid" = "$PPID" ] && continue
    if [ "$MODE" = "apply" ]; then taskkill //F //PID "$pid" >/dev/null 2>&1 && echo "  [kill] ${label} pid=${pid}";
    else echo "  [will] kill ${label} pid=${pid}"; fi
  done
}

say "0. 前置检查"
echo "  模式：$MODE（$( [ "$MODE" = "apply" ] && echo 真删 || echo dry-run )）  ALL=$ALL  项目根：$ROOT"
echo "  ⚠ 不会动：C:/Project 其它目录、~/.dsh（会话历史）、~/.dsh/bili-duty、.bak-before-local、本删除助手/存档/"

say "1. 停进程（先端口，再父进程/宿主；引擎按镜像名兜底）"
for port in 8091 8081 8086 8090; do kill_port "$port"; done
if [ "$MODE" = "apply" ]; then taskkill //F //IM ninfer-serve-89.exe >/dev/null 2>&1 && echo "  [kill] 兜底 ninfer-serve-89.exe"; fi
kill_cmd "cd /c/Project/local_model" "DSH 宿主（cwd 在项目里）"
# nohup 父进程：只在它拉起的就是 8086/8090 时才杀
kill_cmd "nohup.py longctx_proxy" "nohup 父进程（8086）"
kill_cmd "nohup.py console" "nohup 父进程（8090）"
echo "  提示：控制台页面若还开在 Chrome 里，请手动关掉那个标签（不杀整个浏览器）"
if [ "$MODE" = "apply" ]; then sleep 3; echo "  等待 3 s，让引擎/代理把日志句柄与 device-profiles.json 收干净"; fi

say "2. DSH 配置：删 3 个 provider + 默认模型回退 wb/deepseek-v4.1-flash + 删 2 个凭据键"
if [ "$MODE" = "apply" ]; then (cd "$HERE" && python dsh_uninstall.py --apply); else (cd "$HERE" && python dsh_uninstall.py); fi

say "3. 快捷方式（桌面控制台 + 开始菜单 Strata 死链）"
del "$HOME_W/Desktop/本地模型控制台.lnk"
del "$HOME_W/AppData/Roaming/Microsoft/Windows/Start Menu/Programs/Strata.lnk"

say "4. 注册表（Strata 残留 4 个键）"
reg_keys=(
  "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\Strata"
  "HKCU\\Software\\strata"
  "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\FileExts\\.ninfer"
  "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\Start\\TileProperties\\W~ai.strata.desktop"
)
for k in "${reg_keys[@]}"; do
  if reg query "$k" >/dev/null 2>&1; then
    if [ "$MODE" = "apply" ]; then reg delete "$k" //f >/dev/null 2>&1 && echo "  [del ] $k" || echo "  [fail] $k";
    else echo "  [will] $k"; fi
  else echo "  [skip] 不存在  $k"; fi
done

say "5. AppData / 用户目录残留"
del "$LAP/ninfer"                    # device-profiles.json：引擎退出时会重写，必须在进程全退后删
del "$LAP/ai.strata.desktop"
del "$HOME_W/.strata"

say "6. TEMP 残留"
for d in "$TMPD"/llama-longctx-selftest-*; do del "$d"; done
del "$TMPD/mockllama.log"
for d in "$TMPD"/strata-vision-*; do del "$d"; done
del "$TMPD/strata.html" "$TMPD/strata.md" "$TMPD/strata_install.md" "$TMPD/strata_keys.txt" "$TMPD/strata_models.md" "$TMPD/strata_readme.md"
if [ "$ALL" = "1" ]; then del "$TMPD/ex2" "$TMPD/ktx"; else echo "  [keep] ex2 / ktx（各 20 / 58 MB，存疑；ALL=1 才删）"; fi

say "7. Downloads 里本项目的下载件"
del "$DOWN/③超低显存档（llama+KVMem）.zip"
del "$DOWN/infer-27b-kv-stream-3arch-20261019-r3.zip"
del "$DOWN/engine-pack-sm89"
del "$DOWN/04-卡死与循环的防治.md"
del "$DOWN/方案-工具调用与死循环-20261013"
if [ "$ALL" = "1" ]; then del "$DOWN/Strata-本地硬件适配指南-20261013"; else echo "  [keep] Strata-本地硬件适配指南-20261013（56 KB，内容早于本项目；ALL=1 才删）"; fi

say "8. 项目主目录（du 39.06 GiB / 27,201 文件 / 内含 6.39 GB 硬链接，整树删才回收）"
del "$ROOT"

say "9. 工作区刮下来的垃圾（约 1.5 GB；保留 reports/）"
for d in "$WS/tmp" "$WS/work" "$WS/recon" "$WS/repos" "$WS/_recon" "$WS/scratch" "$WS/src" "$WS/bili_subs" "$WS/.tmp-st"; do del "$d"; done

say "10. 收尾校验"
if [ "$MODE" = "apply" ]; then
  echo "  -- 端口："
  for p in 8091 8081 8086 8090; do netstat -ano | grep -q "127.0.0.1:$p .*LISTENING" && echo "     !! $p 还在听" || echo "     ok  $p 已关闭"; done
  echo "  -- 项目目录：" ; [ -e "$ROOT" ] && echo "     !! 还在" || echo "     ok 已删除"
  echo "  -- DSH providers："
  python - <<"PY" 2>/dev/null || echo "     (yaml 校验跳过)"
import yaml
p = r"C:/Users/Administrator/.dsh/profiles/desktop/cordis.patch.yml"
d = yaml.safe_load(open(p, encoding="utf-8"))
for e in d:
    if e.get("id") == "llm-pi-ai":
        print("     providers =", list(e["config"]["providers"]))
PY
  echo "  -- C 盘可用：" ; df -h /c | tail -1
else
  echo "  （dry-run 不做校验）"
fi

printf "\n合计：%.2f GiB%s\n" "$(awk -v t=$TOTAL "BEGIN{print t/1024/1024/1024}")" "$( [ "$MODE" = "apply" ] && echo "（已删除）" || echo "（将被回收）")"
if [ "$MODE" = "apply" ]; then
  echo "完成。请重启 DSH 应用与宿主；默认模型回到 wb / deepseek-v4.1-flash。"
  echo "后悔药：https://github.com/zkkk9555/local_model （HEAD e378c8e）→ RESTORE.md"
else
  echo "以上为演算结果，一条都没删。确认后：bash 删除-本地模型.sh apply"
fi