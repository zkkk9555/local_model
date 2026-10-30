# Qwen3.8-Flash-Next 体检（125B-A6B，8 GB 显存 / 31 GB 内存视角）

> 侦察日期：2026-10-30 · 全部结论只采信带 URL 的一手页面
> 采信等级：**[一手]** = 官方仓库/官方文档/提交者本人的 benchmark issue；**[二手]** = 汇总页转述；**【未核源】** = 论坛/视频说法，未找到一手出处

---

## 0. 三个问题的直接答案

| 问题 | 答案 | 一句话理由 |
|---|---|---|
| ① 它是不是 8 GB 现在能碰到的最强模型？ | **是「8 GB 显存这一档里质量上限最高的开源权重模型」，但「8 GB 就能碰到」这个前提本身是假的** | 卡门槛的不是 8 GB 显存，是**内存**：Q2_0 的专家就要 34 GB 常驻 RAM，加余量约 44 GB。31 GB 内存的机器连 Q2_0 都进不去，只能跑砍半专家的 Coder 或 SSD 流式 |
| ② Q2_0 与 IQ2_XS 哪个更划算？ | **Q2_0**（在 8 GB 这种带宽/算力都紧的机器上） | prefill 3.4 倍（367 vs 108 t/s）、decode 1.33 倍（93.8 vs 70.3）、文件还小 1.6 GB，基准分只差 0.09（89.07 vs 89.16）；代价是分布层面更糙（Q2_0 困惑度 4.475 vs Q8_0 4.052，+10.4%） |
| ③ 31 GB 内存够不够？ | **不够**（满尺寸四档全不够；只有 Coder 勉强在边界上） | 官方口径「RAM 大于等于 专家 + 约 10 GB」：Q2_0 34+10 约 44 GB、IQ2_XS 35.5+10 约 45.5 GB、IQ3_XXS 43+10 约 53 GB、IQ3_S 50+10 约 60 GB；Coder 23+10 约 33 GB（31.1 GiB=33.4 GB，刚好擦线） |

---

## 1. 官方事实（一手）

**发布页 / 权重**
- HF 权重页：<https://huggingface.co/Qwen/Qwen3.8-Flash-Next> —— 仓库创建 2026-08-24，最后更新 2026-08-27；下载 3,853,710、likes 6,644（本次抓取时）；license qwen-community-1.0；pipeline image-text-to-text（带视觉编码器）
- 官方博客（模型卡指向）：<https://qwen.ai/blog?id=qwen3.8-flash-next> —— **该页为 JS 渲染，curl 只拿到 43 字节正文，无法直接取证**，故本文参数以模型卡 + config.json 为准
- 技术报告：<https://github.com/QwenLM/Qwen3.8-Flash-Next/blob/main/tech_report.pdf>（未下载核读）
- 商用版说明：模型卡称 Qwen3.8-Flash 是它的生产版（默认 1M 上下文、内置工具），<https://www.qwencloud.com/models/qwen3.8-flash>

**参数（模型卡 Model Overview 原文）**
- **语言模型 125B 参数、每 token 激活 6B**；**另加 51B n-gram embedding**（20,000,000 个 bigram/trigram，挂在第 2 层）+ **4B MTP 草稿层**
- 因此 **safetensors 总参数 179,999,981,459**（HF API safetensors.total）约 180B；BF16 权重 131 个分片、约 **354 GB**
- 48 层；hidden 2560；**512 个专家，每 token 10 routed + 1 shared 激活**；专家中间维 640
- 架构：Qwen4ExpForConditionalGeneration / model_type qwen4_exp（config.json 一手：<https://huggingface.co/Qwen/Qwen3.8-Flash-Next/raw/main/config.json>，字段 num_experts: 512、num_experts_per_tok: 10、num_hidden_layers: 48、vocab_size: 248320）
- 注意力：Gated DeltaNet + Qwen Sparse Attention（QSA，micro-block 稀疏，预算 512 blocks / 2048 tokens）
- 上下文：**原生 262,144**，可扩到 1,000,000
- 命名纠偏：叫 125B 指的是**语言模型主体**；连 n-gram 表与 MTP 一起算，**实际是 180B 参数 / 每 token 约 6B 激活**。本地清单里「125B 级」的说法没错，但「85 GB 文件」对应的是 **IQ3_S（83.6 GB）**，不是任意一档

---

## 2. 量化档：文件大小与质量损失

一手来源：**ISTA-DASLab GSQ-RCO 量化仓库** <https://huggingface.co/ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-GGUF>
（方法与论文：GSQ <https://arxiv.org/abs/2604.18556>、RCO <https://arxiv.org/abs/2605.00649>；每张量单独选型，不是统一量化）

### 2.1 文件构成（关键结构事实）
每个量化都是 **两个分片**：
- **分片 1 = transformer 权重**（要常驻）
- **分片 2 = n-gram 查找表 per_layer_token_embd，51.2B 参数，固定 IQ4_NL，28.8 GB**，**四档完全相同**，且**不进搜索**（它是查表不是矩阵乘）
- 视觉投影 mmproj-Qwen3.8-Flash-Next-BF16.gguf = 0.91 GB（四档共用）

| 档位 | bpw | 分片 1（权重） | 分片 2（n-gram） | 合计 | HF 实测字节 |
|---|---:|---:|---:|---:|---|
| **Q2_0** | 2.40 | 37.6 GB | 28.8 GB | **66.4 GB** | 37.62 + 28.80 = 66.42 GB |
| **IQ2_XS** | 2.50 | 39.2 GB | 28.8 GB | **68.0 GB** | 39.23 + 28.80 = 68.03 GB |
| **IQ3_XXS** | 3.00 | 47.0 GB | 28.8 GB | **75.8 GB** | 47.04 + 28.80 = 75.84 GB |
| **IQ3_S** | 3.50 | 54.8 GB | 28.8 GB | **83.6 GB** | 54.82 + 28.80 = 83.62 GB |
| BF16（参照） | 16 | — | — | 354 GB | 131 分片 |

> 另有 **Coder** 变体（每层 512 专家砍到 256）：<https://huggingface.co/ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-Coder-GGUF>，单档 IQ1_M、**分片 1 = 29.6 GB（其中专家 23 GB）**，官方自评保留 91% SWE-bench Verified / 99% LiveCodeBench，但「代码以外、非中英日韩语言明显更弱」

### 2.2 质量损失（ISTA 官方评测，对照 BF16 基座）
五零样本均值（arc_easy/arc_challenge/hellaswag/winogrande/piqa）+ 三个推理/生成基准：

| 档 | bpw | GB | ZS 均值 | 恢复率 | AIME25 | GPQA-D | LCB v6 | 三项均值 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| BF16 | 16.00 | 354 | 76.94 | 100.0% | 100.00 | 91.92 | 87.43 | 93.12 |
| **Q2_0** | 2.40 | 66.4 | **78.00** | **101.4%** | 96.67 | 89.39 | 81.14 | 89.07 |
| **IQ2_XS** | 2.50 | 68.0 | 77.16 | 100.3% | 96.67 | 87.37 | 83.43 | 89.16 |
| **IQ3_XXS** | 3.00 | 75.8 | 77.23 | 100.4% | **100.00** | 91.41 | 86.29 | 92.57（基座 99.4%） |
| **IQ3_S** | 3.50 | 83.6 | n/a | n/a | **100.00** | **92.93** | **86.86** | **93.26** |

官方结论口径：「IQ3_XXS 拿到基座 99.4% 的三项均值，体积只要 1/4.7；IQ2_XS 保留 95.7%；Q2_0 最省但掉 3.5 分」；「IQ3_S 是推荐档，每项持平或超过基座」。

### 2.3 分布层面的质量（Strata 独立测量，比基准分更敏感）
docs/QUANTS.md（<https://github.com/Niko1221/Strata/blob/main/docs/QUANTS.md>）在 R9700 上用 4,995 个位置、teacher-forced、对 Q8_0 算 top-1 一致率与 KL：

| 量化 | 与 Q8_0 同 top-1 | 平均 KL | KL p99 | 困惑度（Q8_0 = 4.052） |
|---|---:|---:|---:|---:|
| UD-Q6_K_XL | 94.61% | 0.033 | 0.494 | 4.020 |
| UD-Q4_K_XL | 93.09% | 0.056 | 0.829 | 4.068 |
| UD-IQ4_XS | 88.91% | 0.101 | 1.596 | 4.120 |
| **IQ3_S** | 87.69% | 0.144 | 1.975 | 4.097 |
| **IQ3_XXS** | 84.46% | 0.202 | 2.433 | 4.119 |
| **Q2_0** | **80.60%** | **0.315** | **3.643** | **4.475（+10.4%）** |

⚠️ **IQ2_XS 在这张表里没有测**（Strata 只测了 Q2_0 和 IQ3 两档）。所以「Q2_0 比 IQ2_XS 糙多少」目前没有第三方分布证据，只有 ISTA 的基准分（两者 89.07 vs 89.16，基本相同）。

---

## 3. 8 / 12 / 16 GB 的真实运行报告

### 3.1 8 GB 级（这一档证据最少，但都是本人提交）
| 硬件 | 型号/量化 | 上下文 | 结果 | 来源（一手） |
|---|---|---|---:|---|
| **RTX 4060 8 GB + RTX 2060 6 GB**（合计 14.3 GB VRAM）、i7-9700KF、**62 GB RAM**、SATA SSD、v0.1.43.1 | **IQ2_XS** + mmproj + MTP q2_0 | 32,768，KV int8，--spec 4 | **decode 稳定约 36 tok/s**，无退化；6 GB 的 2060 低于 Strata 的 8 GB 建议线但仍能协同 | <https://github.com/Niko1221/Strata/issues/2248> |
| **RX 6600 XT 8 GB**（gfx1032，非支持列表）、Xeon E5-2678 v3、64 GB DDR3-1600、NVMe、v0.1.40.1 HIP | **IQ3_XXS**（GSQ-RCO 与 Uncensored 两版） | 10,567 token 提示 | **可用**；自动分块下 **prefill 约 250 tok/s**（Uncensored 版 318 tok/s）；需自建 gfx1030 引擎 + HSA_OVERRIDE_GFX_VERSION=10.3.0 | <https://github.com/Niko1221/Strata/issues/1375> |
| **2x Quadro RTX 4000 8 GB**、E5-2620 v3、96 GB RAM | Swift-Qwen3.8-Flash-Next **IQ2_XS** | 131,072 | 73k–74k token 提示：**prefill 100–250 tok/s、decode 18–23 tok/s** | <https://github.com/Niko1221/Strata/blob/main/docs/COMMUNITY_BENCHMARKS.md>（2026-10-07 条） |
| **RTX PRO 2000 Laptop 8 GB**、Windows | IQ3_XXS | 29,854 token 提示 | --prefill-head-alias 把 prefill 从 **292.5 → 667.1 tok/s**（分块 512→2048）；该旗标文档注明 For 8 GB cards | <https://github.com/Niko1221/Strata/blob/main/docs/DETAILS.md> |
| **RTX 2060 6 GB + 32 GB RAM** | — | — | **起不来**（Unable to launch）→ 说明 **8 GB 是硬门槛**，6 GB 不行 | <https://github.com/Niko1221/Strata/issues/916> |

**负面发现（重要）**：仓库里**没有**「单张 8 GB 卡 + 32 GB 内存跑满尺寸 Q2_0/IQ3_S」的一手 benchmark。8 GB 的报告全部配 **62–96 GB 内存**。8 GB 显存这一档唯一的官方定性描述是 ISTA 模型卡：「runs these GGUFs on a single NVIDIA GPU **from 8 GB of VRAM**」（<https://huggingface.co/ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-GGUF>）。

### 3.2 12 GB
| 硬件 | 量化 | 短对话 / 128K / 32K prefill | 来源 |
|---|---|---|---|
| RTX 5070 12 GB、Ryzen 5 7600、64 GB RAM（引擎 0.1.26/0.1.36） | Q2_0 | **94 / 76 / 2,650 tok/s** | Strata docs/MODELS.md 历史表 |
| 同上 | IQ2_XS | 79 / 63 / 2,090 | 同上 |
| 同上 | IQ3_XXS | 62 / 49 / 1,750 | 同上 |
| 同上 | IQ3_S | 53 / 46 / 1,620 | 同上 |
| 同上 | Coder (IQ1_M) | 55 / 43 / 2,180 | 同上 |
| RTX 3060 12 GB、i7-12700、64 GB RAM（v0.1.41 官方 Windows 版） | Q2_0 / IQ2_XS / IQ3_XXS / IQ3_S 全测 | 提示长度 128→128K（三档到 260K），含 recall、HumanEval 0-39、MTP、并发 | <https://github.com/Niko1221/Strata/blob/main/docs/COMMUNITY_BENCHMARKS.md>（2026-10-09 条） |

### 3.3 16 GB
| 硬件 | 量化 | 数字 | 来源 |
|---|---|---|---|
| RX 9070 XT 16 GB、Ryzen 9 3900X、47 GB RAM | Q2_0 | 60 / 48 / 1,160 | Strata docs/MODELS.md 历史表 |
| 同上 | IQ2_XS | 52 / 36 / 1,110 | 同上 |
| RTX 5060 Ti 16 GB（**估算 ±20%**，非实测） | Q2_0 | 1K 341/80 → 128K 476/62 → 262K 435/53（prompt/decode） | docs/DETAILS.md 其他 GPU 估计表 |
| RX 9070 16 GB（实测，IQ3_XXS，131K） | IQ3_XXS | decode 58.7/57.9/57.9；prompt 586/804/833 @4.2k/33k/130k；needle 6/6 | COMMUNITY_BENCHMARKS（2026-10-10 条） |
| RTX 4060 Ti 16 GB（Windows，长上下文专题） | — | 有专帖，未逐项摘录 | <https://github.com/Niko1221/Strata/issues/3558> |

> 社区共识：**8 GB 档 18–40 tok/s、12 GB 档 50–95 tok/s、16 GB 档 45–60 tok/s @128K**；决定速度的是「专家能不能待在内存里」，不是显卡档次。

---

## 4. 31 GB 内存够不够：「专家 + 约 10 GB」的原始出处与准确含义

### 4.1 出处（一手，可点开）
**Strata 官方文档 docs/MODELS.md 的 Qwen3.8-Flash-Next 段「Will it fit?」原文：**

> Shard 1 is loaded at start: its experts go into **RAM**, the rest onto the graphics card. The second shard (a 29 GB lookup table) stays on the SSD. The model fits when **RAM is at least the experts plus about 10 GB** for the OS and other programs.

URL：<https://github.com/Niko1221/Strata/blob/main/docs/MODELS.md>

同页给出的「专家」数字（一手）：

| 档 | 分片 1 里专家占的 RAM |
|---|---:|
| Q2_0 | **34 GB** |
| IQ2_XS | **35.5 GB** |
| IQ3_XXS | **43 GB** |
| IQ3_S | **50 GB** |
| Coder (IQ1_M) | **23 GB** |

### 4.2 准确含义（别望文生义）
1. **进内存的是「专家（routed experts）」，不是整个文件。** 分片 1 里非专家的部分（attention/embedding/output head 等）上显存。
2. **28.8 GB 的 n-gram 表不进内存**：它是查表，按 token 稀疏读，靠 -lm mmap --lazy-mode on（llama.cpp）或 --ple-io 留在 SSD 上；**这是 31 GB 内存机器唯一还能喘气的原因**。
3. **「约 10 GB」是给 OS 和其它程序的余量，不是模型权重**。同一仓库 docs/DETAILS.md 的老表把它写成 **「约 34 GB experts + 约 6 GB」**（<https://github.com/Niko1221/Strata/blob/main/docs/DETAILS.md>），即严格下限是 **专家 + 6 到 10 GB**。两处口径不一致，按更保守的 10 GB 算。
4. 另有第三处口径：DETAILS.md 说 RAM 覆盖「模型需求 + n-gram 表 + 16 GB」时 n-gram 表才整体进内存（那是图省事的更高配，不是最低要求）。

### 4.3 对本机（31.1 GiB 约 33.4 GB）的判读
- Q2_0：专家 34 GB 大于 33.4 GB ⇒ **连专家都放不下**，加余量后需约 44 GB ⇒ **不够**
- IQ2_XS / IQ3_XXS / IQ3_S：更不够（45.5 / 53 / 60 GB）
- **Coder**：23 + 10 = 33 GB ⇒ **刚好擦线**（33.4 GB），要求后台基本全关；且 Coder 代码以外明显弱
- 想跑满尺寸的最低现实配置：**48 GB 内存（Q2_0/IQ2_XS）到 64 GB（IQ3_S）**，官方原文：「With 64 GB of RAM every size fits (IQ3_S with little else open). With 48 GB, Q2_0 and IQ2_XS fit.」
- 唯一「31 GB 也能起」的路径是 --low-ram：专家从模型文件 mmap、只把显卡装不下的部分留内存 —— 官方描述「a 32 GB PC with a 24 GB GPU runs Q2_0/IQ2_XS/Coder this way」「With a small card most experts come from the SSD and **it is much slower**」。8 GB 卡属于小卡，等于常态化读盘。

---

## 5. 非 Strata 路线：llama.cpp / KTransformers / 其他

- **llama.cpp**：ISTA 量化卡明说四档 GGUF「run unmodified in llama.cpp, Ollama, and LM Studio」，给出的启动式是 llama-cli -m ... -lm mmap --lazy-mode on -ngl 99（<https://huggingface.co/ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-GGUF>）。Strata 的 docs/QUANTS.md 里也用 llama.cpp 8bb3cf0d2（-ngl 99 --n-cpu-moe 38-48）做同卡对照。但 llama.cpp 没有 Strata 那套专家缓存/PCIe 分片，**8 GB 显存 + 31 GB 内存** 这个组合下它不是可行方案（专家要么全内存、要么纯 CPU）。
- **KTransformers**：**没有 Qwen3.8-Flash-Next 支持**。官方 README 更新日志到 2026-10-15，最近的支持是 DeepSeek-V4-Flash（LoRA）、GLM-5.3-flash（08-26）、Kimi K2.5/K2.6、MiniMax-M3；全文无 qwen3.8 / flash-next 字样（<https://github.com/kvcache-ai/ktransformers>）。它走的是 DeepSeek/GLM/Kimi 那条线，不是这套架构。
- **Unsloth GGUF**：<https://huggingface.co/unsloth/Qwen3.8-Flash-Next-GGUF> 提供 UD-IQ1_M/S、UD-Q2_K_XL、UD-IQ3_XXS、UD-IQ4_XS、UD-Q3 到 Q8 全套 + MTP 层；官方口径「需要 72–136 GB 才能把所有专家放内存」（Strata docs/MODELS.md）。1–2 bit 档在 8 GB 上更慢（要查表），不如 GSQ-RCO 的 Q2_0。
- **Strata 的模型清单里没有 Nemotron**：docs/MODELS.md 只列 DeepSeek V4.1-Flash、Qwen3.8-Flash-Next（含 Coder/Swift/Gyro/Unsloth/NVFP4）、Qwen3.6-35B-A3B。本地旧文档里「Strata 面向 Qwen3.8-Flash-Next、Nemotron 120B-A12B」的 Nemotron 部分**找不到出处，标【未核源】**。

---

## 6. 判读：三个问题的完整回答

### ① 是不是 8 GB 能碰到的最强模型？
**分两层说：**
- **「8 GB 显存」不是门槛，「内存」才是。** 官方/文档口径是「单卡 8 GB 显存起」，但同一份文档写着满尺寸要 48–64 GB 内存。所以「8 GB 能碰到」这句话只有在 **8 GB 显存 + 至少 48 GB 内存** 时成立；**8 GB 显存 + 32 GB 内存 = 只能 Coder 或 SSD 流式**，那不是跑 125B，是跑 125B 的一半专家。
- **在「能碰到」的那些配置里，它确实是这一档质量最高的开源权重模型**：100B 级 MoE、原生 256K、IQ3_XXS 保留基座 99.4% 的三项均值（AIME25 满分）、IQ3_S 反超基座；同一个 8–16 GB 显存档里，Strata 能跑的另一个模型 Qwen3.6-35B-A3B（35B-A3B）体量与分数都低一档（它自己也要 32–52 GB 内存）。
- **但「最强」没有第三方横评证据**：唯一的横向对照来自 ISTA 自己的量化评测（对照的是它自己的 BF16 基座），没有人在 8 GB 卡上把 Flash-Next 与其它同级模型做过同机对比。所以严谨表述是：**「8 GB 显存这一档里，质量上限最高的开源模型之一，且是唯一有成熟 8 GB 落地工具链（Strata）的 100B+ 模型」**，而不是「实测最强」。

### ② Q2_0 与 IQ2_XS 哪个更划算？
**Q2_0，但要看你在买什么：**

| 维度 | Q2_0 | IQ2_XS | 谁赢 |
|---|---|---|---|
| 体积 | 66.4 GB（少 1.6 GB） | 68.0 GB | Q2_0 |
| ISTA 三项均值 | 89.07 | 89.16 | 平（差 0.09） |
| GPQA-D / LCB v6 | 89.39 / 81.14 | 87.37 / 83.43 | 各赢一项（推理 vs 代码） |
| prefill（llama.cpp，55 提示） | **367.5 t/s** | 108.2 t/s | Q2_0 **3.4 倍**（RAG 9.6 倍、写作 6.8 倍、代码 6.2 倍） |
| decode | **93.8 t/s**（92.5–94.5 稳） | 70.3 t/s（49.4–94.5 抖） | Q2_0 **1.33 倍**，且稳定 |
| 端到端时延 | **6.70 s** | 12.68 s | Q2_0 1.9 倍 |
| 分布质量（Strata KL/PPL） | 80.60% / PPL 4.475 | 未测 | 无法比；但 Q2_0 是全表最糙 |

结论：**8 GB 这种显存紧、内存紧、每 token 都要搬专家的机器上，Q2_0 明显更划算** —— 它把省下来的时间花在 prefill（长文档/RAG 是 9.6 倍），而基准分几乎不掉。但如果你**真的在乎代码准确率**且内存允许，IQ2_XS 的 LCB 高 2.3 分；再往上一步 **IQ3_XXS（多 9.4 GB，恢复 99.4%）才是真正的质量台阶**，那已经不是划算问题而是内存够不够问题。
一句话：**Q2_0 优于 IQ2_XS（同内存档内）；但只要内存能到 48 GB，就该直接 IQ3_XXS 而不是在这两档里挑。**

### ③ 31 GB 内存够不够？
**不够，差 10 GB 以上。** 依据见第 4 节：Q2_0 专家 34 GB 即已超过 31.1 GiB（33.4 GB），按「专家 + 约 10 GB」需约 44 GB；Coder（23+10=33 GB）是唯一擦线选项。想真跑满尺寸，内存要 **48 GB（Q2_0/IQ2_XS）到 64 GB（IQ3_S）**，或者接受 --low-ram 的 SSD 流式（官方原话 much slower，且 8 GB 属于 small card）。

---

## 7. 证据清单（全部可点开）

| # | 用途 | URL | 等级 |
|---|---|---|---|
| 1 | 官方权重页（参数、上下文、架构、许可） | <https://huggingface.co/Qwen/Qwen3.8-Flash-Next> | 一手 |
| 2 | 官方 config.json（512 专家 / top-10 / 48 层） | <https://huggingface.co/Qwen/Qwen3.8-Flash-Next/raw/main/config.json> | 一手 |
| 3 | 官方博客（JS 渲染，正文未取到） | <https://qwen.ai/blog?id=qwen3.8-flash-next> | 一手但不可读 |
| 4 | 四档量化：大小/bpw/评测/性能/内存构成 | <https://huggingface.co/ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-GGUF> | 一手 |
| 5 | Coder（半专家）变体 | <https://huggingface.co/ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-Coder-GGUF> | 一手 |
| 6 | Unsloth 全档 GGUF + MTP | <https://huggingface.co/unsloth/Qwen3.8-Flash-Next-GGUF> | 一手 |
| 7 | Strata 引擎（8 GB 起，OpenAI 兼容） | <https://github.com/Niko1221/Strata> | 一手 |
| 8 | 「专家 + 约 10 GB」原文 + 各档专家 GB | <https://github.com/Niko1221/Strata/blob/main/docs/MODELS.md> | 一手 |
| 9 | 12/16 GB 实测速度表、Coder 内存、8 GB 专用旗标 | <https://github.com/Niko1221/Strata/blob/main/docs/DETAILS.md> | 一手 |
| 10 | Q2_0/IQ3 的 KL 与困惑度独立测量 | <https://github.com/Niko1221/Strata/blob/main/docs/QUANTS.md> | 一手 |
| 11 | 社区 benchmark 汇总（含 2x8 GB 报告） | <https://github.com/Niko1221/Strata/blob/main/docs/COMMUNITY_BENCHMARKS.md> | 二手汇总（指向一手目录） |
| 12 | 4060 8 GB + 2060 6 GB，IQ2_XS，约 36 tok/s | <https://github.com/Niko1221/Strata/issues/2248> | 一手 |
| 13 | RX 6600 XT 8 GB，IQ3_XXS 可跑，prefill 约 250 tok/s | <https://github.com/Niko1221/Strata/issues/1375> | 一手 |
| 14 | 6 GB 卡起不来（8 GB 门槛的反证） | <https://github.com/Niko1221/Strata/issues/916> | 一手 |
| 15 | RTX 3050 8 GB + P6000，Q2_0，131K | <https://github.com/Niko1221/Strata/issues/2214> | 一手 |
| 16 | RTX 4060 Ti 16 GB 长上下文专帖 | <https://github.com/Niko1221/Strata/issues/3558> | 一手 |
| 17 | KTransformers（无本模型支持） | <https://github.com/kvcache-ai/ktransformers> | 一手（缺位证据） |
| 18 | GSQ / RCO 论文 | <https://arxiv.org/abs/2604.18556> · <https://arxiv.org/abs/2605.00649> | 一手 |

### 标【未核源】的说法（不要当结论用）
- 「8 GB 4060 跑 IQ3_S 20–37 tok/s，均值 27」—— 来自 B 站视频评论（BV1HMHw6wETo），本次未取到评论原文 URL，**未核源**。仓库里 8 GB 的一手报告是 IQ2_XS 约 36 tok/s、IQ3_XXS 可用，**没有 IQ3_S 的 8 GB 数据**。
- 「32 GB 内存 + 8 GB 显存，Gyro-M 85 GB 文件 128K 66–67 tok/s」—— 同上，**未核源**；且 Gyro 是另一家（agentionai）的量化，Strata 文档明确说它「更省内存但更慢」，与 IQ3_S 不可直接比。
- 「Strata 面向 Nemotron 120B-A12B」—— Strata 文档里查不到 Nemotron，**未核源**。
- 本地旧文档写「专家约 12B 激活」—— 官方是 **6B 激活**（模型卡原文），旧说法**错**，应更正。

---

## 8. 给本机的三条硬结论

1. **31.1 GiB 内存 = 只能 Coder（23 GB 专家）擦线，或 SSD 流式**；满尺寸 Q2_0 需要约 44 GB，差的不是一点。别下 66 GB 的 Q2_0 去试，会白下。
2. **要真上满尺寸，先加内存到 48 GB（Q2_0）或 64 GB（IQ3_S）**，这比换显卡关键；8 GB 显存本身是官方支持的下限（有 --prefill-head-alias 专门为 8 GB 卡准备）。
3. **档位选择：Q2_0 打速度、IQ3_XXS 打质量**；IQ2_XS 在两者之间两头不靠 —— 省不下多少内存，却掉 1.33 倍 decode 和 3.4 倍 prefill。
