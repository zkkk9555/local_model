# Gyro-S / Gyro-M 与 Qwen3.8-Flash-Next 身份核查

> 侦察时间：2026-10-30（Asia/Shanghai）｜执行：情报侦察子代理
> 取证方式：全部走代理 `HTTP_PROXY/HTTPS_PROXY=http://127.0.0.1:7897`，用 Hugging Face / ModelScope / GitLab / Docker Hub / GitHub raw 的官方 API 与原始文件取证；`web_search` 在本机不可用（报 "DeepSeek search has no API key for DEEPSEEK_API_KEY"），故无二手搜索结果可引。
> 本机基线（结论依据）：RTX 4060 Ti **8188 MiB** VRAM、RAM **31.11 GB**、C: 可用 **110 GB**；已装 Strata 0.2.8，`models/` 里只有 `bonsai2_27b_ternary_ptq1_native_mtp.ninfer`（6.39 GB），无任何 Gyro 文件。

## 0. 一句话结论

1. **Gyro-S 不是新模型，是 Qwen3.8-Flash-Next 的「trellis 量化」**，作者 **Laurent Zuijdwijk（HF 账号 `agentionai`）**，2026-09-30 首发、2026-10-25 最后更新。底座是阿里 Qwen 团队的 Qwen3.8-Flash-Next（125B 总参 / 6B 激活 + 51B n-gram 表）。
2. **28 GB 的「n-gram 表」不是 Gyro 的附加物，而是底座模型自带的一块权重**（`per_layer_token_embd`，51.2B 参数）。ISTA-DASLab 的每一个 GGUF 也都带一个 28.8 GB 的第二分片，只是 Gyro 把它塞进同一个 `.gguf` 里。
3. **S 与 M 的区别是专家矩阵用的 trellis 码率**：S = TQK6(gate/up, 1.625 bpw) + TQK7(down, 1.875 bpw)，M = TQ2_T(2.125 bpw)。S 是「内存最小、质量最差」的一档（KLD 0.401），M 是「≈IQ3_XXS 质量、省 20% 显存」（KLD 0.291）。
4. **社区量：下载数很热闹，独立采用证据很冷**。HF 侧 30 天下载 **523,837**、**146 likes**、**10 条讨论**；但作者自己的 llama.cpp fork 在 GitLab 是 **0 star / 0 fork**，容器 **312 pulls** 总计。生态外唯一硬证据是第三方 fork `halo-box/strix-llama.cpp` 里真的实现了 `block_tq2_t`。
5. **结论：这台机器（8 GB 显存 / 31 GB 内存）不值得为 Gyro-S 花 58 GB 下载与 3 小时。** 见 §5。

---

## 1. Gyro-S / Gyro-M 到底是谁、基于什么

### 1.1 发布者与仓库

| 项 | 值 | 证据 |
|---|---|---|
| 仓库 | `agentionai/Qwen3.8-Flash-Next-Gyro-GGUF` | https://huggingface.co/agentionai/Qwen3.8-Flash-Next-Gyro-GGUF |
| 作者 | Laurent Zuijdwijk（HF `agentionai`，280 followers，13 个模型，账号创建 2026-08-23） | `https://huggingface.co/api/models?author=agentionai`；讨论区作者卡片 fullname |
| 首次发布 | 2026-09-30（S/M），2026-10-12 加 L，2026-10-13 换 8-bit n-gram 表 | 模型卡 `## History` 段 |
| 文件 | S `Qwen3.8-Flash-Next-Gyro-S-TQ1_0.gguf` **58.49 GB**；M `...-Gyro-M-TQ2_0.gguf` **91.97 GB**；L `...-Gyro-L-TQ3_0.gguf` **108.32 GB**；另有 mmproj 0.90 GB、MTP draft 2.70 GB | `https://huggingface.co/api/models/agentionai/Qwen3.8-Flash-Next-Gyro-GGUF/tree/main` |
| 元数据 | 架构 `qwen4exp`，上下文 262,144 | 同上（GGUF header 字段） |
| 许可证 | 模型卡 front-matter `license_name: qwen-community-1.0`（跟随底座的 Qwen Community License 1.0） | 模型卡头部 |
| 家族 | 同作者还有 `-Gyro-Coder-GGUF`（20,331 次下载）与 `-Gyro-abliterated-Huihui-GGUF`（429,393 次下载） | `https://huggingface.co/api/models?search=gyro` |

⚠️ **文件名里的 `TQ1_0` / `TQ2_0` / `TQ3_0` 是误导**：这两个字符串在 ggml 里本来就是**另一种**三元量化类型（`GGML_TYPE_TQ1_0=34`、`TQ2_0=35`，见 §3），而 Gyro 文件内实际的专家类型是 `TQK6/TQK7`（S）、`TQ2_T`（M）、`TQP5-7`（L）。文件名只是「档位标签」。

### 1.2 底座：Qwen3.8-Flash-Next

| 项 | 值 | 证据 |
|---|---|---|
| 发布方 | 阿里巴巴 Qwen 团队 | https://huggingface.co/Qwen/Qwen3.8-Flash-Next |
| 规模 | **125B 总参数、6B 激活**（模型卡原文：125B total / 6B activated）；另有 51B 参数的 n-gram 嵌入、4B 的 MTP 头 | 模型卡 Architecture 段；HF `safetensors.total = 179,999,981,459`（BF16 仓库 360 GB） |
| 结构 | 48 层、512 路由专家（每 token 激活 10 个 + 1 共享专家）、hidden 2560、词表 248,320（padding 后） | 模型卡；ISTA-DASLab 模型卡 "512 routed experts per layer across 48 layers, of which 10 are active per token" |
| n-gram 表 | 第 2 层的 `per_layer_token_embd`，20,000,000 条 bigram/trigram 查表，51.2B 参数 | ISTA-DASLab 模型卡（"the per-layer n-gram embedding table (`per_layer_token_embd`, 51.2B parameters) at IQ4_NL"） |
| 上下文 | 原生 262,144，可扩到 1M（YaRN） | 模型卡 |
| 官方页 | 博客 https://qwen.ai/blog?id=qwen3.8-flash-next （HTTP 200，但正文由 JS 渲染，curl 只拿到 `<title>Qwen</title>`）；技术报告 https://github.com/QwenLM/Qwen3.8-Flash-Next （HTTP 200）；ModelScope `千问3.8-Flash-Next` https://modelscope.cn/models/Qwen/Qwen3.8-Flash-Next | 直接请求状态码 |

### 1.3 为什么下载里含 28 GB 的 n-gram 表

这是**底座模型的固有部分**，不是 Gyro 的发明。决定性证据是 ISTA-DASLab 的仓库结构：四档量化都切成两个分片，**第二分片在所有档位里尺寸完全一样 = 28.8 GB**：

| 目录 | 分片 1（权重） | 分片 2（n-gram） | 合计 | 模型卡标称 bpw |
|---|---:|---:|---:|---:|
| `Q2_0/` | 37.62 GB | 28.8 GB | 66.4 GB | 2.40 |
| `IQ2_XS/` | 39.23 GB | 28.8 GB | 68.0 GB | 2.50 |
| `IQ3_XXS/` | 47.04 GB | 28.8 GB | 75.8 GB | 3.00 |
| `IQ3_S/` | 54.82 GB | 28.8 GB | 83.6 GB | 3.50 |

（尺寸取自 `https://huggingface.co/api/models/ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-GGUF/tree/main?recursive=true`；bpw 取自该仓库 README 表格。）

ISTA 的做法：表以 IQ4_NL（4.5 bpw）固定存放、不进搜索、`-lm mmap --lazy-mode on` 留在 SSD 上按行读。Gyro 的做法：同一张表塞进单文件，Strata 侧的处理也一样——**留 SSD，每 token 读几行**（C:/Project/local_model/tmp/gh/Strata/docs/GYRO.md:39-40 "About half of each file is the n-gram (PLE) table. It stays on the SSD and is read row by row for every token"）。

算术自检（Gyro-S）：27.64 GiB 权重（=29.68 GB）+ 28.8 GB 表 = **58.5 GB**，与仓库里的 58.49 GB 吻合。

### 1.4 量化方法：trellis 编码 + Hadamard 旋转

格式由作者自己写了一份规范：`https://gitlab.com/agentionai-group/agention-gyro`（创建于 **2026-10-24**，1 star；`SPEC.md` 22.5 KB，Apache-2.0 风格开源，含 `src/tq_ref.c` 参考实现与一致性测试）。SPEC.md 原文要点：

- 每 **128 个权重一个 block**：一个 binary16 缩放 `d` + 一串比特流；
- 比特流驱动一个 **tail-biting bitshift trellis**：128 权重分成 32 步 × 4 权重（TQ2_T/TQK）或 64 步 × 2 权重（TQP「pair trellis」）；每步吃 K 个比特，状态是 16 位窗口；
- 状态低 15 位经乘法哈希查 **2048 项二维码本**，权重 = `d × 码本值`；**没有逐权重符号、偏移或子块 scale**；
- 权重通常存放在 **Hadamard 旋转后的基**里，旋转在 GGUF metadata 里逐 tensor 声明；
- 「格式、编码器与 kernel：AgentionAI (Laurent Zuijdwijk)」，并且 SPEC 自己写明「in the family of QTIP (Tseng et al., 2024)」——**是受 QTIP 启发的自研格式，不是 QTIP 的复刻**。

**类型 / 码率表（SPEC.md §1 原表）**：

| 类型 | ggml type id | 每步比特 K | block 字节 | **bits/weight** |
|---|---:|---:|---:|---:|
| TQK4 | 151 | 4 | 18 | 1.125 |
| TQK5 | 150 | 5 | 22 | 1.375 |
| **TQK6**（Gyro-S 的 gate/up） | 145 | 6 | 26 | **1.625** |
| **TQK7**（Gyro-S 的 down） | 146 | 7 | 30 | **1.875** |
| **TQ2_T**（Gyro-M 全部专家） | 144 | 8 | 34 | **2.125** |
| TQP5 / TQP6 / TQP7（Gyro-L 的 pair trellis） | 147 / 148 / 149 | 5 / 6 / 7 | 42 / 50 / 58 | 2.625 / 3.125 / 3.625 |

### 1.5 S / M / L 的差别（官方口径）

| | Gyro-S | Gyro-M | Gyro-L（模型卡有、Strata 文档未列） |
|---|---|---|---|
| 文件名 | `...-Gyro-S-TQ1_0.gguf` | `...-Gyro-M-TQ2_0.gguf` | `...-Gyro-L-TQ3_0.gguf` |
| 专家类型 | TQK6 gate/up + TQK7 down | TQ2_T | TQP5–TQP7（pair trellis） |
| 下载 | 58.5 GB | 92.0 GB | 108.3 GB |
| 常驻权重 | 27.64 GiB | 34.98 GiB | 50.21 GiB |
| KLD（越低越好） | **0.401** | **0.291** | **0.146** |
| top-1 一致率 | 75.29% | 78.75% | 83.87% |
| 对标 | 「比 ISTA IQ2_XS 省 24% 内存」 | 「比 IQ3_XXS(0.311) 好、省 20% 内存」 | 「比 ggml-org IQ4_NL(0.200) 好、省 18 GiB」 |
| 适合 | 32 GB 卡 / 内存小的机器 | 48 GB 或 64 GB 统一内存 | 64 GB 统一内存（Strix Halo） |

（以上取自模型卡 `## Sizes` 与对比表 `https://huggingface.co/agentionai/Qwen3.8-Flash-Next-Gyro-GGUF/raw/main/README.md`；S/M/L 的 KLD 与 top-1 分别是 0.401/0.291/0.146 与 75.29/78.75/83.87。）

一个**必须点出的口径矛盾**：作者自己的 KLD 说 Gyro-S **略好于** ISTA IQ2_XS（0.401 < 0.420，模型卡原文 "ahead of ISTA IQ2_XS with 24% less memory"，属实但只差 0.019）；Strata 的第三方测法方向相反，Gyro-S **略差于** IQ2_XS（0.268 > 0.236，见 §4 表）。两家方向相反、幅度都小 —— **结论只能落到「基本同级」**，且这是**在省 24% 内存的前提下**换来的等价，不是质量优势。

### 1.6 谁能跑它：生态极窄

模型卡原文（README 第 51 行）：**"Upstream llama.cpp cannot load these files yet."** 能跑的三家：

1. **Strata** 0.2.0+（https://github.com/Niko1221/Strata；本机已装 0.2.8，满足；Strata 自己的 TROUBLESHOOTING.md:40 要求引擎 0.1.45.1+）；
2. **halo-box/strix-llama.cpp** master（https://github.com/halo-box/strix-llama.cpp，面向 AMD Strix Halo，CPU/Vulkan/HIP）；
3. **agentionai/llama.cpp**（https://gitlab.com/agentionai-group/llama.cpp，**GitLab 而非 GitHub**；CPU/Vulkan/CUDA，还能跑 MTP draft），镜像 `agentionai/agention-llama`（Docker Hub **312 pulls**）。

**上游能不能读？我直接查了源码**：`https://raw.githubusercontent.com/ggml-org/llama.cpp/master/ggml/src/ggml-common.h` 里 `tqk` 命中 **0** 次；而 `https://raw.githubusercontent.com/halo-box/strix-llama.cpp/master/ggml/src/ggml-common.h` 第 207 行就写着 `// TQ2_T: trellis-coded 2.125 bpw (QTIP-style bitshift trellis, L=16 K=8 V=4, group 128).` 并定义 `block_tq2_t`（`QK_TQ2_T = 128`）——**第三方 fork 是真实实现，不是口头支持**。

> ⚠️ GYRO.md 内部链接不一致：Strata 的 GYRO.md:195 让人 `git clone https://github.com/agentionai/llama.cpp`，模型卡给的是 `gitlab.com/agentionai-group/llama.cpp`。GitHub 上那个路径没有对应仓库（模型卡与 SPEC 都以 GitLab 为准）。

### 1.7 社区实践量（有没有非 Strata 生态的人在用）

| 信号 | 数值 | 含义 |
|---|---|---|
| HF 30 天下载 | **523,837**（S/M/L 合计；Coder 20,331；abliterated 429,393） | 热闹，但 Strata 安装器会自动拉，**不能当作人类采用数** |
| HF likes | **146** | 相对 52 万下载，比例异常低（底座 3.85M 下载 / 6,644 likes，比例高 5 倍） |
| 讨论区 | **10 条**（2026-10-15 → 10-28） | 真实用户约 6 人：`AmadeoMartell`（9070 16GB+32GB RAM）、`kysmodelswhowantcontact`（RTX 5090 Windows）、`tevenfeng`（报 bug）、`SeattleSysop`、`soyalemujica`、`TESTPOINTrxz` |
| 作者 fork 的 star | **0 star / 0 fork**（2026-10-09 创建） | 没有任何外部开发者跟进 |
| 容器 | **312 pulls** | 同上 |
| 规范仓库 | **1 star**（2026-10-24 创建） | 极新、极小 |
| 第三方量化组 | **无**。Unsloth / Bartowski / ggml-org / AtomicChat **都没发布过 TQ* 类型**（HF 搜 `gyro` 只返回 agentionai 自己的三个仓库） | 格式没有扩散 |
| 非 Strata 生态使用 | **有，但只有一个**：`halo-box/strix-llama.cpp` 实现了 `block_tq2_t`；模型卡也附了「strix-llama.cpp + EXL3 Vulkan PR #201/#204」的对比数据 | 属于 Strix Halo 小众圈子的移植 |

**判断**：这不是「一个模型火了」，而是「一个人的格式 + 一个人的运行时」。52 万下载里绝大部分来自 Strata 安装流程；真正逐条讨论、贴数据的用户是**个位数**。
---

## 2. Qwen3.8-Flash-Next 是什么来头

| 问题 | 答案 | 一手证据 |
|---|---|---|
| 谁发的 | **阿里巴巴 Qwen 团队**（模型卡 `Qwen` 组织；ModelScope 中文名「千问3.8-Flash-Next」） | https://huggingface.co/Qwen/Qwen3.8-Flash-Next ／ https://modelscope.cn/models/Qwen/Qwen3.8-Flash-Next |
| 总参数 | **125B**（HF safetensors 合计 **179,999,981,459** 参数，含 51B n-gram 表与 4B MTP 头；BF16 仓库 360 GB） | HF API `safetensors.total`；模型卡 |
| 激活参数 | **6B**（512 路由专家里每 token 走 10 个 + 1 个共享专家） | 模型卡 Architecture |
| 模态 | 文本 + 视觉（`mmproj` 视觉投影器，BF16 0.91 GB） | Qwen 模型卡；ISTA 仓库 `mmproj` 说明 |
| 上下文 | 原生 262,144，YaRN 可到 1M | 模型卡 |
| 官方发布页 | 博客 https://qwen.ai/blog?id=qwen3.8-flash-next（HTTP 200，正文 JS 渲染）；技术报告仓库 https://github.com/QwenLM/Qwen3.8-Flash-Next（HTTP 200） | curl 状态码 |
| 发布日 | HF 仓库创建 **2026-08-24** | HF API `createdAt` |

**社区热度（数字）**

| 指标 | 数值 | 来源 |
|---|---:|---|
| HF 30 天下载 | **3,853,710** | `https://huggingface.co/api/models/Qwen/Qwen3.8-Flash-Next` |
| HF likes | **6,644** | 同上 |
| HF 派生仓库数（`base_model:Qwen/Qwen3.8-Flash-Next`） | **645** | `https://huggingface.co/api/models?filter=base_model:Qwen/Qwen3.8-Flash-Next&limit=1000` |
| ModelScope 下载 / 收藏 | **93,865 / 1,516** | `https://modelscope.cn/api/v1/models/Qwen/Qwen3.8-Flash-Next` |
| 最大第三方 GGUF（ISTA-DASLab GSQ-RCO） | **7,604,113 下载 / 1,089 likes** | `https://huggingface.co/api/models?author=ISTA-DASLab` |

**结论**：这是阿里 2026-08 的主力开源旗舰（MoE + 视觉 + 262K 上下文 + 内置 n-gram 表），生态非常厚（645 个派生仓库、ISTA 一家就 760 万下载）。Gyro 只是挂在这棵树上的一个极窄分支。

> 注意：底座**不是**「125B/6B 就完了」——它的 51B n-gram 表是一块**查表**权重（不是 matmul），这也是为什么所有 GGUF 都必须带 28.8 GB 的第二分片，以及为什么「2-bit 量化」的下载仍然有 58–83 GB。

---

## 3. Q2_0 / IQ2_XS / IQ3_XXS / IQ3_S 到底是几个 bpw、谁的方法

先把两件事分开：**(a) ggml 里的类型定义（固定 bpw）** 与 **(b) 量化商目录名（预算标签）**。两者不是一回事，混起来就会得出「IQ2_XS 是 2.5 bpw」这种半对半错的结论。

### 3.1 类型定义（从源码逐字节算出，误差 0）

| 代号 | ggml 枚举 | block（权重数） | block 字节 | **bpw** | 方法归属 |
|---|---|---:|---:|---:|---|
| **Q2_0** | `GGML_TYPE_Q2_0 = 42` | **64** | 18（2 B fp16 scale + 16 B 2-bit 码） | **2.25** | 先见于 **ikawrakow 的 ik_llama.cpp**（`block_q2_0`，`#define QK2_0 64`），现在已进上游 ggml；4 级非对称 `{-1,0,1,2}·d`。**注意：GGUF 规范 `gguf.md` 的类型表还没收录它**（文档只到 `MXFP4=39`），是文档滞后，不是不存在 |
| **IQ2_XS** | `GGML_TYPE_IQ2_XS = 17` | 256 | 74（2 + 64 + 8） | **2.3125** | **i-quant**，ikawrakow 的方法（importance matrix 驱动的格点/查表量化），上游 ggml 实现 |
| **IQ3_XXS** | `GGML_TYPE_IQ3_XXS = 18` | 256 | 98（2 + 3×32） | **3.0625** | 同上（i-quant 家族） |
| **IQ3_S** | `GGML_TYPE_IQ3_S = 21` | 256 | 106（2 + 13×8 + 2） | **3.4375** | 同上（i-quant 家族） |

算式与出处（可直接复核）：

- 枚举值：`https://raw.githubusercontent.com/ggml-org/ggml/master/include/ggml.h`（`Q2_K=10`、`IQ3_S=21`、`TQ1_0=34`、`TQ2_0=35`、`Q2_0=42`）；GGUF 规范副本 `https://raw.githubusercontent.com/ggml-org/ggml/master/docs/gguf.md`（`IQ2_XS=17`、`IQ3_XXS=18`、`IQ3_S=21`）。
- block 结构：`https://raw.githubusercontent.com/ggml-org/ggml/master/src/ggml-common.h` 里的 `static_assert`：
  - `sizeof(block_iq2_xs)  == sizeof(ggml_half) + QK_K/8*sizeof(uint16_t) + QK_K/32` → 2+64+8 = 74 B / 256 = **2.3125**
  - `sizeof(block_iq3_xxs) == sizeof(ggml_half) + 3*(QK_K/8)` → 2+96 = 98 B / 256 = **3.0625**
  - `sizeof(block_iq3_s)   == sizeof(ggml_half) + 13*(QK_K/32) + IQ3S_N_SCALE` → 2+104+2 = 106 B / 256 = **3.4375**
  - `QK2_0 = 64`，`block_q2_0 = { ggml_half d; uint8_t qs[QK2_0/4]; }` → 2+16 = 18 B / 64 = **2.25**（`https://raw.githubusercontent.com/ikawrakow/ik_llama.cpp/main/ggml/src/ggml-common.h` 同款定义，注释 `2 bits per element, {0,1,2,3} -> {-1,0,1,2} * d`）

### 3.2 但 ISTA-DASLab 目录名不是「统一类型」，是**预算标签**

ISTA 的 README 明说：每档都是**逐 tensor 混合**（GSQ 学格点 + RCO 在总预算下分配类型），标称 bpw 是「transformer 权重的平均」：

| 目录 | 标称 bpw | 实际用法（README §Search 原文） |
|---|---:|---|
| `Q2_0/` | **2.40** | 刻意**避开查表型格式**（i-quant 解码慢，这个模型上解码开销压过精度收益）；`ffn_down_exps` 的 640 行不能被 256 整除，所以只能用 `Q2_0`(block 64) 或 `IQ4_NL`(block 32)，小档位里 48 层全落 `Q2_0` |
| `IQ2_XS/` | **2.50** | 同预算但换成 i-quant 梯子 |
| `IQ3_XXS/` | **3.00** | 48 层里 18 层被抬到 `IQ4_NL` |
| `IQ3_S/` | **3.50** | 推荐档 |

所以：`IQ2_XS` 目录 = 2.50 bpw **平均** ≠ IQ2_XS 类型本身的 2.3125 bpw；差的那 0.19 bpw 是「敏感 tensor 抬高精度」的结果。**问「IQ2_XS 几个 bpw」必须问清是类型还是档位。**

**方法归属一句话版**：IQ2_XS / IQ3_XXS / IQ3_S 全是 **ikawrakow 的 i-quant**（上游 ggml 标准码，非 unsloth 发明；unsloth 只是把它们做成 UD- 动态量化配方并发布文件）；**Q2_0 也源自 ikawrakow**（ik_llama.cpp 原生，后进上游），**Q4_K/IQ4_NL 属于 GGUF/ggml 规范类型**。**TQ*(TQ2_T/TQK*/TQP*) 才是 agentionai 独有的，规范之外、上游不可读**。

---

## 4. 质量口径：三家测法给出的结论并不一致

| 档位 | 作者 KLD（模型卡） | Strata KL（GYRO.md:63-68） | Strata QUANTS.md:73-81（4,995 positions，top-1 一致率 / KL） |
|---|---:|---:|---:|
| Gyro-S | 0.401 | **0.268**（vs IQ2_XS 0.236，差 13%，但省 24% 字节） | — |
| Gyro-M | 0.291 | **0.159**（vs Q2_0 0.312，明显更好；vs IQ3_XXS 0.157，**打平**） | — |
| Q2_0 | — | 0.312 | 80.60% / 0.315 / PPL 4.475 |
| IQ3_XXS | 0.311 | 0.157 | 84.46% / 0.202 |
| IQ3_S | — | — | 87.69% / 0.144 |

**读法**：

- **Gyro-M 是这一族里唯一有说服力的**：与 IQ3_XXS 同质量（0.157 vs 0.159），内存少 20%（35 vs 43.8 GiB）；在 RTX 3060 上仍慢 16%，R9700 上慢 21%（GYRO.md:74-79）。
- **Gyro-S 没有优势**：作者说略胜 IQ2_XS，Strata 测出来略输；两家方向相反、幅度都很小 → **同级**。而它是全族质量最差的一档（top-1 75.29%）。
- **Gyro-M 的推理掉点不能忽略**：Strata 的推理集 **49/60，而 Q2_0 是 57/60**（GYRO.md:68）。KL 打平 IQ3_XXS，但推理集差 8 题——说明「KL 一样」不等于「能力一样」。

### 风险信号（都有一手出处）

1. **格式是孤岛**：上游 llama.cpp 读不了（源码 `tqk` 命中 0），只能 Strata / strix-llama.cpp / 作者自己的 GitLab fork。三者都是单人量级的项目（0 star / 312 docker pulls / 1 star）。
2. **编码器未公开**（模型卡明说），所以你**无法自己复现或微调**这族权重，只能等作者发新文件。
3. **文件名骗人**：`-TQ1_0`/`-TQ2_0`/`-TQ3_0` 借用的是**三元量化**的旧类型名（`TQ1_0=34`、`TQ2_0=35`），文件里其实是 `TQK6/TQK7/TQ2_T/TQP*`。谁按文件名去上游加载，必然失败。
4. **GYRO.md 给的克隆地址是错的**（GitHub 而非 GitLab，见 §1.6）。
5. **有未闭环的 bug 报告**：讨论 #8 `tevenfeng`：「长 agent 任务跑约 2 小时后，只有 thinking，没有 tool call 也没有回复」。后续他自己在 IQ3_XXS 上复现 → **大概率是 Strata 引擎的问题，不是 Gyro 特有**，但确实存在（#8，2026-10-27）。
6. **Gyro-M 在 8 GB 卡上默认配置直接起不来**：GYRO.md:166-168「with setup's 32K context the card is 750 MiB short of one cache slot and the engine stops」，必须 `--max-context 8192 --vram-reserve-mib 100 --prefill 1024`。

---

## 5. 结论：这台机器值不值得为 Gyro-S 花 58 GB 下载与 3 小时

**结论：不值得。** 四条理由，按决定性排序：

1. **硬件对不上，而且是最坏的那种对不上。** Gyro-S 要 **27.64 GiB 常驻权重**，本机 VRAM **8 GiB**、RAM **31.11 GB**。这意味着 ~90% 的专家必须常驻内存、按 token 经 PCIe 拉到卡上。唯一的公开同构实测是 Strata 自己的 Arc A750（**8 GB** + **62 GB** RAM）：**解码 15.8 t/s**、prompt 82 t/s（1406 token）（GYRO.md:146-155）。本机内存只有那台的一半（31 vs 62 GB），还要和 Windows/Strata 抢——**大概率更差，或直接进 SSD 缺页**。
2. **它买到的是「最小」，不是「最好」。** Gyro-S 是全族质量最差的一档（KLD 0.401、top-1 75.29%、推理集 49/60），并且与 ISTA IQ2_XS 基本同级、互有胜负。花 58 GB 换一个**同级但更慢、更孤立**的文件，没有收益。
3. **58 GB 的下载里有一半你用不上。** 28.8 GB 是 n-gram 表，**留在 SSD 上按行读**（两份一手文档都这么说：GYRO.md:39、ISTA README）。磁盘 110 GB 可用，下载完装包（`iq_pack.py` 还要另存 ~1.5 GB pack + MTP draft 2.7 GB）后剩 ~45 GB——为一次「跑通演示」吃掉一半可用空间，性价比很低。
4. **它的存在理由在本机不成立。** Gyro 的卖点是「32 GB 单卡把 125B 塞进显存」（RTX 5090 上 221 tok/s、全驻留）。本机是 8 GB 卡，永远拿不到那个体验；能拿到的只有「CPU 流式解码」——而那正是 Strata 文档反复劝退的用法（MODELS.md:225「Gyro saves memory and is slower」；GYRO.md:54-58「Gyro is not a default」）。

### 如果仍想验证（最短路径，风险自担）

这一条**不是建议**，只是把成本说清：

```sh
strata launch --family gyro --model Gyro-S      # 需要引擎 0.1.45.1+（本机 0.2.8 满足）
# 只想要「能跑」，不要 n-gram 表的显存占用：
#   确保 --ple-io / n-gram 表走 mmap（Strata 对 Gyro 默认留 SSD）
```

按本机条件预期的结果：**首 token 慢、解码大概率 ≤15 t/s、上下文一长就掉到个位数**。若目标是「有个能用的本地模型」，本机已有的 `bonsai2_27b_ternary_ptq1_native_mtp.ninfer`（6.39 GB）在 8 GB 卡上是更合理的选择。

### 更好的替代（同底座，走宽生态）

| 需求 | 选它 | 理由 |
|---|---|---|
| 要跑 Qwen3.8-Flash-Next 且生态最宽 | ISTA-DASLab **IQ2_XS**（68.0 GB）或 **Q2_0**（66.4 GB） | 真 llama.cpp / Ollama / LM Studio 直接读；Q2_0 比 IQ2_XS prompt 快 3.4×、端到端延迟低 1.9×（ISTA README，实测 367 vs 108 tok/s prompt） |
| 要在 8 GB 卡上真跑得动 | 别选 125B。用 27B 级 | Gyro-S 是「32 GB 卡的穷人方案」，不是「8 GB 卡的方案」 |
| 就是想要 Gyro 的方法论 | 只考虑 **Gyro-M**，且等有 24 GB+ 卡时 | 唯一有说服力的一档（≈IQ3_XXS 质量、省 20% 内存）；S 没有存在价值 |

---

## 6. 证据清单（全部带 URL，可逐条复核）

**一手：Gyro**

- 模型仓库 + 模型卡：https://huggingface.co/agentionai/Qwen3.8-Flash-Next-Gyro-GGUF ｜ 原文 https://huggingface.co/agentionai/Qwen3.8-Flash-Next-Gyro-GGUF/raw/main/README.md
- 文件与尺寸：https://huggingface.co/api/models/agentionai/Qwen3.8-Flash-Next-Gyro-GGUF/tree/main
- 作者全部模型：https://huggingface.co/api/models?author=agentionai
- 格式规范 SPEC.md：https://gitlab.com/agentionai-group/agention-gyro/-/raw/main/SPEC.md ｜ 仓库 https://gitlab.com/agentionai-group/agention-gyro
- llama.cpp fork：https://gitlab.com/agentionai-group/llama.cpp ｜ 镜像 https://hub.docker.com/r/agentionai/agention-llama
- 第三方实现：https://github.com/halo-box/strix-llama.cpp（`ggml/src/ggml-common.h:207` 有 `block_tq2_t`）
- 讨论区（10 条）：https://huggingface.co/agentionai/Qwen3.8-Flash-Next-Gyro-GGUF/discussions/3 、`/6`、`/8`

**一手：底座与竞品量化**

- Qwen3.8-Flash-Next：https://huggingface.co/Qwen/Qwen3.8-Flash-Next ｜ https://qwen.ai/blog?id=qwen3.8-flash-next ｜ https://github.com/QwenLM/Qwen3.8-Flash-Next ｜ https://modelscope.cn/models/Qwen/Qwen3.8-Flash-Next
- ISTA-DASLab GSQ-RCO：https://huggingface.co/ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-GGUF （方法：https://arxiv.org/abs/2604.18556 GSQ、https://arxiv.org/abs/2605.00649 RCO、代码 https://github.com/IST-DASLab/GSQ 、https://github.com/IST-DASLab/RCO）

**一手：量化类型定义**

- 枚举：https://github.com/ggml-org/ggml/blob/master/include/ggml.h （`Q2_0=42`）
- 规范（滞后，未收 Q2_0）：https://github.com/ggml-org/ggml/blob/master/docs/gguf.md
- block 布局/`static_assert`：https://github.com/ggml-org/ggml/blob/master/src/ggml-common.h
- ik_llama.cpp 的 `block_q2_0`：https://github.com/ikawrakow/ik_llama.cpp/blob/main/ggml/src/ggml-common.h

**本地一手文档（vendored，只读）**

- `C:/Project/local_model/tmp/strata-docs/MODELS.md`（:225 provider 顺序与 Gyro 速度/质量口径；28 GB n-gram 表说明）
- `C:/Project/local_model/tmp/strata-docs/QUANTS.md`（:73-81 质量尺）
- `C:/Project/local_model/tmp/gh/Strata/docs/GYRO.md`（:33-37 S/M 尺寸与专家类型；:39-40 一半是 n-gram 表；:63-68 KL 与推理集；:74-79 解码速度；:146-172 8 GB 实测与 Gyro-M 起不来；:287 Gyro-M 29.9 GiB 装不满 32 GB 卡；:291 作者署名 Laurent Zuijdwijk）

## 7. 【未核源】与未做项

- **「3 小时」这个下载时长**没有任何一手数据（取决于本机到 HF 的实速），未核。
- **本机（8 GB / 31 GB RAM）上 Gyro-S 的实际 tok/s**：未实测（禁止启停引擎），只能用 A750 8 GB + 62 GB RAM 的 15.8 t/s 作**外推**，不是本机数据。
- **Gyro-L 的 TQP 系类型**：SPEC 有定义、Strata 说「We have not run the 50 GiB file ourselves yet」，本报告不评估 L。
- **web_search 不可用**（`DEEPSEEK_API_KEY` 缺失），所以没有 Reddit/X/知乎等社区舆论面；§1.7 的「社区量」全部来自 HF/GitLab/Docker 的**结构化计数**，不是主观感受。
- **TQ1_0 / TQ2_0 的精确 bpw** 未逐字节核算（与本题无关，仅用于说明「文件名借用了三元类型名」）。

---

_报告生成：2026-10-30；作者：情报侦察子代理（受 session-9bffe7d2 委派）。所有非本地路径均已在代理下 `curl` 验证可访问；本地路径均为只读访问。_