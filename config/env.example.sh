#!/usr/bin/env bash
# 本地模型链的环境变量模板。复制成 config/env.local.sh 后按需修改（env.local.sh 不入库）。

# --- NInfer 引擎（必须与启动它的 shell 同一个） ---
export NINFER_KV_WINDOW=16384          # KVMem 环的门（不设 = 环关，超池必错）
export NINFER_HOST_PAGEABLE=1          # 允许 KV 页落主机内存
export NINFER_KV_REUSE_HOSTBACKED=1    # 跨轮复用 host 页（前缀缓存不塌）
export NINFER_TERNARY_PTQ1_FAST=1      # 三元 PTQ1 快路径
# export NINFER_KV_RETRIEVE=8192       # 别设！留空让引擎 AUTO 给「池的一半」当证据预算

# --- DSH 里的本地 key（本地引擎不校验，值随便填；真实值放 ~/.dsh/.credentials.yaml） ---
export LOCAL_LLM_KEY=local
export LLAMA_API_KEY=local

# --- 端口约定 ---
export ENGINE_PORT=8091                # ninfer-serve-89.exe
export GATEWAY_PORT=8081               # tools/chat_gateway.py（护栏）
export LONGCTX_PORT=8086               # tools/longctx_proxy.py（超池分片）
export LLAMA_PORT=8089                 # llama-server.exe
export CONSOLE_PORT=8090               # tools/console.py

# --- 代理（只有拉 GitHub/HF 时需要） ---
# export HTTP_PROXY=http://127.0.0.1:7897
# export HTTPS_PROXY=http://127.0.0.1:7897