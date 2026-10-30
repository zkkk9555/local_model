#!/usr/bin/env bash
set -u
export HTTP_PROXY=http://127.0.0.1:7897
export HTTPS_PROXY=http://127.0.0.1:7897
cd /c/Users/Administrator/Documents/deepseek-harness/default-workspace/models
TARGET=9520051456
F=Ternary-Bonsai-2-27B-ninfer-v3.ninfer
URL="https://huggingface.co/WaveCut/Ternary-Bonsai-2-27B-NInfer-v3/resolve/main/Ternary-Bonsai-2-27B-ninfer-v3.ninfer"
UA='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
for i in $(seq 1 40); do
  SZ=$(stat -c %s "$F" 2>/dev/null || echo 0)
  if [ "$SZ" -ge "$TARGET" ]; then echo "DONE size=$SZ"; break; fi
  echo "--- attempt $i at $SZ / $TARGET ---"
  curl -L --fail -C - --retry 3 --retry-all-errors --retry-delay 3 -m 3000 -A "$UA" -o "$F" "$URL" 2>/dev/null
  echo "curl rc=$?"
  sleep 2
done
SZ=$(stat -c %s "$F" 2>/dev/null || echo 0)
echo "final size=$SZ target=$TARGET"
if [ "$SZ" -ge "$TARGET" ]; then sha256sum "$F"; fi
