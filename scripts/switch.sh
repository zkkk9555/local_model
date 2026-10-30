#!/bin/bash
# 8 GB 卡上只能跑一个：NInfer(8091, 40K 池, 快) 或 llama.cpp(8089, 262K 窗, 慢但真长)。
# 用法：bash scripts/switch.sh {ninfer|llama|status}
# 两者显存需求 7,459 / 7,909 MiB > 8,188，必须互斥。
set -u
ROOT="C:/Project/local_model"
cd "$ROOT" || exit 1
mkdir -p logs tmp          # 仓库按 .gitignore 不带 logs/，起服第一句就往里重定向
wait_http() { # url max_sec
  local u="$1" n="$2" i=0
  while [ "$i" -lt "$n" ]; do
    if curl -s -m 3 -o /dev/null "$u" 2>/dev/null; then return 0; fi
    # llama 的 /v1/models 要 key，用 401 也算活着
    local c=$(curl -s -m 3 -o /dev/null -w "%{http_code}" "$u" 2>/dev/null)
    [ "$c" = "200" ] || [ "$c" = "401" ] && return 0
    i=$((i+3)); sleep 3
  done
  return 1
}
status() {
  echo "-- 进程 --"
  tasklist //FI "IMAGENAME eq ninfer-serve-89.exe" 2>/dev/null | grep -i ninfer || echo "ninfer: 无"
  tasklist //FI "IMAGENAME eq llama-server.exe" 2>/dev/null | grep -i llama || echo "llama: 无"
  echo "-- 端口 --"
  netstat -ano | grep -E ":(8091|8089|8081) .*LISTENING" || echo "无监听"
  echo "-- 显存 --"
  nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader
  echo "-- 探活 --"
  curl -s -m 3 -o /dev/null -w "8091=%{http_code} " http://127.0.0.1:8091/v1/models
  curl -s -m 3 -o /dev/null -w "8089=%{http_code}\n" -H "Authorization: Bearer $(cat llama8g/bundle/artifacts/api_key.txt 2>/dev/null)" http://127.0.0.1:8089/v1/models
}
case "${1:-status}" in
  ninfer)
    taskkill //F //IM llama-server.exe 2>/dev/null | head -2
    taskkill //F //IM ninfer-serve-89.exe 2>/dev/null | head -2   # 同卡只能一个实例，且 SO_REUSEADDR 会双绑
    sleep 8
    PROFILE=max FORCE=1 GW=1 PORT=8091 MODELID=bonsai27b-ptq1-mtp-rk2v4-40k nohup bash scripts/serve2.sh > logs/serve-switch-ninfer.log 2>&1 &
    disown
    wait_http http://127.0.0.1:8091/v1/models 240 && echo "ninfer up" || echo "ninfer NOT up (看 logs/serve-switch-ninfer.log)"
    status
    ;;
  long72|long64|long80)
    # 长文档：无 MTP，池按 profile（64K/72K/80K），id 由 serve2.sh 自动带 -64k/-72k/-80k 后缀
    taskkill //F //IM llama-server.exe 2>/dev/null | head -2
    taskkill //F //IM ninfer-serve-89.exe 2>/dev/null | head -2   # 同卡只能一个实例
    sleep 10
    PROFILE="$1" FORCE=1 GW=1 PORT=8091 nohup bash scripts/serve2.sh > "logs/serve-switch-$1.log" 2>&1 &
    disown
    wait_http http://127.0.0.1:8091/v1/models 300 && echo "ninfer ($1) up" || echo "ninfer ($1) NOT up (看 logs/serve-switch-$1.log)"
    status
    ;;
  llama)
    taskkill //F //IM ninfer-serve-89.exe 2>/dev/null | head -2
    sleep 8
    nohup bash scripts/llama8g_launch.sh > logs/llama8g-launch.log 2>&1 &
    disown
    for i in $(seq 1 90); do
      c=$(curl -s -m 3 -o /dev/null -w "%{http_code}" -H "Authorization: Bearer $(cat llama8g/bundle/artifacts/api_key.txt)" http://127.0.0.1:8089/v1/models)
      [ "$c" = "200" ] && { echo "llama up"; break; }
      sleep 3
    done
    status
    ;;
  status) status ;;
  *) echo "用法: bash scripts/switch.sh {ninfer|llama|status}"; exit 2 ;;
esac
