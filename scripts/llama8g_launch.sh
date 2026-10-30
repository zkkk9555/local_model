#!/bin/bash
# 启动 llama.cpp 分叉版（bonsai bundle）8G 预设，走官方 launcher
set -u
B=/c/Project/local_model/llama8g/bundle
cd $B || exit 1
export BONSAI_8GB=1
export BONSAI_CTX=262144
export BONSAI_PORT=8089
export BONSAI_SPARSE=1
exec powershell -NoProfile -ExecutionPolicy Bypass -File ./start-server.ps1
