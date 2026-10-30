#!/usr/bin/env bash
set -u
# restore 8091 (NInfer PROFILE=max) + 8081 gateway; safe to run any time 8091 is down
cd /c/Project/local_model
if curl -s -o /dev/null --max-time 3 http://127.0.0.1:8091/v1/models; then echo "8091 already up"; else
  ( nohup env PROFILE=max FORCE=1 GW=1 PORT=8091 MODELID=bonsai27b-ptq1-mtp-rk2v4-40k bash scripts/serve2.sh > logs/restore-8091.log 2>&1 & )
  for i in $(seq 1 40); do
    sleep 5
    C=$(curl -s -o /dev/null -w "%{http_code}" --max-time 3 http://127.0.0.1:8091/v1/models || true)
    G=$(curl -s -o /dev/null -w "%{http_code}" --max-time 3 http://127.0.0.1:8081/v1/models || true)
    if [ "$C" = "200" ] && [ "$G" = "200" ]; then echo "restored in $((i*5))s: 8091=200 8081=200"; break; fi
  done
fi
nvidia-smi --query-gpu=memory.used --format=csv,noheader