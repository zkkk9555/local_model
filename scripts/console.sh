#!/bin/bash
# 本地模型控制台（网页）：bash scripts/console.sh start|stop|status|open
set -u
ROOT="C:/Project/local_model"
cd "$ROOT" || exit 1
PORT=${CONSOLE_PORT:-8090}
pid_on_port() { netstat -ano | grep "127.0.0.1:${PORT} " | grep LISTENING | head -1 | awk '{print $5}'; }
case "${1:-start}" in
  start)
    P=$(pid_on_port)
    if [ -n "${P:-}" ]; then echo "[console] 已在运行 pid=$P -> http://127.0.0.1:${PORT}"; exit 0; fi
    CONSOLE_PORT="$PORT" nohup python -u tools/console.py >> "logs/console-${PORT}.log" 2>&1 &
    sleep 3
    if [ -n "$(pid_on_port)" ]; then
      echo "[console] 启动完成 -> http://127.0.0.1:${PORT}  (log=logs/console-${PORT}.log)"
    else
      echo "[console] 启动失败，看 logs/console-${PORT}.log"; tail -5 "logs/console-${PORT}.log"; exit 1
    fi ;;
  stop)
    P=$(pid_on_port)
    if [ -n "${P:-}" ]; then taskkill //F //PID "$P" >/dev/null 2>&1 && echo "[console] 已停 pid=$P"; else echo "[console] 未在运行"; fi ;;
  status)
    P=$(pid_on_port)
    if [ -n "${P:-}" ]; then echo "[console] 运行中 pid=$P -> http://127.0.0.1:${PORT}"; else echo "[console] 未运行"; fi ;;
  open)
    bash scripts/console.sh start >/dev/null 2>&1; cmd.exe /c start "" "http://127.0.0.1:${PORT}" ;;
  *) echo "用法: bash scripts/console.sh {start|stop|status|open}"; exit 2 ;;
esac