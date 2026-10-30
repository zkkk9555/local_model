#!/bin/bash
# 超池长上下文代理（8086）：DSH 里想用 150K–200K 就指向它；池内请求原样直通。
set -u
cd /c/Project/local_model || exit 1
PORT=${PORT:-8086}
POOL=${POOL:-72000}
ACT=${1:-status}
pid_on_port() { netstat -ano 2>/dev/null | grep -E "127\.0\.0\.1:${PORT}[[:space:]].*LISTENING" | awk "{print \$5}" | head -1; }
case "$ACT" in
  start)
    P=$(pid_on_port)
    if [ -n "${P:-}" ]; then echo "[longctx] 已在运行 pid=$P"; exit 0; fi
    nohup python -u tools/longctx_proxy.py --port "$PORT" --engine http://127.0.0.1:8091 \
      --pool-tokens "$POOL" \
      --advertise "bonsai27b-ptq1-nomtp-rk2v4-shard150k,bonsai27b-ptq1-nomtp-rk2v4-shard200k" \
      >> logs/longctx-"$PORT".log 2>&1 &
    sleep 3
    curl -s -m 4 "http://127.0.0.1:${PORT}/v1/models" && echo && echo "[longctx] 启动完成 log=logs/longctx-${PORT}.log" ;;
  stop)
    P=$(pid_on_port)
    if [ -n "${P:-}" ]; then taskkill //F //PID "$P" >/dev/null 2>&1 && echo "[longctx] 已停 pid=$P"; else echo "[longctx] 未在运行"; fi ;;
  status)
    P=$(pid_on_port)
    if [ -n "${P:-}" ]; then echo "[longctx] 运行中 pid=$P"; curl -s -m 4 "http://127.0.0.1:${PORT}/v1/models"; echo; else echo "[longctx] 未运行"; fi ;;
  *) echo "用法：bash scripts/longctx.sh start|stop|status"; exit 2 ;;
esac