# Strata 8 GB 显存模型选型：社区实践 × 能力上限

生成：2026-10-30　|　目标机器：Win11 / RTX 4060 Ti 8 GB（8,188 MiB）/ 31.1 GB DDR5　|　引擎：Strata 0.1.54

**证据规则**：只采信带 URL 的一手材料（官方文档、GitHub PR/issue、HF 模型卡与 API）。没有数字支撑的社区说法一律标【未核源】。

---

## 0. 结论（先给答案）

**首选 Qwen3.8-Flash-Next 的 IQ2_XS 档（低内存模式）**，而不是名声更大的 Qwen3.6-35B-A3B。

理由三句话：

1. **能力上限**：Flash-Next 在 SWE-bench Pro 上 62.5，35B-A3B 只有 49.5（+26%）；SWE-bench Multilingual 81.0 vs 67.2；NL2Repo 48.1 vs 29.4（+64%）——同门师弟打不过师兄。
2. **8 GB 可达性**：Flash-Next IQ2_XS 在 **RTX 4060 8 GB + 31.9 GB RAM**（和本机同一档内存）上有完整实测：decode **20.7 tok/s**，32,768 上下文，needles 8K/28K 3/3 —— https://github.com/Niko1221/Strata/pull/2004 。
3. **反观 35B-A3B**：社区里 8 GB 跑得最漂亮的例子（**50.6 tok/s**，RTX 3070 Ti 8 GiB + 31.1 GiB RAM）用的是**纯文本 Q5_K_S abliterated 权重、无 mmproj、无 vision、engine 0.1.44.1** —— https://github.com/Niko1221/Strata/pull/3597 。本机同 RAM 同显存档位用 UD-Q4_K_XL + mmproj-F16（0.86 GB）在 0.1.54 上 28 臂全灭，缺 242–418 MiB（见本目录 Strata-8G实测-Qwen36起不来.md）。**这不是模型不行，是那条配方多背了 0.86 GB 的视觉塔。**

**如果内存只有 31 GB**：走 Flash-Next IQ2_XS 低内存模式（专家从 SSD 页读），或直接试 35B-A3B 的**纯文本 GGUF**（去掉 mmproj 正好把 418 MiB 的窟窿填平）。
**如果内存 ≥ 64 GB**：Flash-Next IQ2_XS 能到 **51 tok/s**（PR #2539），不用再看别的。

---

## 1. 先纠正三个前提

### 1.1 官方清单只有三个顶层族，不是七个

https://github.com/Niko1221/Strata/blob/main/docs/MODELS.md 的候选全集是：

| 顶层族 | 真实参数量（HF safetensors total） | 身份 |
| --- | --- | --- |
| Qwen3.8-Flash-Next | 179,999,981,459 | 125B 主干 + 6B 激活 + 51B n-gram 表 |
| Qwen3.6-35B-A3B | 35,951,822,704 | 35B 总参 / 3B 激活 |
| DeepSeek-V4.1-Flash | 763,205,315,794 | 763B，8 GB 无关 |

docs/AI_REFERENCE.md 原文：*"Treat these as the three top-level families. Coder, Swift, Gyro, NVFP4 and OrcaRouter are Flash-Next variants, not additional top-level families."*

**Coder / Swift-1.5 / NVFP4 / OrcaRouter / Gyro 全部是 Flash-Next 的同权重变体**，不是新模型。把它们当独立候选会比出幻觉。

### 1.2 Gyro-S / Gyro-M 不是模型，是量化档

agentionai 的 Gyro 是「trellis-coded experts in a rotated basis」——对 **Qwen3.8-Flash-Next 权重**做的另一种压缩格式（https://github.com/Niko1221/Strata/blob/main/docs/GYRO.md ）。所以 Gyro-S 的能力上限 ≡ Flash-Next，区别只在**速度与内存形态**。

### 1.3 Nemotron-120B-A12B 不在 Strata 清单里

- 仓库无 NEMOTRON.md（404），docs 全文 grep "Nemotron" 零命中。
- 只有功能请求 PR #2740「Add a Nemotron-H MoE engine path (Nemotron 3.5 Super VL 120B-A12B)」和 issue #2657 —— https://github.com/Niko1221/Strata/pull/2740 。
- 本体 123,611,012,096 参数（https://huggingface.co/nvidia/NVIDIA-Nemotron-3-Super-120B-A12B-BF16 ）。

**结论：Strata 跑不了它，讨论到这就结束。** 硬要跑只能换 llama.cpp/LM Studio，而它的 GGUF 生态薄到可以忽略（下详）。

---

## 2. 逐候选体检（四问）

### 2.1 Qwen3.8-Flash-Next（含 Coder / Swift / Gyro / NVFP4 / OrcaRouter）

**① 本体是不是社区主流？—— 是，而且是最强的那一档。**

- HF 主仓 https://huggingface.co/Qwen/Qwen3.8-Flash-Next ：**3,853,710** 下载 / **6,644** likes。
- 量化仓 https://huggingface.co/ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-GGUF ：**7,604,113** 下载 / 1,089 likes —— 单是 GGUF 就比主仓还热。
- 非 Strata 生态的独立使用一大堆：SC117 abliterated 3,046,274、orcarouter 1,127,315、unsloth 1,088,374、Coder 1,059,206、Swift-1.5 763,096。
- ModelScope https://modelscope.cn/models/Qwen/Qwen3.8-Flash-Next ：93,865 下载 / 1,516 stars。
- Strata 仓库内相关 issue/PR 搜索 total_count：**IQ2_XS 549**、**IQ3_S 1,301** —— 这是全仓库讨论量最高的量化档。

**② 8 GB 上真实跑起来的公开报告？—— 有，而且三份，覆盖 32 / 64 / 96 GB 三种内存。**

| 报告 | 硬件 | 量化 | 上下文 | decode | prefill |
| --- | --- | --- | --- | --- | --- |
| [PR #2004](https://github.com/Niko1221/Strata/pull/2004) | RTX 4060 **8 GB** + **31.9 GB** RAM | IQ2_XS（低内存模式 --mmap-experts） | 32,768 | **20.7 tok/s**（82-token prompt，3 次中位） | 9.7K prompt 31.3 / 35.7 tok/s |
| [PR #2539](https://github.com/Niko1221/Strata/pull/2539) | RTX 4060 Ti **8 GB** + 64 GB RAM | IQ2_XS | — | **约 51 tok/s** | 4K 569 tok/s / 16K 624 tok/s |
| [PR #1972](https://github.com/Niko1221/Strata/pull/1972) | RTX 3070 **8 GB** + 96 GB RAM | IQ2_XS / IQ3_XXS / IQ3_S 六配置 | **196,608**（采样到 262,144） | **30.8–46.5 tok/s** | — |

PR #1972 附带八个 agent-coding 任务 **8/8 全过**；thinking 预设 decode 为 greedy 的 0.94。
PR #2004 的诚实记录：读 9.7K prompt 时**卡死过一次**（当时只剩 357 MiB RAM，专家页疯狂换页）—— 低内存模式的代价就是这个。

**③ 8 GB 上最高能上哪个量化档？**

MODELS.md 的门槛（RAM+VRAM 合计）：

| 档 | 合计门槛 | 其中 experts |
| --- | --- | --- |
| Q2_0 | **37.6 GB** | 34 GB |
| IQ2_XS | **39.2 GB** | 35.5 GB |
| IQ3_XXS | **47.0 GB** | 43 GB |
| IQ3_S | **54.8 GB** | 50 GB |

fits 规则：RAM ≥ experts + 约 10 GB。原文：*"With 64 GB ... every size fits; With 48 GB, Q2_0 and IQ2_XS fit."*

- **本机 31.1 GB RAM**：只能走低内存模式（--mmap-experts），实测档位 = **IQ2_XS**（PR #2004 就是这个配置）。
- **RAM 64 GB**：IQ2_XS 满血，51 tok/s。
- **RAM 96 GB**：**IQ3_S** 可用，这是 8 GB 显存的真实天花板（54.8 GB 合计门槛）。

量化质量：MODELS.md 称 IQ3_S *"matches the full model on the published tests"*；IQ3_S 与 Q8_0 top-token 一致率 87.7%，UD-IQ4_XS 88.9%。

**④ 横向能力上限？—— 第一。**

| 基准 | Flash-Next | 35B-A3B |
| --- | --- | --- |
| SWE-bench Pro | **62.5** | 49.5 |
| SWE-bench Multilingual | **81.0** | 67.2 |
| NL2Repo-Bench | **48.1** | 29.4 |
| SWE-bench Verified | — | 73.4 |
| Toolathlon Verified | **73.5** | — |
| JobBench | **55.7** | — |

（来源：https://huggingface.co/Qwen/Qwen3.8-Flash-Next 与 https://huggingface.co/Qwen/Qwen3.6-35B-A3B 模型卡基准表。）

---

### 2.2 Qwen3.6-35B-A3B

**① 社区主流度 —— 全场第一，无可争议。**

| 仓库 | 下载 | likes |
| --- | --- | --- |
| https://huggingface.co/Qwen/Qwen3.6-35B-A3B | **4,560,704** | **3,055** |
| Qwen3.6-35B-A3B-FP8 | 4,241,020 | — |
| nvidia/Qwen3.6-35B-A3B-NVFP4 | 3,994,686 | — |
| unsloth/Qwen3.6-35B-A3B-MTP-GGUF | 1,366,824 | 1,022 |
| unsloth/Qwen3.6-35B-A3B-GGUF | 1,321,885 | 1,741 |
| Huihui abliterated | 1,615,862 | — |
| HauhauCS uncensored | 983,207 | **4,046** |

ModelScope 615,380 下载 / 255 stars。Strata 仓库 total_count：**35B-A3B 105**、qwen36 50 —— 也是仓库里第二热的话题。**非 Strata 生态使用极多**（FP8/NVFP4/GGUF/abliterated 各版本全是独立发布）。

**② 8 GB 实测 —— 有一份很硬的，但配方特殊。**

[PR #3597](https://github.com/Niko1221/Strata/pull/3597)（2026-10-15，jkir4n）：

- 硬件 **RTX 3070 Ti 8 GiB + 31.1 GiB RAM**，上下文 **32,768**
- 权重：**llmfan46 abliterated Q5_K_S**（纯文本，**无 mmproj**），塞进 UD-Q4_K_XL 安装槽
- engine **0.1.44.1**，命令 plain：--native model.gguf --max-context 32768 --prefill auto --mtp 2
- short chat decode **50.6 tok/s**（46.6–60.7），TTFT 0.52 s
- 4K prompt 1,189 tok/s；16K prompt 1,100 tok/s（TTFT 14.6 s）；25K prompt 376 tok/s prompt + **14.7 tok/s** decode
- agent session decode 35.5（22.4–47.3）；并发 4 客户端 36.5 tok/s
- VRAM 恒定 7,666 / 8,192 MiB；**0 of 256 experts per layer 上卡**，专家全走 pageable host RAM；free RAM 0.2–3.8 GiB（贴内存边缘，Windows 一 trim 页面 decode 就掉到 ~14 tok/s）
- 正确性小测 5/5 通过

**⚠️ 与前文的冲突必须说清**：本机（RTX 4060 Ti 8,188 MiB + 31.1 GB DDR5，engine **0.1.54**）用 **UD-Q4_K_XL + mmproj-F16（0.86 GB）** 连续 28 臂全部 EngineDied，报错 *not enough VRAM left for the hybrid experts' buffers and slots (1159 MiB needed, 917 MiB free)* —— 缺 242–418 MiB。

差异只有两处：**（a）多背了 0.86 GB 视觉塔；（b）engine 版本新了 10 个小版本。** 而去掉 mmproj 释放的 ~880 MiB **大于** 418 MiB 的缺口——这是本报告里最便宜、最值得先试的一枪。

**③ 8 GB 最高量化档 —— 官方三档里能到 UD-Q4_K_XL，实测还能再高一档。**

| 档 | 文件 | RAM 计划 |
| --- | --- | --- |
| UD-Q4_K_XL | 22.9 GB | 32 GB |
| UD-Q6_K_XL | 32.6 GB | 44 GB |
| Q8_0 | 37.8 GB | 52 GB |

VRAM 侧不是瓶颈（专家全部走 host RAM），瓶颈是 **RAM = 文件 + 约 9–14 GB 系统余量**。PR #3597 用 Q5_K_S（≈23.9 GB 文件）在 31.1 GiB 上跑通，余量只剩 0.2–3.8 GiB。**本机 31.1 GB → 实际天花板就是 Q4/Q5 这一档，Q6 起不来。**

**④ 横向能力 —— 同门里第二，打不过 Flash-Next。** 见 §2.1 ④ 的对照表。它的定位本来就是小卡：PR #1402 标题直接写 *"a second, smaller model for 8-12 GB cards"*。

---

### 2.3 Gyro-S / Gyro-M

**① 是不是主流？—— 不是，是 Flash-Next 的一个小众量化格式。**

https://huggingface.co/agentionai/Qwen3.8-Flash-Next-Gyro-GGUF ：**523,837** 下载 / 146 likes。相对主仓 3.85M / 7.6M（ISTA GGUF），占比不到 10%。Strata 仓库 total_count "Gyro" = 74。**除 Strata 之外的独立使用几乎看不到**【未核源】。

**② 8 GB 实测 —— 有一份，在 Intel Arc 上。**

https://github.com/Niko1221/Strata/blob/main/docs/GYRO.md （第 146–168 行），**Intel Arc A750 8 GB + 62 GB RAM，32K 上下文**：

| | decode | prompt（1.4K / 2.4K / 20K tok） |
| --- | --- | --- |
| Gyro-S | **15.8 tok/s** | 82.0 / 101.9 / 195 tok/s |
| Gyro-M | **14.2 tok/s**（12.6–14.4） | — |

- 8 GB 卡只能放 24,576 个 experts 中的 **410 个**。
- **Gyro-M 在 8 GB 上 32K 放不下**：差 750 MiB 连一个 cache slot 都开不出，必须降参才起得来：--max-context 8192 --vram-reserve-mib 100 --prefill 1024（412 slots）。
- CUDA 8 GB 上的 Gyro 实测【未核源】—— 公开记录只有 Arc。

**③ 8 GB 最高量化档**：Gyro-S 合计门槛 **27.6 GB**（下载 58.5 GB）、Gyro-M **35 GB**（下载 92.0 GB）。注意下载体积里含 **28 GB 的 n-gram 表**，跟运行内存不是一回事。门槛看着低，是因为它把 experts 摊到 SSD 页读——代价直接写在速度上。

**④ 横向**：能力上限 = Flash-Next（同权重），但**速度只有 Flash-Next IQ2_XS 的 1/2 到 1/3**（15.8 vs 20.7–51），且 Gyro-M 比 Q2_0 还慢 16–21%（RTX 3060 12 GB / R9700 实测）。**没有任何理由在 8 GB 上选 Gyro 而不是 IQ2_XS。**

---

### 2.4 DeepSeek-V4.1-Flash

**① 主流度**：https://huggingface.co/deepseek-ai/DeepSeek-V4.1-Flash **1,895,422** 下载 / 4,791 likes；ModelScope 80,054 / 731。Strata total_count 109。**主流，顶级。**

**② 8 GB 实测？—— 不存在，因为硬件门槛就卡在 12 GB。**

MODELS.md 明确：需 **≥12 GB 显存 + ≥46 GB RAM**（64 GB 舒适）+ NVMe；上下文 8K。8 GB 上没有任何公开报告，只有 12 GB 卡的：

- RTX 5070 12 GB：约 **5 tok/s**（code）
- RTX 3060 12 GB：**6–9 tok/s**

**③ 8 GB 最高量化档 —— 无。** 最低档 IST-DAS 1.75bpw 就要 **239 GB** 下载（2.00bpw 257 GB / 2.25bpw 274 GB），显存侧 12 GB 是硬底线，8 GB 连模型壳都装不下。

**④ 能力上限 —— 绝对第一（763B），但在 8 GB 上是纯理论。** 直接出局。

---

### 2.5 Nemotron-120B-A12B

**① 主流度 —— 分化严重。**

- 本体 https://huggingface.co/nvidia/NVIDIA-Nemotron-3-Super-120B-A12B-BF16 ：1,155,028 下载 / 438 likes；NVFP4 版 524,473。
- **但 GGUF 生态极薄**：unsloth 同款 GGUF 仅 **9,309** 下载 / 155 likes，lmstudio-community 3,764，bartowski 2,286。对比 Qwen3.6-35B-A3B 的 1.37M——差两个数量级。
- 说明：社区主要在数据中心/NVFP4 上用它，**几乎没人在量化小卡上折腾它**。

**② 8 GB 实测 —— 无。** Strata 不支持（§1.3）。

**③ 8 GB 最高量化档 —— 不适用。** 无 Strata 打包；本体 123.6B，Q2 级也要 40 GB 量级【未核源，无官方 GGUF 门槛数字】。

**④ 横向 —— 出局。** 不是能力问题，是**引擎根本不认这个 arch**。

---

## 3. 8 GB 可行的量化档矩阵（RAM + VRAM 合计门槛）

| 模型 | 档位 | 合计门槛 | 8 GB 可行性 |
| --- | --- | --- | --- |
| Qwen3.8-Flash-Next | Q2_0 | 37.6 GB | ✅ 需 RAM ≥ 44 GB |
| Qwen3.8-Flash-Next | IQ2_XS | 39.2 GB | ✅ 需 RAM ≥ 45 GB；**31 GB 走低内存模式也可**（实测） |
| Qwen3.8-Flash-Next | IQ3_XXS | 47.0 GB | ✅ 需 RAM ≥ 53 GB |
| Qwen3.8-Flash-Next | **IQ3_S** | **54.8 GB** | ✅ **8 GB 显存天花板**（需 RAM ≥ 60 GB） |
| Flash-Next Coder | IQ1_M | 29.6 GB（shard1） | ✅ 门槛最低，但能力弱于主型号 |
| Gyro-S | TQ1_0 | 27.6 GB | ✅ 门槛最低，速度 15.8 tok/s |
| Gyro-M | — | 35 GB | ⚠️ 32K 放不下，必须降到 8K |
| Qwen3.6-35B-A3B | UD-Q4_K_XL | ≈40 GB（32 RAM + 8 VRAM） | ✅ 最快 50.6 tok/s（需纯文本 GGUF） |
| Qwen3.6-35B-A3B | UD-Q6_K_XL | ≈52 GB | ✅ 需 RAM 44 GB |
| Qwen3.6-35B-A3B | Q8_0 | ≈60 GB | ✅ 需 RAM 52 GB |
| DeepSeek-V4.1-Flash | 1.75bpw | 239 GB 下载 + 12 GB VRAM | ❌ 显存不够 |
| Nemotron-120B-A12B | — | — | ❌ 引擎不支持 |

---

## 4. 排序表

| # | 模型 | 量化档 | 门槛 GB（合计） | 8G 实测 tok/s | 社区实践量 | 结论 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | **Qwen3.8-Flash-Next** | IQ2_XS（低内存） | 39.2（31 GB RAM 可跑） | **20.7**（31.9 GB RAM）／**51**（64 GB RAM） | HF 3.85M + ISTA GGUF 7.6M；Strata IQ2_XS 549 帖 | **推荐**。能力上限最高且 8 GB 有实测 |
| 2 | Qwen3.8-Flash-Next | IQ3_S | 54.8 | 30.8–46.5（96 GB RAM） | 同上，IQ3_S 1,301 帖 | RAM ≥ 64 GB 时的最优解 |
| 3 | **Qwen3.6-35B-A3B** | UD-Q4_K_XL / Q5_K_S（纯文本） | ≈40 | **50.6**（3070 Ti 8G/31.1G RAM） | **HF 4.56M**（全场第一）；Strata 105 帖 | **次选/最快**。必须去掉 mmproj，本机 0.1.54 上验证过会差 418 MiB |
| 4 | Qwen3.6-35B-A3B | UD-Q6_K_XL | ≈52 | 无 8 GB 报告【未核源】 | 同上 | RAM ≥ 44 GB 才考虑 |
| 5 | Gyro-S | TQ1_0 | 27.6 | 15.8（Arc A750 8G） | HF 524K；Strata 74 帖 | 不推荐。同权重下速度只有 IQ2_XS 一半 |
| 6 | Gyro-M | — | 35 | 14.2（须降到 8K 上下文） | 同上 | 不推荐。8 GB 上最差的选择 |
| 7 | DeepSeek-V4.1-Flash | 1.75bpw | 239 下载 + 12 GB VRAM | 无（需 ≥12 GB 显存） | HF 1.90M | 出局。12 GB 卡上也只有 5–9 tok/s |
| 8 | Nemotron-120B-A12B | — | — | 无 | HF 1.16M，但 GGUF 仅 9.3K | 出局。Strata 无此 arch，仅 PR #2740 请求 |

---

## 5. 给这台机器（8 GB / 31.1 GB RAM）的动作顺序

1. **先补一枪 35B-A3B（成本最低，收益最大）**：换**纯文本 GGUF**（llmfan46 abliterated Q5_K_S 或任何不含 mmproj 的 35B-A3B GGUF），配置里整段删掉 vision，对齐 PR #3597 的命令面：--max-context 32768 --prefill auto --mtp 2。去掉 0.86 GB 视觉塔正好覆盖 418 MiB 缺口。成功即拿到 **~50 tok/s** 的 8 GB 最优解。
2. **并行下 Flash-Next IQ2_XS**（35.5 GB 下载），低内存模式开起来，预期 **~20 tok/s**，能力上限比 35B 高 26%。
3. **Gyro-S 别等了**：下载 58.5 GB（含 28 GB n-gram 表），跑起来只有 15.8 tok/s，性价比最差。
4. 内存升到 64 GB 是**最高杠杆的单点升级**：IQ2_XS 从 20.7 → 51 tok/s（2.5×），IQ3_S 也能上。

---

## 6. 证据索引

| 编号 | URL |
| --- | --- |
| 官方模型清单 | https://github.com/Niko1221/Strata/blob/main/docs/MODELS.md |
| 清单身份说明 | https://github.com/Niko1221/Strata/blob/main/docs/AI_REFERENCE.md |
| Gyro 文档 | https://github.com/Niko1221/Strata/blob/main/docs/GYRO.md |
| 35B-A3B 8 GB 实测 | https://github.com/Niko1221/Strata/pull/3597 |
| Flash-Next 8 GB / 31.9 GB RAM | https://github.com/Niko1221/Strata/pull/2004 |
| Flash-Next 8 GB / 64 GB RAM | https://github.com/Niko1221/Strata/pull/2539 |
| Flash-Next 8 GB / 96 GB RAM / 196K 上下文 | https://github.com/Niko1221/Strata/pull/1972 |
| 8 GB 反例（IQ3_S + 64K 放不下） | https://github.com/Niko1221/Strata/issues/300 |
| 35B-A3B 定位（8–12 GB 卡） | https://github.com/Niko1221/Strata/pull/1402 |
| Nemotron 功能请求 | https://github.com/Niko1221/Strata/pull/2740 |
| Flash-Next 模型卡与基准 | https://huggingface.co/Qwen/Qwen3.8-Flash-Next |
| 35B-A3B 模型卡与基准 | https://huggingface.co/Qwen/Qwen3.6-35B-A3B |
| Flash-Next 量化仓 | https://huggingface.co/ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-GGUF |
| Gyro 量化仓 | https://huggingface.co/agentionai/Qwen3.8-Flash-Next-Gyro-GGUF |
| DeepSeek-V4.1-Flash | https://huggingface.co/deepseek-ai/DeepSeek-V4.1-Flash |
| Nemotron-120B-A12B | https://huggingface.co/nvidia/NVIDIA-Nemotron-3-Super-120B-A12B-BF16 |
| 35B-A3B 官方 GGUF | https://huggingface.co/unsloth/Qwen3.6-35B-A3B-MTP-GGUF |

---

## 7. 未核源 / 存疑项

- Gyro 系列在 **CUDA** 8 GB 卡上的实测：公开记录只有 Intel Arc A750 8 GB，CUDA 侧无数据。
- Nemotron-120B-A12B 在 8 GB 上的任何速度数字：无（引擎不支持）。
- Qwen3.6-35B-A3B 在 8 GB 上跑 UD-Q6_K_XL：无公开报告。
- "35B-A3B 比 Flash-Next 更适合小卡"这类说法：PR #1402 只说它是为 8–12 GB 卡准备的**第二个**模型，**没有任何基准支撑它更强**；模型卡数据反而全面落后。
