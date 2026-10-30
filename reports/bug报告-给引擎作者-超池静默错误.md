# 超池长上下文静默错误 + evidence 预算写死 —— 可复现报告

> 机型 RTX 4060 Ti 8GB / Ryzen 7 7800X3D / 31.1 GB RAM / Windows 11 26100。
> 引擎 `ninfer-serve-89.exe`（801,324,544 B，sha256 `3B6F9AF9…`，PE 时间 2026-10-19 06:18:20 UTC，build 自报 `archive/qwen4exp-port-session2-dirty`）。
> 模型 `bonsai2_27b_ternary_ptq1_native_mtp.ninfer`（6,394,697,216 B）。
> 全部结论为本机当天连续实测；每条都给日志原文与命令，可逐条复核。

## 1. 配置

```
ninfer-serve-89.exe <model> --host 127.0.0.1 --port 8091 --model-id local \
  --kv-capacity 40000 --kv-dtype rk2v4-e8 --host-kv-mib 6144 \
  --device-state-slots 0 --no-cuda-graph --gdn-state-fp16 \
  --spec mtp --draft-tokens 4 --mtp-attention-window 8 \
  --max-context 262144 --max-concurrency 1 --max-shared-prefixes 0 \
  --derive-session-keys --prefill-chunk 1024 --default-max-tokens 8192 \
  --default-reasoning-effort none
env: NINFER_KV_WINDOW=16384 NINFER_KV_RETRIEVE=8192 NINFER_HOST_PAGEABLE=1
     NINFER_KV_REUSE_HOSTBACKED=1 NINFER_TERNARY_PTQ1_FAST=1
```

显存常驻 7,469 / 8,188 MiB。启动闸门本来就判了拒绝，我们是硬起的（gate_rc=2）：

```
[gate] pool=40000 (625 pages) dtype=rk2v4-e8 mtp=1 => engine_est~7776 MiB
       | redline=7488 (card 8188 - reserve 400 - desktop 300) | slack -288 MiB => REFUSE
```

## 2. 现象：同一个进程里，超池请求只可信一次

题面固定：295,944 字符 → prompt 209,095 token，正文 7,244 条中文分条记录，其中 8 条是「关键记录：暗号是 XXX」，
要求按出现顺序列出全部暗号。8 个真暗号分布在第 3/14/27/39/52/65/78/92 百分位。

| 序 | 请求 | 结果 | 备注 |
|---|---|---|---|
| 1 | 209K（进程里第一个大请求） | **8/8 全对**，0 编造，wall 378.6 s | 3 次独立复现，wall 一致 |
| 2 | 13K 池内 | 8/8 | 干净 |
| 3 | 100K | **2/8** | 1 个文档里不存在的编造暗号 |
| 4 | 150K | **0/8** | 输出里 **49 个**文档中不存在的编造暗号 |
| 5 | 209K 复跑（同一份文件） | **2/8** | 块号全部合法 |
| 6 | 100K + 30 条同句式干扰 | 1/8 | 引用了 2 个假编号 |
| 7 | 100K 完全无关文档（公共前缀仅 16 字符，seed 777） | 1/8 | 退化成无限重复同一错暗号 |
| 8 | 污染后再发 30K 池内 | **8/8**，0 编造 | 污染只打超池路径 |

全程 HTTP 200、没有任何 error 行，只有那条已知的 prompt exceeds the resident Device KV pool 警告。
客户端拿到的是一份格式完美、内容错误的答案——这比报错危险得多。

## 3. 证据 A：kvmem_score 的打分表跨请求复用，且块号越界

```
kvmem_score: SELECT label=text_prefill_chunk n_blocks=3268 budget_blocks=512 sink_blocks=64
             kept=512 runs=175 skip=2756 window_tokens=32768 kept_range=[0,3267]
```

- n_blocks 在 209K 请求里从 1 跟到 3,268（该请求真实块数，自洽）。
- 此后所有请求它恒为 3,268：100K 真实只有 1,562 块、150K 只有 2,344 块，但 n_blocks 仍是 3,268，skip=2756 / candidates=3204 一字不变。
- 于是 100K 请求最后一条 KEPT 里 = 64 个真块 + 448 个上一请求的幽灵块（87.5% 预算打在越界块上）；150K 同样 87.3%。
- kept_range=[0,3267] 直接超出本请求的 span。

## 4. 证据 B：ring 的 evidence 预算写死 128 页，free 490 页从不外借

```
[ring] budgets: protect=0 skeleton=0, evidence=128, recent=0, free=490 (pool 625)
       backend_pages=7 backend_capped=1 [protect+skeleton+evidence+recent+backend+free == pool: yes]
```

- 1,700+ 次采样一字不变（209K / 150K / 100K / 30K / 无关文档，五种题面全部同一行）。
- evidence=128 页 × 64 token = 8,192 token，只有 209K 题面的 3.9%；打分器却按 budget_blocks=512（32,768 token）在选。
- free=490 页 = 池的 78%，从不借给 evidence（evidence + free 恒等于池常数）。
- restored_frac = 1.000（1,246 次检索里 preferred=152,079 / restored=152,079）⇒ 不是还原失败，是选页选错。

另有 mask hidden 同步坏掉：首请求 span=742 resident=617 hidden=125 mid_hidden=0；污染后 span=3267 resident=617 hidden=2650 mid_hidden=1143。

## 5. 为什么这两条单看都不足以解释

- 若只怪 H2（预算静态），同一预算、同一长度的 209K 不该出现「8/8 → 2/8」的翻面。
- 若只怪 H1（块号越界），209K 复跑时块号完全合法也依然是 2/8。
- 已排除别名假设：seed 777 生成的毫无共同前缀的 100K 文档，同样 1/8。

我们的推断：H1 把打分器的候选集污染成上一请求的形状，H2 让真正的证据页本来就装不下，两者叠加。准确机理需要你从源码判断——我们只有日志侧观测。

## 6. 建议（按优先级）

1. n_blocks 每个请求重置，或在 n_blocks < 上一请求时丢弃打分表重建。现在的高水位冻结会让任何「先长后短」的会话序列静默降级。
2. evidence 预算自适应：free 有 490 页而 evidence 只有 128 页，是最大的浪费。我们已在二进制里找到 NINFER_KV_EVIDENCE_AUTO / _SHARE / _RESERVE、NINFER_KV_RECENT_PAGES、NINFER_KV_RETRIEVE_SHARE、NINFER_KV_HOST_WRITETHROUGH、NINFER_KV_PROTECT_FRAC，但没有任何文档说明取值语义、默认也没开。若它们就是解药，请在 README 写清推荐值。
3. 超池时把 unverified 从 warning 升级成硬失败（HTTP 4xx，或至少一个响应头/字段）。现在 8 GB 卡用户唯一的防线是「别在同一进程里发第二个长请求」，这条纪律靠文档传不下去。
4. prompt exceeds 警告里建议同时打印 restored_frac、evidence、n_blocks 三个数——三个数放一起，用户一眼能看出自己是否已踩进污染。

## 7. 复现材料

- fixture：d209k-s20261030.txt（295,944 字符 / 209,037 token）、d100k-s20261030.txt、d100k-s777.txt、d30000.txt（同目录，seed 固定可重新生成）。
- 探针脚本：tmp/probe200k.py（单发长文档 + 校验 8 暗号）；reports/超池200K-可用性实测.md（24,556 B，13 组对照全表）；tools/longdoc.py（分片改造版：同一题面切 9 片、每片 ≤ 27K token，8/8 全对 316 s，可重复）。
- 日志：logs/engine-40k.log（含全部 kvmem_score / [ring] budgets / mask hidden 行）。

---

附：本机同一天量到的正面数据，供你判断这台机器没有别的毛病——池内 40K 请求：计数题 97.7 tok/s（MTP accept 82%）、中文散文 47.2 tok/s；37,468-token 提示 prefill 963 tok/s、TTFT 38.9 s、双针全对、超池警告 0 条。分片法把同一份 209K 文档跑成 8/8：9 片、316 s、两次重复 315.5/315.7 s。