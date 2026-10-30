# 全网第三波：HF 与魔搭深挖（8 GB 显存 / 更大上下文 / 更快）

> 侦察员 community-scout ｜ 2026-10-30 ｜ 纯信息收集与核算：**未下载 >200 MB 文件、未启动引擎、未改配置**。
> 标注：**[作者实测]** 作者自跑；**[未复现]** 仅声称；**[本机可核]** 我们能直接对上号。
> 配套文件：reports/广度搜集-站外-20261030.md（同批数据的精简版，≤120 行）。

---

## 方向 1：HF —— 新的量化档 / 262K / 8 GB 讨论区数字

### 1.1 有实质增量的三件

| 发现 | URL / 日期 | 关键数字 | 档位 |
|---|---|---|---|
| **DFlash2 草稿头「缩词表」版**（FR-Spec + d2t 映射，草稿头只覆盖 top-N token，原文称 Lossless） | https://huggingface.co/kristobalus/Ternary-Bonsai-2-27B-DFlash2-dv98304-GGUF ｜ **2026-10-29** | 1.19 GiB / 1.17 GiB；Mac mini M4 16 GB：23.44 → **24.32 tok/s（+3.8% [+1.9;+5.7]）**、接受率 0.624→0.636；dv98304 +3.5%、词表覆盖 99.56%；额外内存 +106/+127 MiB **[作者实测]** | **需要验证**（思路可搬进 --spec dflash2；文件本身是 GGUF） |
| **MTP 头跌破老账**：sudoingx -mtp-lean **5.87 GiB**（比 prism 官方 PTQ1+MTP 5.96 更小）；Cheurteen 把 MTP 矩阵压 Q4_0 → **5.76 GiB**、Q5_0 → 5.81 GiB | https://huggingface.co/sudoingx/Ternary-Bonsai-2-27B-PTQ1_0-MTP-GGUF （2026-09-20 / upd 2026-10-16，dl 34,638 ★72）｜ https://huggingface.co/Cheurteen/Ternary-Bonsai-2-27B-Abliterated-PTQ1_0-MTP-Q4_0-GGUF （2026-10-21） | 省 0.09–0.20 GiB | **立刻可试**（MTP 头 fp16→Q4/Q5，多 1–2K 池） |
| **200K 算术修正**（详见方向 2.2） | — | 设备 2.63 GiB / 宿主 5.02 GiB | **需要验证**（真闸门是 host-restore 正确性） |

### 1.2 无增量 / 陷阱（免得再查）
- HYDRACODEX/Ternary-Bonsai-2-27B(-plus)（2026-10-29）= prism 官方**逐字节同尺寸**镜像（5,946,648,928 / 7,206,168,928 / 53,808,408,928）⇒ 无新档。
- InflexCZE/Ternary-Bonsai-2-27B-MLC（2026-10-23）**只有 214 B README**，无权重 ⇒ 空壳。
- 262K：本轮**没有**比 262,144 更高的档；所有新存档都是 27B 底座 262K 训练窗，未扩窗。
- BoldingBuilds v2 PTQ1_0（2026-10-29）、FreehandZ/Qwen3.8-27B-GSQ-RCO-IQ3_XXS-ninfer（10-29）：新但 dl 0，**无数字**。

### 1.3 NInfer 生态（HF 侧 10-29 一波）
- **neroued/Qwen3.8-Flash-Next-NInfer**、**neroued/GLM-5.3-Flash-NInfer**（均 2026-10-29 新建）；主力 neroued/Qwen3.8-27B-NInfer dl **204,551**。
- WaveCut NInfer-v3 铺到 Qwen3.8-Flash-Next IQ3_S（dl 65,552）与 DeepSeek-V4.1 IQ1_M（dl 2,569）。
- **判定：不可用**（方言是 NVFP4/groupwise，不是我们的 ptq1_g128_fp16）。

## 方向 2：llama.cpp 生态的 KV 压缩 —— 能否把 200K 塞进 8 GB

### 2.1 现成手法（ik_llama.cpp README 原文，2026 版）
- "Low perplexity **Q4_0 KV cache**" — PR #1547 / #1556：https://github.com/ikawrakow/ik_llama.cpp/pull/1547
- **Q8_KV** 新 8-bit KV 类型（PR #208）；**Q8_0 KV + FlashMLA-2**（PR #265）
- **--mtp-requantize-output-tensor new_type**（PR #1809）：官方「MTP 输出张量降精度」开关 ⇒ 与方向 1.1 的 MTP-Q4 化是同一件事的引擎侧做法
- 类型总表：https://github.com/ikawrakow/ik_llama.cpp/discussions/8

### 2.2 算术核算（本轮核心）
按我们引擎的实测口径（rk2v4-e8 每 64-token 页 0.84 MiB；宿主 25.12 KiB/token；权重 5.94 GiB；运行时约 1.0 GiB；卡 8,188 MiB）：

| 项 | 200K（204,800 token）需要 | 我们 8 GB 能给 |
|---|---|---|
| 设备常驻 KV | 3,200 页 × 0.84 MiB = **2.63 GiB** | 约 **1.15 GiB** ⇒ 只能住 **约 87.6K** token |
| 宿主 KV 页 | 204,800 × 25.12 KiB = **5.02 GiB** | 现配 6,144 MiB（够到 **244K**）⇒ 有余量 |

⇒ **修正此前「单遍 200K 算术不可能」的说法**：不是不可能，而是需要「设备常驻 ~87K + 宿主 5 GiB + 分页 host-restore 正确」。
第三项才是真闸门：我们实测超池 8/8→2/8→0/8 静默错；NInfer 生态对应的是显式崩 "Paged KV pool has no free page for host-restore"（https://github.com/1314521gjy/ninfer-fusion-kvmem/issues/12）。
llama.cpp 侧的等价解是「KV 全量进 pinned 主机内存 + 显存划固定 VRAM 线（92,160/262,144 位置）」，并在 245K 处做到 needle 23/24（professorpalmer/bonsai-ada-surgery）。

- **对我们**：**立刻可试** = MTP 头 Q4 化 + 把 --host-kv-mib 从 6,144 提到 8,192 试池外回读；**需要验证** = 回读是否只可信一次（无公开数据能背书，只能自测）。

## 方向 3：魔搭 ModelScope

| 结论 | 证据 |
|---|---|
| **大模型底座不更快**：prism 官方仓魔搭 dl 46,143 / ★197，HF 侧 ★2863 / dl 199 万 | 魔搭 API 实测（2026-10-30） |
| **小件与中文打包有独家价值**：shensanshu/ninfer-ada-ternary（★86，PQ2 完整包）、shensanshu/strata-hardware-adapt-guide（★10，0.1.43.1 手册原件）、KVMem/Bonsai2-27B-T5-MTP-Q4-NInfer（官方 8G 档） | 同上 |
| 新出现：pai8888888/ninfer-kvmem-async-RC1、jiaheng0815/Swift-Bonsai-2-NInfer-Port、Merkyor/…K3-SFT-RLOO-GGUF-NInfer（dl 6,692 ★42） | 同上 |
| 新增 KVMem 官方系：Qwen3.8-27B-IQ3_S-vision-mtp-dflash2-q3（dl 10 ★5）等 | 同上 |

- **对下载源**：仍是「底座走 HF、中文打包走魔搭」；魔搭同步慢、下载量低一到两个数量级。

## 方向 4：2026-09 之后能在 8 GB 上跑 30B 级的新引擎/框架

| 名字 | 出现 | 机制 | 数字 | 复现 |
|---|---|---|---|---|
| FlashMoE 系（gabrielkh/flashmoe-Qwen3.6-35B-A3B；anemll/Hy4-preview-FlashMoE-STQ1_0、anemll/Qwen3.8-2.4T-A95B-FlashMoE-UD-Q1_0；alexintosh/Qwen3.5-35B-A3B-Q4-Tiered-FlashMoE） | 2026-10-29 / 09-03 / 08-14 / 03-21 | 「分层/分级 MoE」+ 量化，面向 Apple ANEMLL | 未见 README 数字 | **[未复现]** |
| tfjack/Qwen3.6-35B-A3B-oQ4e-fp16-mtp 系列 | 2026-09-04 起，10-29 仍更新 | oQ 量化 + fp16 MTP | dl 10–134，无实测 | **[未复现]** |
| White-Wolf13/Qwen3.6-35B-A3B-SILVER-APEX-GGUF | 2026-10-29 | 未验 | 无 | **[未复现]** |

**结论**：2026-09 之后没有出现新的「8 GB 跑 30B 级」推理引擎；创新集中在**量化档**与**草稿头**，不在引擎。8 GB 跑 30B 的现实路径仍是 llama.cpp 分支 / Strata / NInfer 三家的「专家流式」老思路。

---

## 三档行动清单（给 lead 直接派活）

**立刻可试**
1. 把 MTP 草稿头从 fp16 压到 Q4_0/Q5_0（省 0.10–0.20 GiB ≈ 多 1–2K 池；引擎侧对应 ik_llama 的 --mtp-requantize-output-tensor）。
2. 把 --host-kv-mib 从 6,144 提到 8,192 试一次（宿主 25.12 KiB/token ⇒ 8 GiB 够到 326K），看是否只是池外回读崩。

**需要验证**
3. 设备常驻 87.6K + 宿主 5 GiB 下，池外 token 的**重复**回读是否仍正确（200K 唯一没被任何人证明的一环）。
4. NInfer 的 --spec dflash2 草稿头是否也吃满 248,320 行词表；若是，缩词表可白拿 3–5%。

**不可用**
5. WaveCut/neroued 的 NInfer-v3 与 nvfp4 档（方言不同，需换引擎且丢 rk2v4）。
6. 魔搭空壳仓（InflexCZE MLC）与镜像仓（HYDRACODEX）。

（所有数字均来自正文所列 URL 的原文；未核到的已标 [未复现]。）