# Strata PR #1496 —— 「8 GB 显存跑 128K 上下文」完整配方逆向

> 取证对象：https://github.com/Niko1221/Strata/pull/1496
> 取证时间：2026-10-30（Asia/Shanghai），全程走代理 `HTTP_PROXY=http://127.0.0.1:7897`
> 取证方式：`curl` 抓 PR HTML + 抓 PR 的 `.diff`（832,534 B）+ 直接抓 fork 分支 `gbwzzy218/Strata@bench-rtx3070ti-8gb` 上的原始文件（raw.githubusercontent.com，全部 HTTP 200）
> 说明：PR 正文里的表格在 HTML 里被 GitHub 折叠/懒加载，**数值一律取自 PR 分支上的原始 README/results 文件**，不是从渲染页抄的。

---

## 0. 一句话结论

这台 **RTX 3070 Ti 8 GB / Ryzen 9 5900X / 64 GB DDR4-3600 / Win11** 之所以能用 8 GB 显存吃下 **131,072 上下文**，靠的不是「把模型塞进显存」，而是四件事叠加：

1. **专家全部留在内存**：模型 IQ2_XS 共 68.0 GB，其中 **33.02 GiB 的专家 arena 常驻 pinned host RAM**，显存里只放 1,466 MiB 权重 + 一个 **1.31–1.43 GiB 的专家 LRU 缓存**（933–1,051 slots）。
2. **KV 分级**：`--kv k8v4`（K 8-bit / V 4-bit）+ `--kv-resident 20480`（每层只有 20,480 / 131,072 个 cell 在显存，其余 K/V 落在 **1.20 GiB pinned RAM**）。
3. **靠 kv-resident 挤出的显存换来更大的 prefill chunk**：`--kv-resident 20480` 让自动 planner 拿到 **1,024-token chunk + 384-slot ring**（32,768 时只有 768-token + 8-slot staging）。这是 40% 速度差的真正来源——**不是** KV 带宽。
4. **0.1.41 起默认开启的 CPU prefill share**：chunk < 1,024 token 时把一部分专家交给空闲 CPU 池，把 768-token 那档抬了 36–38%，于是 0.2.0-beta 上 `--kv-resident 20480` 的优势消失了。

**代价**：128,000 token 冷启动 prefill 要 **275.6 s**（≈4 分 36 秒），显存常年贴着 **7,34x–7,557 / 8,192 MiB**，每次启动都打印 *"that is little room for the verify windows' buffers under WDDM"*。

---

## 1. 完整启动命令行（逐字）

PR 里没有任何一条「一行式」命令，配方分散在 **setup 命令 → config JSON → 引擎 argv → 服务启动** 四层。下面把 PR 中出现过的命令**全部**列出，一条不省。

### 1.1 环境准备

```bat
git clone --branch v0.2.0-beta https://github.com/Niko1221/Strata.git
:: -> HEAD 3d1fb48090e8f2cefc22d7b5845fb7f5b71f33fa (tag v0.2.0-beta), CMakeLists.txt version 0.1.45.3
:: 引擎用 release 资产手工放进 <repo>\engine\：
:: strata-engine-0.1.45.3-windows-x86_64-cuda-cuda13.tar.gz
:: SHA-256 1b3845ecc3a46644ddc11e5296ab3d35026dbf650041c53657c43874682d1559
```

> 注意：`START-HERE.bat` 在这个 tag 上**找不到**预编译引擎（它去找 `strata-windows-x64.zip`，两个 404），会转去装 VS2022 Build Tools + CUDA Toolkit（setup 自估 "about 8-10 GB, 15-40 minutes"）。作者是把引擎手工放进 `engine\` 才跑起来的。

### 1.2 setup：写配置（4 条，逐字）

```bat
:: A —— 这台机器的默认档（32K / int8）
START-HERE.bat --yes --family qwen --model IQ2_XS --vision no --no-start

:: B —— 128K + k8v4，kv-resident 用 setup 默认 32768
START-HERE.bat --setup --family qwen --model IQ2_XS --context 131072 --kv k8v4 --vision no --yes --no-start

:: D —— 128K + int8（setup 的 KV-streaming 分支写出来的就是这份）
START-HERE.bat --setup --family qwen --model IQ2_XS --context 131072 --vision no --yes --no-start

:: C —— 不重跑 setup，直接改 B 的 config：把 --kv-resident 从 32768 手改成 20480
::       （外加全部 arm 共用的会话缓存，见 1.4）
```

### 1.3 服务启动（每个 block 一次，逐字）

```text
serve/server.py --engine strata --config <block>.json --port 8080
```

> 0.1.40.3 版报告里写的是不带 `--port` 的形式：`serve/server.py --engine strata --config <arm>.json`。
> 每个 block 都是**新起一个引擎进程**（one server start per block），block 内的请求共享引擎缓存状态。

### 1.4 引擎 argv（config JSON 的 `args` 数组，逐字）

这是 128K 的**核心配方**（arm **C**，也就是跑出 464.6 tok/s 的那一档）：

```json
{
 "args": [
  "--pack", "<data-dir>\\packs\\iq2_xs",
  "--native", "<data-dir>\\models\\IQ2_XS\\Qwen3.8-Flash-Next-GSQ-RCO-IQ2_XS-00001-of-00002.gguf",
  "--ple-gguf", "<data-dir>\\models\\IQ2_XS\\Qwen3.8-Flash-Next-GSQ-RCO-IQ2_XS-00002-of-00002.gguf",
  "--expert-profile", "<repo>\\data\\expert-profile.bin",
  "--expert-cache", "auto",
  "--prefill", "auto",
  "--spec", "4",
  "--spec-min-p", "0.5",
  "--mtp", "<data-dir>\\mtp\\rt",
  "--max-context", "131072",
  "--kv", "k8v4",
  "--kv-resident", "20480",
  "--conversation-cache-mib", "4096",
  "--conversation-cache-slots", "4"
 ]
}
```

展开成一行（可直接照抄，把 `<data-dir>` / `<repo>` 换掉即可）：

```bat
strata.exe --pack <data-dir>\packs\iq2_xs --native <data-dir>\models\IQ2_XS\Qwen3.8-Flash-Next-GSQ-RCO-IQ2_XS-00001-of-00002.gguf --ple-gguf <data-dir>\models\IQ2_XS\Qwen3.8-Flash-Next-GSQ-RCO-IQ2_XS-00002-of-00002.gguf --expert-profile <repo>\data\expert-profile.bin --expert-cache auto --prefill auto --spec 4 --spec-min-p 0.5 --mtp <data-dir>\mtp\rt --max-context 131072 --kv k8v4 --kv-resident 20480 --conversation-cache-mib 4096 --conversation-cache-slots 4
```

**各 arm 的差异只有三项**（`--max-context` / `--kv` / `--kv-resident`），其余全部一字不差：

| Arm (block) | `--max-context` | `--kv` | `--kv-resident` | `--prefill` | env | 备注 |
| --- | ---: | --- | ---: | --- | --- | --- |
| A (01-A / 1-A) | 32768 | int8 | —（KV 全在显存） | auto | 无 | setup 默认档 |
| B (02-B, 05-B, 08-B / 2-B, 5-B, 10-B) | 131072 | k8v4 | 32768 | auto | 无 | setup 写出来的 128K 档 |
| **C (03-C, 06-C, 07-C, 12-C / 3-C, 6-C, 9-C)** | **131072** | **k8v4** | **20480** | auto | 无 | **手改一行**，就是 464.6 tok/s 那档 |
| D (04-D / 4-D) | 131072 | int8 | 32768 | auto | 无 | setup 的 KV-streaming 分支 |
| B-share-off (09-B-share-off) | 131072 | k8v4 | 32768 | auto | `STRATA_PREFILL_CPU_SHARE=0` | 只存在于 0.2.0-beta 报告 |
| E1 (7-E1) | 131072 | k8v4 | 20480 | **768**（写死） | 无 | 只存在于 0.1.40.3 报告 |
| E2 (8-E2) | 131072 | k8v4 | 20480 | **768**（写死） | `STRATA_PREFILL_STREAM_MIN=512` | 只存在于 0.1.40.3 报告 |

**E2 的 config 全文**（唯一带 env 的那份）：

```json
{
 "args": [
  "--pack", "<data-dir>\\packs\\iq2_xs",
  "--native", "<data-dir>\\models\\IQ2_XS\\Qwen3.8-Flash-Next-GSQ-RCO-IQ2_XS-00001-of-00002.gguf",
  "--ple-gguf", "<data-dir>\\models\\IQ2_XS\\Qwen3.8-Flash-Next-GSQ-RCO-IQ2_XS-00002-of-00002.gguf",
  "--expert-profile", "<repo>\\data\\expert-profile.bin",
  "--expert-cache", "auto",
  "--prefill", "768",
  "--spec", "4",
  "--spec-min-p", "0.5",
  "--mtp", "<data-dir>\\mtp\\rt",
  "--max-context", "131072",
  "--kv", "k8v4",
  "--kv-resident", "20480",
  "--conversation-cache-mib", "4096",
  "--conversation-cache-slots", "4"
 ],
 "env": { "STRATA_PREFILL_STREAM_MIN": "512" }
}
```

**B-share-off 的 env 段**：

```json
"env": { "STRATA_PREFILL_CPU_SHARE": "0" }
```

### 1.5 关于 `--expert-cache` / `--expert-slots`

- PR 里 **`--expert-cache` 永远是 `auto`**（5 份 arm config 全一样），没有任何一处调过容量数值。
- **`--expert-slots` 在整个 PR（含 832 KB diff）里出现 0 次** —— 这个参数在该版本不存在/未被使用。想要更多 slot 只能靠「少占显存」间接得到（`--kv-resident` 调小 → VRAM free 变大 → slots 变多）。
- 实测得到的 slot 数：A 1,023 / B 968 / C 1,051 / D 902（0.2.0-beta）；A 1,040 / B 985 / C 1,067 / D 918 / E1、E2 1,067（0.1.40.3）。
- 会话缓存 `--conversation-cache-mib 4096 --conversation-cache-slots 4` **不是 setup 默认**，是作者手工加在每一份 config 里的。

### 1.6 测量脚本命令行（逐字）

```bat
:: 128K 吞吐（主测）
python bench/results/2026-09-30-community-rtx-5090/benchmark.py --root <repo> --pack <data-dir>\packs\iq2_xs --url http://127.0.0.1:8080 --targets 4096,16384 --runs 5
:: block 6 额外跑：32768 x 5 和 128000 x 3

:: 开跑前的 harness 自检
benchmark.py --targets 1024 --runs 1

:: needle（6 次）
python tools/needle_bench.py --url http://127.0.0.1:8080 --lengths 32k,128k --depths 10,50,90 --out needles.json

:: 13 题任务检查（0.2.0-beta 在 C 上跑）
quality/strata_eval.py        :: 产出 quality/task-check-C.json
quality/check_results.py      :: 打分 -> quality/task-check-C.scored.txt
```

harness 的关键设定（决定这些数字的含义）：每个请求**开头塞一个 nonce**、用 Strata 自己的 tokenizer 定长、greedy、`reasoning_effort "none"`、上限 256 token、streaming、每次调用前一次短 warm-up（不计）。

> **这一点极其重要**：nonce 在开头 ⇒ 前缀复用被主动破坏 ⇒ 所有 measured 请求 `reused = 0` ⇒ 表里的 275.6 s TTFT 是**冷 prefill 的最坏情况**。

### 1.7 引擎启动时打印的 plan（判断配方是否生效的指纹）

```text
strata generate: KV streaming: 20480 of 131072 cells per QSA layer in VRAM, the K/V in 1.20 GiB of pinned RAM
strata generate: expert arena: cudaHostRegister PORTABLE ok; large pages refused for 35456548864 B (... VirtualAlloc error 1314); using 4 KB pages
strata generate: loaded 33.02 GiB at 2.97 GiB/s
strata generate: 11 pool workers on logical processors 2,4,6,8,10,12,14,16,18,20,22, the host thread on 0 (draining too) (--host-core first)
strata generate: expert cache auto: 2.25 GiB free, 700 MiB reserved (+143 MiB for the draft head) -> 1014 slots
strata generate: expert cache 1051 slots, 1.43 GiB of VRAM; policy is
prefill: the CPU share is ON by default for prompt chunks below 1024 tokens (... mean KL ~0.004). STRATA_PREFILL_CPU_SHARE=0 turns it off.
strata serve: prompt chunk auto: 1024 tokens, a 384-slot ring
strata serve: the prompt path borrows 900 CUDA0 cache slots (1.22 GiB)
strata serve: 337 MiB of VRAM free with everything loaded
strata serve: that is little room for the verify windows' buffers under WDDM; if the engine exits right after this line, --prefill auto:8192 (a smaller prompt chunk borrows fewer cache slots) or a larger --vram-reserve-mib leaves more
```

---

## 2. 8 GB 及以下实测总表

**该 PR 只覆盖一块卡**：NVIDIA GeForce RTX 3070 Ti，8,192 MiB，CC 8.6，PCIe 4.0 x16，290 W，**同时驱动桌面**（驱动 617.42）。CPU Ryzen 9 5900X（12C/24T，Zen 3，无 AVX-512），RAM 63.9 GiB（4×16 GB DDR4-3600，双通道），Samsung 970 EVO Plus 2 TB NVMe，Win11 Pro build 26200，系统托管页面文件，**大页未获批**（`VirtualAlloc error 1314` → 4 KB 页）。

模型：`ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-GGUF` rev `ed59f92082b1e93c0e96d60a8b11aab089b52f09`，IQ2_XS 两个分片 39,225,954,592 B + 28,800,138,432 B。

### 2.1 v0.2.0-beta（tag `3d1fb48`，release engine **0.1.45.3**，BUILD commit `f6d65cb584c0`）

| Arm | 上下文 | KV | kv-resident | prefill tok/s @4K / @16K | decode tok/s @4K / @16K | TTFT s @4K / @16K | 显存峰值 | 质量判定 |
| --- | ---: | --- | ---: | --- | --- | --- | --- | --- |
| A | 32,768 | int8 | — | 542.8 / 586.0 | 49.3 / 48.2 | 7.6 / 28.0 | load 7,440 · 跑后 7,557 | needle 未跑；13 题任务检查在 0.1.40.3 的 32K 默认档上过 |
| B | 131,072 | k8v4 | 32,768 | 485.9 / 498.8 | 46.8 / 47.8 | 8.5 / 32.9 | load 7,349–7,394 · 跑后 7,475–7,519 | 同上（needle 只在 C 上做） |
| **C** | **131,072** | **k8v4** | **20,480** | **498.9 / 493.6** | **49.8 / 49.7** | **8.2 / 33.2** | **load 7,346–7,390 · 跑后 7,501–7,528** | **needle 6/6 · 13 题全过** |
| D | 131,072 | int8 | 32,768 | 438.6 / 432.5 | 52.1 / 48.5 | 9.4 / 37.9 | load 7,359 · 跑后 7,483 | 未单独做质量 |
| C @32,768 | 131,072 | k8v4 | 20,480 | 484.2 | 47.3 | 67.7（total 73.1） | 同上 | — |
| **C @128,000** | **131,072** | **k8v4** | **20,480** | **464.6** [463.7–466.7] | **51.0** [50.4–51.2] | **275.6**（total 280.6） | **7,519（全程峰值 7,557 / 8,192 = 92.2%）** | **needle 6/6（32,045–32,046 与 124,125–124,127 token）· 13 题：15/15 表达式、4/4 拒错、JSON schema、四行七字诗、get_weather、24/7、逻辑题=1、needle 精确、lo = mid + 1** |
| B-share-off（session 2） | 131,072 | k8v4 | 32,768 | 424.7 / 442.8 | 68.7 / 68.1 | 9.7 / 37.0 | load 7,388 · 跑后 7,514 | 未单独做质量（session 2，显示器灭） |

### 2.2 0.1.40.3（tree `d5ea713374`，release engine 0.1.40.3）

| Arm | 上下文 | KV | kv-resident | prefill tok/s @4K / @16K | decode tok/s @4K / @16K | TTFT s @4K / @16K | 显存峰值 | 质量判定 |
| --- | ---: | --- | ---: | --- | --- | --- | --- | --- |
| A | 32,768 | int8 | — | 549.8 / 645.9 | 47.0 / 45.9 | 7.5 / 25.4 | load 7,339–7,508 · 跑后 7,603 | 13 题任务检查（32K 默认档）全过 |
| B | 131,072 | k8v4 | 32,768 | 363.7 / 380.1 | 45.9 / 46.9 | 11.3 / 43.2 | 同上区间 | — |
| **C** | **131,072** | **k8v4** | **20,480** | **508.0 / 537.4** | **47.5 / 47.1** | **8.1 / 30.6** | **跑后 7,603 / 8,192** | **needle 6/6 · 13 题全过** |
| D | 131,072 | int8 | 32,768 | 304.0 / 302.0 | 47.1 / 44.7 | 13.5 / 54.3 | — | — |
| E1 | 131,072 | k8v4 | 20,480（`--prefill 768`） | 380.7 / 397.3 | 48.1 / 51.1 | 10.8 / 41.3 | — | — |
| E2 | 131,072 | k8v4 | 20,480（768 + `STREAM_MIN=512`） | 404.5 / 436.7 | 49.8 / 51.7 | 10.2 / 37.6 | — | — |
| C @32,768 | 131,072 | k8v4 | 20,480 | 534.3 | 47.2 | 61.4（total 66.8） | — | — |
| **C @128,000** | **131,072** | **k8v4** | **20,480** | **520.8** [520.7–522.7] | **43.6** [43.3–46.3] | **246.0**（total 251.6） | **7,603 / 8,192** | **needle 6/6（32,895–32,896 与 125,868–125,870）** |

> 表注：
> - 「显存峰值」= 作者每 block 结束时的 `nvidia-smi` **快照**，不是采样峰值（README 明说 "snapshots, not peaks"）。0.2.0-beta 全程最大值 **7,557 MiB**；0.1.40.3 最大值 **7,603 MiB**。
> - 0.2.0-beta 的 A/B/C 数字来自 session 1（**显示器亮着**）；session 2（推断显示器灭）同一 arm 快 18.7–20.8%（prefill）/ 38.1–48.1%（decode）。**跨 session 不可直接比**。
> - 每个数据点 5 次（128,000 那档 3 次）的中位数，方括号是范围。每个请求固定生成 256 token，`finish_reason "length"`，`reused = 0`。

---

## 3. 显存/内存账本（为什么 8 GB 刚好够）

### 3.1 引擎自己算的账（每个 block 启动时打印，0.2.0-beta）

| Arm | 留给专家缓存的 VRAM | 专家缓存容量 | prompt chunk | 打印的 ring | 借给 prompt 路径的 slot | load 后剩余 VRAM | 放 pinned RAM 的 KV |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| A | 2.21 GiB | 1,023（1.39 GiB） | 1,280 | 351 | 873（1.18 GiB） | 334 MiB | —（全在显存） |
| B | 2.14 GiB | 968（1.31 GiB） | **768** | **8** | 458（0.62 GiB） | 337–408 MiB | 1.20 GiB |
| **C** | **2.25 GiB** | **1,051（1.43 GiB）** | **1,024** | **384** | **900（1.22 GiB）** | **337–408 MiB** | **1.20 GiB** |
| D | 2.05 GiB | 902（1.22 GiB） | 512 | 8 | 398（0.54 GiB） | 337 MiB | 1.55 GiB |

（0.1.40.3 的同一张表：A 2.24 GiB / 1,040 / 1,280 / 351 / 873 / 432 MiB；B 2.16 / 985 / 768 / 8 / 432 / 424–479 / 1.20 GiB；C 2.27 / 1,067 / 1,024 / 384 / 900 / 429–481 / 1.20 GiB；D 2.07 / 918 / 512 / 8 / 372 / 481 / 1.55 GiB。）

### 3.2 内存侧

- `strata.exe` 常驻集：**35.0–36.7 GiB**（load 后），跑完最高 **39.57 GiB**。
- 可用物理内存：load 后 14.2–14.8 GiB，**最低 11.5 GiB**（128K 跑完之后）。
- 专家 arena：**35,456,548,864 B = 33.02 GiB**，`cudaHostRegister PORTABLE ok`，以 **2.97 GiB/s** 载入（≈11 s，从 NVMe 读）。
- KV pinned：1.20 GiB（C/B 的 k8v4），D（int8）1.55 GiB。

### 3.3 算术验证 TTFT

- 0.2.0-beta C @128K：128,000 ÷ 464.6 = **275.5 s**，实测 TTFT **275.6 s** ⇒ **TTFT ≈ 整个 prefill，几乎没有额外开销**；decode 256 ÷ 51.0 = 5.0 s，total 280.6 s ✓
- 0.1.40.3 C @128K：128,000 ÷ 520.8 = 245.8 s，实测 246.0 s ✓；decode 256 ÷ 43.6 = 5.9 s，total 251.6 s ✓

---

## 4. 限制条件（作者 + 维护者原话）

### 4.1 硬件门槛

- **内存**：setup 对 8 GB 卡直接警告 *"[!] less than 12 GB of VRAM: Strata will run, but most experts stay on the CPU and it will be slow"*。实测常驻 35–36.7 GiB、峰值 39.6 GiB ⇒ **64 GB 是硬门槛**，32 GB 机器放不下 33 GiB 的专家 arena。
- **NVMe**：作者**没有把它写成要求**，但 arena 以 2.97 GiB/s 载入、仓库+模型 68 GB 全在 NVMe 上；SATA SSD 会把启动拖到分钟级（**此条为推断，非作者原话**）。
- **大页**：**未获批**（`VirtualAlloc error 1314`），全程 4 KB 页也能跑 —— 说明大页是加分项不是必需。
- **CPU**：11 个 expert-pool worker + 1 个 host thread 绑在物理核 2,4,…,22 上；prefill CPU share 正是靠这 11 个 worker。
- **显示器共用 GPU**：作者明确列为 limitation —— "The display shares the GPU, so the VRAM left for the expert cache depends on the desktop; a PC without a display on the card would plan differently."

### 4.2 为什么 TTFT 是 275 s

- 不是「首 token 慢」，而是 **128,000 token 的 prefill 本身就要 4 分半**：464.6 tok/s × 275.6 s ≈ 128K。
- 而且 **harness 在每次请求开头塞 nonce**，`reused` 恒为 0 ⇒ 这 275 s 是**每次都从零 prefill 一次 128K** 的价格。
- prefill 速率随长度几乎不掉（C 的 4K→128K：500.6 → 491.2 → 484.2 → 464.6 tok/s，仅 −7%），所以慢的原因是「量」，不是「长上下文退化」。

### 4.3 能不能反复问

- **同一份 128K 文档连续追问**：靠 `--conversation-cache-mib 4096 --conversation-cache-slots 4` + 前缀复用，理论上不必每次 275 s。作者只在 **~4.7K token 的对话**上验证过：第二轮只读 24 / 30 个新 token，**4,621 / 4,835 token 被复用**，耗时 **0.6 s / 1.4 s**，对比首轮 10.2 s / 11.1 s（"One run; it shows the feature working, not a measured speedup"）。
- **128K 下的间接证据**：needle 三次 128K 查询耗时 268.3 → 236.2 → 219.3 s（同一 haystack），作者认为 "suggest prefix reuse between depths"。
- **但 128K 的 KV 只有 20,480 / 131,072 个 cell 在显存**，其余 1.20 GiB 在 pinned RAM 里随取随用 ⇒ 长前缀复用的带宽来源是 DDR4-3600 双通道（理论 57.6 GB/s），**128K 前缀复用从未被单独测量**。
- **结论**：冷读一次 128K ≈ 4.6 分钟；同一会话内追问才便宜。**换一份新文档 = 再付一次 4.6 分钟。**

### 4.4 稳定性坑

- 每次启动都打印 *"that is little room for the verify windows' buffers under WDDM; if the engine exits right after this line, `--prefill auto:8192` … or a larger `--vram-reserve-mib` leaves more"* —— 8 GB + 桌面共用时随时可能起不来。
- 0.2.0-beta 里 **98 个请求中 28 个被标记为受干扰**（27 个是 GPU 的 SW thermal slowdown 0x20 / 0x24，温度 72–84 °C，needle 时到 85 °C；1 个是别的进程吃了 2.33 核）。
- `setup.py` 对 `--kv k8v4` 仍打印 `KV cache: 4-bit (Hadamard-rotated)`（标签 bug，config 里确实是 k8v4）。

---

## 5. PR 状态 / 版本 / 后续

| 项 | 事实 |
| --- | --- |
| 是否合并 | **没有。从未 merge**（页面 `merged` 出现 0 次；`main` 上 `bench/results/2026-10-19-…` 与 `2026-10-07-…` 两个目录都是 **HTTP 404**） |
| 最终状态 | **Closed**（第 2 次关闭），2026-10-29，by Niko1221 |
| 时间线 | 2026-10-07/08 开 PR（3 commits，engine 0.1.40.3）→ **2026-10-19 closed**（0.2.0-beta tracker 重置，原话 "Closed here does not mean rejected"）→ 10-19 18:49 追加 3 commits（merge main、0.2.0-beta 重测、README 修正）→ 10-21 作者 `/reopen`，github-actions 机器人重开 → **10-29 再次 closed** |
| 对应版本 | 数字对应 **v0.2.0-beta**（tag `3d1fb48`，CMakeLists 0.1.45.3，release engine **0.1.45.3**，BUILD commit `f6d65cb584c0`）；早期数字对应 **0.1.40.3**（tree `d5ea713374`） |
| 代码改动 | **零**（"A results-only PR: measurements, no code"）⇒ 不会产生版本号变化 |
| 6 个 commit | `1e94e23`(初版报告)、`d154332`(per-block configs)、`27b6c65`(补充检查)、`4ae193f`(merge main)、`56e6ae5`(0.2.0-beta 重测)、`4698a5f`(README：把推断写成推断、补启动命令) |
| 维护者 10-29 原话 | "The 8 to 9 percent slower 16K prompt reading you measured on 0.2.0-beta compared with 0.1.40.3 is on our list for the next update. We are building a Strata website with a page for community benchmarks, and results like these will be added there when it launches, so we are closing this pull request here; the numbers are not lost." |
| 后续修正 | ① 10-19 的重测**撤回了** 0.1.40.3 报告里「10 GB 以下卡建议选更小窗口」的建议（CPU share 把差距抹平了）；② 维护者承认 **16K prompt 比 0.1.40.3 慢 8–9%** 是回归，进了下个版本清单；③ 报告将迁到 Strata 官网的 community benchmarks 页 |

---

## 6. 复现风险清单

1. **`--kv-resident 20480` 只在 0.1.40.3 上划算**。0.2.0-beta 起 CPU prefill share 默认开，20,480 与 32,768 差 −2.8%…+2.7%（噪声级）。**新版本直接用 setup 默认 32,768 即可**。
2. **显示器状态值 20%**。同一 arm，session 1（亮）vs session 2（灭）：prefill +18.7~20.8%，decode +38.1~48.1%。跨 session 对比不可信；复现必须在**同一 session 内**做 A/B。
3. **温度/功耗墙**。28/98 请求被 throttle 标记，72–84 °C；290 W 默认功耗墙，未锁频。
4. **`--expert-cache auto` 不要在 8 GB 上手填数值**：VRAM free 只有 2.05–2.25 GiB，填大了引擎会抢 verify window 的 buffer。
5. **引擎版本错位**：报告用的是 release 资产（`f6d65cb584c0` 编译），**不是** `3d1fb48` 源码自编译 —— 作者自己标注 "assumed, not checked"。
6. **`--prefill auto` 的隐式陷阱**：chunk < 1,024 就掉进 8-slot staging 慢路径（B/D）。启动日志看 `prompt chunk auto: N tokens, a M-slot ring`：**ring 只有 8 就是掉坑了**。

---

## 7. 附录

### 7.1 抓取到的原始文件（本地副本 `C:/Project/local_model/raw/`）

| 文件 | 大小 | 内容 |
| --- | ---: | --- |
| `pr1496.html` | 341,144 B | PR 渲染页（comments/timeline 可读，表格被懒加载） |
| `pr1496.diff` | 832,534 B | 全部 diff（57 个文件） |
| `files/README-1019.md` | 21,590 B | 0.2.0-beta 报告正文（本报告数值主要来源） |
| `files/README-1007.md` | 22,100 B | 0.1.40.3 报告正文 |
| `files/1019/engine-start.txt` | 19,550 B | 每个 block 的 plan 行 + 内存快照 |
| `files/1019/arms/{A,B,C,D,B-share-off}.json` | 各 ~600 B | 引擎 argv 原文 |
| `files/1019/system.txt` | 4,852 B | 硬件探针、BUILD.json、setup 摘录 |
| `files/1019/needles.json` | 1,011 B | 6 次 needle 逐条记录 |
| `files/1019/summary.json` | 10,150 B | 每 block 中位数/范围 |
| `files/1007/configs/*.json` | 10 份 | 0.1.40.3 的 A/B/C/D/E1/E2 配置 |

### 7.2 关键源码行（作者引用）

- `src/prefill/prefill.cpp` **lines 194-198**（本 tree）：CPU share 自 0.1.41 起在「单 GPU、无 batch slot 的 CUDA 构建」中**默认开启**；line 185 是 0.1.40.2 的 opt-in 开关。
- `ring_slots()` 对任何小于 `stream_all_min()`（默认 1,024，可由 `STRATA_PREFILL_STREAM_MIN` 改）的 chunk 返回 `STAGE = 8`；只有 ≥ 该阈值且 ring > STAGE 时才走 `stream_all`（line 1990）。
- `STRATA_PREFILL_CPU_SHARE` 不设 = `auto`，配 `STRATA_PREFILL_CPU_SHARE_MAX=1024`；设 0 = 退回 0.1.40.3 行为。

### 7.3 参照（非本 PR，别混用）

`docs/COMMUNITY_BENCHMARKS.md`（main 分支）里同期的**双卡** 8 GB 条目：`bench/results/2026-10-07-community-2x-rtx-4000/`（2× Quadro RTX 4000 8 GB = 16 GB 总显存，64 GB RAM，131,072 上下文，IQ2_XS）：73,000–74,600 token 提示 126.3–249.2 tok/s，decode 18.1–23.2 tok/s，专家缓存命中 48–53%。**这是 16 GB 总量，不属于「单卡 8 GB」档，仅作对照。**

原始链接：
- PR: https://github.com/Niko1221/Strata/pull/1496
- 0.2.0-beta 报告: https://github.com/gbwzzy218/Strata/blob/bench-rtx3070ti-8gb/bench/results/2026-10-19-community-rtx3070ti-8gb-0.2.0-beta/README.md
- 0.1.40.3 报告: https://github.com/gbwzzy218/Strata/blob/bench-rtx3070ti-8gb/bench/results/2026-10-07-community-rtx3070ti-8gb/README.md
