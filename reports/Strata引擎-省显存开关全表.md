# Strata 引擎「省显存 / 多吃内存 / 换页」开关全表

- 主机：Windows 11，C:/Project/local_model
- 引擎：C:/Project/local_model/strata/components/engine/0.1.54-windows-x86_64-cuda-cuda13/strata.exe（272,742,400 B，sha256 107ef7fa…，build 8c1aea4bca1b+cuda13.0，CUDA 13.0，sm_75/86/89/120）
- help 全文：C:/Project/local_model/tmp/stratahelp/help.txt（272 行，已全文读完）
- **注意**：serve-help.txt 与 help.txt 的 md5 完全相同（ca1e784f3a3361b842ca4d25f2e18e8f），当初导出的其实是同一份文本；0.1.54 的 generate help 已包含全部 --serve 开关，所以本文以它为唯一 help 基准，没有第二份 serve 专享 help 可对。
- 全程只读：没有启动/停止任何引擎，没改 C:/Project/local_model 下任何配置与脚本。
- 证据等级：【H】= help.txt 原文；【B】= strata.exe 二进制内字符串（grep -a -o）；【D】= 官方仓库 docs（带 URL）；【S】= 本机 Terminal python 源码；【推测】= 按机制推断、无实测数字。

---

## 0. 一句话结论

Strata 的省显存不是单个开关，而是**四层可叠加的置换**，按“省下来的 VRAM 给谁”排序：

1. **专家权重层（省得最多，23–50 GB 量级）**：`--mmap-experts`（映射文件，靠 OS 页缓存）→ `--resident-cpu-experts` / `--resident-budget-gib N`（把 GPU 装不下的专家钉进内存）→ `--resident-experts`（= 前两者 + 页锁定 + 4 GiB 余量，setup 的“低内存模式”）。
2. **KV / 上下文层（省几 GB 到十几 GB）**：`--kv-resident N`（整条 K/V 搬到 pinned RAM，每层只留 N 格在 VRAM）、`--kv-grow`（按实际触达增长，剩下的让专家缓存接管），再加 `--kv int8|k8v4|q4_0` 降精度。
3. **显存预算层（不改驻留位置，但决定“留下多少给权重”）**：`--expert-cache N|auto`、`--expert-cache-per-layer`、`--peer-device N`、`--vram-elastic` + `--vram-segment-mib`、`--trim-stage-weights`、`--no-pool`。
4. **只吃内存/磁盘、并不省显存的**（任务清单里混进来的）：`--memory-limit-mib`、`--conversation-cache-mib`、`--prompt-cache`、`--session-min-free-mib`（**这个是磁盘，不是内存**，见 §4）。

> 本机硬约束（原文抄自二进制，不是猜）：`--resident-cpu-experts requires --mmap-experts and a static --expert-profile`；`--shared-expert-arena backs the resident arena and cannot be used with --mmap-experts`；`--kv-grow is off (one GPU, a profile, the whole K/V in VRAM, every expert in RAM, no --batch, --vram-elastic or --peer-device)`。

---

## 1. 专家权重：让 23–50 GB 的专家不进 VRAM

| 开关 | 默认 | help 原文（0.1.54，逐字） | 相互作用 | 推测 / 实测代价 | 证据 |
|---|---|---|---|---|---|
| `--mmap-experts` | 关（默认是 resident arena：整块读进内存 + cudaHostRegister 页锁定） | “R2.1: opt OUT of the resident expert arena, back to MapViewOfFile. The A/B arm: the mmap's rate depends on the OS page cache holding 34 GB, and measured 71.97 vs 34.78 ms/token cold vs warm.” | 与 `--shared-expert-arena` 互斥【B】；`--resident-experts` / `--resident-cpu-experts` / `--resident-budget-gib` 都**要求**它先开 | 冷/热差 2.07×（71.97 vs 34.78 ms/token），瓶颈是 SSD 随机读；同时把常驻内存从 23–50 GB 降到 0，压力转给页缓存 | 【H】253-255 |
| `--resident-cpu-experts` | 关 | “with mmap and a static profile, keep the experts the GPU cache does not hold resident in ordinary RAM (and the prompt path's lend region as far as RAM allows); adaptive swaps exchange them, so none is read from the file again.” | **必须** `--mmap-experts` + 静态 `--expert-profile`【B】；`--adapt-async` 时 swap 在窗口之间跑 | 稳态 0 次磁盘读（日志 resident RAM: ... blob reads from the file，稳态为 0【D】）；代价 = RAM 多占“全部非 GPU 专家”的体积 | 【H】259-261；【B】 |
| `--resident-experts` | 关（setup 在低内存机器上自动开） | “the low-RAM PC's resident mode (setup): --mmap-experts --resident-cpu-experts with the copy page-locked when possible, 4 GiB headroom, plain mmap if it does not fit. Same answers as --mmap-experts for the same placement.” | = 前两条的封装；页锁定后 GPU 还能分摊 PCIe miss（`--pcie-frac`；`STRATA_RESIDENT_PIN=0` 或 `--pcie-frac 0` 回到与纯 mmap **逐位相同**的输出【D】） | 装不下时静默降级：WARNING: the resident RAM mode does not fit (%s); ... read from the model folder through the OS file cache【B】。位精确性靠 `--pcie-frac 0` | 【H】262-264；【D】 |
| `--resident-budget-gib N` | help 未收录，二进制有（`strata generate: --resident-budget-gib needs N > 0`） | 官方 docs：The N GiB of experts the GPU does not hold that the profile ranks hottest are copied into RAM; the rest are read from the files. Implies --mmap-experts and leaves 4 GiB of headroom. On Windows the available commit limit also caps N, and a clamped budget is reported. | 隐含打开 `--mmap-experts`；与 `--conversation-cache-mib` 抢 RAM（docs 明说 park 卡顿的解药是“更小的 --resident-budget-gib”）；一旦给它，`STRATA_UNBUFFERED_LOAD` 才有意义【B】 | **唯一能“部分驻留”的旋钮**，介于 mmap 与全 resident 之间。超预算日志：WARNING: the RAM budget (--resident-budget-gib) cannot be kept (%s)【B】 | 【D】DETAILS.md#low-ram-modes；【B】 |
| `--shared-expert-arena FILE` | 关 | “Linux: back the resident arena with one MAP_SHARED file. Put this file on /dev/shm, not ordinary SSD storage. A small header binds an existing backing file to the same pack.” | 与 `--mmap-experts` 互斥【B】 | **Windows 构建用不上**（help 明写 Linux，/dev/shm 是 Linux 概念），本机不必考虑 | 【H】256-258 |
| `--expert-profile P` / `--expert-profile-save P` | 关（按首次使用自适应填充） | “R4.2e: pre-load the VRAM tier from a profile.bin (see tools/make_profile.py) instead of admitting on first use.” / “--serve, #477: save what the adaptive tier learned ... on QUIT and every --expert-profile-save-every MIN minutes (default 10; 0 = on QUIT only)” | `--resident-cpu-experts` 与 `--kv-grow` **都要求**它；`--expert-cache-per-layer` 配它才吃满收益（help 里 4096 槽 54.4% 命中的就是这套） | 本身不省显存，但它是省显存方案不抖的前置件：没有 profile 的 mmap 冷启动命中≈0 | 【H】181-186 |

### 1.1 一个容易踩的坑：`--expert-cache` 的默认值

- help 原文：**DEFAULT 0**【H】192-195。
- 官方 docs：**`--expert-cache auto`（the default）checks again once the slots are written and shrinks if they do not fit**【D】380-381。
- 二进制确有 auto 分支：strata generate: expert cache auto: %.2f GiB free, %d MiB reserved ... -> %d slots【B】。
- **判断**：裸引擎默认 0 槽（专家不进 VRAM）；`auto` 是 Terminal/setup 写进 config 的值。**说“默认值”必须讲清是哪一层**，否则结论正好相反。这是本次唯一发现的 help 与 docs 口径不同的点。

---

## 2. KV / 上下文：把 K/V 挪出 VRAM

| 开关 | 默认 | help 原文 | 相互作用 | 代价 | 证据 |
|---|---|---|---|---|---|
| `--kv-resident N` | **0 = 全部在 VRAM** | “KV streaming: keep N cells of each QSA layer in VRAM (min 20480) and the whole K/V in pinned RAM; the freed VRAM goes to expert slots. 0 (default): all of it in VRAM. A context of N cells or fewer is not streamed” | 启动行回显 KV streaming: %lld of %lld cells per QSA layer in VRAM, the K/V in %.2f GiB of pinned RAM【B】；WSL 下驱动只能钉 ~1 GB，等于关【D】 | **13.7 KB/上下文 token**（int8；k8v4 10.6 KB；q4_0 7.5 KB）→ 128K ≈ 1.7 GB 内存；公式 ctx × 13 × cell_bytes（12 个 QSA 层 + draft 层）【S】setup.py:5962-5965 | 【H】26-28 |
| `--kv-grow`（`STRATA_KV_GROW=1/0`） | 关（启动即按 `--max-context` 全量分配） | “the K/V takes VRAM only for the cells the requests reach and the expert cache holds the rest, giving slots back as the context grows (one GPU, with --expert-profile; STRATA_KV_GROW=1/0 also). Default: the whole --max-context allocated at start” | **前置条件极硬**：单卡 + `--expert-profile` + 整条 K/V 在 VRAM + 全部专家在 RAM，且**不能**有 `--batch` / `--vram-elastic` / `--peer-device`；不满足就打一行 --kv-grow is off (...) 然后不用它【B】 | 实测（Radeon AI PRO R9700，Q2_0，196608 ctx）：槽位 6,213 → 7,968，decode 96.3 → 98.5 tok/s（×1.023，5/5）【D】1347 行。≤24 GB 卡 + 128K 以上才划算 | 【H】29-32；【D】218 |
| `--kv int8` / `k8v4` / `q4_0` | int8（docs 口径；help 写 default fp16 until gate G-C accepts int8，是版本口径差） | int8: half the VRAM；q4_0: half of int8's memory；k8v4: 816 B/cell (vs int8's 1,056) | k8v4 可与 `--kv-resident` 同用（streams with --kv-resident too） | q4_0：128K 快 ~4% 但 PPL +8–12%；k8v4：比 int8 省 23% KV，prompt 慢 2–5%【D】215-216 | 【H】20-25 |
| `--ple-io direct\|mmap\|ram` + `--ple-row-cache N` | direct（表**从不进** RAM / 页缓存） | “n-gram table reads (plan v0.3 P2). direct (default): unbuffered SSD reads, the table never enters RAM or the file cache; mmap: A/B arm; ram: the whole table locked in RAM at start (VirtualLock on Windows, mlock elsewhere)” | `STRATA_PLE_AUTO_RAM` / `STRATA_PLE_AUTO_MMAP` 会让引擎自选（日志 --ple-io ram chosen by the residency policy (the table is %.1f GiB ...）【B】 | 反向开关：默认省内存不占显存；ram 模式用 GB 级内存换掉 prompt 路径上的 SSD 读 | 【H】12-17 |

---

## 3. 显存预算层：不换位置，但决定“能剩多少给权重”

| 开关 | 默认 | help 原文 | 相互作用 | 代价 | 证据 |
|---|---|---|---|---|---|
| `--expert-cache N` / `auto` | 0（裸引擎）/ auto（Terminal 写） | “R4: keep N expert blobs resident in VRAM and compute their rows on the GPU via moe_hit_grouped_s2. DEFAULT 0. Measured at 4096 slots with --expert-cache-per-layer: 54.4% hits, CPU pool drain 19.1 -> 10.3 ms/token, -2.7 ms/token end to end.” | N = N × 最大专家 blob【D】；**Windows 下超配不报错**——驱动把超出的分页到系统内存，启动正常、速度崩【D】382-383；`auto` 写完槽位后再量一次并缩 | 这是**反向**旋钮：加大 = 多占 VRAM。省显存要调小/关掉，或抬 `--vram-reserve-mib` | 【H】192-195；【D】378-393 |
| `--expert-cache-per-layer` | 关 | “R4.2g: give each layer its OWN slots ... The default policy fills in arrival order from one shared counter, so 256 slots went to ~26 layers of position 0 and measured 2.97%. Per-layer, the same routing gives 21.4% at 8 slots/layer and 70.4% at 64.” | 同一 VRAM 预算下命中率 2.97% → 21.4%（8 槽/层） | 免费：不改显存占用，只改分配策略。**同预算下省显存性价比最高的一条** | 【H】210-215 |
| `--vram-elastic` + `--vram-segment-mib N` | elastic 关；segment **512**（下限 64） | “--serve (#533, opt-in, NVIDIA): the expert cache in segments (--vram-segment-mib, default 512), so the command VRAM <reserve_mib> (the server's POST /v1/vram) can give VRAM back to other programs between requests and take it back later” | 关闭条件写在二进制里：非 `--serve`、层切分（a layer split has a cache per GPU）、其它卡上的 helper cache、段 < 64 MiB、HIP【B】【D】。与 `--kv-grow` 互斥（kv-grow 一开它就 off）【D】218 | **只动专家缓存**，dense 权重 / KV / MTP head / CUDA context / prompt buffer 都不动【D】。让出的段里的专家转 CPU 算 → 答案不变、速度下降。必须显式 POST /v1/vram {"reserve_mib":N}，**不会自己缩**【D】 | 【H】100-102；【D】VRAM_ELASTIC.md |
| `--trim-stage-weights` | 关 | “an explicit --layer-split: each GPU loads only its own layers' dense weights” | 只在 `--layer-split` 下有意义；与 `--batch N --batch-groups G` 是多卡并发标准配方【D】MULTI_GPU.md:235 | 直接砍掉每卡上“别人的层”的 dense 权重副本（多卡各几 GB），零精度代价 | 【H】114 |
| `--peer-device N` + `--peer-reserve-mib N` + `--peer-slots N` | 关；reserve 600 MiB | “a second GPU as an adaptive expert-cache tier (rows over P2P; it also computes its experts' prompt rows). Not with --layer-split or --expert-cache-device1..3. Default output unchanged without it.” | 与 `--kv-grow`、`--vram-elastic` 互斥 | 不是省显存，是把专家摊到第二张卡；单卡机器无关 | 【H】202-209 |
| `--no-pool` | 关（默认有 CPU 专家池） | “skip the CPU expert pool (the GPU-only floor)” | 与 `--gpu-only-full`（测 GPU 地板）同族 | 极端档：连内存里的专家池都不要，全在 GPU。**方向相反**，列此为防误开 | 【H】160 |

---

## 4. 只吃内存/磁盘、**并不**省显存的（别当省显存开关用）

| 开关 | 默认 | help 原文 | 它到底管什么 | 证据 |
|---|---|---|---|---|
| `--memory-limit-mib N`（`STRATA_MEMORY_LIMIT_MIB`） | 0 = 无限制 | “--serve: the total RAM (MiB) this engine's container or cgroup may use, when the container cannot see its real limit (also STRATA_MEMORY_LIMIT_MIB; the flag wins; 0 = none). Parking and session save/restore keep their floor under it” | **上限闸门，不是省显存**。启动行 memory guard: limit X GiB (source: flag\|cgroup\|meminfo)【D】708。实测：2×RTX 3080 20 GB、90 GiB 容器，101376 → 135 次 park 0 跳过；78000 → 8 次 park 全跳过，请求正常【D】1462 | 【H】90-92 |
| `--conversation-cache-mib N`（+`-slots`/`-min-free-mib`/`-min-tokens`/`-park-gain`） | 按空闲 RAM 自动定，上限 8192；min-free = **2560 MiB** | “--serve: RAM budget for parked conversations (default: sized from the free RAM, up to 8192; 0 = off)” | 纯 **RAM**：对话快照缓存，省的是重读 prompt 的时间。docs 公式：装完模型后剩余 RAM 的 40%，上限 8192，256 步进，<1024 则关【D】700 | 【H】86-97 |
| `--prompt-cache N` | **6** | “--serve: keep N conversation checkpoints between requests (default 6, ~118 MB of RAM each; 0 = read every prompt from the start)” | 纯 RAM：6 × 118 MB ≈ **708 MB**。0 是“逐位可复现”配方的一部分（--prompt-cache 0 --adapt-swaps 0 --pcie-frac 0）【D】330 | 【H】84-85 |
| `--session-min-free-mib N` | **4096** | “--serve: **disk space** a SAVE must leave free (default 4096; 0 = no check)” | **磁盘**。任务清单把它列进省显存是误列 —— 它与显存无关，管的是会话写盘前留多少空盘 | 【H】98 |
| `--conversation-cache-min-free-mib N` | 2560 | “--serve: RAM floor (under MemAvailable, the cgroup limits and --memory-limit-mib) when parking, saving or restoring a session” | RAM 地板（防 OOM），不是省显存 | 【H】88-89 |
| `--session-save-reclaim` | 关 | “--serve: reclaim unpinned host caches if SAVE needs RAM (opt-in)” | RAM：写盘前回收非锁定页缓存 | 【H】99 |

---

## 5. 二进制里挖出、help 一字未提的相关环境变量（本地一手）

### 5.1 内存 / 驻留

| 变量 | 语义（由二进制串反推） | 证据串 |
|---|---|---|
| `STRATA_ARENA_PIN_GIB` | 专家 arena 页锁定的 GiB 上限；Windows 默认 **29**；多卡 WDDM 硬顶 **8 GiB** | multi-GPU under WDDM: at most 8 GiB of the expert arena is pinned (STRATA_ARENA_PIN_GIB changes it) / strata generate: STRATA_ARENA_PIN_GIB=%d: %s / =0 registers it（核显 UMA） |
| `STRATA_ARENA_LOCK=0` | 关掉 arena 锁页 | large pages are resident without a lock; arena lock disabled (STRATA_ARENA_LOCK=0) |
| `STRATA_ARENA_RELEASE` | 把已进 VRAM 的那块专家交还 OS | expert arena: %.2f GiB of VRAM-held experts handed back to the OS |
| `STRATA_ARENA_RAM_WAIT_S` | 启动时等 RAM 变出来的秒数（另一个引擎正在退） | the expert arena needs %.2f GiB of RAM and %.2f GiB is available; waiting up to %.0f s (STRATA_ARENA_RAM_WAIT_S changes this) |
| `STRATA_RESIDENT_HEADROOM_GIB` | resident 模式必须留空的 RAM（**默认 4**） | 【D】keeps 4 GB of the RAM it finds free (STRATA_RESIDENT_HEADROOM_GIB) |
| `STRATA_RESIDENT_PIN=0` | 关掉 resident 副本的页锁定 → 回到与 mmap **逐位相同**的 token | 【D】--pcie-frac 0（or STRATA_RESIDENT_PIN=0）gives the mapped mode's exact tokens |
| `STRATA_RAM_ADAPT=n` | opt-in：RAM 副本也跟着对话走（每窗口最多换 4 对），n 只限需要读文件的对数 | 【D】241-246 |
| `STRATA_PIN_BY_NEED=1` / `_SKIP` | 按 profile 排名钉，而不是按前 ~30 GiB 顺序钉 | pin by need: %zu of the %zu ranked pairs taken as GPU-resident ... |
| `STRATA_PIN_RESERVE_MIB` / `_GIB` | CUDA 钉 arena 时保留的还能锁的余量（Windows 640 → 160 MiB），0 = 关 | 【D】258-260；错误尾 [pinned-memory-exhausted] |
| `STRATA_FILE_RELEASE=1` | **Windows 专用**：专家上传 GPU 后裁掉文件后备页 | 实测：32 GB Win11 笔记本 + RTX 4080 Laptop/3090，**可用 RAM 中位 0.51 → 12.19 GiB**，prefill −3.7~−4.4%【D】1395。docs 明说是工作集提示，不是 unmap，不减少提交内存与 SSD 读 |
| `STRATA_UNBUFFERED_LOAD` | 文件层是否绕过页缓存直读；有 `--resident-budget-gib` 才生效 | the file tier reads through the file cache (STRATA_UNBUFFERED_LOAD=%s ignored: without --resident-budget-gib the file cache holds the experts) |
| `STRATA_EMBED_VRAM=1` | **反向**：把 native embedding 表塞进 VRAM（默认在 mapped host memory，**不占 VRAM**） | strata: native embedding: STRATA_EMBED_VRAM=1 not taken (%llu MiB free, the table needs %llu MiB plus 512 MiB): kept in mapped host memory |
| `STRATA_KEEP_MAPPING` / `STRATA_STAGE_PIN` / `STRATA_STAGE_TRIM` | 层切分下 stage buffer 的映射 / 锁定 / 裁剪 | FileExpertSource: the stage buffers are pinned (cudaHostAlloc) |

### 5.2 VRAM 观测 / 预算

| 变量 | 语义 | 证据 |
|---|---|---|
| `STRATA_VRAM_FREE=device` | Windows+NVIDIA 用 NVML 读**整卡**空闲显存（而非 CUDA 只算本进程）；实测能差 6 GiB【D】1449 | STRATA_VRAM_FREE=device: free VRAM is read for the whole card (NVML: %lld MiB now; CUDA's figure for this process alone: %lld MiB) |
| `STRATA_PARK_VRAM_MIB` | 会话 snapshot 的 VRAM 预算 | 字符串表 |
| `STRATA_KV_GROW_INIT/STEP/FLOOR/HOLD` | `--kv-grow` 的初始格数 / 步长 / 地板 / 保持 | elastic K/V: %lld of %lld cells in VRAM (...) |
| `STRATA_HIP_VMM=0` | 关掉 HIP 上的虚拟内存管理（kv-grow 用） | 【D】218 |

### 5.3 验证用探针（不改行为）
`STRATA_TRACE` · `STRATA_PARK_TRACE` · `STRATA_ROUTE_STATS` · `STRATA_IO_STATS` · `STRATA_RSS_TRACE` · `STRATA_ADAPT_CHECKRES`

---

## 6. 冲突 / 前置条件矩阵（照这个排，别照 help 的字母序排）

| 组合 | 结果 |
|---|---|
| `--resident-cpu-experts` 缺 `--mmap-experts` 或缺静态 `--expert-profile` | **拒绝启动**：--resident-cpu-experts requires --mmap-experts and a static --expert-profile |
| `--shared-expert-arena` + `--mmap-experts` | **拒绝启动**：--shared-expert-arena backs the resident arena and cannot be used with --mmap-experts |
| `--kv-grow` + (`--batch` \| `--vram-elastic` \| `--peer-device`) | 自动关闭并打一行原因，不报错 |
| `--vram-elastic` + 层切分 / 多卡 helper cache / 段<64 / HIP / 非 --serve | 自动关闭：--vram-elastic is off: <原因> |
| `--kv-resident N`（N<20480） | --kv-resident must be >= 0 + help 的 min 20480；N ≥ 上下文长度时根本不 stream |
| `--resident-budget-gib 0` 或负 | --resident-budget-gib needs N > 0 |
| resident 模式 RAM 不够 | 三级降级，各有 WARNING 串：整体装不下→mmap；部分装下→整份装不下…最热的 %.2f GiB 留在 RAM；预算保不住→全读文件 |

---

## 7. 三套可直接抄的组合（本文只读，未跑）

**A. 8–12 GB 卡 + 32 GB 内存（最保守，先求跑得动）**
`--mmap-experts --kv-resident 20480 --kv k8v4 --expert-cache auto --expert-cache-per-layer --vram-reserve-mib 1500`
→ 专家走页缓存，K/V 只留 20K 格在 VRAM，每层各自分槽。再叠 `STRATA_FILE_RELEASE=1` 把可用 RAM 从 0.5 GiB 拉回 12 GiB 量级。

**B. 24 GB 卡 + 64 GB 内存 + 128K 上下文（收益最大）**
`--mmap-experts --resident-budget-gib 40 --expert-profile P --expert-cache auto --expert-cache-per-layer --kv-grow`
→ 最热的 40 GiB 专家进 RAM，其余走页缓存；K/V 只按实际触达占 VRAM（实测 +1,755 槽 / +2.3% decode）。

**C. 要把显存让给别的程序（与 8091 生产并存时）**
`--serve --vram-elastic --vram-segment-mib 512 --memory-limit-mib <容器上限>`
→ 之后 POST /v1/vram {"reserve_mib":N} 按需让出，{"reserve_mib":null} 收回。让出的段里的专家转 CPU 计算：答案不变、速度下降。

---

## 8. 未核源 / 待实测（明确标注，不当结论用）

1. 【未核源】`--resident-budget-gib` 与 `--conversation-cache-mib` 的争抢曲线：docs 只说 park 卡顿的解药是更小的 budget，没给数字。
2. 【未核源】`--kv-resident 20480` 这个下限对应省多少 VRAM —— help 只说每层留 N 格，没给 20480 格 ≈ 多少 MiB。要 `--stats` 实跑才知道。
3. 【未核源】`--vram-elastic` 让出 8 GiB 后 decode 掉多少，没有官方数字。
4. 【未核源】`--expert-cache` 裸引擎默认 0 vs docs 说 auto：我判断是引擎层 vs Terminal config 层的口径差，**未经运行验证**（只读约束下不能启动引擎比对启动行）。
5. 【未核源】本机 8091 生产实例当前实际用哪一套 —— 没碰生产口，未验证。

---

## 9. 复现命令（全部只读）

```bash
# help 全文
cat C:/Project/local_model/tmp/stratahelp/help.txt

# 全部环境变量
cd C:/Project/local_model/strata/components/engine/0.1.54-windows-x86_64-cuda-cuda13
grep -a -o "STRATA_[A-Z0-9_]*" strata.exe | sort -u

# 某开关的运行时语义（错误串 / 日志串）
LC_ALL=C grep -a -o "strata generate: [ -~]\{5,200\}" strata.exe | grep -i resident

# 官方 docs（需代理）
export HTTP_PROXY=http://127.0.0.1:7897 HTTPS_PROXY=http://127.0.0.1:7897
curl -s https://raw.githubusercontent.com/Niko1221/Strata/main/docs/DETAILS.md -o DETAILS.md
```

## 10. 来源清单

- 引擎 help（本地一手，0.1.54）：`C:/Project/local_model/tmp/stratahelp/help.txt`，272 行全文
- 引擎二进制字符串（本地一手）：`strata.exe` sha256 `107ef7fa3b33976c8f89f6d0cc5c4529d8d44c4a5ce1b9dffd3c7b255a40f080`
- 本机 Terminal 源码（一手，setup 的低内存/KV 判定）：`C:/Project/local_model/strata/data/terminal/0.1.54/setup.py:5959-5975`
- 官方仓库：<https://github.com/Niko1221/Strata>
  - 技术参考（Memory modes / Low-RAM modes / 专家缓存预算 / prompt-cache 表）：<https://github.com/Niko1221/Strata/blob/main/docs/DETAILS.md#memory-modes>
  - 低内存模式锚点：<https://github.com/Niko1221/Strata/blob/main/docs/DETAILS.md#low-ram-modes>
  - VRAM 弹性（POST /v1/vram）：<https://github.com/Niko1221/Strata/blob/main/docs/VRAM_ELASTIC.md>
  - 多卡与 `--trim-stage-weights`：<https://github.com/Niko1221/Strata/blob/main/docs/MULTI_GPU.md>
  - 模型与内存需求：<https://github.com/Niko1221/Strata/blob/main/docs/MODELS.md>
- 版本核对：`git ls-remote --tags` 显示仓库有 `v0.2.8`；其 `docs/DETAILS.md` 与 `main` **字节数完全一致（156,192 B，200-270 行 diff 无输出）**，故上述 URL 与 0.2.8 装机文档口径一致。
