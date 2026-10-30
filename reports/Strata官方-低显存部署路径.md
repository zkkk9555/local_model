# Strata 官方文档与 release notes 里的 8G / 12G 路径

- 侦察对象：https://github.com/Niko1221/Strata（公开仓库）
- 代码基线：commit `870aedd9e1ebe1c91f94da93b59af17729f6c5c0`（2026-10-29 18:13 +0100），AGENTS.md 记 app 0.2.8 / engine 0.1.54
- 采集时间：本次会话，全部经 `HTTP(S)_PROXY=http://127.0.0.1:7897` 抓取
- 只采一手证据（仓库文件 + releases.atom + issues 页面），每条事实后面都带 URL；官方没写、只有社区口径的明确标【社区/未核源】。
- 证据分级：**[原文]** = 官方文档/发布说明原句；**[源码]** = 官方源码里的注释或常量（可核对，但不是面向用户的承诺）；**[单次]** = 单机单次实测通过；**[反复]** = 多次/多次配对运行。

---

## 0. 一句话结论

**官方没有「8 GB 显存跑主力模型」这条路径。** 官方写死的地板是 **12 GB 显存 + 46 GB 内存**（DeepSeek V4.1-Flash），通用建议同样是「12 GB or more」。8 GB 在官方文档里只以三种身份出现：① 小卡兜底玩法（Coder / IQ1_M / Gyro-S，大头走 CPU+SSD）；② 一个专门给 8 GB 的服务端开关 `--prefill-head-alias`；③ 引擎「8 GB 卡能起来」的版本门槛（0.1.23）。真正让 8 GB 机器「能跑且不炸」的官方机制，是**低内存模式（--resident-experts / --mmap-experts / --resident-budget-gib）+ 显存 reserve + KV 策略**这四件事，而不是把大模型塞进 8 GB。

---

## 1. 官方地板：12 GB（硬口径，不是建议）

| 事实 | 原文 | 来源 |
| --- | --- | --- |
| DeepSeek 最低配置 | "**A very large model:** DeepSeek V4.1-Flash, **12 GB graphics card, 46 to 64 GB of RAM** and 257 GB of disk." | https://github.com/Niko1221/Strata/blob/870aedd9e1ebe1c91f94da93b59af17729f6c5c0/docs/MODELS.md#L49 |
| 显卡清单 | "NVIDIA RTX 30, 40 and 50 series, **12 GB or more** \| Windows, Linux" | https://github.com/Niko1221/Strata/blob/870aedd9e1ebe1c91f94da93b59af17729f6c5c0/docs/MODELS.md#L71 |
| 需求段 | "**What you need:** a graphics card with **12 GB or more**, **46 GB of RAM at least** (64 GB is the tested comfortable size)" | https://github.com/Niko1221/Strata/blob/870aedd9e1ebe1c91f94da93b59af17729f6c5c0/docs/MODELS.md#L84 |
| 通用下限 | "A card needs enough VRAM to be useful. **12 GB or more is recommended**, as for every card." | https://github.com/Niko1221/Strata/blob/870aedd9e1ebe1c91f94da93b59af17729f6c5c0/docs/OLDER_GPUS.md#L30 |
| 12 GB 卡体感 | "A slow SSD lowers every number, because **12 GB cards spend most of each token waiting on the SSD and the CPU**." | https://github.com/Niko1221/Strata/blob/870aedd9e1ebe1c91f94da93b59af17729f6c5c0/docs/MODELS.md#L107 |
| 实测（12 GB 档） | "RTX 5070 12 GB, Ryzen 5 7600, 64 GB RAM \| about 5 tokens/s (code) \| 231 tokens/s"；"RTX 3060 12 GB, 46 GB RAM \| 6 to 9 tokens/s" | https://github.com/Niko1221/Strata/blob/870aedd9e1ebe1c91f94da93b59af17729f6c5c0/docs/MODELS.md#L102-L103 |
| 发布说明口径 | "Strata now runs DeepSeek V4.1-Flash on a PC with one 12 GB graphics card and 46 to 64 GB of RAM"；"Output on 12 GB cards is 4 to 8 tokens/s" | https://github.com/Niko1221/Strata/releases |

**推论（给 8 GB 机器用）**：8 GB 显存按官方口径不在支持矩阵内。想在 8 GB 上跑，只能选小体积 pack（Coder 23 GB / IQ1_M / Gyro-S）并必须吃低内存模式，速度落在个位数到几十 tok/s，且大头在 SSD。任何「8 GB 跑 Q2_0/IQ3_XXS 全量」的说法，官方文档里没有对应文字。

---

## 2. 低内存模式（`--resident-experts`）：触发条件与用法

### 2.1 两种变体 + 一种预算模式

| 模式 | 开关 | 官方原文 | 来源 |
| --- | --- | --- | --- |
| Mapped | `--mmap-experts` | 专家从 pack 的 experts.bin 映射（+23–50 GB 磁盘），或直接从 GGUF 里读 | https://github.com/Niko1221/Strata/blob/870aedd9e1ebe1c91f94da93b59af17729f6c5c0/docs/DETAILS.md#L223-L232 |
| **Resident（重点）** | `--resident-experts` | "**When the experts the GPU does not hold fit the RAM, the engine copies exactly those into RAM at start. Nothing is read from the SSD while it answers.**" | https://github.com/Niko1221/Strata/blob/870aedd9e1ebe1c91f94da93b59af17729f6c5c0/docs/DETAILS.md#L231 |
| RAM 预算 | `--resident-budget-gib N` | 隐含 `--mmap-experts`，保留 4 GiB 余量；Windows 上 commit limit 还会二次夹紧 | https://github.com/Niko1221/Strata/blob/870aedd9e1ebe1c91f94da93b59af17729f6c5c0/docs/DETAILS.md#L232 |

### 2.2 触发条件（setup 自己算，不是拍脑袋）

源码常量与判定（可逐行核对，文件根为仓库 `setup.py`）：

- **L5900** `LOW_RAM_HEADROOM_GB = 10`（"RAM beside the experts: the OS, the engine's other buffers, the server"）
- **L5912-5915** `low_ram_needed()` → `return ram < MODELS[model]["arena_gb"] + LOW_RAM_HEADROOM_GB`
  → **判据一：内存 < 专家体积 + 10 GB 就进低内存模式。**
- **L5923-5929** `low_ram_gpu_gb()` → `max(0.0, min(arena_gb, vram_gb - 5 - (MTP_VRAM_GB if mtp else 0.0) - longer))`，其中 `kv_tok = 13 * KV_CELL_BYTES...`、`longer = max(0, ctx-32768) * kv_tok / 1e9`
  → **判据二：卡上能装的那部分 = 显存 − 5 GB（− MTP 1 GB）− 32K 以上上下文的增量。**
- **L5937-5942** `low_ram_resident()` → `rest = arena - low_ram_gpu_gb(...); return ram >= rest + 10`
  → **判据三：卡装不下的那部分 + 10 GB 装得进内存，才选 resident，否则退 mmap。**
- **L5945-5948** `low_ram_fits()` → `ram - 6 + max(0.0, vram - 5 - 1.0) >= arena`
- **L5951-5959** `low_ram_wanted()`：RAM 预算型模型直接 False；用户显式 `on/resident/mmap` 强制；`auto` 时按 `low_ram_needed()`。

来源：https://github.com/Niko1221/Strata/blob/870aedd9e1ebe1c91f94da93b59af17729f6c5c0/setup.py#L5900-L5959

**对 8 GB 卡的代入**：`vram_gb=8` → `low_ram_gpu_gb = min(arena, 8-5-1-Δ) ≈ 2 GB`（开 MTP 时）。也就是说 **8 GB 卡只能装下约 2 GB 专家，其余 20–48 GB 专家必须落在内存或 SSD**；内存装不下（8 GB 卡常配 16–32 GB 内存）时 setup 退到 `--mmap-experts`，即「反复读盘」。

### 2.3 怎么用（两个入口，别记混）

| 入口 | 命令 | 官方说明 |
| --- | --- | --- |
| 源码 setup | `START-HERE.bat --setup --low-ram on\|off`；`--low-ram resident\|mmap` 强制变体 | "In a source checkout, START-HERE.bat --setup --low-ram on\|off overrides the choice, and --low-ram resident\|mmap forces one variant."（https://github.com/Niko1221/Strata/blob/870aedd9e1ebe1c91f94da93b59af17729f6c5c0/docs/DETAILS.md#L234） |
| 源码 setup | 自动 | "When RAM cannot hold the experts beside the system, setup maps them from the model files..."（https://github.com/Niko1221/Strata/blob/870aedd9e1ebe1c91f94da93b59af17729f6c5c0/docs/MODELS.md#L137） |
| Terminal / 桌面版 | **没有 `--low-ram` 开关** | "`strata launch` has no `--low-ram` flag."（https://github.com/Niko1221/Strata/blob/870aedd9e1ebe1c91f94da93b59af17729f6c5c0/docs/MODELS.md#L141）；只能用 `--set` 传引擎参数/环境变量 |

resident 变体额外规则：保留 4 GB 空闲（`STRATA_RESIDENT_HEADROOM_GIB`）；启动日志出现 `resident RAM: ... blob reads from the file`，稳态应为 0（https://github.com/Niko1221/Strata/blob/870aedd9e1ebe1c91f94da93b59af17729f6c5c0/docs/DETAILS.md#L234-L237）。**层切分下 resident 需要 engine ≥ 0.1.40**（`RESIDENT_SPLIT_ENGINE = (0, 1, 40)`，setup.py L5902，引 #642）；更早的引擎会把 resident 变体自动换成 `--mmap-experts` 并打警告（setup.py L1966-1975）。

### 2.4 版本门槛（setup.py MIN_ENGINE 变更记录）

| engine | 原文 |
| --- | --- |
| 0.1.23 | "8 GB cards start" |
| 0.1.30 | "resident low-RAM variant" |
| 0.1.31 | "GGUF-in-place low-RAM mode"；同时 "caps the sliced pin below that budget (and honours STRATA_ARENA_PIN_GIB)"（#243） |
| 0.1.35 | "the low-RAM resident mode on Windows 32 GB (#467)" |
| 0.1.38 | "a 6 GB card starts (#496)" |
| 0.1.40 | "`--resident-experts` on a layer split with the split+resident variant (#848), `--kv k8v4` with KV streaming (#711)" |

来源：https://github.com/Niko1221/Strata/blob/870aedd9e1ebe1c91f94da93b59af17729f6c5c0/setup.py#L253

---

## 3. `--kv-resident` / `--kv-grow`：官方推荐值

| 项 | 官方口径 | 来源 |
| --- | --- | --- |
| KV 常驻推荐值 | **`--kv-resident 32768`**（32K 常驻，其余在 RAM） | https://github.com/Niko1221/Strata/blob/870aedd9e1ebe1c91f94da93b59af17729f6c5c0/docs/DETAILS.md#L217 ；真实配置样例 https://github.com/Niko1221/Strata/blob/870aedd9e1ebe1c91f94da93b59af17729f6c5c0/docs/BATCHING.md#L353（`--resident-experts`、k8v4、262K 上下文、`--kv-resident 32768`、`STRATA_ARENA_PIN_GIB=24`、Windows 11） |
| setup 自动写入值 | `args += ["--kv-resident", "32768"]`（同一个 32768） | https://github.com/Niko1221/Strata/blob/870aedd9e1ebe1c91f94da93b59af17729f6c5c0/setup.py#L9938 |
| 何时开 | "Setup turns it on **from 64K** when the RAM has room; `on` overrides the RAM test with a note. **Never under WSL.**" | https://github.com/Niko1221/Strata/blob/870aedd9e1ebe1c91f94da93b59af17729f6c5c0/docs/DETAILS.md#L217 |
| 自动判据（源码） | `ctx >= 65536 and (ram >= MODELS[model]["ram_gb"] + kv_streaming_ram_gb(ctx,kv) + 1 or choice=="on")`；`kv_streaming_ram_gb = ctx * 13 * KV_CELL_BYTES / 1e9`（8-bit KV ≈ 13.7 KB/token，128K 时 1.7 GB） | https://github.com/Niko1221/Strata/blob/870aedd9e1ebe1c91f94da93b59af17729f6c5c0/setup.py#L5962-L5975 |
| 代价 | "Costs about 13.7 KB of RAM per context token (1.7 GB at 128K)" | 同上 |
| WSL 为何关 | "NVIDIA driver pins only ~1 GB, so `--kv-resident` is off, the KV cache stays in VRAM" | https://github.com/Niko1221/Strata/blob/870aedd9e1ebe1c91f94da93b59af17729f6c5c0/docs/DETAILS.md#L202-L204 |
| `--kv-grow` 适用面 | "Needs one GPU, an expert profile, **the whole KV in VRAM and every expert in RAM**. Otherwise the engine says so and stays off... **It pays on cards of about 24 GB or less with contexts of 128K and more.**" | https://github.com/Niko1221/Strata/blob/870aedd9e1ebe1c91f94da93b59af17729f6c5c0/docs/DETAILS.md#L218 |
| `--kv-grow` 实测 | 0.1.40 R9700（32 GB）：slots 6,213 → 7,968，decode 96.3 → 98.5 tok/s（5 配对，5/5 同向） | https://github.com/Niko1221/Strata/blob/870aedd9e1ebe1c91f94da93b59af17729f6c5c0/docs/DETAILS.md#L1347 |

**关键坑（对低显存机器最要命）**：`--kv-resident` 的自动判据要求「内存装得下**全部**专家 + KV + 1 GB」。低内存机器上这条恒为假 → **setup 永远不会自动开 KV 流式**。这正是 issue #3726 的题目（"Setup, low-RAM mode: KV streaming is never chosen"，后被作者自己撤回：withdrawn: slower for agent workloads）。该 issue 里的手工 A/B（RTX 5070 Ti 16 GB + RTX 3070 8 GB，31 GB RAM，`--resident-experts --max-context 131072 --kv int8`，MTP + `--spec 4`）：

| 指标 | KV 在 VRAM | KV 流式（`--kv-resident 32768`） |
| --- | --- | --- |
| 专家槽（RTX 3070 stage 0） | 1941 | 2086 |
| 大卡可用专家空间 | 7.57 GiB | 8.65 GiB |
| 新 ~20K prompt | 23.5 s（~920 tok/s） | 14.3–17.6 s（1140–1440 tok/s） |
| 解码 300 tokens | 106–112 tok/s | 81–108 tok/s |

来源：https://github.com/Niko1221/Strata/issues/3726 **[单次 A/B，作者自撤]**

→ **给 8 GB 机器**：prompt 长、内存紧 → 值得手开 `--kv-resident 32768`（省显存换专家槽）；纯长对话/agent 解码为主 → 官方默认（不开）反而稳。

---

## 4. `STRATA_ARENA_PIN_GIB`：官方说明（含 Windows 默认值与 auto）

| 取值 | 官方语义 | 来源 |
| --- | --- | --- |
| 未设置 | Windows + 多卡（WDDM）下**只 pin 8 GiB** 专家 arena，其余走 pinned staging ring；Linux 全量 pin | https://github.com/Niko1221/Strata/blob/870aedd9e1ebe1c91f94da93b59af17729f6c5c0/docs/MULTI_GPU.md#L163-L164；helper 卡场景同（https://github.com/Niko1221/Strata/blob/870aedd9e1ebe1c91f94da93b59af17729f6c5c0/docs/SECOND_GPU.md#L23-L24） |
| `N` | "`STRATA_ARENA_PIN_GIB=N` **pins at most N GiB**, `0` the whole arena, on any OS." | https://github.com/Niko1221/Strata/blob/870aedd9e1ebe1c91f94da93b59af17729f6c5c0/docs/MULTI_GPU.md#L164 |
| `0` | 「整个 arena 都 pin」，上限到驱动拒绝为止 | 同上；https://github.com/Niko1221/Strata/blob/870aedd9e1ebe1c91f94da93b59af17729f6c5c0/docs/STRIX_HALO.md#L113 |
| `none` | 完全不注册（等于不 pin） | https://github.com/Niko1221/Strata/blob/870aedd9e1ebe1c91f94da93b59af17729f6c5c0/docs/STRIX_HALO.md#L242；https://github.com/Niko1221/Strata/blob/870aedd9e1ebe1c91f94da93b59af17729f6c5c0/docs/AMD_HIP.md#L469 |
| **Windows 默认 29 GiB** | "`STRATA_PIN_BY_NEED=1`（单卡 arena）按 rank 注册非 GPU 常驻专家，**up to `STRATA_ARENA_PIN_GIB`（29 by default on Windows）**，而不是「前 ~30 GiB」" | https://github.com/Niko1221/Strata/blob/870aedd9e1ebe1c91f94da93b59af17729f6c5c0/docs/DETAILS.md#L256-L257 |
| `auto` | 文档只出现一次："both runs used `STRATA_ARENA_PIN_GIB=auto`: without it, the full sliced arena pin on this 64 GB PC left WDDM with 0 GiB free for the cache (#243)" | https://github.com/Niko1221/Strata/blob/870aedd9e1ebe1c91f94da93b59af17729f6c5c0/docs/PREFILL_HEAD_ALIAS.md#L134-L135 |

### 4.1 `auto` 的精确语义（源码级，官方文档没写全）

`src/core/pinned.cu`（`git show HEAD:src/core/pinned.cu`）：

- L352-358 `arena_pin_cap_gib()`：`"auto" → -2`，注释 "#243: the Windows shared-memory budget sets the sliced pin's cap"；`"none" → -1`，`"0" → 0`。
- L459-463：只有 `#ifdef _WIN32` 且 `env_gib == -2` 时才启用 `sliced_pin_limit()`；注释原文：
  > "#243 (opt-in, STRATA_ARENA_PIN_GIB=auto): **not up to the driver's refusal but below the shared-memory budget**, for a PC where the full sliced pin leaves WDDM refusing later allocations. **Not the default: a 64 GB PC pins 30 GiB past that budget without trouble, and capping it at 26 cost ~20% prompt speed.**"
- L538-545：`"auto" (-2): the sliced pin's shared-memory-budget limit (**29 GiB when it cannot be worked out**); STRATA_ARENA_PIN_GIB=0 ("the whole arena"): no cap, up to the driver's refusal.`
- 预算本身："Windows (WDDM) lets a process page-lock **about half the RAM** for the GPU"；`sliced_pin_limit()` 里给 arena 之后引擎自己的分配**留 4 GiB**，拿不到 DXGI 数字时退化到 **RAM/2 − 8 GiB**；引擎另有 **640 + 160 MiB** 两段预留（Windows CUDA），`STRATA_PIN_RESERVE_MIB=N` 可改、`0` 关闭（见 `include/strata/core/pin_budget.hpp` 头部注释）。**[源码]**

### 4.2 失败长什么样（官方给了自诊断串）

"**If a required buffer is still refused, the error ends with `[pinned-memory-exhausted]` and names the `STRATA_ARENA_PIN_GIB` to start with.**"（https://github.com/Niko1221/Strata/blob/870aedd9e1ebe1c91f94da93b59af17729f6c5c0/docs/DETAILS.md#L260）—— 看到这个尾巴就按它建议的数值设，别硬顶。

**实操（8–12 GB 机器）**：单卡 Windows + 大内存，默认别动；一旦出现「首个 device 分配 OOM / pinned-memory-exhausted」，按序试 `STRATA_ARENA_PIN_GIB=auto` → `16`/`24` → `none`。一手案例 #243（63 GB 内存 + RTX 4090：整块注册失败后切片 pin 到 28 GiB，之后**每一个** cudaMalloc 都 OOM，包括 1 MB 的 logits buffer），维护者回复 "0.1.31 caps the sliced pin below that budget (and honours STRATA_ARENA_PIN_GIB)"：https://github.com/Niko1221/Strata/issues/243

---

## 5. 最近版本里「12 GB 及以下显卡」的改进条目（版本号 + 原文）

### 5.1 0.2.7：默认**开**

> **Strata 0.2.7: faster 12 GB NVIDIA cards, DeepSeek on Ryzen AI Max, a bigger web chat page, French**
> "**NVIDIA cards with 12 GB or less answer faster.** The router now prefers experts that are already on the card, which saves page-ins from RAM. On an RTX 3060 12 GB (Qwen3.8-Flash-Next IQ3_XXS, **five paired runs** against the same build with the setting off), a story answer went from **46.2 to 53.1 tok/s (+15%)** and a code answer from **45.7 to 62.5 tok/s (+37%)**... A stronger setting (2.0) did show copy and code defects, so the default is 1.5. **It applies to a discrete NVIDIA card of 13 GiB or less**; larger cards, Radeon and Strix Halo are not changed."

来源：https://github.com/Niko1221/Strata/blob/main/docs/release-notes-0.2.7.md#L1 、#L7（**【反复】**：五次配对运行）

### 5.2 0.2.8：**又关回去**（当前最新，2026-10-29）

> "**RTX cards with 12 GB or less: the 0.2.7 routing speed-up is off again by default.** It made answers faster (RTX 3060: story +15%, code +37%), but your reports and our own checks tied it to **repeated text in long sessions**. With nothing set, the engine now routes exactly as 0.2.6 did. To get the speed back, turn on 'Faster answers on 12 GB NVIDIA cards' under Models, Native engine settings, Speed (or run `strata launch --set STRATA_ROUTE_PRIOR=1.5`)."

来源：https://github.com/Niko1221/Strata/releases （Strata 0.2.8 条目）；文档同步 https://github.com/Niko1221/Strata/blob/870aedd9e1ebe1c91f94da93b59af17729f6c5c0/docs/DETAILS.md#L1041 与 #L1243-L1244（"opt-in again in 0.2.8 ... because of repetition loops and weaker results in long agent sessions, #4402"；agent 任务 4.5/10 vs 5.6/10）

**必须照这个说**：0.2.7 曾对 ≤13 GiB 的 NVIDIA 卡**默认开启** `STRATA_ROUTE_PRIOR=1.5`；**0.2.8（owner decision of 2026-10-29）已撤回为 opt-in**。谁说「现在 12 GB 卡自动快 15%」，那是 0.2.7 的旧事实。

### 5.3 其他与内存/低配直接相关的版本条目

| 版本 | 原文要点 | 来源 |
| --- | --- | --- |
| 0.2.6 | 所有 CPU 侧专家能装进内存且余 8 GiB 时，加载时**全部拷入**并关掉 demand store（Windows 还需 commit 空间） | https://github.com/Niko1221/Strata/releases |
| 0.2.5 | RAM store 现在能装下**全部**专家（以前到 48 GB 就停），并留 12 GB 空闲 | 同上 |
| 0.2.4 | "runs DeepSeek V4.1-Flash on a PC with **one 12 GB graphics card** and 46 to 64 GB of RAM"；"Output on 12 GB cards is 4 to 8 tokens/s" | 同上 |
| 0.2.2 | "A model that is slightly too big gets smaller settings by itself... tries a **32K, 16K and 8K context**, a smaller prompt chunk and a smaller reserve, in that order... Gyro-M on the 8 GB A750 used to stop with no room for a single c[ontext]" | https://github.com/Niko1221/Strata/blob/870aedd9e1ebe1c91f94da93b59af17729f6c5c0/docs/release-notes-0.2.2.md#L7 |

---

## 6. 8 GB 显存：官方到底给了什么

| 类别 | 内容 | 来源 |
| --- | --- | --- |
| 唯一专门的 8 GB 服务端开关 | `--prefill-head-alias`（`--serve`，单卡）—— "**For 8 GB cards.**" | https://github.com/Niko1221/Strata/blob/870aedd9e1ebe1c91f94da93b59af17729f6c5c0/docs/DETAILS.md#L1032 |
| 它的实测 | "8 GB RTX PRO 2000 Laptop, Windows, IQ3_XXS, 590 MiB reserve, 29,854-token prompt"：prefill **292.5 → 667.1 tok/s**（chunk 2,048 而不是 512）；代价：读到 512 个新 token 时多花 **0.6–0.75 s**；解码期 0 MiB 空闲 | https://github.com/Niko1221/Strata/blob/870aedd9e1ebe1c91f94da93b59af17729f6c5c0/docs/DETAILS.md#L1443 |
| 原理 | "On an 8 GB card the prompt chunk is as large as the free VRAM allows, and prefill speed follows the chunk closely" | https://github.com/Niko1221/Strata/blob/870aedd9e1ebe1c91f94da93b59af17729f6c5c0/docs/PREFILL_HEAD_ALIAS.md#L12 |
| 8 GB 装多少专家 | "With 8 GB the card holds **410 of the 24,576 experts**, so about 15 experts per layer and token come from the CPU pool"（Gyro-S） | https://github.com/Niko1221/Strata/blob/870aedd9e1ebe1c91f94da93b59af17729f6c5c0/docs/GYRO.md#L157 |
| 8 GB 的 KV 收益 | 8 GB 卡上 `--kv k8v4` 在 128K 多 **780** 个专家槽；不开 `--mtp` 时槽位 **1,000 → 1,678** | https://github.com/Niko1221/Strata/blob/870aedd9e1ebe1c91f94da93b59af17729f6c5c0/docs/DETAILS.md#L1341、#L1346 |
| 小卡通用调参 | Arc A750 8 GB：`--vram-reserve-mib 100 --prefill 1024`；<12 GB 卡建议 300 MiB reserve + `--draft-vocab en` | https://github.com/Niko1221/Strata/blob/870aedd9e1ebe1c91f94da93b59af17729f6c5c0/docs/INTEL.md#L281、#L236 |
| 多卡里的 8 GB 位置 | 有更大卡时 ≤8 GB 的卡默认设 **Off**；<8 GB 与别的卡混用被拒（"each card holds a copy of the dense weights"） | https://github.com/Niko1221/Strata/blob/870aedd9e1ebe1c91f94da93b59af17729f6c5c0/docs/MULTI_GPU.md#L58 |
| 低内存模式效果（0.1.26） | "Coder \| Low-RAM mode: **committed memory 36 -> ~13 GB**, same answers" | https://github.com/Niko1221/Strata/blob/870aedd9e1ebe1c91f94da93b59af17729f6c5c0/docs/DETAILS.md#L1381 |

### 6.1 社区一手案例：GTX 1070 Ti 8 GB 跑通 Gyro-S

https://github.com/Niko1221/Strata/issues/4517 —— **[单次协议通过；非反复长跑]** 官方文档自己写 "Not tested: any other sm_61 card (Tesla P4, GTX 10 series)"，这是补上的数据点：

- 硬件：GTX 1070 Ti 8 GB（sm_61）、Ryzen 9 3900X、**32 GB DDR4 + 16 GB zram**、NVMe；Strata Terminal 0.2.7 / engine 0.1.52（cuda12 发行二进制）；模型 **Gyro-S（Qwen3.8-Flash-Next trellis）58.5 GB + MTP**，vision off。
- "**32 GB of RAM is below the 64 GB your matrices recommend, so setup chose low-memory mode.**"（自动进低内存模式，无需手工开关）
- 通过度：标准协议 **21/21** 必答请求、**12/12** 理智检查；加载 **13–18 s**；解码 **27–34 tok/s**；prompt **89–211 tok/s**。
- 真正的坑是 **VRAM reserve**，不是模型：

| `--vram-reserve-mib` | 加载后空闲显存 | 10K prompt 结果 |
| --- | --- | --- |
| 不设 | 178–505 MiB | 150 s × 2 次无结果 |
| 1024 | 1,482 MiB | 97 s 完成 |
| 1344 | 1,164 MiB | 稳定 |

- 引擎自己的警告（可当排障锚点）："only 218 MiB of VRAM free at the start of this request (below 512 MiB): when the card is this full the driver can page GPU memory to system RAM, decode falls to a few tok/s and a window may never finish (#2065). Add --vram-reserve-mib 1344..."
- 真瓶颈：planner 自述 "chunk 1280, ring 96 kept: **file set 24.2 GiB does not fit the page cache 21.3 GiB** -> about **518.7 GB read from the drive per 32768-token prompt** (26 chunks); no option does better"——**32 GB 内存差约 3 GB 就够，64 GB 能把 26 遍变 1 遍**。

### 6.2 其他 8 GB / 低内存相关 issue（标题级）

- #300 "Image encoder keeps failing on 8GB GPU" —— https://github.com/Niko1221/Strata/issues/300
- #1375 "Strata working on an RX 6600 XT (gfx1032, 8 GB) and a Xeon E5-2678 v3 with 64 GB DDR3"
- #2248 "Benchmark on RTX 4060 (8 GB) + RTX 2060 (6 GB) heterogeneous dual-GPU"
- #3726 "Setup, low-RAM mode: KV streaming is never chosen"（见 §3，作者自撤）
- #467 "Windows + 32 GB RAM: the low-RAM resident mode never engages — the fit check runs after the engine's own cache warm-up"（0.1.35 修）
- #243 / #633 pinned expert arena 没有 host-RAM 检查 → OOM killer（arena pin 家族）
- #3734 "In-place GGUF expert pages stay GPU-pinned on top of the resident pool (~2x expert RAM)"（低内存模式下的内存翻倍风险）

检索方式：github.com/search（`type=issues`，blackbird JSON），`8gb`→1、`8 GB`→24、`low ram`→12、`lowram`→0、`oom`→21、`pinned`→9、`out of memory`→12。

---

## 7. 8 GB 机器照官方该怎么设（可执行清单）

1. **先认命**：官方支持矩阵最低 12 GB；8 GB 只能跑小 pack（Coder 23 GB / IQ1_M / Gyro-S），速度按 #4517 量级（解码 ~30 tok/s，prompt 100–200 tok/s），大头在读盘。
2. **内存优先于显存**：#4517 的硬结论是 file set 24.2 GiB 不 fit 21.3 GiB page cache → 每个 32K prompt 读 518.7 GB。8 GB 卡 + 16 GB 内存基本没救；**内存 ≥ 48–64 GB 才是 8 GB 卡真正的前置条件**。
3. **显存 reserve 一定显式设**：从 `--vram-reserve-mib 1344` 起（8 GB 卡实测稳定值），别吃默认；空闲 <512 MiB 会出现「请求永不返回」。
4. **低内存模式**：源码 setup 用 `--low-ram on`（优先 `resident`，内存不够才 `mmap`）；Terminal/桌面版没这个 flag，靠 setup 自动判据（内存 < 专家 + 10 GB）。日志确认 `resident RAM: ... blob reads from the file` 稳态为 0。
5. **KV**：官方推荐值就一个 —— `--kv-resident 32768`（`--kv-streaming on` 或 `auto`）；但低内存机器上它**不会**被自动选中，手开要看用途（长 prompt 有收益，长对话解码可能变慢，见 #3726）。`--kv-grow` 官方只对「≤24 GB 且 ≥128K 上下文、KV 全在 VRAM、专家全在 RAM」说有用——8 GB + 低内存通常不满足前置条件。
6. **arena pin**：Windows 单卡默认 29 GiB / 多卡 8 GiB；不要无脑设 `0`（整块 pin）。报 `[pinned-memory-exhausted]` 时按 `auto` → 小 N → `none` 收敛。
7. **0.2.8 的 12 GB 提速**要手动开：`strata launch --set STRATA_ROUTE_PRIOR=1.5`（仅 ≤13 GiB 离散 NVIDIA；长 agent 会话有复读风险）。

---

## 8. 证据边界

- **已核到原文/源码**：12 GB 地板；四种低内存模式与判定公式；`--kv-resident 32768`；`--kv-grow` 前置条件；`STRATA_ARENA_PIN_GIB` 的 N/0/none/auto/29 GiB；0.2.7 与 0.2.8 的 12 GB 条目；8 GB 的 `--prefill-head-alias`。
- **只有社区一手数据（非官方承诺）**：8 GB GTX 1070 Ti 跑通 Gyro-S（#4517，单机单次协议通过）；8 GB 卡的 reserve 数值（#4517 与 INTEL.md 的 100/300 MiB 属不同后端/不同卡，不能互套）。
- **明确没找到**：官方任何「8 GB 跑 Q2_0/IQ3_XXS 级主力模型」的说明；`STRATA_ARENA_PIN_GIB=auto` 的**用户文档级**定义（只有 PREFILL_HEAD_ALIAS.md 一句实测引用 + 源码注释）；`--kv-resident` 在 8 GB 卡上的官方专用推荐值（官方只给 32768 这个通用值）。
- **github REST API 被限流**（"API rate limit exceeded for 207.32.218.91"），故 releases 走 `releases.atom`、issue 走 HTML 页面，均为公开一手内容。

---

## 附：本次抓取命令（可复现）

```
export HTTP_PROXY=http://127.0.0.1:7897 HTTPS_PROXY=http://127.0.0.1:7897
git clone --depth 1 --filter=blob:none https://github.com/Niko1221/Strata.git
git show HEAD:src/core/pinned.cu | sed -n '340,370p;430,485p'   # arena pin 语义
curl -sL https://github.com/Niko1221/Strata/releases.atom         # 发布说明（REST 被限流）
curl -sL https://github.com/Niko1221/Strata/issues/4517           # 8 GB 一手案例
```
