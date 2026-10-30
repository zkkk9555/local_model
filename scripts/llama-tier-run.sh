#!/bin/bash
set -u
cd /c/Project/local_model || exit 1
KEY=$(cat llama8g/bundle/artifacts/api_key.txt)
echo "== 停 NInfer $(date +%H:%M:%S)"
taskkill //F //IM ninfer-serve-89.exe 2>/dev/null | head -1
sleep 8
nvidia-smi --query-gpu=memory.used --format=csv,noheader
echo "== 起 llama（cells 钉 16384 / ctx 36864）$(date +%H:%M:%S)"
CELLS=16384 CTX=36864 nohup bash scripts/llama-tier-test.sh > logs/llama-tier.log 2>&1 &
for i in $(seq 1 60); do
  c=$(curl -s -m 3 -o /dev/null -w "%{http_code}" -H "Authorization: Bearer $KEY" http://127.0.0.1:8089/v1/models 2>/dev/null)
  [ "$c" = "200" ] && { echo "llama up after ${i}0s"; break; }
  sleep 10
done
grep -aE "tiered KV|VRAM cells|host-tail|window|n_ctx" logs/llama-tier.log | head -8
echo "== 探针：30K 文档单发 $(date +%H:%M:%S)"
python -u tools/llama_probe.py --api-key "$KEY" --doc tmp/exp/llama-30k8.txt \
  --needles "银色海豚-4402,青铜狐狸-1180,白色猫头鹰-9067,黑色蝙蝠-2551,紫色孔雀-6388,金色水母-8223,红色麋鹿-5019,蓝色海豹-7314" \
  --max-tokens 512 --tag tier16k-30k --out tmp/exp/llama-tier.jsonl 2>&1 | tail -3
echo "== 收尾 停 llama 起 long72 $(date +%H:%M:%S)"
taskkill //F //IM llama-server.exe 2>/dev/null | head -1
sleep 8
bash scripts/switch.sh long72 >/dev/null 2>&1
curl -s -m 5 http://127.0.0.1:8091/v1/models | head -c 120; echo
echo "== done $(date +%H:%M:%S)"