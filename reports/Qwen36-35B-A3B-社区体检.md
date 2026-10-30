# Qwen3.6-35B-A3B 社区体检：它是不是"社区主流强模型"？

- 侦察时间：2026-10-30（Asia/Shanghai），全部数字为当日抓取
- 侦察目标：①社区实践量 ②35B 总量 / A3B 激活在同代里的位置 ③8 GB 显存上有没有非 Strata 生态的真实部署报告
- 证据标准：只采信可直接打开的 URL 一手页面（HF/ModelScope API、厂商模型页、框架源码、作者实操文）；只有搜索摘要、无法打开原文的标 **【未核源】**

---

## 0. 三句话结论

1. **量大，但已不是"当前主力"。** 官方权重 4,560,704 次下载 / 3,055 赞，衍生仓库 1,000+（可见 655 个带 base_model 关系的微调/量化），ModelScope 61.5 万下载，Ollama 18 个 `35b` tag，LM Studio 260 万下载 —— 这是"大版本级"的社区体量。但同门 **Qwen3.8-27B（2026-08-05）已达 7,509,924 下载 / 18,688 赞**，是它的 1.65 倍下载、6.1 倍点赞。所以准确说法是：**社区主流之一，但不是社区当下的第一选择**。
2. **A3B 的定位是"工具/Agent 型特种兵"，不是"知识/重构型主力"。** 官方同尺寸对比表里，它在 Terminal-Bench 2.0（51.5）、Claw-Eval（68.7）、MCPMark（37.0）、NL2Repo（29.4）**全组第一**，明显压过稠密 Qwen3.5-27B；但在 SWE-bench Verified（73.4 vs 75.0）、MMLU-Pro（85.2 vs 86.1）、WideSearch（60.1 vs 66.4）**略输稠密 27B**。比上一代 Qwen3.5-35B-A3B 全面上涨（SWE-bench 70.0→73.4，Terminal-Bench 40.5→51.5）。
3. **8 GB 上有真实非 Strata 报告，而且是 llama.cpp 路线。** RTX 4060 8 GB + 32 GB DDR4 + Win11，llama.cpp + UD-Q4_K_M：显存 7.2–7.8 GB、内存 16–20 GB、CPU 90%、文本约 **30 token/s**、图文 2–3 秒、连跑 4 小时不崩。代价是**必须把路由专家分流到内存**；纯上卡不可能（最小可用量化 10.05 GB，Q4_K_M 22.13 GB）。

---

## 1. 它到底是个什么东西（一手规格）

| 项 | 值 | 来源 |
| --- | --- | --- |
| 仓库 | `Qwen/Qwen3.6-35B-A3B`，2026-04-15 创建，Apache-2.0 | https://huggingface.co/Qwen/Qwen3.6-35B-A3B |
| 参数量 | 35,951,822,704（BF16 safetensors 实测计数），**激活约 3B** | HF API `safetensors.total` |
| 架构 | `Qwen3_5MoeForConditionalGeneration` / model_type `qwen3_5_moe`，llama.cpp 侧 arch 名 `qwen35moe` | https://huggingface.co/Qwen/Qwen3.6-35B-A3B/raw/main/config.json |
| 层结构 | 40 层 = 10 × (3 ×(Gated DeltaNet→MoE) → 1 ×(Gated Attention→MoE))，256 experts / 8 routed + 1 shared，hidden 2048 | 模型卡 + config.json |
| 上下文 | 262,144 原生，可扩到 1,010,000 | 模型卡 |
| 模态 | 图文（image-text-to-text，带 vision encoder / mmproj） | 模型卡 + HF pipeline_tag |
| 官方发布页 | https://qwen.ai/blog?id=qwen3.6-35b-a3b （"Following the launch of Qwen3.6-Plus, we are excited to open-source Qwen3.6-35B-A3B — a sparse yet remarkably capable mixture…"）；卡片标题 *Agentic Coding Power, Now Open to All* | 模型卡引用 + 搜索引擎摘要 |

> 关键含义：**35B 总量 / 3B 激活 + 混合线性注意力**，决定了它显存账很怪 —— 权重体积像 35B（Q4 要 22 GB），算力开销像 3B（30 tok/s 在 8 GB 卡上也可能达成）。这正是"8 GB 能不能跑"争议的根源。

---

## 2. ① 社区实践量：大到什么程度

### 2.1 官方权重（HF + ModelScope）

| 指标 | 数值 | 来源 |
| --- | --- | --- |
| HF downloads | **4,560,704** | https://huggingface.co/api/models/Qwen/Qwen3.6-35B-A3B |
| HF likes | **3,055** | 同上 |
| ModelScope downloads | **615,380** | https://modelscope.cn/api/v1/models/Qwen/Qwen3.6-35B-A3B |
| ModelScope stars | **255** | 同上 |
| HF 讨论串 | 79 条（官方仓库下） | https://huggingface.co/Qwen/Qwen3.6-35B-A3B/discussions |

### 2.2 官方自家其它权重（同一模型的兄弟版本，说明被反复取用）

| 仓库 | downloads | likes |
| --- | --- | --- |
| Qwen/Qwen3.6-35B-A3B-FP8 | 4,241,020 | 440 |
| nvidia/Qwen3.6-35B-A3B-NVFP4 | 3,994,686 | 672 |
| RedHatAI/Qwen3.6-35B-A3B-NVFP4 | 990,586 | 195 |
| QuantTrio/Qwen3.6-35B-A3B-AWQ | 519,622 | 39 |

### 2.3 衍生生态（量化 / 微调 / 去审查）

- HF 搜索 `Qwen3.6-35B-A3B` 命中 **1,000 条（已到 API 返回上限，实际更多）**，其中 **655 条**带 `base_model:quantized:` 或 `base_model:finetune:` 关系；这 1,000 条**累计下载 24,583,117 次**。
- 头部第三方：
  - `HauhauCS/Qwen3.6-35B-A3B-Uncensored-HauhauCS-Aggressive`：983,207 下载 / **4,046 赞** —— 赞数比官方仓库还高，说明"去审查分支"是社区主力消费口。
  - `unsloth/Qwen3.6-35B-A3B-GGUF`：1,321,885 下载 / 1,741 赞（llama.cpp 路线的事实入口）。
  - `unsloth/Qwen3.6-35B-A3B-MTP-GGUF`：1,366,824 / 1,022。
  - `LuffyTheFox/…Genesis-Hermes-GGUF`：492,609 / 720。
- **llama.cpp 官方 GGUF**：`ggml-org/Qwen3.6-35B-A3B-GGUF` 141,593 下载 / 28 赞，2026-04-18 建立 —— 这是"被上游框架正式收录"的硬信号。

### 2.4 消费端软件集成（全部非 Strata）

| 生态 | 状态 | 一手证据 |
| --- | --- | --- |
| **llama.cpp** | 原生支持，arch `qwen35moe`（`LLM_ARCH_QWEN35MOE`）+ 官方 GGUF | https://raw.githubusercontent.com/ggml-org/llama.cpp/master/src/llama-arch.cpp （第 45 行 `{ LLM_ARCH_QWEN35MOE, "qwen35moe" }`） |
| **Ollama** | 官方库收录，`qwen3.6` 下 **18 个 35b tag**（`35b-a3b`、`-q4`、`-q8`、`-mlx`、`-nvfp4`、`-coding`、`-mtp-q4`…） | https://ollama.com/library/qwen3.6/tags |
| **LM Studio** | 有专属模型页，标 2.6M 下载 / 144 星 / 9 fork，**"Minimum system memory 20 GB"** | https://lmstudio.ai/models/qwen/qwen3.6-35b-a3b |
| **vLLM** | 架构白名单含 `Qwen3_5MoeForConditionalGeneration`（同 arch） | https://docs.vllm.ai/en/latest/models/supported_models.html |
| **SGLang / KTransformers** | 模型卡正文逐条给出部署文档链接 | https://huggingface.co/Qwen/Qwen3.6-35B-A3B |
| **MTP 变体** | `ggml-org/Qwen3.6-35B-A3B-MTP-GGUF`（2026-05-15） | HF API author=ggml-org |

### 2.5 但：它已经不是"当代第一"

| 模型 | 发布 | downloads | likes |
| --- | --- | --- | --- |
| **Qwen/Qwen3.8-27B** | 2026-08-05 | **7,509,924** | **18,688** |
| Qwen/Qwen3.8-Flash-Next | 2026-08-24 | 3,853,710 | 6,644 |
| Qwen/Qwen3.6-35B-A3B | 2026-04-15 | 4,560,704 | 3,055 |
| Qwen/Qwen3.6-27B | 2026-04-21 | 2,364,421 | 2,342 |

（来源：HF API `author=Qwen&search=Qwen3.8` 与 `Qwen3.6`）

**判读**：3.6 系列的 open-weight 只有 35B-A3B 和 27B 两支，之后 Qwen 直接跳到 3.8。所以"Qwen3.6-35B-A3B 是社区主流强模型"这句话，**在 2026 年 4–8 月成立，在 10 月底已经过期**：它仍是存量最大、教程最多的"8 GB 能跑的 35B"，但热度第一已被 Qwen3.8-27B 拿走。另注：**3.6 系列没有更大尺寸的开源旗舰**，所以"同代最强"这个说法在 3.6 内部也不成立（还有 dense 27B 在若干项上压它）。

---

## 3. ② 35B/3B 在同代里什么位置（官方对比表，逐行抄录）

列顺序来自模型卡表头：**Qwen3.5-27B | Gemma4-31B | Qwen3.5-35B-A3B | Gemma4-26B-A4B | Qwen3.6-35B-A3B**

| 基准 | 3.5-27B(dense) | Gemma4-31B | 3.5-35B-A3B | Gemma4-26B-A4B | **3.6-35B-A3B** |
| --- | --- | --- | --- | --- | --- |
| SWE-bench Verified | **75.0** | 52.0 | 70.0 | 17.4 | 73.4 |
| SWE-bench Multilingual | **69.3** | 51.7 | 60.3 | 17.3 | 67.2 |
| SWE-bench Pro | **51.2** | 35.7 | 44.6 | 13.8 | 49.5 |
| Terminal-Bench 2.0 | 41.6 | 42.9 | 40.5 | 34.2 | **51.5** |
| Claw-Eval Avg | 64.3 | 48.5 | 65.4 | 58.8 | **68.7** |
| SkillsBench Avg5 | 27.2 | 23.6 | 4.4 | 12.3 | **28.7** |
| NL2Repo | 27.3 | 15.5 | 20.5 | 11.6 | **29.4** |
| MCPMark | 36.3 | 18.1 | 27.0 | 14.2 | **37.0** |
| Tool Decathlon | **31.5** | 21.2 | 28.7 | 12.0 | 26.9 |
| WideSearch | **66.4** | 35.2 | 59.1 | 38.3 | 60.1 |
| MMLU-Pro | **86.1** | 85.2 | 85.3 | 82.6 | 85.2 |
| GPQA | 85.5 | 84.3 | 84.2 | 82.3 | **86.0** |
| AIME26 | 92.6 | 89.2 | 91.0 | 88.3 | **92.7** |
| LiveCodeBench v6 | **80.7** | 80.0 | 74.6 | 77.1 | 80.4 |
| HLE | **24.3** | 19.5 | 22.4 | 8.7 | 21.4 |

（来源：https://huggingface.co/Qwen/Qwen3.6-35B-A3B 卡片 "Benchmark Results" 表，由 HTML `<td>` 逐格解析）

**三点判读**

1. **赢在"跑起来干活"，输在"想清楚再动手"。** 长程 Agent/终端/工具链（Terminal-Bench 2.0 51.5、Claw-Eval 68.7、MCPMark 37.0、SkillsBench 28.7）它是全表第一，且领先幅度不小（Terminal-Bench 比 dense 27B 高 9.9 分）；但纯代码修补与知识检索（SWE-bench Verified −1.6、WideSearch −6.3、MMLU-Pro −0.9、HLE −2.9）输给稠密 27B。
2. **对上一代同壳模型是全面升级**：SWE-bench Verified 70.0→73.4、Terminal-Bench 40.5→51.5、Claw-Eval 65.4→68.7、NL2Repo 20.5→29.4。所以"35B-A3B 这档"本身的性价比确实抬了一档。
3. **同尺寸横向看，它是"最强的一档之一"但不能说"最强"**：对 Gemma4-26B-A4B 是碾压级（SWE-bench 73.4 vs 17.4）；对 Gemma4-31B 在 Agent 项赢、SWE-bench 赢 21 分；只在自己家的稠密 27B 面前互有胜负。
4. **注意基准口径**：SWE-bench 系列用"内部 agent scaffold"，Terminal-Bench 用 Harbor/Terminus-2 三次取均值 —— **官方数字不能直接与第三方榜单横比**。

---

## 4. ③ 8 GB 显存 × 非 Strata 生态：有真实报告

### 4.1 先看硬算术（量化体积，来自 unsloth 官方 GGUF 仓库）

| 量化 | 体积 | 8 GB 能否整卡装载 |
| --- | --- | --- |
| UD-IQ1_M（最小可用） | **10.05 GB** | ❌ |
| UD-IQ2_XXS | 10.76 GB | ❌ |
| UD-Q2_K_XL | 12.29 GB | ❌ |
| UD-Q3_K_S | 15.36 GB | ❌ |
| UD-Q4_K_M | **22.13 GB** | ❌ |
| UD-Q8_K_XL | 38.45 GB | ❌ |
| mmproj-BF16（视觉投影） | 0.86 GB | 另计 |

（来源：https://huggingface.co/api/models/unsloth/Qwen3.6-35B-A3B-GGUF/tree/main）

→ **结论：任何量化都放不进 8 GB 显存。** 8 GB 上唯一的活路是"注意力/共享专家上卡、路由专家分流到内存"（llama.cpp `--n-cpu-moe` / `-ot` 一类做法），或者纯 CPU。

### 4.2 真实部署报告（llama.cpp + GGUF，非 Strata）

**案例 A（可打开原文，数据完整）** —《Qwen3.6-35B-A3B MoE大模型消费级显卡实战（RTX4060 8G）》，2026-05-26 发布 / 2026-10-22 更新
https://haies.cn/ai-moe-qwen3-6-35b-a3b/

| 项 | 实测值 |
| --- | --- |
| 硬件 | RTX 4060 8 GB + Intel i9-11900KB + **32 GB DDR4 双通道** + Win11 |
| 软件 | llama.cpp 预编译 `llama-b9305-bin-win-cuda-12.4-x64`（CUDA 12.4） |
| 模型 | `Qwen3.6-35B-A3B-UD-Q4_K_M.gguf`（22.13 GB）+ `mmproj-BF16.gguf`，权重来自 unsloth/hf-mirror |
| 显存占用 | **7.2–7.8 GB**（"稳定不溢出"） |
| 内存占用 | **16–20 GB**（专家层分流） |
| CPU | ~90% |
| 文本速度 | **约 30 token/s** |
| 图文 | 响应 2–3 秒，OCR/图片问答"可用" |
| 稳定性 | 连续 4 小时无崩溃 |
| 作者自己的归因 | "MoE 专家分流到内存，32 G 内存成为关键"、"UD-Q4_K_M 量化 + KV 缓存量化，适配 8G 显存" |

**案例 B（只见摘要，原文 403，标【未核源】）**：知乎《8G显存封神！本地部署 Qwen3.6-35B-A3B 大模型教程》，2026-07-09，摘要称"一张普通 8G 显存显卡…生成速度: 35 Tokens 每[秒]"。
https://zhuanlan.zhihu.com/p/2055361478400684230 —— 抓取返回 403，数字**未经原文核验**，仅作交叉参考。

**旁证（厂商口径）**：LM Studio 模型页明写 **"Minimum system memory 20 GB"**（https://lmstudio.ai/models/qwen/qwen3.6-35b-a3b）—— 与案例 A 的 16–20 GB 内存占用吻合：**这道门的门槛在系统内存，不在显存**。

### 4.3 这条路线已知的坑（llama.cpp 官方 issue，非道听途说）

| Issue | 标题（原文） | 含义 |
| --- | --- | --- |
| [#29970](https://github.com/ggml-org/llama.cpp/issues/29970) | "Eval bug: Qwen3.6-35B-A3B (qwen35moe) **cannot read text in images** — sees shapes/colors, misreads letters/digits; same on CPU, all quants, all projectors, latest master" | **视觉 OCR 在 llama.cpp 上有缺陷**，与案例 A "OCR 可用" 的乐观说法冲突，做图文任务前必须自测 |
| [#29980](https://github.com/ggml-org/llama.cpp/issues/29980) | "Eval bug: **prompt processing ~2x slower** on Qwen3.6-35B-A3B since #29184 (fuse shared experts into MMVQ)" | prefill 曾出现 2× 回退（报告者为 3×RTX PRO 6000 环境，非 8 GB 场景） |

### 4.4 与 Strata 路线的对照（本机已有结论）

同目录 `Strata-8G实测-Qwen36起不来.md` 记录：RTX 4060 Ti 8 GB 上，Strata 0.1.54 用 UD-Q4_K_XL（22.85 GB）**28 个臂全部 EngineDied**，卡在"混合专家缓冲 + 槽"缺 242–418 MiB，且 `--expert-slots` 只能让需求变大（1→1235 MiB，2→1310，4→1460…）。
→ 所以"8 GB 上到底能不能跑"这个问题的答案是**分生态的**：**llama.cpp 能（要 32 GB 内存 + 专家分流，约 30 tok/s）；Strata 这条引擎路线不能（它把路由专家放卡上）**。这条差异比"模型行不行"更值得写进结论。

---

## 5. 反证与风险（不要只看好消息）

1. **"主流"有时效**：Qwen3.8-27B 已上线近 3 个月且下载/点赞均远超它；2026-10 之后新建项目选型，3.6-35B-A3B 属于"存量方案"。
2. **下载量 ≠ 真部署**：HF downloads 含 CI、镜像、重复拉取；且 655 个衍生仓库意味着流量被 FP8/NVFP4/AWQ/GGUF 多份摊薄，官方仓库的 456 万不能当"456 万次部署"读。
3. **官方基准是自家跑分**：agent scaffold、judge 模型（TAU3 用 gpt-5.2 当 user model、VITA 用 claude-4-sonnet 当 judge）都由 Qwen 自行设定，跨厂商对比需打折。
4. **社区负反馈确实存在**：HF 讨论区有 "Poor tools use and endless resoning loop"（10 回复）、"endless reasoning loops"（10 回复）、"太吃显存啦"（7 回复）等热帖 —— 说明工具调用稳定性与显存饥饿是真实痛点，不是个别现象。
   https://huggingface.co/Qwen/Qwen3.6-35B-A3B/discussions
5. **8 GB 报告的样本量很小**：目前只核到 1 篇完整一手（案例 A），属于"存在性证明"，不是"普遍体验"。30 tok/s 这个数字还依赖 DDR4/DDR5 带宽与 CPU，换机器会明显变化。

---

## 6. 一句话回答提问者

- **①量有多大**：官方 456 万下载 / 3,055 赞、1000+ 衍生仓库（合计 2,458 万下载）、ModelScope 61.5 万、Ollama 18 个 tag、LM Studio 260 万——**是"大版本级"体量，但 2026-08 起已被 Qwen3.8-27B（750 万/1.87 万赞）盖过**。
- **②质量位置**：**Agent/终端/工具链同尺寸第一（Terminal-Bench 51.5、Claw-Eval 68.7、MCPMark 37.0），纯代码修补与知识略输自家稠密 27B（SWE-bench 73.4 vs 75.0）**；对 Gemma4 同尺寸是压制级。
- **③8 GB 部署**：**有，走 llama.cpp**：RTX 4060 8 GB + 32 GB 内存，UD-Q4_K_M，显存 7.2–7.8 GB / 内存 16–20 GB / 约 30 tok/s / 4 小时稳定；**Strata 同机不可行**（专家槽必须上卡，缺 242 MiB 起）。

---

## 附：抓取命令留痕（可复现）

```bash
export HTTP_PROXY=http://127.0.0.1:7897 HTTPS_PROXY=http://127.0.0.1:7897
curl -s "https://huggingface.co/api/models/Qwen/Qwen3.6-35B-A3B"
curl -s "https://modelscope.cn/api/v1/models/Qwen/Qwen3.6-35B-A3B"
curl -s "https://huggingface.co/api/models?search=Qwen3.6-35B-A3B&limit=100&skip=0"   # 分页至 1000
curl -s "https://huggingface.co/api/models/unsloth/Qwen3.6-35B-A3B-GGUF/tree/main"
curl -sL "https://raw.githubusercontent.com/ggml-org/llama.cpp/master/src/llama-arch.cpp"
curl -sL "https://docs.vllm.ai/en/latest/models/supported_models.html"
curl -sL "https://ollama.com/library/qwen3.6/tags"
curl -sL "https://lmstudio.ai/models/qwen/qwen3.6-35b-a3b"
curl -sL "https://haies.cn/ai-moe-qwen3-6-35b-a3b/"
```
