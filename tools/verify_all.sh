#!/usr/bin/env bash
# tools/verify_all.sh - DSH 本地 provider 一键验收（只发 HTTP，不启停任何引擎，可重复跑）
#
# 用法：
#   bash tools/verify_all.sh                        # 全部检查
#   CONFIG=/path/cordis.patch.yml bash tools/verify_all.sh
#   SKIP_STRATA=1 bash tools/verify_all.sh          # 不看 Strata
#   OVERPOOL=45000 bash tools/verify_all.sh         # 顺带测超长提示是 4xx 还是静默 200（慢，约 70 s）
#
# 依次做：1 显卡显存 -> 2 8091 引擎 /v1/models -> 3 8081 网关 /v1/models
#         -> 4 DSH 视角：cordis.patch.yml 声明的 id vs 引擎真实 id（点名谁缺席、要起哪一档）
#         -> 5 dsh_provider_test.py --config 六项逐模型 PASS/FAIL
#         -> 6 若 Strata 在跑，再对它跑一遍
# 判据：全 PASS 才算通过。两类东西不算 FAIL：
#   * 缺席：DSH 里写了但引擎当前没跑的那一档（8 GB 卡同时只能跑一档，如 -52k 只在 long 档存在）
#   * Strata 没起来（跳过）
#   但某 provider 声明的 id 一个都命中不了 -> 那是真 FAIL（起错档 / 引擎没起）。
# 输出：同时打印并 tee 到 logs/verify-<时间戳>.log；退出码 0=通过 1=有 FAIL。
set -u
ROOT=/c/Project/local_model
CONFIG=${CONFIG:-/c/Users/Administrator/.dsh/profiles/desktop/cordis.patch.yml}
PY=${PY:-python}
SKIP_STRATA=${SKIP_STRATA:-0}
OVERPOOL=${OVERPOOL:-0}
ENGINE=${ENGINE:-8091}   # 引擎端口（换档实验时可指到别的端口）
GW=${GW:-8081}           # 网关端口
TS=$(date +%Y%m%d-%H%M%S)
mkdir -p "$ROOT/logs"
LOG="$ROOT/logs/verify-$TS.log"
: > "$LOG"

fails=0
say() { printf '%s\n' "$*" | tee -a "$LOG" ; }
fail() { fails=$((fails + 1)) ; say "!! FAIL: $*" ; }

say "================= DSH 本地 provider 验收 $TS ================="
say "配置 : $CONFIG"
say "脚本 : tools/dsh_provider_test.py"
say "日志 : $LOG"

# ---------------- 1 显卡 ----------------
say ""
say "--- 1/6 显卡 ---"
GPU=$(nvidia-smi --query-gpu=name,driver_version,memory.used,memory.total,utilization.gpu --format=csv,noheader 2>&1)
if [ $? -ne 0 ] ; then
  fail "nvidia-smi 执行失败：$GPU"
else
  printf '%s\n' "$GPU" | sed 's/^/    /' | tee -a "$LOG" >/dev/null
  say "    $GPU"
fi

# ---------------- 2/3 模型列表 ----------------
probe_models() {   # $1 标签  $2 baseURL  $3 文件 slug（后面第 4 步还要读它）
  local name=$1 base=$2 slug=$3 code tmp
  tmp="$ROOT/logs/.verify-models-$slug.json"
  code=$(curl -s -m 10 -o "$tmp" -w '%{http_code}' "$base/models" 2>/dev/null)
  [ -z "$code" ] && code=000
  say ""
  say "--- $name  GET $base/models -> HTTP $code"
  if [ "$code" != "200" ] ; then
    fail "$name /v1/models 不可用（HTTP $code）；原始响应体："
    if [ -s "$tmp" ] ; then head -c 1200 "$tmp" | sed 's/^/    | /' | tee -a "$LOG" >/dev/null ; head -c 1200 "$tmp" | sed 's/^/    | /' ; fi
    return 1
  fi
  $PY - "$tmp" 2>&1 <<'PYEOF' | tee -a "$LOG"
import json, sys
d = json.load(open(sys.argv[1], encoding="utf-8"))
items = d.get("data") if isinstance(d, dict) else d
for it in items or []:
    print("    id=%-40s ctx=%-8s owner=%s" % (it.get("id"), it.get("context_window") or it.get("max_model_len"), it.get("owned_by")))
PYEOF
  return 0
}

probe_models "2/6 ${ENGINE} 引擎直连" "http://127.0.0.1:${ENGINE}/v1" engine || true
probe_models "3/6 ${GW} 网关"     "http://127.0.0.1:${GW}/v1" gw || true

# ---------------- 4 DSH 视角：配置里的 id vs 引擎真实 id ----------------
# 这一步只读、只比对：拿 DSH 配置里声明的 models[].id，去对上面第 2/3 步抓到的
# /v1/models 列表。写清楚「谁命中、谁缺席、缺席那档要起哪个 PROFILE」，
# 免除「选择器里有 2 个 ninfer 条目但其实只有 1 个能用」的误会。不参与 PASS/FAIL。
say ""
say "--- 4/6 DSH 视角：cordis.patch.yml 声明的 id vs 引擎真实 id ---"
$PY - "$CONFIG" "$ENGINE" "$ROOT/logs/.verify-models-engine.json" "$GW" "$ROOT/logs/.verify-models-gw.json" 2>&1 <<'PYEOF' | tee -a "$LOG"
import json, sys
try:
    import yaml
except Exception:
    print("    (没装 pyyaml，这一步跳过：python -m pip install pyyaml)")
    sys.exit(0)

cfg = sys.argv[1]
pairs = [(sys.argv[2], sys.argv[3]), (sys.argv[4], sys.argv[5])]   # (端口, /v1/models 落盘文件)
served = {}
for port, path in pairs:
    try:
        d = json.load(open(path, encoding="utf-8"))
        items = d.get("data") if isinstance(d, dict) else d
        served[port] = [it.get("id") for it in (items or [])]
    except Exception:
        served[port] = []

HINTS = (("-52k", "PROFILE=long（池 51,200 / 无投机）"), ("-40k", "PROFILE=max 或 ctx40（池 40,000）"))
rows = []
try:
    d = yaml.safe_load(open(cfg, encoding="utf-8")) or []
except Exception as e:
    print("    读配置失败：%r" % (e,))
    sys.exit(0)
for e in d:
    if e.get("id") != "llm-pi-ai":
        continue
    for key, prov in ((e.get("config") or {}).get("providers") or {}).items():
        base = (prov.get("baseURL") or "").rstrip("/")
        port = None
        for pd, _path in pairs:
            if "127.0.0.1:" + pd in base:
                port = pd
                break
        if port is None:
            continue
        for m in prov.get("models") or []:
            mid = m.get("id")
            hit = mid in served[port]
            why = ""
            if not hit:
                why = "预期不存在：该档当前没在跑"
                for suf, h in HINTS:
                    if suf in mid:
                        why = "预期不存在：要它得按 " + h + " 起服"
                        break
            rows.append((key, port, mid, str(m.get("contextWindow")), "命中" if hit else "缺席", why))
print("    %-8s %-5s %-36s %-9s %-5s %s" % ("provider", "端口", "DSH 声明的 id", "ctx", "判定", "说明"))
for r in rows:
    print("    %-8s %-5s %-36s %-9s %-5s %s" % r)
hit_n = sum(1 for r in rows if r[4] == "命中")
seen = []
for p, _ in pairs:
    if p not in seen:
        seen.append(p)
print("    引擎真实 id：%s" % "  ".join("%s=%s" % (p, served[p] or "-") for p in seen))
print("    -> 命中 %d / 声明 %d；缺席的条目不是故障（一张卡同时只跑一档），第 5/6 步也只标「缺席」不算 FAIL" % (hit_n, len(rows)))
if rows and hit_n == 0:
    print("    !! 一个都没命中：引擎起的档与配置里的 id 不一致，或引擎没起（回看第 2/6 步）")
PYEOF
# ---------------- 5 六项行为验收 ----------------
# 先探 Strata 在线状态：它现在是启用态的 provider，若离线必须从 step4 里排除，
# 否则「Strata 没装」会把「NInfer 能不能用」的结论带成 FAIL。
STRATA_BASE=$($PY - "$CONFIG" 2>/dev/null <<'PYEOF'
import sys
try:
    import yaml
except Exception:
    sys.exit(0)
d = yaml.safe_load(open(sys.argv[1], encoding="utf-8"))
for e in d or []:
    if e.get("id") == "llm-pi-ai":
        p = ((e.get("config") or {}).get("providers") or {}).get("strata")
        if p and p.get("baseURL"):
            print(p["baseURL"].rstrip("/"))
PYEOF
)
STRATA_CODE=skip
if [ -n "$STRATA_BASE" ] ; then
  STRATA_CODE=$(curl -s -m 5 -o /dev/null -w '%{http_code}' "$STRATA_BASE/models" 2>/dev/null)
  [ -z "$STRATA_CODE" ] && STRATA_CODE=000
fi

say ""
say "--- 5/6 dsh_provider_test --config（127.0.0.1 上的 provider，逐模型 PASS/FAIL）---"
EXTRA=""
if [ "$OVERPOOL" != "0" ] ; then EXTRA="--overpool-tokens $OVERPOOL" ; say "    （附带超长提示检查：$OVERPOOL tok，会慢）" ; fi
# Strata 固定从这一步排除：它的 model id 现在还是文档占位，不能让它把「NInfer 能不能用」带红。
# 它单独在第 6/6 步测（那边用 --weak-absent，id 对不上只报 WARN 并给出改法）。
# 排除都不在线的路线：--exclude-provider 是「逗号分隔」的单值参数，不能传两次（后一个会覆盖前一个）。
EXCLUDE="strata"
# llama.cpp（8089）与 NInfer（8091）互斥：同一张 8 GB 卡只能跑一个。
# 端口没监听就把 llama 也排除，否则「另一档在跑」会把验收判成 FAIL。
LLAMA_CODE=$(curl -s -m 3 -o /dev/null -w '%{http_code}' -H "Authorization: Bearer $(cat "$ROOT/llama8g/bundle/artifacts/api_key.txt" 2>/dev/null)" http://127.0.0.1:8089/v1/models 2>/dev/null)
[ -z "$LLAMA_CODE" ] && LLAMA_CODE=000
if [ "$LLAMA_CODE" != "200" ] ; then
  EXCLUDE="$EXCLUDE,llama"
  say "    （llama 8089 未在跑 -> 排除；切过去用 bash scripts/switch.sh llama）"
fi
# 超池分片代理（8086）：只在手动 start 时存在，没起就排除（它的模型是 long72 档专属）。
LONG_CODE=$(curl -s -m 3 -o /dev/null -w '%{http_code}' http://127.0.0.1:8086/v1/models 2>/dev/null)
[ -z "$LONG_CODE" ] && LONG_CODE=000
if [ "$LONG_CODE" != "200" ] ; then
  EXCLUDE="$EXCLUDE,ninfer-long"
  say "    （分片代理 8086 未在跑 -> 排除；要用就 bash scripts/longctx.sh start）"
fi
EXTRA="$EXTRA --exclude-provider $EXCLUDE"
if [ "$STRATA_CODE" != "200" ] && [ "$SKIP_STRATA" != "1" ] ; then
  say "    （Strata 不在线 -> 第 6/6 步会报「跳过」）"
else
  say "    （Strata 是否在线都不影响这一步：它固定排除，放到第 6/6 步）"
fi
# shellcheck disable=SC2086
$PY "$ROOT/tools/dsh_provider_test.py" --config "$CONFIG" $EXTRA --json "$ROOT/logs/verify-$TS.json" 2>&1 | tee -a "$LOG"
rc=${PIPESTATUS[0]}
if [ "$rc" -eq 0 ] ; then
  say "    -> provider_test 全 PASS"
else
  fail "provider_test 有 FAIL（退出码 $rc，原始响应体见上面；完整 json: logs/verify-$TS.json）"
fi

# ---------------- 6 Strata ----------------
say ""
say "--- 6/6 Strata（在跑才测）---"
if [ "$SKIP_STRATA" = "1" ] ; then
  say "    跳过（SKIP_STRATA=1）"
elif [ -z "$STRATA_BASE" ] ; then
  say "    配置里没有启用的 strata provider，跳过"
elif [ "$STRATA_CODE" != "200" ] ; then
  say "    Strata 未在跑（$STRATA_BASE/models -> HTTP $STRATA_CODE），跳过（不算 FAIL）"
else
  say "    Strata 在线（$STRATA_BASE），跑六项："
  # shellcheck disable=SC2086
  $PY "$ROOT/tools/dsh_provider_test.py" --config "$CONFIG" --provider strata --weak-absent $EXTRA 2>&1 | tee -a "$LOG"
  rc2=${PIPESTATUS[0]}
  [ "$rc2" -eq 0 ] || fail "Strata provider_test 有 FAIL（退出码 $rc2）"
fi

# ---------------- 总结 ----------------
say ""
say "================= 结果 ================="
if [ "$fails" -eq 0 ] ; then
  say "验收通过：0 FAIL"
  exit 0
else
  say "验收未通过：$fails 项 FAIL"
  exit 1
fi