# 广度搜集：Strata 8 GB 实测全景 + 四档量化在本机的可行性 + 网盘/中文资源 + 可迁移技巧

> 侦察员 comment-miner ｜ task-18 ｜ 2026-10-30 ｜ 只做网络搜集，未启动任何引擎、未下载任何网盘文件。
> 标注约定：**【实测】** = 有原始日志/表格/机器配置的第三方报告；**【官方 bench】** = 上游仓库 bench/results 或官方文档里的数字；**【博主口径】** = 媒体/UP 主汇总，未附原始日志；**【转述】** = 只见标题/摘要。
> 本机基线（取自 reports/社区侦察-Strata出处与8G长上下文.md 与 reports/部署方案-最终-4060Ti-8G.md）：RTX 4060 Ti 8 GB（sm_89，8,188 MiB）+ Ryzen 7 7800X3D + 31 GB DDR5-6000 + Win11；现役 NInfer --kv-capacity 40000 --kv-dtype rk2v4-e8 --host-kv-mib 6144 --max-context 262144 + MTP draft4，峰值 7,469 MiB、97–98 tok/s（计数题）。
> 姊妹报告（别重复看）：reports/HF与魔搭-情报.md（Bonsai 量化档/HF 体积/魔搭生态）、reports/社区侦察-Strata出处与8G长上下文.md（Strata 作者与出处、8G 长上下文配方）。本文只补「广度 + 本机可行性 + 技巧」。

---

# 一、结论先说（六条）

1. **同卡同 RAM 的最硬对标，是官方 tracker 里一份被关闭的 PR：RTX 4060 8 GB + 31.9 GB RAM + 32K 上下文 → decode 只有 20.7 tok/s（Flash-Next IQ2_XS 低内存模式）/ 15.5 tok/s（Coder IQ1_M 驻留模式）**【实测】。我们现在的 NInfer 27B 在同机 32K 池下是 97–98 tok/s。**Strata 换不来速度，它换的是"125B 参数"。**
2. **8 GB 卡的 Strata 速度由 RAM 决定，而不是显卡**：同是 8 GB 卡，64 GB RAM 的 4060 Ti 跑 IQ2_XS 有 ~51 tok/s，31.9 GB RAM 的 4060 只有 20.7 tok/s；96 GB RAM 的 3070 能开 196,608 上下文还保持 30.8–46.5 tok/s【实测×3】。
3. **四档量化里，我们这台机器只有 Gyro-S（27.6 GB 合计）算"官方口径装得下"**：Q2_0 37.6 GB、IQ2_XS 39.2 GB、IQ3_XXS 47 GB、IQ3_S 54.8 GB 都超过"31 GB RAM + 8 GB VRAM 扣掉 10 GB 系统余量"的预算。Gyro-S 的代价是质量比 IQ2_XS 差 13%（KL 0.268 vs 0.236），且一半文件是 n-gram 表、每个 token 从 SSD 随机读。
4. **两个能直接搬到我们引擎上的数值规律**（详见 §4）：①**8 GB 卡上 prompt chunk 一被显存挤小，prefill 就掉 40%**（512→256 掉 43%，1024→768 掉 40%）；②**prefill 分一块给 CPU 反而 +36~38%**（STRATA_PREFILL_CPU_SHARE）。
5. **一条几乎零成本的硬件实验**：让推理卡不再驱动显示器。同一台机器上"会话 2 显示器关掉"比会话 1 prompt 快 18.7–20.8%、decode 快 38.1–48.1%（作者标注为推断）【实测-带保留】。我们有 7800X3D 的核显可用。
6. **网盘只有一条可核实的**：中文教程 itbanana 内嵌的夸克链接 https://pan.quark.cn/s/5e904afcaeb0（模型文件；安装包要走官方 Releases）。其余"一体包"多为转述，未见可核实链接。

---

# 二、Strata 8 GB 实测表（全部带机器配置与出处）

## 2.1 单卡 8 GB（严格同量级）

| # | 机器 | 档位 | 上下文 | decode | prefill / TTFT | 显存/内存占用 | 出处 |
|---|---|---|---|---|---|---|---|
| 1 | **RTX 4060 8 GB**（也驱动桌面，PCIe 3.0 x8）+ i7-8700 + **31.9 GB RAM** + NVMe，Win10，engine 0.1.42 | Flash-Next **IQ2_XS**，--mmap-experts 低内存模式，--kv int8 + MTP + vision 走 CPU + --vram-reserve-mib 300 | 32,768 | **20.7 tok/s** | **31.3 / 35.7 tok/s**（约 9.7K token 新提示，3 次中 2 次；另 1 次卡死） | 启动日志曾警告 "0 MiB of VRAM free … add --vram-reserve-mib 812"；读 ~9.7K prompt 时 357 MiB RAM 可用、专家文件页大量换页→看门狗重启 | 【实测】https://github.com/Niko1221/Strata/pull/2004 |
| 2 | 同上 | **Coder IQ1_M**，--resident-experts | 32,768 | **15.5 tok/s** | **134.9 tok/s**（中位 3 次） | 同上；60 分钟 soak 168/179 成功（11 次 JSON 循环到上限→502） | 【实测】同上 |
| 3 | **RTX 4060 Ti 8 GB** + i9-14900K + **64 GB DDR4**，Win11 | Flash-Next **IQ2_XS** | 未写（短测） | **~51 tok/s** | **4K ~569 tok/s / 16K ~624 tok/s** | 未写 | 【实测-简版】https://github.com/Niko1221/Strata/pull/2539 |
| 4 | **RTX 3070 8 GB** + Ryzen 9 5900X + **96 GB**，engine 0.1.41，OpenCode 1.18.16 | IQ2_XS / IQ3_S / IQ3_XXS，六套配置 | **196,608**（采样 A/B 用 262,144） | **30.8–46.5 tok/s** | 未测 4K/32K/128K 扫描 | 8/8 agent 任务全过，总时长 68m32s–107m54s | 【实测】https://github.com/Niko1221/Strata/pull/1972 |
| 5 | **RTX 3070 Ti 8 GB**（也驱动显示器）+ Ryzen 9 5900X + 64 GB DDR4-3600，Win11，engine 0.1.45.3 | IQ2_XS，setup 写出的 32K / 128K 配置 | 32K + 128K | 未给单值（以 prompt 为主） | 128K 档 **586.6 / 602.8 tok/s**（4K/16K，CPU share 开）；关掉 CPU share 只有 424.7 / 442.8 | needle 32k 6/6、128k 6/6 | 【实测】https://github.com/Niko1221/Strata/pull/1496 |
| 6 | **Radeon RX 7600 8 GB**（gfx1102，headless）+ i9-10900 + **62.7 GB**，Debian13，engine 0.1.53 | **Q2_0**（原生）/ **Coder IQ1_M** | 32K | Q2_0 **27.2**；IQ1_M **19.8** | Q2_0 **215.9 @4K / 237.9 @16K**；IQ1_M **176.9 / 174.4** | 见原文 data/ 里的快照；needle Q2_0 6/6 到 22,646 token | 【实测】https://github.com/Niko1221/Strata/pull/4543 |
| 7 | **2× Quadro RTX 4000 8 GB**（Proxmox LXC）+ 双 Xeon E5-2620v3 + 64 GB DDR4-2133，engine 0.1.38 | **Swift IQ2_XS**，--max-context 131072 --kv q4_0 --kv-resident 32768 --expert-cache auto --vram-reserve-mib 700 --spec 4 --spec-min-p 0.5 | 131,072 | **18.1–23.2**（500–1100 输出 token，专家缓存命中 48–53%） | **126.3–249.2 tok/s** @73k–74.6k prompt | 真生产负载（45k–62k token 播客稿流水线） | 【官方 bench】tmp/web/Strata/bench/results/2026-10-07-community-2x-rtx-4000/README.md |

**读表要点**：8 GB 卡的 decode 天花板 ~51 tok/s 需要 64 GB 内存托底；内存只有 32 GB 时，8 GB 卡的实测区间是 **15.5–20.7 tok/s**（#1、#2），这正是我们的内存档位。3070（96 GB）能开 196K 并保持 30+ tok/s，靠的是整份专家进 RAM。

## 2.2 12 GB 卡（同架构邻档，用于判断"加内存/加显存"的边际收益）

| 机器 | 档位 | decode | prompt | 出处 |
|---|---|---|---|---|
| **RTX 3060 12 GB + 64 GB**，0.1.41 Windows，四档全跑完 128K（Q2_0/IQ3_XXS/IQ3_S 还跑完 260K） | IQ2_XS | 39.8（en）/ 40.9（ja）@4K | 930.7 @64K 级提示 | 【官方 bench】tmp/web/Strata/bench/results/2026-10-09-community-rtx-3060-0141/README.md |
| 同上 | IQ3_XXS | 25.6–27.2 | 883.6 @32K | 同上 |
| 同上 | IQ3_S | 18.2–20.9 | 820.0 @32K | 同上 |
| **RTX 3060 12 GB + 32 GB RAM**（就地读 + 20.5 GiB 专家在 RAM + --adapt-async 1 --spec 3） | IQ2_XS | **48.71 → 51.40**（改 STRATA_RAM_ADAPT 前后） | 137.4 → 141.5，存储读 408 → 308 GB | 【官方文档实测】tmp/web/Strata/docs/DETAILS.md:1391 |
| 同上 | IQ3_XXS | 33.07 → 38.71 | 97.8 → 104.2 | 同上 |

**这行最有价值**：**32 GB RAM + 12 GB 显存**（只比我们多 4 GB 显存）就能把 IQ2_XS 跑到 ~51 tok/s；而 8 GB 显存 + 32 GB RAM 只有 20.7。差额全在"显卡能装下多少专家"→ 说明 8 GB 是硬瓶颈，不是内存。

## 2.3 博主口径汇总（媒体表，未附原始日志）

小众软件《8GB显存就够，Strata 让普通电脑也能运行千亿参数大模型》（2026-10-10）给出的社区表【博主口径】https://www.appinn.com/strata/ ：

| 显存 | 显卡 | 系统内存 | 档位 | 生成速度 |
|---|---|---|---|---|
| 8 GB | RTX 4060 Ti | **32 GB** | Coder IQ1_M | **19–21 tok/s** |
| 8 GB×2 | Quadro RTX 4000×2 | 96 GB | Swift IQ2_XS | 18–23 tok/s |
| 12 GB | RTX 3060 | 64 GB | IQ3_XXS | 30 tok/s |
| 12 GB | RTX 5070 | 64 GB | Q2_0 / IQ3_S | 94 / 53 tok/s |
| 16 GB | RTX 4060 Ti | 96 GB DDR3 | Q2_0 / IQ3_S | 48.1–55.8 / 30.5–35.1 tok/s |
| 16 GB | RX 9070 XT | 47 GB | Q2_0 | 60 tok/s |
| 16 GB | RX 7800 XT | ~121 GiB | Coder IQ1_M | 38–44 tok/s |
| 16 GB | RX 9060 XT | 64 GiB | Coder IQ1_M | 27.1 tok/s |
| 24 GB | RTX 3090 | 64 GB | IQ3_XXS / IQ3_S | 50–60 / 60–77.9 tok/s |
| 24 GB×2 | TITAN RTX×2 | 125 GiB | IQ3_S | 70.9–77.3 tok/s |

同文原话两条口径值得记住：①"**只要有 8GB 显存、16GB 内存**……就有机会运行"（**博主口径，与实测矛盾**：#1 的 31.9 GB RAM 机器都只跑 20.7 tok/s，16 GB 内存必然全程读盘，勿信）；②"不要使用机械硬盘……太慢，慢死"【博主口径但被 §4 的盘速实测支持】。

什么值得买（smzdm）系列长文（2026-10-02 起多篇，标题即结论）【转述-360 搜索摘要，正文站内被反爬】：
- 《8G显存跑125B 刷屏风暴：这批实测数字摆完，本地部署的门槛原来是内存不是显卡》——摘要含"**4060Ti+32G内存的30.1**""5070 12GB 加 64GB 内存的官方机跑出 93 t/s""双卡 48GB 显存 + 128GB DDR4 四通道上满 IQ3_S 实测 105.8 tokens/s"。
- 《Strata 26天2.8万star：125B大模型塞进游戏主机，8G能跑 和 64G才舒服 吵翻了——上车前先算清三道门槛》（2026-10-20）。
- 《12G显存跑125B模型刷屏：官方94 tok/s和有人实测30多的差距，就藏在README这五行里》（2026-10-10）。

---

# 三、Qwen3.8-Flash-Next 各量化档在本机的可行性

## 3.1 官方体积与"能不能装下"的公式（原文）

- 体积（VRAM+RAM 合计，权重）：**Q2_0 37.6 GB / IQ2_XS 39.2 GB / IQ3_XXS 47.0 GB / IQ3_S 54.8 GB / Coder IQ1_M shard1 29.6 GB（专家 23 GB）/ Gyro-S 27.6 GB / Gyro-M 35 GB**（tmp/web/Strata/docs/MODELS.md）。
- 公式：**RAM ≥ 专家体积 + 约 10 GB**；"Big GPU, little RAM"档位表写明：**32 GB RAM + 12–16 GB GPU 只能跑 Coder**（tmp/web/Strata/docs/MODELS.md「Will it fit?」）。
- 低内存三模式：--mmap-experts（映射 experts.bin/GGUF，OS 文件缓存兜底）、--resident-experts（显卡装不下的专家整份拷进 RAM）、--resident-budget-gib N（按热度只拷 N GiB，留 4 GiB 余量；**Windows 还受 commit limit 限制**）——tmp/web/Strata/docs/DETAILS.md:223-238。
- Gyro 专项：**"Memory it needs (VRAM + RAM together) 27.6 GB"**；**"About half of each file is the n-gram (PLE) table. It stays on the SSD and is read row by row for every token, so keep the file on a fast local drive."**——tmp/web/Strata/docs/GYRO.md:28-40。

## 3.2 判定表（本机 31 GB RAM + 8 GB VRAM，预算 ≈ 39.2 GB）

| 档 | 官方体积 | 官方规则判定 | 我们机器上的现实路径 | 8 GB 上的实测读数 | 结论 |
|---|---|---|---|---|---|
| **Q2_0** | 37.6 GB | RAM ≥ 34 + 10 = 44 GB → **不达标** | 只能 --resident-budget-gib（按热度驻留）或全 mmap；Windows commit limit 还会再压 | 8 GB 卡上**无单卡实测**；RX 7600 8 GB（62.7 GB RAM）27.2 tok/s | **不建议**：内存不够，速度会比 20 tok/s 更低 |
| **IQ2_XS** | 39.2 GB | 需 35.5 + 10 = 45.5 GB → **不达标** | 同 PR #2004 的 --mmap-experts 低内存模式 | **20.7 tok/s @32K**（RTX 4060 8 GB + 31.9 GB RAM），且出现过一次换页卡死 | **唯一有同配置实测的档**，但速度只有我们现役 NInfer 的 1/5 |
| **IQ3_XXS** | 47.0 GB | 需 43 + 10 = 53 GB → **明确不达标** | 无可行路径（专家全在盘上，必崩/极慢） | 无 8 GB 单卡数据 | **放弃** |
| **IQ3_S** | 54.8 GB | 需 50 + 10 = 60 GB → **明确不达标** | 同上 | 无 8 GB 单卡数据（16 GB + 64 GB RAM 才有 18–21 tok/s） | **放弃** |
| **Coder IQ1_M** | shard1 29.6 GB（专家 23 GB） | 官方明说"能在 32 GB RAM 上跑" | --resident-experts：23 GB 专家进 RAM，其余在显存/盘 | **15.5 tok/s @32K**，prefill 134.9 | **能跑但慢**；只有代码任务强（91% SWE-bench / 99% LiveCodeBench，非代码场景弱） |
| **Gyro-S** | **27.6 GB（VRAM+RAM 合计）** | **符合"官方口径装得下"的唯一档** | 直接 launch，n-gram 表留 SSD 逐 token 读 | 3060 12 GB decode **62.5**（比 Q2_0 的 65.5 慢 7%）；Arc A750 8 GB：1.4K/2.4K/20K prompt **82.0 / 101.9 / 195 tok/s** | **值得一试的唯一完整档**；代价见下 |
| Gyro-M | 35.0 GB | 需 35 GB 合计 → 压线，Windows 上偏危险 | — | 3060 12 GB decode 54.8（比 Q2_0 慢 16%），≈IQ3_XXS 质量 | 内存会被吃满，不建议先试 |

Gyro-S 的两个代价（都有原文）：质量 **KL 0.268 vs IQ2_XS 0.236（差 13%）**，且"the smallest option… Lower quality than the 2 to 3-bit sizes"；下载仍有 **58.5 GB**（一半是 n-gram 表）。出处：tmp/web/Strata/docs/GYRO.md:31-40、:65-77。

**一句话给 Lead**：想在 8 GB + 31 GB 上完整体验 125B，只有 **Gyro-S** 一条路，预期 3060 12 GB 的 62.5 tok/s 打七折上下（8 GB 显存更紧），质量比 IQ2_XS 差一档；**要"又准又快"就别在这台机器上追 Strata 的 125B**——IQ2_XS 的低内存模式在同配置机器上是 20.7 tok/s。

---

# 四、可迁移技巧（每条：做法 → 实测收益 → 出处 → 能不能搬到 NInfer）

> 说明：Strata 是 MoE + 专家缓存架构，我们是 dense 27B + 三元权重，"专家"这类技巧不能照抄；下面只留能对应到**显存/带宽/预填/投机/前缀**的。

## 4.1 显存侧

1. **推理卡不要驱动显示器**（最重要的免费收益）。同一台 3070 Ti 8 GB（也驱动显示器）：把显示器关掉的会话相比开着，**prompt +18.7~20.8%、decode +38.1~48.1%**（作者注明"by inference"，非受控实验）【实测-带保留】https://github.com/Niko1221/Strata/pull/1496 。另有一份 PR 记录"自动 prompt chunk 从 512 掉到 256"只因空闲 VRAM 少了 ~70 MB，吞吐立掉 43%（131–136 → 76–78 tok/s），decode 不变【实测】https://github.com/Niko1221/Strata/pull/2004 。**本机动作**：7800X3D 有核显，把显示器插主板、BIOS 里设 iGPU 优先，4060 Ti 只做计算——成本 0，可当场 A/B。
2. **非显示卡的 --vram-reserve-mib 可以从 700 降到 50**：专家槽 6,519 → 7,012（+2%），因为不用给桌面留显存【实测，社区 fork 作者自测】https://raw.githubusercontent.com/apatassini/Strata/qwen38-16gb/QWEN38.md 。**NInfer 对应物**：我们的 --kv-headroom-mib（默认 1024，本机实测 1024 会 FATAL）——若显卡不驱动桌面，余量旋钮还有下压空间。
3. **请求级显存借还（VRAM loans）**：prefill 期间把"仅 decode 用"的显存（MTP 头、verifier）临时借给专家缓存，生成前再还回。作者称在自己的 8 GB 笔记本 GPU 上"massive PP speed win"【实测-定性】https://github.com/Niko1221/Strata/pull/1581 。**NInfer 对应物**：我们有 --device-state-slots、--mtp-attention-window；"prefill 时把投机头/草稿槽腾出去"是可试的新思路（未验）。
4. **显存弹性分段**：专家缓存改成 512 MiB 分段（--vram-elastic），可 POST /v1/vram 按需把最后几段解映射让给别的程序；只动专家缓存，dense/KV/MTP/prompt buffer 不动——tmp/web/Strata/docs/VRAM_ELASTIC.md 。**NInfer 无对应**，但说明"整块 cudaMalloc 是浪费的来源"。
5. **路由偏好本地数据**：STRATA_ROUTE_PRIOR=1.5（≤13 GiB 离散 N 卡默认开）让路由优先选"已在该卡上的专家"，RTX 3060 12 GB IQ3_XXS 五对跑：**故事 46.2→53.1（+15%）、代码 45.7→62.5（+37%）**；2.0 会出现抄写/代码缺陷——tmp/web/Strata/docs/release-notes-0.2.7.md:7 。社区 fork 用 1.0 得到 **+23% decode** 且质量无损失：https://raw.githubusercontent.com/apatassini/Strata/qwen38-16gb/README.md 。**NInfer 无 MoE 路由**，但"'优先命中本地副本'的权重偏置"可类比到 KV 检索打分。

## 4.2 预填 / 短提示 / 盘速

6. **prefill 分一块给 CPU = +36~38%**：3070 Ti 8 GB 上，默认开着的 CPU share（仅 <1024 token 的 prompt chunk）让 128K 档的 4K/16K 提示读取从 424.7/442.8 → **586.6/602.8 tok/s**（关掉 CPU share 的同一会话对照）【实测】https://github.com/Niko1221/Strata/pull/1496 。**NInfer 对应物**：我们 prefill 在 4K 只有 ~1000 tok/s、113K 掉到 704；把短 chunk 的 attention/MLP 一部分交给 CPU（或至少别让 CPU 空等）是可试方向。
7. **chunk 越小 prefill 越差，是 8 GB 卡的隐性税**：0.1.40.3 上 128K 档因显存只够 768-token chunk，比 1024-chunk 配置**慢 38.8–41.4%**；0.2.0-beta 用 CPU share 抹平后差距变 -2.8%~+2.7%【实测】同上 PR 。**对应到我们**：--prefill-chunk 1024 已是默认，但本机 32K 池时 512 只省 85 MiB（见 reports/部署方案-最终-4060Ti-8G.md）——**别为省 85 MiB 把 chunk 降到 512**，按此规律那是 -40% 的税。
8. **按盘速自适应 prompt chunk（planner）**：SATA 450 MB/s 模拟环境下把 chunk 8192→3840：20,400 token 提示 **334.0 → 822.3 tok/s（2.46×）**，盘读 26.1→2.7 GB，decode 25.4→42.6——tmp/web/Strata/docs/DETAILS.md:1392 。**NInfer 对应物**：我们的 --prefill-chunk 是固定值；若模型在 NVMe 上，按"盘读/显存"两约束自动选 chunk 是可直接实现的策略。
9. **启动预读（read-ahead）**：Gen3 NVMe + 32 GB + Q2_0 驻留 262K：读前移把就绪时间 **920 s → 70 s**、填充速率 **39 MB/s → 3.2 GB/s**——tmp/web/Strata/docs/DETAILS.md:1385 。**NInfer 对应物**：我们有 --disk-kv-restore（已测为"全量重算"级别慢，见 reports/ninfer-analysis.md:212），但"启动时并行预读权重到页缓存"没有做。
10. **短提示读取是 agent 的真瓶颈**：一次 5 小时、526 次模型调用的真实会话里，**74% 的 prompt 读取 <1000 token，却占了 57% 的读取时间**（200–750 tok/s，而长提示 3000+）；针对性打补丁后短提示读取 **-37~-41%**【实测，社区 fork】https://raw.githubusercontent.com/apatassini/Strata/qwen38-16gb/QWEN38.md 。**对应到我们**：TTFT 在 agent 场景基本等于"1K 提示的 prefill"，本机 1K prefill ~1000 tok/s → ~1 s，值得单独优化。

## 4.3 投机解码 / 前缀缓存

11. **按自己的语言/任务重训草稿词表**：tools/draft_vocab.py --coverage 0.99 用自己的真实回答做词表（默认表漏 8.5% 意大利语词，补 4,253 词后漏 0.45%），接受率 **80.5→86.9%（代码）、66.1→73.4%（agent）**，即 **代码 +6%、agent +10%**【实测，社区 fork】同 §4.1-2 链接。**NInfer 对应物**：我们 MTP 头是 PTQ1 固定的；但 5258MF 报告过"精简 MTP 输出头只在 13 万常用词里猜、快约 10%"（--lm-head-draft，本机未试）——**中文词表裁剪**是同一思路，值得排期。
12. **自己训一个 MTP 草稿头**：用自己长会话（16K 上下文、模型自身概率）训，相比官方 Basalt 头 **+4~5%**【实测，社区 fork】同上。**NInfer**：不现实（我们拿不到训练管线），记下即可。
13. **前缀/边界检查点**：STRATA_CACHE_MESSAGE_BOUNDARY=1 在上一轮边界存检查点（≥8192 token 前缀、尾 ≤1024），改最后一句用户消息时不必重读历史；STRATA_KV_PREFETCH=1 用另一条流预取下一层 KV 上传，避免长上下文 KV 在 RAM 时 GPU 空等；STRATA_CLIENT_MEMORY=2048 让"另一个程序抢过缓存后回来的客户端"恢复专家计数，**agent 回来后的第一步 +21% tok/s**。——tmp/web/Strata/docs/MESSAGE_BOUNDARY_CACHE.md、docs/KV_PREFETCH.md、fork QWEN38.md 。**NInfer 对应物**：我们有前缀缓存（67,137 token 冷启 84.2 s → 0.54 s）、NINFER_HOST_PAGEABLE / KV_REUSE_HOSTBACKED；"消息边界检查点"（只改最后一句话时复用整段历史）+ "KV 预取流"两个机制我们都没有对应实现，收益方向一致。

## 4.4 明确无效（省时间，别试）

- **预先拷贝"预测的专家"进显存**（下一层路由、训 1–2 层的头、校准阈值 75% 命中）：最好也只是打平——CPU 省 ~0.26 ms/步，GPU 多花 ~0.2 ms，且"只要缺 1 个专家整层就等 CPU"（每层缺一次 ~45 µs）【实测】fork QWEN38.md。→ **任何"猜下一层要什么，先搬上去"的方案都要先算这笔账。**
- **学出来的缓存替换规则**（加权衰减计数）打不过 Strata 自带的（4.05% vs 3.93% 未命中），只有在换两次时才赢，实际更贵【实测】同上。
- **短提示走 decode 窗口**（--short-read）：窗口每多 1 token 约 3 ms，比 prefill 还差【实测】同上。
- **把 AMD 的开关搬到 CUDA**（STRATA_DOORBELL_STORE、STRATA_FUSE_WAIT）：-3% 和 -6.7%【实测】同上。
- **更强路由偏置（>1.5）**：出现抄写/代码缺陷（官方 0.2.7 说明与 fork 一致）。
- **llama.cpp 路线上的 -ngl 99**：16 GB 显卡 + 64 GB RAM 跑 IQ3_S 时加了它起不来，去掉才能跑（9–11 tok/s，262144 与更小上下文同速）【实测】https://huggingface.co/ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-GGUF/discussions/55 。

---

# 五、网盘与中文资源清单（只列，不下）

| 类型 | 链接 | 内容/说明 | 可靠性 |
|---|---|---|---|
| 模型（网盘） | **https://pan.quark.cn/s/5e904afcaeb0** | 夸克网盘，中文教程 itbanana 文中给出的"模型文件"下载（安装包走官方 Releases，文中明确） | 【可核实来源】文章正文第 109、366 行提到（本地文本 tmp/web/pages/abdf8d0464.txt）｜**提取码文中未给** |
| 安装包（官方） | https://github.com/Niko1221/Strata/releases/latest | Strata-0.2.8-windows-x64-setup.exe 等；Windows/Linux 安装包**不含引擎**，首启按显卡下载（约 200–400 MB） | 【官方】tmp/web/Strata/AGENTS.md |
| 模型（官方 HF） | https://huggingface.co/ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-GGUF | 四档共 28 文件 294.8 GB；Q2_0 66.42 / IQ2_XS 68.03 / IQ3_XXS 75.84 / IQ3_S 83.62 GB（各 2 分片）+ mmproj BF16 0.91 GB | 【实测-API】HF tree API |
| 模型（国内镜像） | https://hf-mirror.com/ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-GGUF | hf-mirror 的 API 可通（HTTP 200），/resolve/ 直链要按仓库真实文件名取 | 【实测】curl 200 |
| 魔搭 | https://modelscope.cn/models/ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-GGUF | 网页 200（40 KB）；API 404，未验证有同名模型 | 【实测-弱】 |
| 社区群 | https://t.me/+cSNCZGpuDVhlOTll | itbanana 文中给的 Telegram 群 | 【转述】 |
| 短视频 | https://v.douyin.com/YhBtUuqZ3u4/ ｜ 油管 @caoziwen | 同一教程作者的视频版 | 【转述】 |
| AMD 分支 | https://github.com/gufo-org/gufo | 小众软件文末推荐的"A 卡版 Strata" | 【博主口径】https://www.appinn.com/strata/ |
| 中文资讯 | https://www.appinn.com/strata/ ｜ https://www.appinn.com/strata-0-2-3/ | 小众软件追踪报道 7 篇（0.2 → 0.2.7.1），含社区速度表 | 【博主口径】 |
| 中文长文 | smzdm 系列（标题见 §2.3） | 正文站内反爬（curl 只拿到 1.5 KB 壳），只能引摘要 | 【转述】 |

**负面结论（省时间）**：① Reddit r/LocalLLaMA 用 pullpush 归档查 "Strata" **0 条**、查 "Strata 8GB" 只返回无关波兰语帖——英文社区尚未覆盖这个项目，别再去 Reddit/HN 找读数；② 知乎两篇（2089282096925878242、2090202087120553566）**403**，api/v4 也 403；③ CSDN 正文空壳（453 字符）；④ 小众软件评论区 24 条评论是 JS 加载、wp-json 401，拿不到；⑤ 唯一"6 GB 显存跑 125B"的 CSDN 标题【转述】与所有实测矛盾（8 GB + 31.9 GB RAM 只有 20.7 tok/s），**不要采信**。

---

# 六、落到本机（4060 Ti 8 GB + 31 GB + 现役 NInfer 97 tok/s）的判定

## 6.1 横向对照（同机 32K 级上下文）

| 方案 | decode | prefill/TTFT | 上下文 | 出处 |
|---|---|---|---|---|
| **现役 NInfer Bonsai 27B ternary** | **97–98**（计数题）/ 48–50（散文） | 1000 @1K / 899 @56K | 池 32–64K，逻辑窗 16K | reports/部署方案-最终-4060Ti-8G.md:21-25 |
| Strata IQ2_XS 低内存（8 GB + 31.9 GB） | 20.7 | 31.3–35.7 @9.7K | 32K | PR #2004 |
| Strata Coder IQ1_M 驻留（同上） | 15.5 | 134.9 @9.7K | 32K | PR #2004 |
| Strata Gyro-S（推算） | 62.5 × 0.7 ≈ 40–45（3060 12 GB 为 62.5，8 GB 更紧） | 82–195（A750 8 GB 实测区间） | 可到 128K+ | tmp/web/Strata/docs/GYRO.md:74-77、:151-153 |

**判定**：Strata 的 125B 在我们这台机器上是"**能力升级、速度降级 5 倍**"；唯一值得实机验证的是 **Gyro-S**（27.6 GB 装得下、质量 -13%、decode 可能 40 上下）。

## 6.2 按收益排序、可直接执行到本机的动作

| 优先级 | 动作 | 预期 | 成本 | 依据 |
|---|---|---|---|---|
| **P0** | **把显示器从 4060 Ti 挪到 7800X3D 核显**，再跑一次现役 NInfer 基准 | prompt +18~21%、decode +38~48%（他人实测，含推断成分） | 0（一根线 + BIOS） | PR #1496 |
| **P0** | 同一基准里把 --kv-headroom-mib 现值（512/1024）与 256 做 A/B | 可能多出 200–700 MiB 池；注意本机 1024 曾 FATAL | 0 | PR #2004 的 ~70 MB→-43% 效应；fork 的 700→50 槽位 +2% |
| **P1** | 显存固定后**别为省几十 MiB 把 --prefill-chunk 降到 512**；只在池/窗口确实装不下时才降，且优先降窗口 | 保住 ~40% prefill | 0 | PR #1496、PR #2004 |
| **P1** | 试 --lm-head-draft + 中文词表裁剪（呼应 5258MF 的"13 万常用词头，快 10%"） | 投机解码 +5~10% | 低（换 flag） | fork QWEN38.md 的 draft_vocab 实测；reports/评论区与竞品项目-洞察.md |
| **P2** | 给 NInfer 提"消息边界检查点 + KV 预取流"两个功能（长历史只有最后一句改动时复用） | TTFT 大幅下降（Strata 侧 22.06 s → 0.404 s 类） | 中（引擎改动） | docs/MESSAGE_BOUNDARY_CACHE.md、docs/KV_PREFETCH.md、bench/results/2026-10-09…/README.md |
| **P2** | 若必须体验 125B：只装 **Gyro-S**（58.5 GB 下载，留 60 GB NVMe），strata launch --family gyro --model Gyro-S，上下文先 32K | 可跑；质量 -13%；decode 预期 40 上下 | 高中（60 GB 盘 + 学习成本） | GYRO.md:21、:28-40 |
| **不做** | 装 Strata 的 IQ2_XS/Q2_0 当日常主力 | 20.7 tok/s，且换页会卡死 | — | PR #2004 |

## 6.3 上游已知坑（装之前先看）

- **v0.2.7.1 / engine 0.1.53 显存占用暴涨**：VRAM 0 MiB free、请求持续溢出（6 条评论）https://github.com/Niko1221/Strata/issues/4474 。
- **v0.1.50 启动时会静默把 --prefill 改成 512**：https://github.com/Niko1221/Strata/issues/4164 。
- **sm_89（4060 Ti 16 GB）上 MTP 一个草稿都不提**：https://github.com/Niko1221/Strata/issues/4575 （与我们 NInfer 的 MTP 无关，但同卡同架构，装 Strata 前值得先确认）。
- **RTX 3070 长任务突然崩**：https://github.com/Niko1221/Strata/issues/2212 ；**3070 8 GB + 1660S 6 GB 混卡 docker 起不来**：https://github.com/Niko1221/Strata/issues/3899 。
- **质量侧**：Q2_0/IQ3_S 偶发在英文回答里蹦中文 token（官方怀疑是 base 模型而非量化）https://huggingface.co/ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-GGUF/discussions/60 ；IQ3_S 有一段可复现的"编造前文已读过文件"幻觉（50% 概率，Strata 与 Unsloth 都复现）https://huggingface.co/ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-GGUF/discussions/63 。
- **内存 <32 GB 别碰 125B**：多方口径一致（含 #1 的 31.9 GB 机器都会换页卡死）。

---

# 七、复现命令（网络侧，本报告全部结论可重跑）

    export HTTPS_PROXY=http://127.0.0.1:7897 HTTP_PROXY=http://127.0.0.1:7897
    # GitHub PR/issue 正文（不用 API，避开限流）
    python tmp/web/fetch.py "https://github.com/Niko1221/Strata/pull/2004"   # → tmp/web/pages/197477757d.txt
    python tmp/web/fetch.py "https://github.com/Niko1221/Strata/pull/2539"   # 4060 Ti 8GB + 64GB
    python tmp/web/fetch.py "https://github.com/Niko1221/Strata/pull/1972"   # 3070 8GB + 96GB, 196K
    python tmp/web/fetch.py "https://github.com/Niko1221/Strata/pull/1496"   # 3070 Ti 8GB + CPU share
    # 中文检索（360 可用；Bing 相关性差；知乎/CSDN/Reddit 不可用）
    python tmp/web/cn.py "Strata 8G 显存 实测 4060 生成速度"
    # HF 体积 / 讨论区
    python tmp/web/hf.py ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-GGUF
    python tmp/web/hfd.py ; python tmp/web/hfd2.py
    # 仓库内官方 bench（已 clone 到 tmp/web/Strata）
    grep -n "decode" tmp/web/Strata/bench/results/2026-10-09-community-rtx-3060-0141/README.md | head

---

# 八、本报告没做到 / 需要后来人补

- **博客园/掘金/微信公众号正文**未抓到：微信需客户端，知乎 403，CSDN 空壳。smzdm 的 4 篇长文只有摘要数字。
- **X/Twitter** 无 API key，未覆盖（Strata 的英文一手信息大量在 X 上）。
- **网盘只核实到 1 条夸克链接**，其余"一键包"全在视频/群里，无法核实是否含可执行文件（不建议下载运行）。
- **8 GB 单卡 + Gyro-S 的真实读数**全网未找到（现有是 3060 12 GB 62.5 tok/s 与 A750 8 GB 的 prompt 区间）——如果要上，这一步要我们自己实测补。
