#!/bin/bash
set -u
cd /c/Project/local_model || exit 1
KEY=$(cat llama8g/bundle/artifacts/api_key.txt)
taskkill //F //IM ninfer-serve-89.exe 2>/dev/null | head -1
taskkill //F //IM llama-server.exe 2>/dev/null | head -1
sleep 10
nvidia-smi --query-gpu=memory.used --format=csv,noheader
echo "== 起 llama CTX=155648（cells 自动，launcher 算显存线）$(date +%H:%M:%S)"
CTX=155648 nohup bash scripts/llama-tier-test.sh > logs/llama-150k.log 2>&1 &
for i in $(seq 1 90); do
  c=$(curl -s -m 3 -o /dev/null -w "%{http_code}" -H "Authorization: Bearer $KEY" http://127.0.0.1:8089/v1/models 2>/dev/null)
  [ "$c" = "200" ] && { echo "llama up after $((i*10))s"; break; }
  sleep 10
done
grep -aE "window |kv tiered|host-tail|spec  |n_ctx_slot" logs/llama-150k.log | head -6
echo "== 150K 单发探针 $(date +%H:%M:%S)"
python -u tools/llama_probe.py --api-key "$KEY" --doc tmp/exp/doc-150k8.txt \
  --needles "白色鲸鱼-3141,灰色鹦鹉-5926,橙色章鱼-8412,青色刺猬-2673,褐色獾子-7058,粉色火烈鸟-1936,墨绿壁虎-4482,杏色绵羊-6207" \
  --max-tokens 512 --timeout 14400 --tag llama150k --out tmp/exp/llama-tier.jsonl 2>&1 | tail -3
echo "== 收尾 停 llama 起 long72 $(date +%H:%M:%S)"
taskkill //F //IM llama-server.exe 2>/dev/null | head -1
sleep 10
bash scripts/switch.sh long72 >/dev/null 2>&1
sleep 25
curl -s -m 8 http://127.0.0.1:8091/v1/models | head -c 100; echo
echo "== done $(date +%H:%M:%S)"