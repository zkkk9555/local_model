#!/usr/bin/env bash
set -u
export HTTPS_PROXY=http://127.0.0.1:7897 HTTP_PROXY=http://127.0.0.1:7897
T=/c/Project/local_model/tmp/clonecheck
rm -rf "$T"
echo "=== 浅克隆（--depth 1）实测"
time git clone --depth 1 -q https://github.com/zkkk9555/local_model "$T" || { echo "clone 失败"; exit 1; }
cd "$T" || exit 1
echo "--- 文件数 / 体积"
git ls-files | wc -l
du -sh .
echo "--- engine-dlls 内容"
ls -la engine-dlls
echo "--- 校验哈希"
cd engine-dlls && sha256sum -c SHA256SUMS.txt
echo "--- restore_check 能否识别（不带 --deep，只看存在与字节）"
cd "$T" && python tools/restore_check.py 2>&1 | tail -25