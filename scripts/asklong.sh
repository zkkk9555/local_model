#!/usr/bin/env bash
# asklong.sh - 一条命令问长文档。自动在「池内直问」/「池内分片」/「重启后一次性超池」之间选路。
#
#   bash asklong.sh <doc.txt|md> "<问题>"              # 自动选路（推荐）
#   bash asklong.sh <doc> "<问题>" --shard            # 强制分片（可信、可重复）
#   bash asklong.sh <doc> "<问题>" --oneshot          # 重启引擎 + 整篇一次问（快、但每次要重启）
#
# 背景（2026-10-30 本机实测）：池 40,000 token。题面 <= 池 => 干净且可重复；
# 题面 > 池 => 只有**刚启动后的第一个**超池请求可信，同进程后续超池请求静默错（HTTP 200 + 编造）。
set -u
ROOT=/c/Project/local_model
PORT=${PORT:-8091}
# [DSH] models[].id 会原样发成请求的 model 字段，引擎按 --model-id 逐字强校验：
# 对不上直接 404 model_not_found（经 8081 网关变 502）。这里的默认值必须与
# ~/.dsh/profiles/desktop/cordis.patch.yml 里 ninfer provider 的 models[].id 一致。
# 命名规范：模型族+尺寸+量化+关键配置，见 reports/DSH配置与验收.md
MODELID=${MODELID:-bonsai27b-ptq1-mtp-rk2v4-40k}
ENGINE=${ENGINE:-http://127.0.0.1:$PORT/v1}
PY=${PY:-python}
POOL=${POOL:-40000}

DOC=${1:?用法: asklong.sh <doc> "<问题>" [--shard|--oneshot]}
shift
Q=${1:?用法: asklong.sh <doc> "<问题>" [--shard|--oneshot]}
shift
MODE=auto
SHARD=26000
while [ $# -gt 0 ]; do
  case "$1" in
    --shard) MODE=shard ;;
    --oneshot) MODE=oneshot ;;
    --shard-tokens) SHARD=$2; shift ;;
    --pool) POOL=$2; shift ;;
    *) echo "[asklong] 未知参数 $1"; exit 2 ;;
  esac
  shift
done

BYTES=$(wc -c < "$DOC")
EST=$($PY -c "print(int($BYTES/4.246)+1)")
echo "[asklong] 文档 $DOC  $BYTES 字节 / 预估 $EST token / 池 $POOL"

if [ "$MODE" = auto ]; then
  if [ "$EST" -le 36000 ]; then MODE=direct; else MODE=shard; fi
fi
echo "[asklong] 选路: $MODE"

ready() {
  i=0
  while [ $i -lt 90 ]; do
    i=$((i+1))
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 3 "http://127.0.0.1:$PORT/v1/models" 2>/dev/null)
    if [ "$code" = "200" ]; then echo "[asklong] 引擎就绪"; return 0; fi
    sleep 2
  done
  echo "[asklong] 引擎 180s 内未就绪"; return 1
}

ask_once() {
  $PY - "$DOC" "$Q" "$ENGINE" "$MODELID" <<'PYEOF'
import json, sys, time, urllib.request
doc, q, engine, model = sys.argv[1:5]
text = open(doc, encoding="utf-8", errors="replace").read()
body = {"model": model,
        "messages": [{"role": "user", "content": "【文档】\n" + text + "\n\n【问题】" + q}],
        "max_tokens": 1024, "temperature": 0.0, "stream": False}
req = urllib.request.Request(engine.rstrip("/") + "/chat/completions",
    data=json.dumps(body).encode(),
    headers={"Content-Type": "application/json", "Authorization": "Bearer local-any-key"})
t0 = time.time()
d = json.load(urllib.request.urlopen(req, timeout=3600))
u = d.get("usage") or {}
print("\n===== 答案 =====\n" + (d["choices"][0]["message"].get("content") or "").strip())
print("\n[asklong] prompt=%s  %.1fs" % (u.get("prompt_tokens"), time.time() - t0))
PYEOF
}

case "$MODE" in
  direct)
    ask_once
    ;;
  shard)
    $PY "$ROOT/tools/longdoc.py" --doc "$DOC" --question "$Q" --engine "$ENGINE" \
        --model "$MODELID" --shard-tokens "$SHARD" --out "$ROOT/tmp/asklong-$(date +%H%M%S).md"
    echo "[asklong] 分片模式全程池内，可无限重复"
    ;;
  oneshot)
    echo "[asklong] 重启引擎（一次性超池模式：每次最多一份长文档）"
    taskkill //F //IM ninfer-serve-89.exe >/dev/null 2>&1
    sleep 3
    ( cd "$ROOT" && PROFILE=ctx40 FORCE=1 GW=0 PORT="$PORT" MODELID="$MODELID" \
        POOL=40000 HOSTKV=6144 nohup bash scripts/serve2.sh > logs/engine-oneshot.log 2>&1 & )
    ready || exit 1
    ask_once
    echo "[asklong] 这一次可信；再问一份长文档必须先重启引擎（--oneshot 会自动做）"
    ;;
esac
