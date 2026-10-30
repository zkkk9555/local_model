# Strata low-RAM 开关链：8 GB VRAM + 31 GB RAM（Windows）的正确组合

> 侦察报告 · 2026-10-30 · 证据基线：本机引擎 **0.1.54**（应用 0.2.8 自带）+ 官方 main 分支 docs
> 标注约定：带 URL = 一手可核；【本机实测】= 本机日志/二进制，非 URL；【未核源】= 无数字支撑的推断。
> 未启停任何引擎或服务（8091/8081 全程未触碰），未改 C:/Project/local_model 下任何配置脚本；仅执行过一次 `strata.exe --help`（不绑端口，exit 0）。

## 0. 结论速览

| 目标 | 判定 | 一句话理由 |
| --- | --- | --- |
| 125B 级 **Q2_0** | ❌ 不属于可运行档 | shard1 experts **34 GB**，官方判据「RAM ≥ experts + 约 10 GB」⇒ 需 **44 GB**，本机 31 GB（[docs/MODELS.md](https://github.com/Niko1221/Strata/blob/main/docs/MODELS.md#will-it-fit)，L120-130） |
| 125B 级 **Gyro-S**（27.6 GB，本机唯一在档） | ⚠️ 可行，待验证 | experts 约 24 GB，8 GB 卡扛约 4 GB ⇒ 约 20 GB 进 RAM < 可用 27 GB（31−4 headroom） |
| **35B-A3B**（qwen36 路径） | ❌ 8 GB 卡上起不来 | 整族 low-RAM 开关被运行时忽略；且缺 **1159 MiB** 给 hybrid experts 的 buffers+slots（2K 时只空出 917 MiB）【本机实测】 |

**125B 正确开关链（一行版）**：

```
strata serve --model gyro-Gyro-S --gpus 0 --resident-experts \
  --expert-cache auto --expert-cache-per-layer \
  --kv int8 --kv-streaming on --kv-resident 20480 \
  --max-context 32768 --batch 1 --vram-reserve-mib 512
```

## 1. 问题与证据面

任务要求把 `--resident-experts`／`--expert-cache N`／`--expert-cache-per-layer`／`--resident-experts`↔`--shared-expert-arena`／`--kv-resident N`／`--kv-grow`／`--expert-profile`／`--memory-limit-mib`／`--vram-elastic`／`--batch --slots` 之间的依赖整理成图，并给出 Windows 单机（8 GB 显存 / 31 GB 内存 / 大页面文件）的完整命令行模板。

证据面（全部为本轮亲自核过）：

| 来源 | 用法 | 备注 |
| --- | --- | --- |
| `C:/Project/local_model/tmp/stratahelp/help.txt` | 开关语义、默认值、实测命中率 | 272 行 = `strata.exe --help` 全文（本轮复核） |
| [docs/DETAILS.md](https://github.com/Niko1221/Strata/blob/main/docs/DETAILS.md) | 低内存三模式、expert cache 预算、KV 流式 RAM 成本 | 主证据 |
| [docs/MODELS.md](https://github.com/Niko1221/Strata/blob/main/docs/MODELS.md) | 装得下判据、四档 experts 体积 | L118-141 |
| [docs/BATCHING.md](https://github.com/Niko1221/Strata/blob/main/docs/BATCHING.md) | slot 的 VRAM 成本、何时推荐 | L143-157 |
| [docs/QWEN36.md](https://github.com/Niko1221/Strata/blob/main/docs/QWEN36.md) | qwen36 路径的 `--parallel` 与 slot 成本 | L74-87 |
| [docs/VRAM_ELASTIC.md](https://github.com/Niko1221/Strata/blob/main/docs/VRAM_ELASTIC.md) | `--vram-elastic` 的拒绝条件 | L61-68 |
| [docs/TROUBLESHOOTING.md](https://github.com/Niko1221/Strata/blob/main/docs/TROUBLESHOOTING.md) | 超配 → 100→14 tok/s；32 GB 机锁页卡死 | L255-280 |
| `C:/Project/local_model/strata/install/res-*.log`（09:28-09:30） | 35B-A3B 的 flag 忽略与 VRAM 闸【本机实测】 | 另一子代理刚跑完 |

**版本漂移，先记一笔**：`help.txt` L20-21 写「`--kv` 默认 fp16 直到 gate G-C 接受 int8」，而 [docs/DETAILS.md](https://github.com/Niko1221/Strata/blob/main/docs/DETAILS.md) L214 写「`--kv int8`（默认）」。本机是 0.1.54，上游 main 更新。**所以模板里显式写 `--kv`，不赌默认值。**

另：`strata.exe --help` 的 272 行里**没有** `--vram-reserve-mib` / `--pcie-frac` / `--resident-budget-gib` / `--adapt-every`（仅作为 `--adapt-every 0` 出现在别的开关说明里）/ `--expert-slots` / `--parallel`，但【本机实测】二进制字符串里全都有（`--parallel`、`--low-ram` 确实没有）。⇒ **help 不全 ≠ 引擎不支持**，本文不据 help 断言任何 flag 不存在。

## 2. 依赖图

```mermaid
graph TD
  subgraph RAM 层（31 GB）
    RE[--resident-experts<br/>=mmap+cpu-experts, 4GiB headroom, fallback→mmap]
    MM[--mmap-experts<br/>opt OUT of resident arena]
    RCE[--resident-cpu-experts<br/>需 mmap + static profile]
    AR[--shared-expert-arena FILE<br/>仅 Linux /dev/shm]
    RBG[--resident-budget-gib N<br/>隐含 mmap, 被 Windows commit limit 封顶]
    KVR[--kv-resident N ≥20480<br/>K/V 全文进 pinned RAM]
    ML[--memory-limit-mib N<br/>只在容器/cgroup 需要]
  end
  subgraph VRAM 层（8 GB）
    EC[--expert-cache N|auto<br/>预算=N×最大blob, 默认0]
    ECPL[--expert-cache-per-layer<br/>同一 N 改成每层自己的 slots]
    KVG[--kv-grow<br/>需单卡+profile+全部专家在RAM]
    VE[--vram-elastic<br/>与 resident 模式互斥]
    BA[--batch N / --slots N (2..8)<br/>每 slot 0.56GiB@32K]
    EP[--expert-profile P<br/>kv-grow 的前置; 静态放置]
  end
  RE --> MM; RE --> RCE; RE -.->|装不下| MM
  RCE --> EP; AR --> RCE
  RBG --> MM
  KVR -->|腾出的 VRAM| EC
  EC --> ECPL
  EC -->|竞争| BA; KVR -->|竞争| BA; KVG -->|竞争| EC
  KVG --> EP; KVG -->|要求| RAM层
  VE -.->|互斥| RE; VE -.->|互斥| RBG; VE -.->|batch 解码时拒绝| BA
  ML -->|压低 parking / 会话地板| KVR
```

ASCII 版（便于贴进别的文档）：

```
                 ┌─ --mmap-experts ─────────────┐
                 │                              │
--resident-experts ──┬─ --resident-cpu-experts ── 需要 static --expert-profile
  (4 GiB headroom)   └─ --shared-expert-arena ── 仅 Linux（/dev/shm），Windows 无
  装不下 ⇒ 自动退回 --mmap-experts（答案与 mmap 同）

--resident-budget-gib N ⇒ 隐含 --mmap-experts；离 4 GiB；Windows commit limit 封顶 N

VRAM 预算（8 GB）的来源与争夺者：
    [dense 权重] + [KV 窗口] + [--batch slots: 0.56 GiB/32K] + [--vram-reserve-mib] + [--expert-cache N]
                                                  ↑ --kv-resident N 把 KV 搬到 pinned RAM 后，这块腾给 expert slots
    --expert-cache-per-layer 不改 N，只改分配粒度（默认共用一个计数器 → 2.97% 命中）
    --expert-cache 默认 0 ⇒ 不开就是每 token 的专家全走 PCIe/盘

--kv-grow ⇒ 单卡 + --expert-profile + 整个 KV 在 VRAM + 每个 expert 都在 RAM
            ⇒ 与 --kv-resident 的取向相反；31 GB 机上直接出局（34 GB/24 GB experts 放不下）

--vram-elastic ⟂ resident 低内存模式；⟂ --peer-device；batch slots 解码时服务端拒绝 resize
```

## 3. 逐开关：作用、默认、依赖、互斥

| 开关 | 作用（原文要点） | 默认 | 依赖（读） | 影响（写） | 互斥/注意 |
| --- | --- | --- | --- | --- | --- |
| `--resident-experts` | 低内存 PC 的常驻模式（setup 会选它）：`--mmap-experts --resident-cpu-experts`，能锁页时锁页，**4 GiB headroom**，装不下退回纯 mmap；同一放置下答案与 `--mmap-experts` 相同（help.txt L262-264） | 关 | `--expert-profile` 提升静态放置质量 | 从文件 map + 卡装不下的部分常驻 RAM | 与 `--vram-elastic` 互斥；锁页可能挤死 32 GB 机（[TROUBLESHOOTING](https://github.com/Niko1221/Strata/blob/main/docs/TROUBLESHOOTING.md) L260-262，`STRATA_RESIDENT_PIN=0` 改可换页） |
| `--mmap-experts` | 退出常驻 arena，回到 MapViewOfFile；速率取决于 OS page cache 能否装下（34 GB 时 71.97 vs 34.78 ms/token，cold/warm）（help.txt L253-255） | arena（默认） | 无 | 盘 + page cache | 小卡 + 小内存时就是「很多专家从 SSD 读」 |
| `--resident-cpu-experts` | mmap + 静态 profile 时，GPU cache 装不下的 experts 常驻普通 RAM；adaptive swap 只换它们，故不再读文件（help.txt L259-261） | 关 | **必须有 mmap**；static profile | RAM 占用 | 与 `--resident-experts` 二选一/被其包含 |
| `--shared-expert-arena FILE` | 用一份 `MAP_SHARED` 文件支撑常驻 arena，放 `/dev/shm` 不放 SSD（help.txt L256-258） | 无 | arena 模式（即**不要** `--mmap-experts`） | 一小段 header 绑定回原 pack | **仅 Linux**；与 `--resident-experts` 天然冲突（后者带 mmap） |
| `--expert-cache N` | 保留 N 个 expert blob 常驻 VRAM，用 `moe_hit_grouped_s2` 在 GPU 算；4096 slots + per-layer 实测 54.4% 命中、CPU pool drain 19.1→10.3 ms/token、端到端 −2.7 ms/token（help.txt L192-195） | **0** | 写入前的 free VRAM | 决定多少专家不上 PCIe | 预算是 **N × 最大 blob**，Windows 超配不报错而是驱动把页到系统内存 → 100→14 tok/s（[DETAILS](https://github.com/Niko1221/Strata/blob/main/docs/DETAILS.md) L378-398） |
| `--expert-cache-per-layer` | 每层拥有自己的 slots；默认共用计数器时 256 slots 被约 26 层的 position 0 吃掉，实测 **2.97%**；per-layer 8 slots/层 **21.4%**、64 slots/层 **70.4%**；native pack 上 N 仍是 N 个最大 blob 的预算（help.txt L210-215） | 关 | `--expert-cache N` 的 N | 命中率（分布） | 不改 N，只改分配粒度 |
| `--kv-resident N` | KV 流式：每 QSA 层留 N cells 在 VRAM（**min 20480**），整个 K/V 在 **pinned RAM**；腾出的 VRAM 给 expert slots；0=全在 VRAM；上下文 ≤N cells 不流式（help.txt L26-28） | 0 | RAM（约 **13.7 KB/context token**，128K=1.7 GB，[DETAILS](https://github.com/Niko1221/Strata/blob/main/docs/DETAILS.md) L217） | 腾出 VRAM → expert slots | `--kv k8v4` 也能流式（816 B/cell vs int8 1056） |
| `--kv-grow` | K/V 只按请求触达的 cells 占 VRAM，expert cache 拿其余，上下文增长时归还 slots（help.txt L29-32；[DETAILS](https://github.com/Niko1221/Strata/blob/main/docs/DETAILS.md) L218） | 关 | **单 GPU + `--expert-profile` + 整个 KV 在 VRAM + 每个 expert 在 RAM** | 归还 slots | 缺一项引擎自己说不行并保持关闭；`STRATA_KV_GROW=1` |
| `--expert-profile P` | 从 `profile.bin` 预载 VRAM 层（tools/make_profile.py）；`--expert-profile-save P`（serve）在 QUIT 与每 `--expert-profile-save-every MIN` 存（help.txt L181-186） | 无 | 一段真实流量 | 静态放置质量；`--kv-grow` 的前置 | 无 profile 时 `--resident-cpu-experts` 只能按默认顺序放 |
| `--memory-limit-mib N` | 容器/cgroup 看不到真实上限时告诉引擎总 RAM 上限；parking 与会话存取的地板都压在它下面（help.txt L90-92） | 0=无 | 容器环境 | parking / conversation cache 上限 | 也 `STRATA_MEMORY_LIMIT_MIB`，flag 优先；裸机不需要 |
| `--vram-elastic` | expert cache 分 512 MiB 段（`--vram-segment-mib`），`POST /v1/vram` 的 reserve_mib 可在请求间让出/取回 VRAM（help.txt L100-102） | 关（opt-in） | `--serve`、单 NVIDIA 卡 | 运行期 VRAM 配额 | 服务端明确拒绝：`VRAM: not with the resident low-RAM mode`、`not with --peer-device`、`not while batch slots are decoding`（[VRAM_ELASTIC](https://github.com/Niko1221/Strata/blob/main/docs/VRAM_ELASTIC.md) L61-68） |
| `--batch N` / `--slots N` | 2..8 个 slot 同时 decode，每 slot 自己的 session（VRAM 同主 session）（help.txt L103-105） | 1 | free VRAM | 吞吐/延迟 | 每 slot **0.56 GiB @32K（8-bit KV）**；只在「专家大部分装进 VRAM」时推荐，12/16 GB 单卡一律 1 个，且单请求慢 **10-25%**（[BATCHING](https://github.com/Niko1221/Strata/blob/main/docs/BATCHING.md) L143-157） |

## 4. 这台机器上的两份预算

### VRAM（8 GB）

```
8.0 GiB
 - dense 权重（125B 约 2-3.6 GB；35B 实测 4.40 GB）
 - KV 窗口（--max-context × 每 cell 字节；--kv-resident 后只剩 20480 cells 的窗口）
 - --batch slots（0.56 GiB/32K/slot，8 GB 上必须 =1）
 - --vram-reserve-mib（建议 512，防「0 MiB free」陷阱）
 = 剩给 --expert-cache 的余量  ←启动日志会写 ... MiB of VRAM free with everything loaded
```

### RAM（31 GB）

```
31 GiB
 - 4 GiB headroom（STRATA_RESIDENT_HEADROOM_GIB 默认 4）
 - KV 流式的 pinned 部分（13.7 KB/token：32K≈0.45 GB，128K≈1.7 GB）
 - 模型 29 GB PLE 表若 --ple-io ram 会整个锁进 RAM ⇒ 这台机器**绝不能**这么设（默认 direct 不在 RAM 里）
 = 27 GiB 可用于 experts
```

于是判据变成一句：**experts − 卡能扛的量 ≤ 27 GiB？**

| 档 | experts | 卡扛（约） | 需进 RAM | ≤27 GiB? |
| --- | --- | --- | --- | --- |
| Q2_0 | 34 GB | 4 | **30** | ❌ 差 3 GB |
| Gyro-S（TQ1_0，27.6 GB 文件） | ~24【未核源】 | 4 | ~20 | ✅ |
| Coder | 23 GB | 4 | 19 | ✅（官方 32 GB + 12-16 GB 卡的档） |

## 5. 模板 A：125B 级 Gyro-S（本机唯一在档，推荐）

```bat
set STRATA_RESIDENT_HEADROOM_GIB=4
strata serve ^
  --model gyro-Gyro-S --gpus 0 ^
  --resident-experts ^
  --expert-profile C:/Project/local_model/strata/profiles/gyro.profile ^
  --expert-cache auto --expert-cache-per-layer ^
  --kv int8 --kv-streaming on --kv-resident 20480 ^
  --max-context 32768 ^
  --batch 1 ^
  --vram-reserve-mib 512
```

每个参数的依据：

| 参数 | 依据 | 若省略会怎样 |
| --- | --- | --- |
| `--resident-experts` | help.txt L262-264 的低内存模式；本机 RAM 刚好装得下卡装不下的部分（~20 GiB < 27 GiB） | 默认 arena 会把全部 experts 拷进 RAM（27.6 GB 会撑爆 31 GB 机） |
| 不写 `--shared-expert-arena` | help.txt L256：**仅 Linux**；且它要求 arena 模式，与 mmap 冲突 | 写了不生效/更糟 |
| `--expert-profile` | L181-186：静态放置 + `--resident-cpu-experts` 的「static profile」前提；也是将来 `--kv-grow` 的入口 | 放置退化为到达顺序，命中率与 resident 复制都不稳 |
| `--expert-cache auto` | L193 默认 0（等于每 token 都走 PCIe）；auto 是「写完再量」，避开 Windows 超配不报错（DETAILS L378-398） | 开 0 就直接 PCIe 打满；开固定大数会踩 100→14 tok/s |
| `--expert-cache-per-layer` | L210-215：同一 N 下 2.97% → 21.4%(8/层) → 70.4%(64/层)；8 GB 卡每层只分到几十个 slot，正是 per-layer 的甜区 | 命中率掉一个数量级 |
| `--kv int8` | 显式钉住（版本漂移：help 说默认 fp16，docs 说默认 int8） | 可能白占一倍 KV VRAM |
| `--kv-streaming on` + `--kv-resident 20480` | L26-28：把 whole K/V 搬进 pinned RAM，腾出 VRAM 给 expert slots；min 20480 是硬下限 | 32K 上下文独占约 0.45 GB VRAM，等于少 300+ 个 slots |
| `--max-context 32768` | 与 `--kv-resident 20480` 的配对：>20480 才开始流式；32768 时 RAM 侧约 0.45 GB | 更大上下文只增 RAM，不增 VRAM 收益 |
| `--batch 1` | BATCHING L152-157：只有「专家大部分在 VRAM」才推荐并行；8 GB 明确不在其列，且每 slot 抢 0.56 GiB | 拉起 2 个 slot 就可能把 expert cache 压到 0 |
| `--vram-reserve-mib 512` | DETAILS L378-398：<256 MiB free 报 LOW；留 512 让驱动不至於到系统内存 | 隐性 7× 变慢，日志仍「启动成功」 |
| `--memory-limit-mib` 不写 | help.txt L90-92：仅容器/cgroup 需要 | 裸机写了反而压低 parking 地板 |
| `--vram-elastic` 不写 | VRAM_ELASTIC L64：resident 模式直接被拒 | 400，且白改配置 |

**备选（更保守，不锁页）**：把 `--resident-experts` 换成

```
--mmap-experts --resident-budget-gib 20
```

依据：DETAILS L223-232 —— 预算模式「把 profile 排名最热的 N GiB 专家拷进 RAM，其余从文件读」，隐含 `--mmap-experts`，同样留 4 GiB，并且**在 Windows 上被可用 commit limit 截断并上报**。代价是剩下的 ~7 GiB 专家仍走盘（但 0.1.40.2 起会额外要 ≥1.5 GiB 缓冲缓存，实测 20-32 GB 机上 7%-118% 更快、盘读降到 1/3-1/6，[TROUBLESHOOTING](https://github.com/Niko1221/Strata/blob/main/docs/TROUBLESHOOTING.md) L264-270）。

若出现卡顿/系统假死：`set STRATA_RESIDENT_PIN=0`（改可换页，DETAILS L249-250 明说 `--pcie-frac 0` 或它给出 mapped 模式的逐位相同答案）。

## 6. 模板 B：Q2_0 硬要跑

Q2_0 需要 experts 34 GB（[MODELS](https://github.com/Niko1221/Strata/blob/main/docs/MODELS.md) L126），官方判据 44 GB RAM；官方给的「小内存大卡」例子是 **32 GB + 24 GB 卡**（L137-141），本机是 8 GB 卡，连 Coder 档（32 GB + 12-16 GB）都不到。

所以 Q2_0 只有一种跑法：**纯 mmap，接受盘速**。

```bat
strata serve --model Qwen3.8-Flash-Next-Q2_0 --gpus 0 ^
  --mmap-experts --resident-budget-gib 18 ^
  --expert-cache auto --expert-cache-per-layer ^
  --kv int8 --kv-streaming on --kv-resident 20480 ^
  --max-context 16384 --batch 1 --vram-reserve-mib 512
```

预期：约 12 GB 专家每次命中都要从 NVMe 读，decode 由盘随机读主导；help.txt L253-255 给的量级是 cold 71.97 vs warm 34.78 ms/token（同一放置）。**这不是「能用」，是「能起」**。要真正可用，得把 RAM 加到 44 GB 以上或换 24 GB 卡。

`--kv-grow` 在这两个 125B 模板里都**不能加**：它要求每个 expert 都在 RAM（DETAILS L218），34/24 GB 都超过 27 GiB。它适合的场景是「大 RAM + ≤24 GB 卡 + ≥128K 上下文」。

## 7. 模板 C：35B-A3B（qwen36 路径）—— 为什么这族开关全废

【本机实测】本机唯一引擎 0.1.54 里，`--family qwen36` 走的是另一条 engine path（日志前缀 `strata-q36:`），它对 low-RAM 整族开关逐条报**忽略**：

```
strata-q36: ignoring --resident-experts (not an option of this engine)
strata-q36: ignoring --mmap-experts (not an option of this engine)
strata-q36: ignoring --resident-cpu-experts (not an option of this engine)
strata-q36: ignoring --kv-resident 20480 (not an option of this engine)
strata-q36: ignoring --kv-grow (not an option of this engine)
strata-q36: ignoring --expert-cache 512 (not an option of this engine)
strata-q36: ignoring --memory-limit-mib 24000 (not an option of this engine)
```

（来源：`C:/Project/local_model/strata/install/res-A1..A6.log`、`res-B1..B3/B5.log`，另有 S/T 组对 `--mmap-experts` / `--resident-cpu-experts` 的同样报错。）⇒ **35B-A3B 的 low-RAM 开关链不存在**，它只有 `--expert-slots` / `--parallel`（= `--batch`/`--slots` 语义）/ `--kv` / `--prefill` / `--mtp`。

真正的闸（每次启动都停在这）：

```
strata-q36: ...: 753 tensors (layout checked), 4.40 GiB on the GPU in ~2 s
             (the routed experts are placed after the engine's buffers), context N cells,
             prompt chunk 512, MTP block loaded, X GiB of VRAM free
strata-q36: not enough VRAM left for the hybrid experts' buffers and slots
             (1159 MiB needed, Y MiB free after the weights, the context and the sessions):
             use fewer slots (parallel / --batch), a shorter --max-context
```

【本机实测】同一台 8 GB 卡，Y 随上下文变化：4K→817 MiB、2K→917 MiB、16K→217 MiB、32K→0 MiB；需求 1159 MiB（`--expert-slots 1` 反而 1235 MiB）。**2K 上下文就是最宽松的一点，仍差 242 MiB。**09:30 前 20+ 组配置（含 `--kv q4_0`、`--expert-slots 1/2/4/8/32`、`--batch 1`、去 vision、去 MTP）无一过闸。

结论：8 GB 卡上 35B-A3B（UD-Q4_K_XL 22.85 GB）**不可能靠开关救活**，官方 hybrid 模式的最低门槛是 **12 GB**（8K 4 slots / 32K 0 slots，[QWEN36](https://github.com/Niko1221/Strata/blob/main/docs/QWEN36.md) L85）。要么换 ≥12 GB 卡，要么等更小的量化档（官方只发 UD-Q4_K_XL 22.9 / UD-Q6_K_XL 32.6 / Q8_0 37.8 GB，[MODELS](https://github.com/Niko1221/Strata/blob/main/docs/MODELS.md) L263-291）。

若强行在 12 GB 卡上跑，qwen36 侧推荐：

```
--family qwen36 --parallel 1 --expert-slots auto --kv q4_0 --max-context 8192 --prefill 1024
```
（`--parallel` 1..8，每 slot 32K 时 1.5 GB，QWEN36 L23/L74-77；`--batch 2..4` 时 chunk 建议 ≤1024，L105）

## 8. Windows 专章

1. **commit limit 是真的上限**：`--resident-budget-gib` 会被 Windows 可用 commit limit 截断并上报（DETAILS L232）；页面文件给大一点才有 27 GiB 的余量。
2. **锁页会反噬**：32 GB 机用 resident 模式「把预算锁进 RAM，OS 和 CPU worker 没地方」（[TROUBLESHOOTING](https://github.com/Niko1221/Strata/blob/main/docs/TROUBLESHOOTING.md) L260-262，issue #649）。旋钮：`STRATA_RESIDENT_PIN=0`（可换页）、`STRATA_PIN_GUARD=0`、`STRATA_PIN_RESERVE_GIB=N`（默认 4）。
3. **expert cache 超配在 Windows 不报错**：驱动把多出的页换到系统内存，启动正常、速度从 100 掉到 14 tok/s。判据只有一行日志：`... MiB of VRAM free with everything loaded`，<256 报 LOW（DETAILS L378-398）。
4. **`--vram-elastic` 在本案不可用**：resident 低内存模式直接互斥（VRAM_ELASTIC L64）。想动态腾 VRAM 就得放弃 resident，改用 mmap + 手动 N。
5. **PLE 表别进 RAM**：125B 侧第二 shard 是 29 GB 查表，`--ple-io ram` 会 VirtualLock 整表（help.txt L12-15）——31 GB 机上必炸；保持默认 `direct`。
6. **不要开多卡/peer**：`--vram-elastic` 与 `--peer-device` 互斥，且低内存模式官方建议单卡（DETAILS L247-248）。

## 9. 启动后必须核对的 3 行日志

```
1) resident RAM: ... blob reads from the file          ← 稳态应为 0（DETAILS L236-237）
2) ... MiB of VRAM free with everything loaded          ← 要 >256，最好 >512（DETAILS L378-398）
3) expert cache: N slots, hit rate ...                  ← per-layer 下 8 slots/层≈21.4%，64/层≈70.4%（help L213-214）
```

任一条不达标，按序调：`--max-context` 降 → `--expert-cache` 降 N → `--vram-reserve-mib` 加 256。

## 10. 未核源 / 待验证

- **Gyro-S 的 experts 体积**：27.6 GB 是模型文件总大小（本机 `.gguf.part`），不是官方 experts 数；表里 ~24 GB 是按 125B/Q2 与 dense 比例的推算【未核源】。而且它**尚未下载完**，res-A/B 那批日志全是 qwen36 的，125B 侧我没有一条真启动记录。
- **`--expert-cache auto` 在 0.1.54 是否被接受**：docs 写 auto，本机 help 只写 N【未核源】。一条命令即可验：跑起来看是否报 unknown option；不接受就换 `--expert-cache <数值>` 并用日志里的 free VRAM 反推。
- **`--vram-reserve-mib` / `--pcie-frac` / `--resident-budget-gib` / `--adapt-every` / `--expert-slots` 未出现在 0.1.54 的 `--help`**，但二进制含串（`--parallel`、`--low-ram` 不含）。它们的行为以 upstream docs 为准，本机版本可能有差异。
- **KV cell 与 13.7 KB/token 的口径未打通**：help 说 `--kv k8v4` 816 B/cell vs int8 1056 B/cell，docs 说 13.7 KB/context token；两者换算需要引擎启动日志的实测值，本文不做推算。
- 结论里的 4 GiB「卡扛的 experts」是按 8 GB 卡减 dense/ KV/slots 估的，真实值以启动日志 `... MiB of VRAM free` 为准。

## 11. 一页速查

```
125B 判据：experts − 卡扛 ≤ 31 − 4 = 27 GiB
  Q2_0   experts 34 → 需 44 GB RAM  → 本机❌（纯 mmap 才起得来）
  Gyro-S experts ~24 → 本机✅（--resident-experts）
开关配方（Windows 单卡小显存）：
  基础层：--resident-experts（= mmap + resident-cpu-experts，4 GiB headroom）
  替代层：--mmap-experts + --resident-budget-gib N（可换页、commit limit 封顶）
  显存层：--expert-cache auto --expert-cache-per-layer --vram-reserve-mib 512
          （绝不超配：Windows 不报错、只掉速 7×）
  上下文：--kv int8 --kv-streaming on --kv-resident 20480 --max-context 32768
  并发：  --batch 1（8 GB 卡没有第二个 slot 的位置）
  禁用：  --kv-grow（要求全部专家在 RAM）、--vram-elastic（与 resident 互斥）、
          --shared-expert-arena（仅 Linux）、--ple-io ram（29 GB 表会锁满 RAM）
35B-A3B：low-RAM 整族被 q36 路径忽略；8 GB 卡缺 1159 MiB 的 hybrid buffers+slots → 换 ≥12 GB 卡
```

---
本报告所有外部事实均来自 github.com/Niko1221/Strata 的 docs；本机事实来自 `tmp/stratahelp/help.txt`、`strata/install/res-*.log`、以及引擎二进制字符串扫描。未启动、未停止任何引擎或服务。
