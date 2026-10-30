# Strata 英文社区低显存实测（8 GB / 12 GB 档）

> 侦察范围：r/LocalLLaMA、r/LocalLLM、HuggingFace 模型 discussion、GitHub issue（英文一手）、X、Discord 公开搬运
> 采集时间：2026-10-30（Asia/Shanghai）｜侦察员：情报侦察子代理
> 证据规则：**每个数字都带 URL**；只有"听说能跑"没有数字的，一律标【未核源】；明确区分「单次首发成功」与「反复问都正确」

---

## 0. 结论先行（5 条）

1. **8 GB 显存确实能跑 125B MoE，但门槛不是显存，是"内存 + SSD 随机读 + vram-reserve"三件套。** 8 GB 档的公开实测集中在 **decode 20–40 tok/s、prefill 130–700 tok/s**；机器共同点几乎都是 **32–64 GB 内存 + NVMe + Linux**。
2. **12 GB 档已经能跑出"可用"体验**：Linux + 30 GB RAM 的 4070 SUPER 报 40–50 tok/s（中位 48.4）；Windows + 63.8 GB 的 4070 Ti 报 decode 50.2、32K prompt 1443 tok/s；0.1.52 引擎把 12 GB 卡推到 50–75 tok/s。
3. **pagefile / 虚拟内存在这件事上要拆成四种完全不同的现象**，混为一谈会得出相反结论：①Windows 记账幻觉（committed 虚高，其实没分页）②commit limit 触顶 → 静默 0xC0000409 崩溃 ③pagefile 状态改变引擎的 expert cache 自动值（差 30%）④真实 paging（换入换出，SSD 300 MB/s 常读）。**只有 ④ 才是"pagefile 在帮忙"，而 ④ 恰恰是性能崩塌的那一档。**
4. **"跑起来了"和"反复问都正确"是两件事**。8 GB 档唯一做过任务级验证的是 GitHub #4517（21/21 required、12/12 sanity、Hermes 4 任务 12/12 满分）；Reddit 上最高赞的 8 GB 配方（1x5p822）在另一张 8 GB 卡上**复现失败**（prefill 只有 50 tok/s）。
5. **X / Discord 没有可核一手来源**（x.com 无公开 API、xcancel 451、nitter 000、Discord 无公开导出）。任何"Discord 里有人说"的转述都应视为【未核源】。

---

## 1. 取证方法与证据分级

### 1.1 哪些渠道真的取到了

| 渠道 | 可用性 | 取证方式 |
|---|---|---|
| Reddit | ✅（仅 RSS） | `*.json` 一律 403，redlib 镜像全挂，pullpush 429；**唯一可用是 Atom RSS**（限流 ≈1 请求/45 s，需轮换 UA） |
| HuggingFace discussion | ✅ | HF API 直读 |
| GitHub issue | ✅ | REST API 403（共享出口 IP 被限流），改解析 issue HTML 页内嵌 JSON |
| X / Twitter | ❌ | 无公开 API，xcancel 451、nitter 000 |
| Discord | ❌ | 无公开 API / 导出 |
| Bing / 搜索引擎 | ⚠️ | 可用，但 `site:reddit.com` 检索退化，10 组查询全返回知乎/appinn/smzdm 等中文站 |

### 1.2 证据分级（本文用法）

- **A 级**：带完整硬件、量化、参数、上下文、tok/s 的一手贴（作者自述实测）。
- **B 级**：有硬件 + 有数字，但缺参数或缺上下文。
- **C 级**：有硬件 + 定性结论（"能跑，很慢"），无数字 → 标【未核源】。
- **反例**：明确报失败 / OOM / 不可用的样本，单列，不与成功样本混算。

---

## 2. 8 GB 档：谁真跑起来了，多少 tok/s

### 2.1 主参考贴：r/LocalLLaMA 1xft2ae（作者本人配方，A 级）

https://www.reddit.com/r/LocalLLaMA/comments/1xft2ae/have_8_gb_of_vram_and_32_gb_of_ram_you_can_run/

u/BleynSpecnaz，2026-10-26，**Linux**；RTX 5060 Laptop **8 GB** + Ryzen 9 8945HX + **32 GB DDR5-5200** + NVMe 5200 MiB/s + PCIe 4.0 x8；量化 **Gyro-S**。

| 场景 | 上下文 | Prefill (PP) | Decode (TG) |
|---|---|---|---|
| Chat | 262144 | 800–970 | 30–40 |
| Chat | 131072 | 930–1040 | 30–45 |
| Agentic | 262144 | 520–740 | 30–40 |
| Agentic | 131072 | 670–890 | 30–45 |

参数（可复制）：

~~~bash
--mmap-experts
--kv-resident 20480
--vram-reserve-mib 500      # 作者建议 900
--pcie-frac 0.35
# env
STRATA_RESIDENT_HEADROOM_GIB=4   # Windows 上要更大
# MTP 关闭（作者：10 GB 以上再开）
# Vision 跑 CPU（独立进程，可挪到 swap）
# 多会话：--conversation-cache-mib 4096 --slots 2 --min-tokens 8000 --min-free-mib 1024
# 不要 --parallel
~~~

**关于虚拟内存的原话**（本节最重要的一条）：
- Linux 上建 **32 GB 专用 swap 分区** + systemd `[Service] MemorySwapMax=0`，把服务**钉在内存里**（即：swap 存在，但**禁止**这个进程用）。
- 警告：乱调参数会把模型 "push the model into heavy swapping"。
- **"All tests were run on Linux…If you use Windows, try allocating less memory…reduce throughput significantly, but also lowers the risk of running out of memory."**
  → 作者自己承认：**这套配方搬到 Windows 要主动降配**，否则就是拿崩溃换速度。

同帖评论串（都是 8 GB 档一手数据）：

| 用户 | 硬件 | 量化 | 上下文 | Decode | Prefill | 备注 |
|---|---|---|---|---|---|---|
| u/kassany | RTX 3050 8 GB + R7 5700G + 32 GB DDR4-3200 | Gyro-S | — | **20–25** | 300–700 | B 级 |
| u/Switchboy1 | 2070 SUPER 8 GB + 32 GB | — | — | **26**（opencode，稳定） | — | B 级 |
| u/lorendroll | 3070 Laptop 8 GB + 32 GB | Coder | 128K | **25** | 600 | q4 KV，无 MTP |
| u/SecretHelicopter2371 | 8 GB + **64 GB** | IQ3_XXS | 108K | **31–39** | — | 原话 "very tight" |
| u/Jcqn_ | 5060 8 GB + 64 GB | — | — | 60–70 | **~300** | prefill 是瓶颈 |

反例 / 边界：
- **u/dampflokfreund**：2060 Laptop **6 GB** + 32 GB，**Windows**，PP 130 / TG **6**（IQ3_XXS 13），"maybe Linux is better"。
- **u/bluep1x**：3060 Ti + 32 GB DDR4，**10–12 tok/s**，原话 "I think some of it is going to memory swap. Is there any way to pin it to system memory as you did on Linux?" ← **这是"用户直觉认为是 pagefile 的锅"的典型样本，但没有任何 /proc 或 perf 证据**。
- **作者（Niko1221）的边界判定**：Gyro-S 活跃参数约 5.3 GB VRAM；**小于 8 GB 的卡，PP 超不过 50 t/s、TG 超不过 8 t/s**。
- 作者复测 Gyro-M @ 131K：PP 550–670 / TG 20–30，**长跑掉到 TG 1–2**（RAM/SSD 重压），建议 8+ GB VRAM 且 **48+ GB RAM**。

### 2.2 8 GB 最高赞配方：1x5p822（A 级 + 明确的反例复现）

https://www.reddit.com/r/LocalLLaMA/comments/1x5p822/qfn_q_2_strata_configs_for_8gb_vram_and_32gb_ram/

标题即结论：**"QFN Q_2 strata configs for 8gb vram and 32gb ram. 36 tps | 340 prefill 176128 context."**

~~~bash
--expert-cache 2000
--prefill auto
--spec 2
--max-context 176128
--kv q4_0
--resident-experts
--kv-resident 20480
--pcie-frac 0.00
--spec-min-p 0.70
--adapt-every 1
--adapt-swaps 80
--adapt-decay 0.97
# MTP 关闭
~~~

- 实测：**36 tps，有时 28；上下文几乎占满时 22**；prefill 340。
- SSD 读 ~600 MB/s，"prefill is more ssd bound"。
- harness = pi；**3 次上下文压缩后仍正常**（这是"反复问"意义上最接近的证据，但只是"没崩"，不是正确率）。

**复现失败样本（同一帖，必须并列）**：u/TheCat001，RX 6600 8 GB + **31 GB 可用 RAM**，照抄参数 →

- decode 尚可 **10–15 t/s**；
- **prefill 只有 50 t/s**（"can't beat laws of physics"）；
- SSD 被持续按 **300 MB/s 常读**，担心寿命；
- 作者（Strata 作者）说 Q2 这个模型**要吃 ~48 GB RAM**，他只有 31 GB。

OP 不服："Decode was 47–50 when I had low prefill like you are getting… There is something you are doing wrong."
→ **这就是本文要区分的核心：同一份配置，在 32 GB 内存的机器上是 36 tok/s，在 31 GB 且 AMD 卡上是 10–15 tok/s。差异不在参数，在"内存够不够把专家留在 RAM"。**

同帖另一条 12 GB 数据：u/Present_Resource4022 —— 12 GB VRAM / 32 GB RAM，**Gyro-M** + 自建 fork https://github.com/Gitshop77/GyroStrata ，vision/MTP 全关，**36 mean tps、1700 TPS prefill**（接近满上下文）。

u/himiaoxin 的关键经验：**8 GB 卡上 MTP 的 draft 层白吃 VRAM，prefill 收益几乎为零** → 与 #4517、#1375 独立吻合（见下）。

### 2.3 其他 8 GB 一手：1xdoclb（3070 + 64 GB，A 级）

https://www.reddit.com/r/LocalLLaMA/comments/1xdoclb/

u/SetNo7692：R5 5600 + **4×16 GB DDR4-2666（超到 3000）** + RTX 3070 8 GB（**PCIe 3.0 x8**，b350 板）+ Ubuntu server。
IQ3_S + **262144 ctx** + `--kv int8` + `--vram-reserve-mib 512` + `--kv-resident 20480` + `--adapt-async 1` + `--spec 4` + `--spec-min-p 0.5` + `--vision`(cpu) + `--prompt-cache-tail`。

- 标题数字：**1000 PP / 40 tps**；关掉 route tail skip 后 decode **35 tps**。
- **MTP 在这张卡上开不开差不多**（第三个独立样本印证"8 GB 别开 MTP"）。
- 评论补充：`--spec-min-p 0.7` + `STRATA_KV_ROT=1` 能提速（多人验证），有人照抄配置 **+10 t/s**。

### 2.4 GitHub issue 里的 8 GB 台账（全是英文一手）

| Issue | 硬件 | 量化 | 关键数字 | 证据等级 |
|---|---|---|---|---|
| [#4517](https://github.com/Niko1221/Strata/issues/4517) | GTX 1070 Ti **8 GB**（sm_61）+ R9 3900X + 32 GB DDR4 + 16 GB zram | Gyro-S 58.5 GB | 32K PP **133–145**、48K PP **173**；decode **30–34** | **A**（唯一做了任务级验证） |
| [#2477](https://github.com/Niko1221/Strata/issues/2477) | RTX 3080 Laptop **8 GB** + Linux | Coder IQ1_M | 32768 ctx，`--kv int8`，**≥13 tok/s**，0 失败请求 | A− |
| [#2248](https://github.com/Niko1221/Strata/issues/2248) | RTX 4060 8 GB + RTX 2060 6 GB（合并 14.3 GB）+ 62 GB | 125B MoE | **~36 tok/s** 稳定 | B |
| [#1375](https://github.com/Niko1221/Strata/issues/1375) | RX 6600 XT **8 GB** + Xeon E5-2678 v3 + 64 GB DDR3 | — | 可用；**去掉 MTP 后 prompt read 快 20–35%** | B |
| [#2212](https://github.com/Niko1221/Strata/issues/2212) | RTX 3070 8 GB + 128 GB RAM | — | 长任务整机重启，判定**电源**而非 OOM | C（故障排除） |

**#4517 值得单独展开**（8 GB 档信息密度最高的一手）：u/raidbeforebed，2026-10-28，Pop!_OS 24.04，Strata 0.2.7 / engine 0.1.52，Gyro-S 58.5 GB + MTP，vision off。

- 跑通了：**21/21 required 请求、12/12 sanity、Hermes 4 个 agent 任务 12/12 满分**（64K 上下文），模型加载 13–18 s。
- 核心结论一句话：**"the VRAM reserve is what decides it"**（决定成败的是显存预留，不是别的）。
- 排查教训（对本次任务特别有价值）：为了查"请求无返回"他花了几个小时 **"chasing page cache, swap and swappiness, all of which looked plausible and were wrong"** ← **page cache / swap / swappiness 三个都很像真凶，全都是假线索。**
- page-cache 算术：24.2 GiB 专家 vs 21.3 GiB 可用 page cache = **26 趟**，每个 prompt ~**519 GB** 的盘读。
- **反直觉结论**：8 GB 上 **Coder IQ1_M 比 Gyro-S 更合适** —— 12/12 vs 10/12、超时 0 vs 2、下载 29.6 vs 58.5 GB、27K prompt 时 **181 vs 93 tok/s**（Gyro-S 到 37K 掉到 41）、decode **20–22 vs 30–34**、12 个任务总耗时 **95 vs 158 min**。

### 2.5 Windows 上的 8 GB（HF discussions，A 级）

HuggingFace **ISTA-Coder discussion #24**，u/theacidblack，2026-10-11，**Windows**（D: 路径 + strata.exe + 端口 8080）：

- 3070 Ti Laptop **8 GB** + 32 GB DDR5-4800，Coder IQ1_M，engine 0.1.44；
- **~20 t/s** → 加 draft 2 + min-p 0.20 后 **29 t/s**；prefill **~210**（已预热）；
- 同时还在跑 Pi agent / OpenCode / 浏览器 / Blender；
- 参数：`--pack coder-iq1_m --expert-cache auto --prefill auto --spec 3 --spec-min-p 0.2 --mtp --max-context 131072 --kv q4_0 --mmap-experts --kv-resident 20480 --vision(gpu:false) --vram-reserve-mib 745`，temp 0.6；
- 主观质量：优于 35B-a3b。

→ **Windows + 8 GB 是可行的**，代价是 prefill 只有 210 左右（Linux 同类机器能到 600–1000）。

### 2.6 8 GB 档小结

- **能跑**，不是传闻。但**决定 tok/s 的是内存容量与 SSD 随机读**：32 GB 是及格线，48–64 GB 才是舒适区（作者本人对 Gyro-M 的建议就是 48+ GB）。
- decode 分布 **20–40 tok/s**，prefill 分布 **130–1000 tok/s**（Windows 明显偏低）。
- **8 GB 上 MTP 基本是负收益**（3 个独立样本：#4517、#1375、himiaoxin）。
- **8 GB 上 Coder IQ1_M 往往比更大的量化更实用**（#4517 的量化对照）。

---

## 3. 12 GB 档：从"能跑"到"能用"

### 3.1 标杆：1x7sbdc（Linux + 30.4 GB RAM，A 级）

https://www.reddit.com/r/LocalLLaMA/comments/1x7sbdc/qwen38flashnextgsqrco_iq3_s_4050_toksec_decode/

u/bodhi371：**12 GB VRAM + 32 GB RAM + NVMe**，IQ3_S（SC117 abliterated），**decode 40–50 tok/s、prefill 1300–1500 @131K**（44K thinking）。

- fork：https://github.com/bodhi37/strata
- 配方：https://github.com/bodhi37/Qwen3.8-Flash-12GBRAM-32GBVRAM-SSD-Recipe （**Linux only**，sway + kitty 仅 ~1 GB RAM）
- 机器：R9 9900X + DDR5-6200 + RTX 4070 SUPER **12 GB（12,282 MiB）** + **30.4 GiB RAM** + **30 GiB zram swap** + SPCC 1 TB NVMe（DRAM-less）
- README 统计：decode 中位 **48.4** / p90 **50.9** / max **57.8**；冷 prefill **1350–1450**（32K chunks、2K tiles）；prefix 命中 **18.8k t/s @65K**
- 模型结构：48 层 / 512 专家 top-10 / emb 2560 / 24 heads / 2 KV heads / 原生 262144；每 token 480 blob；IQ3_S arena 46.8 GiB、每 blob 2.046 MB、每 token 982 MB

参数（长，但是目前最完整的 12 GB 配方）：

~~~bash
--mmap-experts
--hot-ram-gib 26.0            # mlock；STRATA_LRU_GIB=24 STRATA_LRU_EXACT=1
--expert-cache 1700 --expert-cache-per-layer   # STRATA_VRAM_EXPERT_MIB=4100
--adapt-swaps 24              # STRATA_ADAPT3=1
--pcie-frac 0.15
--pool-workers 11
--kv q4_0
--max-context 131072
--prompt-cache 2
--prefill 32768
--spec 5 --spec-min-p 0.8 --spec-split --suffix-draft 3 --mtp
# env: STRATA_RSPLIT=1 STRATA_STATIC_TIER=1 STRATA_NO_HITS=1 STRATA_NO_LA=1 STRATA_EARLY=1 STRATA_EARLY_CPU=23
~~~

投机接受率 **75–85%**，prompt cache 复用 **92.9%**。

**同帖反例（重要）**：
- u/Xantrk：**32 GB RAM + 12 GB VRAM 笔记本**（系统自己吃 5–6 GB）→ **默认配置直接 OOM**；降上下文后最多 **3–4 t/s**，还看到 SSD1 莫名写入。
- u/tehnomad：5600X + 32 GB DDR4 + 3060 **12 GB**，IQ3_S → 只有 **3–4 tok/s**。
- bodhi371 的归因：**换 SSD**（随机读 0.6 → 3.5 GB/s）后 decode 立刻**翻三倍**。→ 12 GB 档的瓶颈常常是**盘**，不是卡。

### 3.2 GitHub 12 GB 台账

| Issue | 硬件 / OS | 量化 / ctx | 数字 | 备注 |
|---|---|---|---|---|
| [#3984](https://github.com/Niko1221/Strata/issues/3984) | RX 6700 XT **12 GB** + R7 5800X + 64 GB，Ubuntu 26.04 | IQ2_XS / 128K | **58 tok/s** decode（pcie-frac 0.2）/ **700** prefill | experts 33.02 GiB 在 RAM；GPU expert cache 4,282 experts ≈5.75 GiB；**0 B swap** |
| [#4234](https://github.com/Niko1221/Strata/issues/4234) | RTX 4070 Ti **12 GB** + i5-13600KF + 63.8 GB，**Win10 19045** | IQ3_S / 131072 | decode **50.2**（44.7–60.3）、TTFT 0.77 s；32K prompt **1443.8** tok/s | agent 会话 decode **56.2**、prompt 12,762、TTFT 3.06 s |
| [#3097](https://github.com/Niko1221/Strata/issues/3097) | RTX 5070 Ti Laptop **12 GB** + Core Ultra 7 255HX + 63.4 GB，**Win11 26200** | IQ3_XXS / 262144 | decode **108.8**（92.7–122.7）、TTFT 0.41 s；30 题稳态 **143.3** | 编码 prompt 115.9 / 124.4 tok/s |
| [#1250](https://github.com/Niko1221/Strata/issues/1250) | RTX 3080 **12 GB** + 62 GB，Ubuntu | IQ2_XS / 262K | **整机 OOM**（0.1.40.1） | 崩在 FileExpertSource 分配 page-locked 副本；0.1.31 正常（峰值 47.7 GiB） |
| [#1194](https://github.com/Niko1221/Strata/issues/1194) | RTX 4070 SUPER **12 GB** + 31 GB | Q2_0 | 0.1.39 **58–69** → 0.1.40 **29–33** tok/s | O_DIRECT 无缓冲读所致，`STRATA_UNBUFFERED_LOAD=0` 恢复 |
| [#3940](https://github.com/Niko1221/Strata/issues/3940) | RTX 5070 **12 GB** + 47.9 GiB，Win11 | IQ3_XXS / 128K | 仅 bench 清理 bug | 无性能数字 |

### 3.3 只有 16 GB 内存的 12 GB 卡：1x1tclb（A 级，最极端样本）

https://www.reddit.com/r/LocalLLaMA/comments/1x1tclb/qwen_38_flash_nextgsqrcoiq2_xs_at_21_toks_on_just/

u/zyxciss：RTX 3060 **12 GB** + **单条 16 GB DDR4**（另一条烧了，单通道）+ IQ2_XS + **262K ctx**：

- **~21 tok/s**（冷缓存），**>24 tok/s** 热缓存，100% bit-exact 无 gate pruning；
- 有人问"我只有 8 GB VRAM + 16 GB RAM 呢"，答：**"would still work 262k Context and 10-15tg/s"**【未核源：作者推断，非实测】；
- u/Open-Adhesiveness-86 的质疑很到位：**68 GB 权重 + 16 GB RAM，本质上靠 mmap + page cache 撑着**，应该用 `/usr/bin/time -v` 看 **major page fault** 才能证明是"专家预测"在起作用，还是"page cache 恰好命中了热子集"。
  → **这是"低内存高 tok/s 到底靠什么"的方法论争点，值得记住：只有 major page fault 计数能分辨。**

### 3.4 12 GB 的版本效应：0.1.52 是分水岭（1xh1asc，A 级数字 + C 级质量争议）

https://www.reddit.com/r/LocalLLM/comments/1xh1asc/

- u/Squale279：i5-11400 + **RTX 12 GB** + **96 GB RAM**，IQ3_S，128K 上下文 —— **0.1.50：35–45 tps → 0.1.52：50–75 tps**；**384K 上下文仍有 55–65 tps**。
- u/CertainPerformance33：Legion Pro 7，Core Ultra 9 275HX + 64 GB + **RTX 5070 Ti 12 GB** —— 0.1.52 后 **70–75 t/s，但"模型明显变差，尤其是长乌克兰语文本"**。
- u/MAPSOIL：6700 XT + 128 GB，IQ4_XS —— 同一引擎**昨天 25 t/s、今天 13–14 t/s**（方差极大，勿把单次数字当基线）。
- 质量争议主线：Dreeew84 指出引擎会"优先用在 GPU 上的专家"，等价于 **STRATA_ROUTE_TAIL_SKIP** 的取舍；他做过 15 个植入 bug 的递增难度测试，"性能在难度 3 左右开始崩"，而**默认 skip=7 在那批任务上与不 skip 一样好**。
- Niko1221 的回应：每个版本都在**自己做的 65 组任务集**上评估"变笨"程度，会牺牲质量的功能改成可选（如 KVA，prefill +30%）。
- 反方（u/karmaisnonsense）：**"没有数字，全是轶事"**，要求 perplexity / 散度指标。
  → **本节对"区分单次首发成功与反复正确"最有价值：同一引擎版本更新，速度 +40%，长文本质量主观下降；社区里没有任何一方拿出可复现的量化指标。**

### 3.5 12 GB 档小结

- **可用区间：decode 35–75 tok/s，prefill 700–1500 tok/s**（Linux + 32 GB 起；Windows + 64 GB 也能到 50–75）。
- **失败的共同点不是显存，是内存**：12 GB + 32 GB 且系统吃掉 5–6 GB 就 OOM；12 GB + 16 GB 只能靠 IQ2_XS + page cache 硬撑到 21 tok/s。
- **PCIe 代际与盘速权重很高**：3070 在 PCIe 3.0 x8 上仍能 40 tps（1xdoclb），而 DRAM-less SSD 直接把 12 GB 机器打到 3–4 tps（1x7sbdc 反例）。

---

## 4. pagefile / swap / 虚拟内存：必须拆成四层（本次侦察的核心发现）

社区里 90% 关于"pagefile 有没有帮上忙"的讨论是**把四种现象混为一谈**。逐层拆开：

### 4.1 第一层：Windows 的记账幻觉（committed 虚高，但没真分页）

GitHub [#141 "Pagefile and RAM usage"](https://github.com/Niko1221/Strata/issues/141)，u/rrrrrex，RTX 5060 Ti 16 GB + R5 5600 + 48 GB DDR4 + IQ2_XS：

- 任务管理器读数：dedicated VRAM **15/16**、shared **23/24**、RAM **44/48**、committed **64/72**；
- 算下来 strata.exe = 36 GB RAM + 15 GB VRAM + 23 GB shared = **74 GB**，看起来"pagefile 一定在拼命工作"；
- 但 resmon 里只看到 n-gram 的读，**没有 pagefile 的读写**。

**Niko1221 的解释（本报告最重要的一段机制说明）**：
- shared GPU memory 就是**同一份 RAM 被 pin 住**，Windows 把它记两次；
- Windows 还会把 VRAM 计入 "RAM + pagefile" 的 commit 上限，所以 **committed 看起来爆表，但其实没有真分页**（page file 是被 **reserved**，不是 **used**）；
- IQ2_XS 的专家 ~35 GB 在 RAM，**瓶颈是 RAM，不是 VRAM+RAM**；
- 一句话判据：**"please reopen if you see real paging (disk reads of the page file)"**。

→ **可操作判据：判断"pagefile 是否在帮忙"，唯一标准是 pagefile 的磁盘读写计数（Windows 资源监视器"内存"页的硬错误/秒 + 页面文件 I/O），不是 committed 数字、不是任务管理器里那根共享显存条。**

### 4.2 第二层：commit limit 触顶 → 静默崩溃（pagefile 太小会直接死，不是变慢）

GitHub [#1607](https://github.com/Niko1221/Strata/issues/1607)，u/masel，RTX 5060 Ti 16 GB + **80 GB RAM** + Win11 26200，UD-IQ4_XS 55.4 GB experts，`--max-context 393216`：

- 引擎**静默退出，退出码 0xC0000409（3221226505）**，而此时物理内存还有 **7.0 GiB** 空闲；
- 根因：Windows 的 **commit 上限**（RAM + pagefile 之和）先到顶；
- 代码层面：`conversation_memory.cpp` 的 `conversation_available_memory()` 只读 **ullAvailPhys**（`expert_source.cpp` 已经读 ullAvailPageFile 了）；
- **v0.1.42 修法**：改成 `min(avail RAM, avail commit)`，并在启动时打印 commit 余量与 pagefile 建议；
- 但 0.1.43 复测**仍在 111.88 / 111.93 GiB 处崩**（physical 7.0 GiB 可用）→ **修复不彻底，仍在活跃 bug**。

补充样本 GitHub [#1630](https://github.com/Niko1221/Strata/issues/1630)（u/rekaXua，RX 7900 XTX 24 GB，Win10 LTSC，pagefile 100 GB 固定 + 4–35 GB 系统托管）：所谓"commit 一秒跳 70 GB"其实是 **WER 在给刚崩的进程做快照**；真因是 HIP 启动失败。0.1.42 起 Windows HIP 的 `--prefill auto` 封顶 6144，commit 才平稳。

→ **可操作结论：Windows 上 pagefile 的作用首先是"抬高 commit 上限、避免 0xC0000409"，其次才是"溢出到磁盘"。把 pagefile 关掉去"省 SSD"，换来的是随机崩溃。**

### 4.3 第三层：pagefile 状态会**改变引擎行为**（同样的卡、同样的二进制，专家缓存差 30%）

GitHub [#3692](https://github.com/Niko1221/Strata/issues/3692)，u/dai8647，Windows HIP：

| 日期 | pagefile 状态 | commit limit | expert cache 自动值 | 剩余显存 |
|---|---|---|---|---|
| 2026-10-18 | **关闭** | 107.8 GiB | **3087 slots，4,456 MiB** | 4.4 GiB 空着 |
| 2026-10-21 | 系统托管 **9 GiB** | — | **4480 slots，7.29 GiB** | — |

同卡、同二进制，**差 1,393 slots（约 30%）**，而 4.4 GiB 显存**白白空着**。
机制：槽位写入后，WDDM 下 free-VRAM 读数接近 0，**缩容循环按四分之一往下砍**，于是"自动"变成"自动变小"。

→ **可操作结论：Windows 上把 pagefile 设成"系统托管"或固定一个够大的值，不只是防止崩溃，还会让引擎的 expert cache 自动值回到正常水位。这是"pagefile 帮上忙"最实在的一条，且完全没人提。**

同类但更严重的一例：GitHub [#1250](https://github.com/Niko1221/Strata/issues/1250)，RTX 3080 12 GB + 62 GB RAM + Ubuntu，0.1.40.1 在 FileExpertSource 分配 **page-locked 副本**时**整机 OOM**（IQ2_XS + 262K）；退回 0.1.31 正常（峰值 47.7 GiB）→ **page-lock / mlock 的额度本身就是一条"隐形低显存约束"。**

### 4.4 第四层：真正的 paging —— 出现就是性能崩塌（不是"帮忙"）

- **#4517 的教训（最干净的证伪）**：作者花了几个小时 **"chasing page cache, swap and swappiness, all of which looked plausible and were wrong"**。他机器上有 16 GB zram swap，但**真凶是 vram-reserve 没设够**。
- **1x5p822 的失败样本**：RX 6600 8 GB + 31 GB RAM，**SSD 被持续按 300 MB/s 常读**，prefill 掉到 50 tok/s → 这就是"内存不够、专家反复从盘上取"的真实 paging 表现。
- **u/bluep1x**（3060 Ti 8 GB + 32 GB，10–12 tok/s）：直接怀疑 "some of it is going to memory swap"，并问"能不能像你在 Linux 上那样把模型钉在内存里"→ **用户直觉指向 swap，但没有证据；按 #141 的判据应先排除记账幻觉。**
- **#4517 的 page-cache 算术**：24.2 GiB 专家 vs 21.3 GiB 可用 page cache = **26 趟**，每 prompt ~**519 GB** 盘读 → 这个量级下任何"swap 帮了大忙"的说法都不成立。

### 4.5 反面对照：Linux 上 swap **存在但没被用**

| 样本 | swap 配置 | 实际使用 |
|---|---|---|
| 1xft2ae（8 GB 作者） | 32 GB 专用 swap 分区 | **`MemorySwapMax=0` 禁止该服务使用**，即"建了但钉死不用" |
| u/iNternBe_（3080 10 GB + 48 GB） | 16 GB NVMe swapfile | 原话 "It remained unused in the measurements"；跑完 240K 后 **Swap used 0 GB**，VRAM 9,568 MiB / free 306 MiB |
| 1x7sbdc（12 GB 标杆） | **30 GiB zram swap** | 未报使用量；zram 是**内存压缩**，不是磁盘 |
| #3984（6700 XT 12 GB） | — | **0 B swap**，58 tok/s 照跑 |
| 1x1tclb（3060 12 GB + 16 GB） | — | 靠 mmap + page cache，非 swap |

→ **规律：能跑的机器，swap 都是"安全垫"而非"工作内存"；一旦 swap 真被用上（1x5p822 反例、1x7sbdc 的 3–4 t/s 反例），性能直接掉一个数量级。**

### 4.6 一句话回答"有没有人提到虚拟内存/页面文件帮忙"

**有，但结论是反的**：
1. **Windows 上 pagefile 的主要作用是抬高 commit 上限**（#1607、#1630）与**让 expert cache 自动值正常**（#3692），不是提供带宽；
2. **真靠 pagefile 提供工作内存的机器，全部落在 3–15 tok/s 那一档**（1x5p822 反例、Xantrk、tehnomad）；
3. **Linux 侧的 swap 都是"建而不用"**（1xft2ae 的 MemorySwapMax=0、iNternBe_ 的 0 GB used）；
4. **唯一明确的 Windows 大内存技巧是 VirtualLock + 工作集下限**：1xfe04h（4090 24 GB + 48 GB，Win10 19045）里引擎自报 "page-locking refused (out of memory); locked 33612 MiB via working-set minimum + VirtualLock ← the one lever still open on a 48 GB Windows box"，并抱怨 "Windows sucks and doesnt pin memory w cuda, so every host->GPU expert copy is CPU-driven"；照此调优后 decode **97 → 142（+45%）**，145K prompt **2076 tok/s**。

---

## 5. 可复制参数：两套最小可用配方

### 5.1 8 GB + 32 GB（Windows 友好，源自 1x5p822 + 1xft2ae 的交集）

~~~bash
--mmap-experts
--resident-experts
--kv-resident 20480
--vram-reserve-mib 900        # 1xft2ae 建议；1x5p822 未设
--pcie-frac 0.15~0.35         # 1x5p822 用 0.00（有 64 GB 内存才敢）
--expert-cache 1700~2000
--kv q4_0
--max-context 131072          # 先跑通再往上加
--prefill auto
--spec 2 --spec-min-p 0.70
--adapt-every 1 --adapt-swaps 80 --adapt-decay 0.97
# MTP 关闭；Vision 走 CPU
# env: STRATA_RESIDENT_HEADROOM_GIB=4（Windows 更大）
~~~

### 5.2 12 GB + 32 GB（源自 1x7sbdc，Linux 为主）

~~~bash
--mmap-experts
--hot-ram-gib 26.0            # mlock，需要 30 GB 内存
--expert-cache 1700 --expert-cache-per-layer   # STRATA_VRAM_EXPERT_MIB=4100
--adapt-swaps 24
--pcie-frac 0.15
--pool-workers 11
--kv q4_0 --max-context 131072
--prompt-cache 2 --prefill 32768
--spec 5 --spec-min-p 0.8 --spec-split --suffix-draft 3 --mtp
# env: STRATA_RSPLIT=1 STRATA_STATIC_TIER=1 STRATA_NO_HITS=1 STRATA_NO_LA=1 STRATA_EARLY=1 STRATA_EARLY_CPU=23
~~~

### 5.3 三个跨样本一致的调参结论

1. **8 GB 关 MTP**（#4517、#1375、himiaoxin、1xdoclb 四票）。
2. **`--vram-reserve-mib` 是成败开关**（#4517 原话 "the VRAM reserve is what decides it"；#2477 从 423 MiB 空闲提到 553 MiB；1xdoclb 用 512）。
3. **`--pcie-frac` 有明确最优区间 0.15–0.35**（#3984 扫描：0.0 48.1 / 0.2 **50.6** / 0.35 48.9 / 0.55 45.3 / 1.0 36.3 tok/s）。

---

## 6. 单次首发成功 vs 反复问都正确

这是本次任务明确要求区分的维度，社区里**几乎没人认真做**。现有的全部证据：

| 样本 | 验证深度 | 结论 |
|---|---|---|
| **#4517**（1070 Ti 8 GB） | **21/21 required + 12/12 sanity + Hermes 4 任务 12/12 满分（64K）** | **唯一达到"反复问都正确"级别**；且 Coder IQ1_M 12/12 > Gyro-S 10/12 |
| **1x5p822**（8 GB Q2_0） | pi harness，3 次上下文压缩后无异常 | 只证明"没崩"，不证明正确；且**在另一张 8 GB 卡上复现失败** |
| **#4402**（≤13 GiB 卡） | 1,839 条回复 → 4 次复读循环（50K→83K） | **典型"首发看起来好、长跑崩"**：关掉 STRATA_ROUTE_PRIOR=1.5 后 12 GB 的 3060 从 55 → 45 tps，仍约 1 小时后复读 |
| **1xh1asc**（0.1.52） | 用户主观：长乌克兰语文本"明显变差"；作者自述 65 组内部任务集 | 速度 +40%，质量无量化指标；**"没有数字，全是轶事"** |
| **#2477**（3080 Laptop 8 GB） | 4 轮 bench，0 失败请求，无一次低于 13 tok/s | 稳定性证据，非正确率 |

→ **给使用者的实操建议**：看到任何 8 GB 配方，先跑 #4517 那套"12 个 agent 任务 + 12 条 sanity"的最小验证集，再看 tok/s。**只看 tok/s 的配方在 8 GB 上有一半会在 20 分钟后开始复读。**

---

## 7. 对本机（4060 Ti 8 GB + 31 GB DDR5 + Win11）的可操作含义

1. **31 GB RAM 落在危险区**。多个 8 GB 成功样本是 32–64 GB，而 #4517 明确说 Q2 要 ~48 GB RAM；作者的 Gyro-M 建议是 48+ GB。→ 优先 **Coder IQ1_M / Q2_0**，别碰 IQ3_XXS 以上。
2. **Windows 必须把 pagefile 设成"系统托管"或固定 ≥16 GB**：既避免 #1607 的 0xC0000409，又让 #3692 的 expert cache 自动值不掉 30%。**但别指望它提供带宽**。
3. **`--vram-reserve-mib 900` 起步**（不是 500）；本机是 8188 MiB 的 4060 Ti，比作者的 5060 Laptop 更吃紧。
4. **关 MTP**；prefill 才是 8 GB 上的真瓶颈（多个样本 prefill 130–340）。
5. **benchmark 必须带盘读指标**（Windows 资源监视器 → 磁盘 → 页面文件 I/O + 硬错误/秒），否则会把"内存不够"误判成"CPU 慢"——这正是 #4517 作者浪费几小时的原因。

---

## 8. 无法核实的渠道（明确标注）

| 渠道 | 状态 | 处理 |
|---|---|---|
| **X / Twitter** | x.com 无公开 API；xcancel 451；nitter.poast 连接失败（000） | 无任何可引一手贴，**不采信任何"X 上有人说"** |
| **Discord** | 无公开 API / 无导出；"搬运贴"均为二手截图 | 全部归为【未核源】 |
| Reddit 站内搜索 / 第三方镜像 | *.json 403、redlib 全挂、pullpush 429 | 仅靠 Atom RSS，可能漏帖 |
| Bing `site:reddit.com` | 检索退化，10 组查询全返回中文站 | 未用于取证 |

---

## 附：证据索引（全部 URL）

**Reddit**
1. https://www.reddit.com/r/LocalLLaMA/comments/1xft2ae/have_8_gb_of_vram_and_32_gb_of_ram_you_can_run/ — 8 GB 主配方（作者）
2. https://www.reddit.com/r/LocalLLaMA/comments/1x5p822/qfn_q_2_strata_configs_for_8gb_vram_and_32gb_ram/ — 8 GB Q2_0 36 tps + 复现失败
3. https://www.reddit.com/r/LocalLLaMA/comments/1xdoclb/ — 3070 8 GB / 64 GB DDR4-3000
4. https://www.reddit.com/r/LocalLLaMA/comments/1x7sbdc/qwen38flashnextgsqrco_iq3_s_4050_toksec_decode/ — 12 GB 标杆
5. https://www.reddit.com/r/LocalLLaMA/comments/1x1tclb/qwen_38_flash_nextgsqrcoiq2_xs_at_21_toks_on_just/ — 12 GB + 16 GB 单通道
6. https://www.reddit.com/r/LocalLLM/comments/1xh1asc/ — 0.1.52 速度/质量之争
7. https://www.reddit.com/r/LocalLLaMA/comments/1xhncny/ — 16 GB + Win + 32 GB 失败
8. https://www.reddit.com/r/LocalLLaMA/comments/1xfe04h/ — Windows 24 GB pagefile + VirtualLock

**GitHub（Niko1221/Strata）**
9. https://github.com/Niko1221/Strata/issues/4517 — 1070 Ti 8 GB，任务级验证 + 假线索教训
10. https://github.com/Niko1221/Strata/issues/141 — pagefile/committed 记账机制（作者解释）
11. https://github.com/Niko1221/Strata/issues/1607 — Windows commit limit 崩溃
12. https://github.com/Niko1221/Strata/issues/1630 — WER 快照误判
13. https://github.com/Niko1221/Strata/issues/3692 — pagefile 状态影响 expert cache 30%
14. https://github.com/Niko1221/Strata/issues/3984 — 6700 XT 12 GB + pcie-frac 扫描
15. https://github.com/Niko1221/Strata/issues/4402 — 12 GB 长跑复读
16. https://github.com/Niko1221/Strata/issues/2477 — 3080 Laptop 8 GB reserve 实验
17. https://github.com/Niko1221/Strata/issues/2248 — 4060 8 GB + 2060 6 GB 合并
18. https://github.com/Niko1221/Strata/issues/1375 — 6600 XT 8 GB，MTP 无收益
19. https://github.com/Niko1221/Strata/issues/4234 — 4070 Ti 12 GB Windows
20. https://github.com/Niko1221/Strata/issues/3097 — 5070 Ti Laptop 12 GB Windows
21. https://github.com/Niko1221/Strata/issues/1250 — 12 GB page-lock OOM
22. https://github.com/Niko1221/Strata/issues/1194 — 12 GB 0.1.40 回退
23. https://github.com/Niko1221/Strata/issues/2212 — 3070 8 GB 电源问题
24. https://github.com/Niko1221/Strata/issues/3940 — 5070 12 GB（无性能数字）

**HuggingFace**
25. https://huggingface.co/ISTA-DASLab/Qwen3.8-Flash-Next-ISTA-Coder-GGUF/discussions/24 — Windows 8 GB 笔记本
26. https://huggingface.co/ISTA-DASLab/Qwen3.8-Flash-Next-ISTA-Coder-GGUF/discussions/31 — llama.cpp → Strata 对照
27. https://huggingface.co/unsloth/Qwen3.8-Flash-Next-GGUF/discussions/48 — 3060 laptop 12 GB llama.cpp
28. https://huggingface.co/unsloth/Qwen3.8-Flash-Next-GGUF/discussions/66 — 6 GB 1660 Ti（非 Strata，参照）

**配方仓库**
29. https://github.com/bodhi37/Qwen3.8-Flash-12GBRAM-32GBVRAM-SSD-Recipe
30. https://github.com/Gitshop77/GyroStrata

---

*本文所有 tok/s 均为报告者自述，未经我独立复测；跨样本比较时注意上下文长度、量化、OS、内存容量四项必须同时看，否则数字不可比。*
