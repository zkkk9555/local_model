# Strata 在 8 GB 显存显卡上的公开报告合集（一手证据，逐字命令）

采集时间：2026-10-30（Asia/Shanghai）
来源仓库：Niko1221/Strata（一次性只服务 Qwen3.8-Flash-Next / 125B MoE 的推理引擎）
采集范围：该仓库 **issues + pull requests + 仓库内 docs/bench results**。
**Discussions 不存在**：https://github.com/Niko1221/Strata/discussions 返回 404，该仓库未启用讨论区，因此"逐个翻 discussions"这一项客观无内容可查（不是遗漏）。

## 0. 口径与检索面

检索用 GitHub Search API（HTML 页面交叉核对；REST core 限额 60/h 当时已耗尽，403 rate limit exceeded）。检索词与命中数（repo 内全文检索，issues+PR 合并）：

    8GB=42   "8 GB"=826   8192=477   3070=58   4060=98
    3060=277 2070=22      OOM=192    "out of memory"=135
    kv-resident=1131       "expert slots"=658     "expert cache"=1549

去重后 728 条线索（其中 314 个是 PR），标题里直接含 8GB 的 41 条。本文件只收录"**卡在 8 GB 一档、且带 URL、且给出了可复核数字或逐字命令**"的条目；每条都标明它是"作者自述实测"还是"官方维护者整理"。

重要前提（判断 8 GB 是否受支持时的官方口径）：仓库 README 与 docs 的排版口径是 **12–24 GB 显存 + 64 GB RAM**；docs/COMMUNITY_BENCHMARKS.md（main 分支）收录的社区报告里，8 GB 一档官方只登记了 **2× NVIDIA Quadro RTX 4000 8 GB**（2026-10-07-community-2x-rtx-4000）。也就是说：**8 GB 单卡跑起来是社区行为，不在官方承诺的硬件区间内**，下面所有数字都不构成官方保证。

## 1. 逐条：8 GB 单卡报告

### 1.1 PR #1496 — RTX 3070 Ti 8 GB（最重要一手，含 128K）
https://github.com/Niko1221/Strata/pull/1496
标题：[Benchmark] RTX 3070 Ti 8 GB, IQ2_XS at 32K and 128K: re-measured on 0.2.0-beta；作者 gbwzzy218；state=closed。
关闭原因不是"数据不行"：作者 2026-10-19 用 /reopen 重开后，owner 以"0.2.0-beta 跟踪器重置"关闭，理由是 1300+ 个 open 项无法逐一 review，并说明 **Closed 不等于 rejected**，结果会进即将上线的官网社区 benchmark 页。
报告目录（在该 PR 的 fork 分支 gbwzzy218:bench-rtx3070ti-8gb 上，main 分支没有）：
    bench/results/2026-10-19-community-rtx3070ti-8gb-0.2.0-beta/
    bench/results/2026-10-07-community-rtx3070ti-8gb/          （上一版，0.1.40.3）

硬件：RTX 3070 Ti 8,192 MiB（cc 8.6，PCIe 4.0 x16，290 W，**同一张卡带显示器**）、Win11 build 26200、驱动 617.42、Ryzen 9 5900X 12C/24T、63.9 GiB DDR4-3600。
引擎：v0.2.0-beta 发布资产 strata-engine-0.1.45.3-windows-x86_64-cuda-cuda13.tar.gz（commit f6d65cb584c0，tree 3d1fb48）。

逐字引擎 config（configs/arms/C.json，即 128K + k8v4 + 20,480）：

    args = --pack <data-dir>\packs\iq2_xs
           --native <data-dir>\models\IQ2_XS\...-IQ2_XS-00001-of-00002.gguf
           --ple-gguf <data-dir>\models\IQ2_XS\...-IQ2_XS-00002-of-00002.gguf
           --expert-profile <repo>\data\expert-profile.bin
           --expert-cache auto --prefill auto
           --spec 4 --spec-min-p 0.5 --mtp <data-dir>\mtp\rt
           --max-context 131072 --kv k8v4 --kv-resident 20480
           --conversation-cache-mib 4096 --conversation-cache-slots 4

另外三臂：B.json 与 C 完全相同、只把 --kv-resident 改成 32768；A.json 是 32768 + int8、不带 kv-resident；D.json 是 131072 + int8 + --kv-resident 32768（不带 --kv k8v4）。
四臂是这么生成的（README 表里的原命令）：

    A: START-HERE.bat --yes --family qwen --model IQ2_XS --vision no --no-start
    B: START-HERE.bat --setup --family qwen --model IQ2_XS --context 131072 --kv k8v4 --vision no --yes --no-start
    D: 同 B，但不带 --kv k8v4
服务端与基准（逐字）：

    serve/server.py --engine strata --config <block>.json --port 8080
    python bench/results/2026-09-30-community-rtx-5090/benchmark.py --root <repo> --pack <data-dir>\packs\iq2_xs \
        --url http://127.0.0.1:8080 --targets 4096,16384 --runs 5
    （128K 那一块另加 --targets 32768 --runs 5 与 128000 --runs 3）
    python tools/needle_bench.py --url http://127.0.0.1:8080 --lengths 32k,128k --depths 10,50,90

Session 1（显示器开，作者注明"推断"）prompt tok/s @4096 / @16384，decode tok/s @4096 / @16384：

| 臂 | 配置 | prompt 4K | prompt 16K | decode 4K | decode 16K |
| --- | --- | ---: | ---: | ---: | ---: |
| A | 32768, int8, 无 kv-resident | 542.8 | 586.0 | 49.3 | 48.2 |
| B | 131072, k8v4, 32768 | 485.9 | 498.8 | 46.8 | 47.8 |
| C | 131072, k8v4, 20480 | 498.9 | 493.6 | 49.8 | 49.7 |
| D | 131072, int8, 32768 | 438.6 | 432.5 | 52.1 | 48.5 |

C 臂长上下文：128,000 tokens 时 **464.6 tok/s**（[463.7–466.7]）、decode **51.0**（[50.4–51.2]）、**TTFT 275.6 s**；32,768 tokens 时 484.2 tok/s、TTFT 67.7 s；TTFT@4096 ≈ 8.2–9.4 s、@16384 ≈ 32.9–37.9 s。
显存：加载后 **7,346–7,440 MiB / 8,192**，运行中最高 **7,557 MiB**；进程 RSS 35.0–36.7 GiB（峰值 39.6），可用 RAM 只剩 14.2–14.8 GiB。
engine-start 计划日志（证明参数怎么落到显存上）：A = 1280-token chunk / 351 slots / 加载后空 2.21 GiB；B = 768 / 8-slot ring / 空 2.14 GiB；C = 1024 / 384 / 空 2.25 GiB；D = 512 / 8 / 空 2.05 GiB；KV 另有 1.20 GiB（B、C）或 1.55 GiB（D）在 pinned RAM。

这篇的技术结论（比速度值更值钱）：
- 0.1.40.3 时代，C 比 B 快 **+39.7% ~ +41.4%**，纯粹因为 prefill chunk 拿到 1024 而不是 768。
- 0.2.0-beta 上这个差距**消失了**（−2.8% ~ +2.7%）：从 0.1.41 起 **CPU prefill share 默认开启**（src/prefill/prefill.cpp:194-198：chunk < 1024 且单张 CUDA 卡时，把一部分专家交给 CPU 池）。设 STRATA_PREFILL_CPU_SHARE=0 可复现旧行为。
- 同机同臂跨版本对照（session 1）：A 549.8/645.9 → 542.8/586.0（−1.3%/−9.3%）；B 363.7/380.1 → 485.9/498.8（**+33.6%/+31.2%**）；C 508.0/537.4 → 498.9/493.6（−1.8%/−8.2%）；D 304.0/302.0 → 438.6/432.5（**+44.3%/+43.2%**）；128K 下 C：520.8 → 464.6 tok/s、43.6 → 51.0 decode、TTFT 246.0 → 275.6 s。
- 新 README **撤回了"<10 GB 卡要选更小窗口"的建议**（这是 8 GB 用户最该记住的一条）。
- 质量侧：needle 6/6 命中（32,045–32,046 与 124,125–124,127 tokens 正确召回）；13 项任务检查全过；98 个请求全部完成，其中 28 个被标记受扰（GPU 软降频 0x20/0x24，温度 72–84 °C，同卡带显示器）。
- 踩坑：0.2.0-beta 的 setup.py 去找 strata-windows-x64.zip（404），会转去装 VS2022 Build Tools + CUDA Toolkit（8–10 GB）；且 --kv k8v4 仍被打印成 "KV cache: 4-bit (Hadamard-rotated)"。

### 1.2 PR #1972 — RTX 3070 8 GB，196608 上下文
https://github.com/Niko1221/Strata/pull/1972
硬件：RTX 3070 8 GB（8192 MiB，240 W）+ R9 5900X + 96 GB，Ubuntu 24.04.4，驱动 580.178.04；引擎 0.1.41（仓库 Dockerfile 派生的本地 Docker 构建）；用 OpenCode 1.18.16 真跑 8 个 agent-coding 任务。
引擎参数（section 1/2 全部运行一致，逐字）：

    --max-context 196608 --kv int8 --kv-resident 20480 --spec 4 --spec-min-p 0.5 --mtp
    --expert-cache auto --prefill auto
section 3（A/B 采样实验）改用：

    --max-context 262144 --kv int8 --kv-resident 32768
结果：IQ2_XS decode **46.5 tok/s**、prompt **563 tok/s**；IQ3_S 30.8–32.3 tok/s / 290–302 tok/s；**峰值显存 7,676–7,799 MiB**；无重试、无超时、无 OOM。IQ2_XS 比 IQ3_S 少花 28 分 44 秒跑完同样 8 个任务。

### 1.3 PR #2581（与 #3597 重复）— RTX 3070 Ti 8 GB + R5 7600X，Qwen3.6-35B Q5_K_S
https://github.com/Niko1221/Strata/pull/2581
硬件：3070 Ti 8 GiB + Ryzen 5 7600X + 31.1 GiB，Win11 build 26200，驱动 617.14，Strata 0.1.44.1（commit 296b59d2，官方 Windows CUDA13 release）。模型 llmfan46/Qwen3.6-35B-A3B-...-GGUF Q5_K_S。
逐字：

    strata.exe --native <model>.gguf --max-context 32768 --prefill auto --mtp 2
    serve/server.py --engine strata --config strata-qwen36-ud-q4_k_xl.json --port 8080
数字：短聊天 decode **50.6**（46.6–60.7）/ TTFT 0.52 s；4K fresh prompt **1189.1 tok/s** / TTFT 3.40 s；16K **1100.2 tok/s** / TTFT 14.62 s；agent 会话 decode **35.5**（22.4–47.3）；25,298-token prompt 只有 **376.2 tok/s**、decode 14.7、TTFT ≈ 67 s（已贴近 32768 上限）；--clients 4 合计 36.5 tok/s。
显存 **7,666 / 8,192 MiB 稳态**，free RAM 0.2–3.8 GiB；**0/256 个专家进 VRAM**（全走可换页主机内存）；qwen36 这条路径没有 batch slots（日志 "ignoring --batch 4"）；会话缓存复用率 0%。这是一条"8 GB 能跑，但把 8 GB 当 4 GB 用"的极端案例。

### 1.4 PR #2004 — RTX 4060 8 GB（同卡带桌面），两种专家驻留策略对打
https://github.com/Niko1221/Strata/pull/2004
硬件：RTX 4060 8 GB（PCIe 3.0 x8，同卡带桌面）+ i7-8700 + 31.9 GB，Win10 22H2，驱动 610.88，Strata 61b3fb5（engine 0.1.42）。
两套配置共用的逐字参数：

    --max-context 32768 --kv int8 --expert-cache auto --prefill auto
    --spec 4 --spec-min-p 0.5 --vram-reserve-mib 300 --vision
    # 环境变量：STRATA_RESIDENT_HEADROOM_GIB=6
    # 差异：Coder IQ1_M 用 --resident-experts（318 GPU slots / 0.61 GiB + 约 18.5 GB 锁定 RAM）
    #       IQ2_XS 用 --mmap-experts（1226–1231 slots / 1.67 GiB）
    python -m serve.server --engine strata --config strata-coder-iq1_m.json --port 8080
    python -m serve.server --engine strata --config strata-iq2_xs.json        --port 8080
数字：82-token decode **15.5 vs 20.7** tok/s；9.7K fresh prompt **134.9 vs 31.3/35.7** tok/s；TTFT@9.7K **72.7 s vs 276–335 s**；28K needle **212–215 s vs 564–765 s**；**峰值 VRAM 7,645 / 7,769 MiB**（含桌面）；峰值 RAM 31.8/31.9 GiB。
坑：**默认 --vram-reserve-mib 700 时 IQ1_M 拿到 0 个 GPU 专家槽**，启动自检直接失败；必须降到 300 并配 STRATA_RESIDENT_HEADROOM_GIB=6 才起来。

### 1.5 PR #2064 — RTX PRO 1000 Blackwell Laptop 8 GiB，65536 上下文
https://github.com/Niko1221/Strata/pull/2064
硬件：RTX PRO 1000 Blackwell Laptop 8 GiB + Core Ultra 7 255H + 63.4 GiB，Win11，0.1.43。
逐字（IQ1_M 臂）：

    strata.exe --pack coder-iq1_m --native ...IQ1_M-00001-of-00002.gguf --ple-gguf ...-00002-of-00002.gguf
      --expert-profile expert-profile-coder.bin --expert-cache auto --prefill auto
      --spec 4 --mtp rt --max-context 65536 --kv int8 --kv-resident 32768
      --spec-min-p 0.5 --pool-workers 10
    （IQ2_XS 臂同参数，仅换 --pack iq2_xs 与 expert-profile.bin）
数字：IQ1_M — chat decode **23.5**、4K **345.0 tok/s**（TTFT 11.71 s）、16K **335.0**（48.02 s）、32K **314.4**（102.01 s）、agent **21.5**；IQ2_XS — chat **39.0**、4K **535.9**（7.55 s）、16K **537.6**（29.92 s）、agent **34.9**。会话缓存命中 68.7% / 68.8%。报告目录：2026-10-12-...coder-iq1-m、2026-10-13-...iq2-xs。

### 1.6 PR #2479 — RTX 3080 Laptop 8 GiB（Linux），32768
https://github.com/Niko1221/Strata/pull/2479
硬件：MSI GP66，RTX 3080 Laptop 8 GiB（sm_86，140 W）+ i7-11800H + 31 GiB，Ubuntu 24.04.5，驱动 580.178.04，0.1.43.1 源码编译。
逐字：

    strata --pack coder-iq1_m --native ...IQ1_M-00001-of-00002.gguf --ple-gguf ...
      --expert-profile expert-profile-coder.bin --expert-cache auto --prefill auto
      --spec 4 --spec-min-p 0.5 --mtp rt --max-context 32768 --kv int8 --resident-experts
    （IQ2_XS 臂把 --resident-experts 换成 --mmap-experts）
数字：cpu-share 臂 chat decode **25.3**、4K **541.1 tok/s**（7.48 s）、16K **627.5**（25.65 s）、agent **21.1**；首轮 TTFT 3.24 s；缓存命中 68.6%。32K 没测（上下文正好 32768，没法再往上加）。

### 1.7 PR #2539 — RTX 4060 Ti 8 GiB，IQ2_XS，32768
https://github.com/Niko1221/Strata/pull/2539
硬件：RTX 4060 Ti 8 GiB + i9-14900K + 64 GB DDR4，Win11。
逐字：

    strata.exe --pack iq2_xs --native ...IQ2_XS-00001-of-00002.gguf --ple-gguf ...-00002-of-00002.gguf
      --expert-profile expert-profile.bin --expert-cache auto --prefill auto
      --spec 4 --mtp rt --max-context 32768 --kv int8 --pcie-frac 0.00
      --spec-min-p 0.70 --pool-workers 15 --adapt-every 1 --adapt-swaps 160 --adapt-decay 0.97
数字：chat decode **51.1**、4K **568.6 tok/s**（7.10 s）、16K **623.9**（25.78 s）、agent **48.1**。这张卡（同容量 8 GB）在 4K/16K 上与 3070 Ti 基本同档，说明 8 GB 的瓶颈主要在"专家缓存能放多少"而不是带宽。

### 1.8 PR #3026（与 #3408 重复）— RTX 4060 Laptop 8 GiB，131072 上下文
https://github.com/Niko1221/Strata/pull/3026
硬件：RTX 4060 Laptop 8 GiB + i7-14700HX + 31.7 GiB，Win11，0.1.45。
逐字：

    strata.exe --pack q2_0 --native ...Q2_0-00001-of-00002.gguf --ple-gguf ...Q2_0-00002-of-00002.gguf
      --expert-profile expert-profile.bin --expert-cache auto --prefill auto
      --spec 4 --spec-min-p 0.5 --mtp rt --max-context 131072 --prompt-cache-every 8192
      --kv q4_0 --kv-resident 20480 --vram-reserve-mib 200 --vision
      --resident-experts --pool-workers 19
    # 环境变量：STRATA_PCIE_AUTO_CANON=1
数字：chat decode **30.5**；4K **220.1 tok/s**（18.33 s）；16K **220.4**（72.97 s）；agent **23.1**。日常 88 个 64K–120K 请求：prompt 中位 **47.0**、decode 中位 **24.0**。KV 只有 **20,480 / 131,072** 个单元在 VRAM，约 0.84 GiB 移到 pinned RAM。同机同模型的 RAM 对照：可用 10.53 GiB 时 decode 15.5，16.93 GiB 时 21.6 tok/s（+39%）——**8 GB 卡上，RAM 余量直接换 decode**。

### 1.9 PR #1378 — RX 6600 8 GB（HIP），IQ3_XXS 128K
https://github.com/Niko1221/Strata/pull/1378
硬件：RX 6600 8 GB（gfx1032，用 HSA_OVERRIDE_GFX_VERSION=10.3.0 跑）+ EPYC 7232P + 128 GB，Ubuntu 24.04.5，ROCm 7.2.4，v0.1.40.2。
参数：0.1.40.2 + **STRATA_HIP_PROMPT_F16=1**；专家缓存 auto 985 slots / 1.62 GiB；MTP draft 835 MiB；加载后剩 620 MiB。
数字：prompt **262.6 / 265.6 tok/s**、decode **24.0 / 23.8**。

### 1.10 PR #4543 — RX 7600 8 GB（HIP 自编译），Q2_0，32768
https://github.com/Niko1221/Strata/pull/4543
自编译开关（逐字）：

    -DSTRATA_ENABLE_HIP=ON -DSTRATA_ENABLE_CUDA=OFF -DSTRATA_BUILD_TESTS=OFF
    -DSTRATA_PREFILL_MMQ=ON -DSTRATA_Q6K_EXPERTS=ON -DSTRATA_MMQ_KQUANTS=ON
    -DCMAKE_HIP_ARCHITECTURES=gfx1102
    ./setup.sh --backend hip --model Q2_0 --context 32768 --vision no --parallel 1 --no-start --yes
    # 引擎参数：--expert-cache auto --prefill auto --spec 4 --spec-min-p 0.5 --mtp <draft-layer>
    #           --max-context 32768 --kv int8
数字：Q2_0 专家 arena 32,400 MiB、1,730 slots / 2,280 MiB、prefill cap 3,584、加载后剩 634 MiB；4K **215.9 tok/s**（TTFT 18.659 s）、16K **237.9**（67.542 s）、chat decode **27.2**；手动快照 VRAM **7.41 GiB**。

### 1.11 PR #1681 — RTX 5080 16 GB + RTX 4060 Ti 8 GB 当二级专家缓存（双卡）
https://github.com/Niko1221/Strata/pull/1681
这是 8 GB 卡唯一一条"不作为主卡、而是被 16 GB 主卡当 L2"的用法：

    strata --serve --pack <pack> --native <IQ3_S shard1> --ple-gguf <shard2>
      --expert-profile data/expert-profile.bin --expert-cache auto --prefill auto:16384
      --spec 4 --spec-min-p 0.5 --mtp <mtp/rt> --max-context 131072 --kv int8
      --kv-resident 32768 --pcie-frac 0 --ple-inflight 128
      --vram-reserve-mib 713 --expert-cache-device1 3300
    # env: CUDA_VISIBLE_DEVICES=<5080>,<4060Ti> STRATA_IO_THREADS=64 CUDA_MODULE_LOADING=LAZY
    #      STRATA_GR_V3=1 STRATA_PF_FUSED=1 STRATA_MMVQ_IL=1 STRATA_ADAPT_LAG=2 STRATA_DISJOINT_ADAPT=1
数字：4K **3,451 tok/s** / decode 146.0 / TTFT 1.20 s；32K 4,277 / 132.2 / 7.70 s；128K 4,166 / 124.9 / 30.80 s。

### 1.12 PR #2248 — RTX 4060 8 GB + RTX 2060 6 GB 双卡，Qwen3.8-Flash-Next IQ2_XS
https://github.com/Niko1221/Strata/pull/2248
硬件：RTX 4060 8 GB（Ada sm_89，PCIe 3.0 x8）+ RTX 2060 6 GB（Turing sm_75），--layer_split auto，卡序 1,0；i7-9700KF 8C/8T（只有 AVX2）；62 GB RAM；driver 595.99.02 / CUDA 13.0；Strata v0.1.43.1 源码编译（CMAKE_CUDA_ARCHITECTURES=75;89）。
逐字（setup 写出的 strata-iq2_xs.json）：

    --expert-cache auto --prefill auto --spec 4 --spec-min-p 0.5
    --max-context 32768 --kv int8 --vision --vram-reserve-mib 700
    --server 127.0.0.1:8080 --gpu 0,1 --layer_split auto
    # 日志：[strata] layer split: card order 1,0（快的卡放最后）
数字：chat decode **35.8**（34.1–43.8）/ TTFT 0.93 s；4K **287.7 tok/s**（283.1–289.4）/ TTFT 14.01 s；16K **298.5**（298.4–299.2）/ TTFT 53.84 s；agent **36.1**（30.9–43.4），prefix 命中 68.7%；**合计显存 13.3 / 14.3 GB**。冷启动 VRAM 命中率约 38%（410 专家），热起来到 ~1548 专家。
作者自己写明：2060 的 6 GB 低于 Strata 的 8 GB 门槛，官方警告"可能比不插还慢"，实测没退化，但**这只是保守下界**（两张都 ≥8 GB 会更好）。

## 2. 逐条：8 GB 相关 issue（不是 PR，无 bench 目录）

### 2.1 Issue #1009 — RTX 4060 Ti 8 GB：0.1.39 的 --prefill auto 比 0.1.31 慢 40%
https://github.com/Niko1221/Strata/issues/1009
硬件：RTX 4060 Ti 8 GB（PCIe 4.0 x8），驱动 610.88，Win11；i5-14400F（**无 AVX-512**）；32 GB DDR4-3200；Kingston NV2 1 TB。
对比版本：v0.1.39（6f32ec0）vs 0.1.31（9259cad）。
逐字（setup 写出的 config args）：

    --pack <data>/packs/coder-iq1_m --native <data>/models/coder-IQ1_M/...-00001-of-00002.gguf
    --ple-gguf <data>/models/coder-IQ1_M/...-00002-of-00002.gguf
    --expert-profile <strata>/data/expert-profile-coder.bin
    --expert-cache auto --prefill auto --spec 4 --mtp <data>/mtp/rt
    --max-context 32768 --kv int8 --resident-experts --spec-min-p 0.5
    # setup 命令：--family coder --model IQ1_M --context 32768 --kv int8 --vision no --experimental-speed-projection off
测量（每行一次运行；prompt 6,851–6,853 与 22,370–22,375 tokens）：

| 引擎/参数 | 专家缓存 | chunk | prefill 8K | prefill 22K | TTFT 22K | decode 22K |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 0.1.31 默认（run1） | 181–240 slots | 512 | 148.5 | 189.9 | 118.3 s | 19.1 |
| 0.1.31 默认（run2） | 181–240 slots | 512 | 147.2 | 196.6 | 114.2 s | 20.0 |
| 0.1.39 默认 | 309 slots | 256 | 113.7 | 116.9 | 191.9 s | 19.0 |
| 0.1.39 + STRATA_RING_BYTES=0 | 314 slots | 256 | 113.8 | 113.9 | 196.8 s | 19.5 |
| 0.1.39 + --prefill 512 --no-prefill-borrow | 1 slot | 512 | 193.4 | 207.7 | 108.1 s | 21.2 |

原因作者自己定位到了：256-token chunk 要借 146 个缓存 slot，512 就要约 290，而借用后必须留 128 个（src/program/generate.cpp 里的 fits_one），290+128 > 309，于是 auto 只能降到 256。
可行绕过（这是他给出的逐字建议）：在 config 的 args 里加

    --prefill 512 --no-prefill-borrow
代价是专家缓存缩到 1 slot（decode 命中率从 14–22% 掉到 0.1%），但 decode 没变慢（22K prompt 上 21.2 vs 19.0 tok/s），prefill 回到 207.7 tok/s。注意：**setup 重写 config 时不会保留手加的参数**，每次升级要重加。

### 2.2 Issue #2477 — RTX 3080 Laptop 8 GB：0.1.44.1 启动只剩 423 MiB 显存
https://github.com/Niko1221/Strata/issues/2477
配置（逐字）：

    --expert-cache auto --prefill auto --spec 4 --mtp ... --max-context 32768 --kv int8 --resident-experts
现象：启动时 1.99 GiB 空闲、预留 700 MiB（+218 MiB 给 draft head）→ 441 slots，最终缓存 566 slots / 1.09 GiB VRAM；加载完只剩 **423 MiB**，首次请求打警告"only 423 MiB of VRAM free (below 512 MiB)"，并建议 --vram-reserve-mib 832；后来一次警告在 291 MiB，建议 960。三次启动都是 417–423 MiB。IQ2_XS（mapped）加载后剩 481 MiB。
实际没出事：四轮 bench、0 个失败请求、没有低于 13 tok/s 的解码。0.1.43.1 上 --vram-reserve-mib 832 → 553 MiB 空闲、502 slots，decode 无可测变化。

### 2.3 Issue #300 — 8 GB + IQ3_S + 64K：prompt 路径直接起不来（含官方警告原文）
https://github.com/Niko1221/Strata/issues/300
现象：0.1.130 上 48K/32K/16K 全都报同一个错；--kv k8v4 无效；--vram-reserve-mib 700/1200 无效；--prefill auto 无效；**只有 --prefill 512 能起来**。日志逐字：

    strata generate: expert cache auto: 0.06 GiB free, 700 MiB reserved (+86 MiB for the draft head) -> 0 slots
    strata generate: no VRAM is left for the expert cache: lower --max-context, use --kv k8v4,
                     run images on the CPU, or close other programs that use the GPU
    strata serve: the prompt path allocates its own buffers (too few cache slots to borrow)
    strata serve: prefill: device buffers for a chunk of 1024 tokens do not fit
    strata serve: the GPU has too little free VRAM for the prompt path: turn images off (setup: --vision no),
                  close other programs using the GPU, use a shorter context, or read prompts in smaller chunks (--prefill 512)
另有一条信息：该机 cudaHostRegister 整个 arena 直接失败（out of memory），退回 47 slices pinned（45 GiB），大页被拒（VirtualAlloc error 1314），用 4 KB 页——说明 8 GB + 64 GB RAM 的机器在 Windows 上 pinned 内存也紧。

### 2.4 Issue #1375 — RX 6600 XT 8 GB + Xeon E5-2678 v3 + DDR3
https://github.com/Niko1221/Strata/issues/1375
硬件：Huananzhi X99-TF，Xeon E5-2678 v3（12C/24T，AVX2，无 AVX-512），4×16 GB DDR3-1600 ECC 四通道，RX 6600 XT 8 GB（gfx1032），PCIe 3.0 x8（实测 6.7 GB/s），Debian 13，v0.1.40.1（82f46a8，为 gfx1030 编译，-DSTRATA_PREFILL_MMQ=ON），ROCm 7.14.0a20260612。
关键参数（这张卡是他调出来的配方，逐字）：

    --prefill auto                       # Uncensored: 自动 3840-token chunk → 约 318 tok/s（512 时只有 79）
                                          # GSQ-RCO: 自动 2304 → 约 250 tok/s（请求 3840 被降到 960 只有 133）
    STRATA_HIP_PROMPT_F16=1               # 318 vs 229 tok/s
    STRATA_HIP_ADAPT_KERNEL_COPY=1        # 长 prompt 的 SDMA page fault 消失
    --max-context 131072 --kv int8 --kv-resident 20480
    --mtp-draft-vocab data/draft_vocab_fr.bin    # draft head 77.6 MiB（默认词表 178.4 MiB）
    --vram-reserve-mib 700                # 326–327 tok/s；500 MiB 时多 89 slots 但 decode 无提升
    --spec 4 --spec-min-p 0.5
数字（10,567-token prompt）：GSQ-RCO IQ3_XXS 解码 **16–17 tok/s**、读 **约 250 tok/s**、42,176-token 时 **341 tok/s**、专家缓存 1134 slots / 1.87 GiB；Uncensored IQ3_XXS 解码 14–16、读约 320、1236 slots / 2.50 GiB；MTP draft 接受率 63–72%；冷启动 46 s；系统内存用 46–56 GiB；128K 配置下能在 115,350-token prompt 中段找到植入句。Vision 走 CPU 编码器：800×600 约 8–9 s，1920×1080 密排文字约 65 s。

### 2.5 Issue #4517 — GTX 1070 Ti 8 GB（sm_61）：reserve 不够会"请求永远不返回"
https://github.com/Niko1221/Strata/issues/4517
硬件：GTX 1070 Ti 8 GB（cc 6.1），驱动 580.173.02 / CUDA 12.9，Ryzen 9 3900X（AVX2），32 GB DDR4 + 16 GB zram，Pop!_OS 24.04 / kernel 6.17；Strata Terminal 0.2.7 + **engine 0.1.52 linux-x86_64-cuda-cuda12**；模型 Gyro-S（Qwen3.8-Flash-Next trellis pack，58.5 GB）+ MTP，vision off；32 GB RAM 低于建议的 64 GB，setup 走了 low-memory 模式。
核心发现（这是他最想留下的东西）：在这张卡上，**一个"永不返回"的请求几乎总是 VRAM reserve 不够**，日志里写着：

    WARNING: only 218 MiB of VRAM free at the start of this request (below 512 MiB):
    when the card is this full the driver can page GPU memory to system RAM, decode falls to a few tok/s
    and a window may never finish (#2065).
    Add --vram-reserve-mib 1344 to the config's args, or lower --max-context / --batch
实测：64K 无 reserve 时，三个请求分别在 150 s / 300 s / 540 s 后仍然没有任何结果（GPU 峰值 60–80% 后空闲，主机侧 22 GB 可用内存、swap 安静）——不是内存问题、不是模型问题、不是卡住，就是被驱动换页。

| 设置 | 加载后空闲显存 | 10K prompt 结果 |
| --- | ---: | --- |
| 无 reserve | 178–505 MiB | 150 s 内两次无结果 |
| --vram-reserve-mib 1024 | 1,482 MiB | 97 s 完成 |
| --vram-reserve-mib 1344 | 1,164 MiB | 稳定 |

prompt 吞吐（唯一变量是上下文窗口，reserve 固定 1024 MiB，max_tokens=1）：

| prompt | 8K/int8 | 32K/q4_0 无 reserve | 32K/q4_0 | 48K/q4_0 | 64K/q4_0 |
| --- | ---: | ---: | ---: | ---: | ---: |
| ~4.6K | 203 | 203 | 133 | 168 | 89 |
| ~9K | 211 | 211 | 138 | 176 | 89 |
| ~18K | 211 | 211 | 144 | 173 | 91 |
| ~27K | n/a | 211 | 145 | 173 | 93 |
| ~37K | n/a | n/a | n/a | 105 | 93 |

decode 全程 **27–34 tok/s**，基本不随窗口变；变的是 prompt。
两条反直觉结论：(1) 同一个 1024 MiB reserve 下，**48K 反而比 32K 快**（9K prompt 138 → 176 tok/s），因为 reserve 是固定成本、从专家槽里扣，窗口越大 KV 越大、reserve 摊薄得越好；(2) 真正的瓶颈是专家集合装不进页缓存：

    prefill plan: chunk 1280, ring 96 kept: file set 24.2 GiB does not fit the page cache 21.3 GiB
    -> about 518.7 GB read from the drive per 32768-token prompt (26 chunks)
    no option does better (the set cannot fit: fewest passes win)
所以 32 GB 机器上"每个 chunk 重读全部"；**加到 64 GB 内存把页缓存撑到装得下，等于把 519 GB 读盘变成约 24 GB**——这台机器该升级的是内存不是显卡。
agent 实测：64K + 1344 MiB reserve，12 任务 harness 里 4 个跑通（01-json-extract 1.00/12 轮/340 s、04-rename-safe 1.00/8 轮/369 s、05-memory-nodestructive 1.00/8 轮/498 s、09-long-context-retrieval 1.00/8 轮/310 s），每轮约 11K 输入 tokens 靠会话缓存复用——**8 GB 上会话缓存是load-bearing，不是可选优化**。
另一条实用告警：Hermes Agent 拒绝 context < 64,000 的模型（agent/model_metadata.py 的 MINIMUM_CONTEXT_LENGTH），且 OpenAI 兼容端点没有覆盖开关，所以 8K/32K/48K 在 Hermes 里根本用不了，只有 64K 可用。

## 3. 横向对照表（只收有数字的）

| 报告 | 卡（8 GB） | 上下文 | 引擎 | prompt tok/s | decode tok/s | TTFT | 显存 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| PR #1496 C | 3070 Ti | 131072 | 0.2.0-beta | 498.9@4K / 493.6@16K / 464.6@128K | 49.8 / 51.0@128K | 8.2–9.4 s@4K，275.6 s@128K | 峰 7,557 MiB |
| PR #1496 A | 3070 Ti | 32768 | 0.2.0-beta | 542.8@4K / 586.0@16K | 49.3 | — | 7,440 MiB |
| PR #1972 | 3070 | 196608 | 0.1.41 | 563 | 46.5（IQ2_XS） | — | 峰 7,799 MiB |
| PR #2581 | 3070 Ti | 32768 | 0.1.44.1 | 1189.1@4K / 1100.2@16K | 50.6 / agent 35.5 | 3.40 s@4K，14.62 s@16K | 7,666 MiB |
| PR #2004 | 4060 | 32768 | 0.1.42 | 134.9@9.7K | 15.5 / 20.7 | 72.7 s@9.7K | 峰 7,645–7,769 MiB |
| PR #2064 IQ2_XS | PRO 1000 BW | 65536 | 0.1.43 | 535.9@4K / 537.6@16K | 39.0 / agent 34.9 | 7.55 s@4K | — |
| PR #2064 IQ1_M | PRO 1000 BW | 65536 | 0.1.43 | 345.0@4K / 335.0@16K / 314.4@32K | 23.5 / agent 21.5 | 11.71 s@4K | — |
| PR #2479 | 3080 Laptop | 32768 | 0.1.43.1 | 541.1@4K / 627.5@16K | 25.3 / agent 21.1 | 7.48 s@4K | — |
| PR #2539 | 4060 Ti | 32768 | — | 568.6@4K / 623.9@16K | 51.1 / agent 48.1 | 7.10 s@4K | — |
| PR #3026 | 4060 Laptop | 131072 | 0.1.45 | 220.1@4K / 220.4@16K | 30.5 / agent 23.1 | 18.33 s@4K | — |
| PR #1378 | RX 6600 | 131072 | 0.1.40.2 | 262.6@10.5K | 24.0 | — | 加载后空 620 MiB |
| PR #4543 | RX 7600 | 32768 | 0.1.45 | 215.9@4K / 237.9@16K | 27.2 | 18.659 s@4K | 7.41 GiB |
| PR #2248 | 4060 + 2060 | 32768 | 0.1.43.1 | 287.7@4K / 298.5@16K | 35.8 / agent 36.1 | 14.01 s@4K | 13.3/14.3 GB 合计 |
| PR #1681 | 5080 + 4060 Ti(helper) | 131072 | 0.1.41 | 3,451@4K / 4,277@32K | 146.0 / 124.9@128K | 1.20 s@4K | — |
| IS #1009 | 4060 Ti | 32768 | 0.1.31 → 0.1.39 | 189.9→116.9@22K（补丁后 207.7） | 19.0→21.2 | 118.3→191.9 s@22K | — |
| IS #1375 | RX 6600 XT | 131072 | 0.1.40.1 | 约 250@10.5K / 341@42K | 16–17 | — | — |
| IS #4517 | 1070 Ti | 65536 | 0.1.52 | 203@4.6K / 211@9K / 89–93@64K | 27–34 | — | reserve 后 1,164 MiB 空闲 |

## 4. 从证据里能归纳出的 8 GB 配方

这是把上面 17 条的公共项收敛出来的，不是官方推荐，每条后面标了出处：

1. 上下文起点用 **32768**（PR #1972/#2004/#2248/#2479/#2539/#2581 全是这个值起步）；要更长就直接 131072，中间档没人在 8 GB 上报过（#1496 是 131072，#3026 是 131072，IS #1375 是 131072）。
2. KV：**--kv int8** 是默认选择；要 128K 且要省显存时用 **--kv k8v4**（#1496 C 臂）或 **--kv q4_0**（#3026）。注意 #1496 实测：0.2.0-beta 上 k8v4 相对 int8 **不再有速度优势，只剩显存优势**。
3. 长上下文必配 **--kv-resident N**：20480（#1496 C、#1972、#3026、IS #1375）或 32768（#1496 B/D、#2064、#1681）；剩下的 KV 会进 pinned RAM（#1496：1.20 GiB；#3026：约 0.84 GiB）。
4. 专家缓存：**--expert-cache auto --prefill auto** 是所有人的起点；在 8 GB 上要显式调 **--vram-reserve-mib**——300（#2004，配 STRATA_RESIDENT_HEADROOM_GIB=6）、200（#3026）、700（#2248、IS #1375）、1024–1344（IS #4517）、713（#1681）。**默认 700 会在部分卡上导致 0 个专家槽直接起不来（#2004）**。
5. 专家驻留二选一：**--resident-experts**（锁定 RAM，快，但 #2004 上要 18.5 GB）或 **--mmap-experts**（可换页，慢，1.67 GiB）。#2004 同机对照：resident 路线 9.7K prompt 读 134.9 tok/s、TTFT 72.7 s；mmap 路线只有 31.3–35.7 tok/s、TTFT 276–335 s。
6. 投机解码统一 **--spec 4 --spec-min-p 0.5**（#2539 用 0.5 的变体 0.70），MTP 用 **--mtp rt**（或 --mtp 2、--mtp <draft-layer>）。
7. 线程数 **--pool-workers**：10（#2064）、15（#2539）、19（#3026），一般配 CPU 核数。
8. 专项环境变量（按卡型）：
   - Windows/CUDA：STRATA_PREFILL_CPU_SHARE=0 关闭 CPU prefill 份额（复现 0.1.40 行为，#1496）、STRATA_RESIDENT_HEADROOM_GIB=6（#2004）、STRATA_PCIE_AUTO_CANON=1（#3026）
   - HIP：STRATA_HIP_PROMPT_F16=1、STRATA_HIP_ADAPT_KERNEL_COPY=1、HSA_OVERRIDE_GFX_VERSION=10.3.0（IS #1375、PR #1378、#4543）
   - 双卡：STRATA_GR_V3=1 / STRATA_PF_FUSED=1 / STRATA_MMVQ_IL=1 / STRATA_ADAPT_LAG=2 / STRATA_DISJOINT_ADAPT=1（#1681）
9. 会话缓存不是可选：IS #4517 的 agent 任务靠它把 12 轮压到每轮约 11K tokens；#2064/#2479/#2248 的命中率都在 68% 上下。
10. 8 GB 卡的 RAM 门槛：**≥32 GB 只是能起，#1496 的 RSS 到 39.6 GiB 峰值**；IS #4517 证明 32 GB 会让页缓存装不下专家集合（24.2 GiB > 21.3 GiB），prompt 吞吐塌到 89–93 tok/s。想跑 64K+，64 GB 是实际下限。

## 5. 互相矛盾 / 需要注意的点

- **--vram-reserve-mib 是不是越小越好**：#2004 用 300 才起得来（700 → 0 slots），#2539 用默认值还行，IS #4517 反而要求 1024–1344 才能不出"永不返回"。结论是**它必须随 --max-context 和卡上桌面占用一起调，没有一个通用值**（IS #4517 明确建议文档改成随上下文缩放）。
- **--prefill auto 在 8 GB 上会自己降档**：0.1.39 在 4060 Ti 8 GB 上把 512 降到 256，代价是 22K prompt 从 189.9 掉到 116.9 tok/s（IS #1009）。手动 --prefill 512 --no-prefill-borrow 能救回来，但要牺牲专家缓存。
- **#1496 的 k8v4 结论只适用于 0.2.0-beta**：0.1.40.3 上 k8v4 + chunk 1024 曾快 40%，0.1.41 之后被 CPU prefill share 抹平。
- **"8 GB 官方支持"是误解**：README 口径 12–24 GB，COMMUNITY_BENCHMARKS.md 里 8 GB 只有 2×RTX 4000 一条；所有 8 GB 单卡数据都来自社区 PR/issue，且多数 PR 处于 closed 状态（#1496 的 closed 是跟踪器重置，不代表数据被否）。
- **PR 编号有重复对**：#2581 = #3597、#3026 = #3408，内容相同，引用时注意别当两条独立证据。

## 6. 【未核源】与缺口（明确标注，不要当数字用）

- 【未核源】仓库内 docs/COMMUNITY_BENCHMARKS.md 只登记了 2×Quadro RTX 4000 8 GB 一条 8 GB 报告，其具体数字我未逐项抄录（文件 21.5 KB，HTML 渲染后表格未逐行核对）。
- 【未核源】"8 GB 卡在 0.1.45 之后有专门优化"一类说法：在检索到的 728 条线索里没有找到带 URL 的发布说明支撑，故不列入。
- 缺口：**没有任何一条 8 GB 单卡报告给出 262,144（256K）上下文的成功数字**；最高是 #1972 的 196,608 与 #1496/#3026/IS #1375 的 131,072。
- 缺口：8 GB 单卡的 **OOM 计数**在 #1496 里是"98 请求 0 OOM"，但那是 IQ2_XS + 128K + 20,480 KV 驻留的组合；IQ3_S/IQ3_XXS 在 8 GB 上的 OOM 边界没有系统数据（#300 是启动就 0 slots，不是运行中 OOM）。
- 缺口：Discussions 404，没有讨论区数据可交叉验证。

## 7. 原始证据落地位置（本机）

抓取过程中的原始文件（HTML、patch、config json）在：
    C:/Users/Administrator/Documents/deepseek-harness/default-workspace/.tmp-st/pages/    （各 issue/PR 页面 HTML）
    C:/Users/Administrator/Documents/deepseek-harness/default-workspace/.tmp-st/patches/  （PR 的 .patch，逐字命令都从这里提取）
    C:/Users/Administrator/Documents/deepseek-harness/default-workspace/.tmp-st/api/      （12 个 search API 的 JSON）
其中 PR #1496 的三臂 config（cfg_A.json / cfg_B.json / cfg_C.json）与报告 README（pr1496_README_007.md、pr1496_README_019.md）单独存了副本。
