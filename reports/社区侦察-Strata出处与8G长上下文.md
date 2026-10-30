# 社区侦察：Strata 是谁的作品 · 8 GB 卡拿 128K/200K 的配方

> 侦察员 community-scout ｜ task-9 ｜ 2026-10-30 ｜ 结论全部来自当场抓取的 GitHub API / raw 文件 / 仓库文本，每条给 URL + 原文片段。
> 本机基线：RTX 4060 Ti 8 GB（sm_89, 8,188 MiB）+ Ryzen 7 7800X3D + 32 GB DDR5-6000；引擎 ninfer-serve-89.exe（build engine-v0.11.0-kvmem-20261003-98-g43c39c6）；现役 --kv-capacity 40000 --kv-dtype rk2v4-e8 --host-kv-mib 6144 --max-context 262144 + MTP draft4/win8，峰值 7,469 MiB / 97-98 tok/s。

---

# 一、结论先说

**A) Strata 的作者是斯洛文尼亚的独立开发者 Niko1221（GitHub: Niko1221，昵称 "Niko"，Ljubljana），不是沈三殊。**
官方仓库 https://github.com/Niko1221/Strata ，MIT 许可。沈三殊（GitHub: 1314521gjy）只是 **Strata 的中文布道者 + fork 作者**（他的 `1314521gjy/Strata` 仓库 `fork=true`、★0、描述与上游逐字相同），他自己的主战场是 **NInfer / KVMem / Bonsai 那条线**（`1314521gjy/ninfer-fusion-kvmem`，★500，自述"是 NInfer 的下游衍生项目"）。

**B) 8 GB 卡上真正跑过 128K/200K 的配方一共 6 条，最贴合我们机器的是两条：**

| 配方 | 卡 | 逻辑窗 | decode | 一句话 |
|---|---|---|---|---|
| **Aurora-Serendipity/ninfer-8gb-playbook** ★2 | **RTX 4060 Laptop 8 GB（sm_89，同族同 dtype rk2v4-e8）** | 131,072 / **262,144** | **63-72 / 20 tok/s** | 两档现成：`12800+host3328` 与 `51200+host3328`，峰值 7,015 / 7,171 MiB |
| **professorpalmer/bonsai-ada-surgery** ★96 | RTX 2060 SUPER 8 GB（llama.cpp 路线） | **262,144 全窗口** | 52.4 / 29.6 / 11.4 在 4k/128k/245k | 不靠 KVMem 检索，q3_0 KV 溢出到 pinned RAM 走 PCIe |

---

# 二、A 部分：Strata 的出处（逐条证据）

## 2.1 官方仓库与体量

**URL：https://github.com/Niko1221/Strata**（`GET https://api.github.com/repos/Niko1221/Strata` 当场返回）

```json
"full_name": "Niko1221/Strata",
"description": "Local 100B-class MoE inference on 8-32 GB of VRAM (and more), OpenAI-compatible, no cloud",
"created_at": "2026-09-24T16:40:20Z",
"pushed_at": "2026-10-29T…",
"stargazers_count": 35970, "forks_count": 3883, "watchers_count": 185,
"open_issues_count": 872, "size": 80868,
"license": { "spdx_id": "MIT" }
```

仓库根目录（`git clone --filter=blob:none --sparse` 后 `ls`）：
`START-HERE.bat`、`SETUP.bat`、`UPDATE.bat`、`BENCH.bat`、`LICENSE`、`AGENTS.md`、`CONTRIBUTING.md`、`SECURITY.md`、`Dockerfile`、`CMakeLists.txt`、`README.md` + 8 种语言 README（`README.zh-CN.md` / ja / de / fr / es / pt-BR / pl）、`apps/desktop`（Tauri 桌面端）、`docs/`（15 MB）、`serve/`（Python 服务端 `serve/server.py`）。

> **「START-HERE.bat 向导」对上了**：安装包双击的就是仓库根的这个文件。任务描述里的 `--kv-resident / --expert-cache / --ple-io / --vram-reserve-mib / --pcie-frac / --batch / --slots / --peer-*` 也都能在 `docs/` 里逐个查到出处（`docs/DETAILS.md`、`docs/BATCHING.md`、`docs/PREFILL_HEAD_ALIAS.md` 等）。

## 2.2 许可证 = MIT，版权人写死

`LICENSE` 原文（文件头两段）：

```
MIT License

Copyright (c) 2026 Niko1221 and the Strata contributors
```

`.github/FUNDING.yml` 原文：

```yaml
buy_me_a_coffee: strataengine
```

⇒ 单人主导 + 社区贡献者模式，没有公司实体、没有商业授权条款，打赏走 Buy Me a Coffee（账号 `strataengine`）。

## 2.3 作者身份（GitHub 用户 API）

**URL：https://api.github.com/users/Niko1221**

```json
"login": "Niko1221", "id": 86886444,
"name": "Niko",
"bio": "AI & fun",
"location": "Ljubljana, 🇸🇮",
"created_at": "2021-07-03T…",
"public_repos": 1, "followers": 805, "following": 1,
"blog": null, "twitter_username": null
```

解读：2021 年注册的老账号，**名下只有 Strata 一个公开仓库**（一个人只做一个项目的典型），粉丝 805，位置斯洛文尼亚首都卢布尔雅那；没有个人博客 / 推特 / 官网。

## 2.4 版本线：0.1.43.1 是「引擎版本」，不是客户端版本

用户手上的 Strata 0.1.43.1 属于**引擎（server）版本线**，与 README 上的客户端版本（当前 **0.2.8**）不是一回事。仓库内 `docs/` 原文（行号为 clone 后实测）：

- `docs/AMD_HIP.md:589` — `engine 0.1.43.1`
- `docs/BATCHING.md:41` — `engine (0.1.43.1) pipelines and leaves --batch-mtp off`
- `docs/COMMUNITY_BENCHMARKS.md:64` — `Strata a0116b2 (0.1.43.1)`
- `docs/OLDER_GPUS.md:333` — `engine 0.1.43.1 with the sm_61 changes`
- `docs/DETAILS.md:1341`（更新日志表）— `| 0.1.25 | RTX 3090, Coder, 198K context, --kv k8v4 | 99 instead of 85 tok/s output … On an RTX 2060 SUPER 8 GB at 128K: +780 expert slots over resident K8V4 |`

发布页（README 徽章直链）：**https://github.com/Niko1221/Strata/releases/latest**，资产名 `Strata-0.2.8-windows-x64-setup.exe` / `-linux-x86_64.AppImage` / `-macos-arm64.dmg`。

## 2.5 代码血缘：llama.cpp / ggml 的 MIT 衍生，ninfer 是「思路来源」而非上游

`docs/DETAILS.md` 原文（血缘段）：

> "the i-quant formats, the GPU dot products and dequantizers transcribed in src/kernels/cuda/iq_kernels.cu, the CPU backend linked for the i-quant experts, the mtmd library behind the image encoder (tools/vision/), and gguf-py"

**`docs/DETAILS.md:1315` 与 `docs/HOW_IT_WORKS.md:68` 同一句原文：**

> "Ideas from [Splash](https://github.com/incoai/splash), [ninfer](https://github.com/Neroued/ninfer) and [HyperQwen](https://github.com/syv-ai/HyperQwen)"

⇒ **Strata 把 ninfer 写成第三方「思路来源」并给原始仓库链接**，口吻是"我借鉴了别人"，不是"这是我自己的另一个分支"。这与沈三殊的 `ninfer-fusion-kvmem` 完全不同：后者在 `NOTICE.md` 里明确写「上游 = Neroued/ninfer」「本仓是 NInfer 的下游衍生项目」。

## 2.6 是多人协作项目，不是单人小作坊

`docs/` 里点名的外部贡献（原样摘录）：
`pjgmobile` PR #54（加 Coder 量化）、`code-martin` PR #22（Monitor）、#3176 `mnott`、#1628 `thoives`、#2972/#2974 `CC-David-CC`、#3550 `sakuumomo`、#1787 `Scotty-Hudson`、#2615 `uppet`、issue #3823/#4004 `xvcezrqpbxtpzblrt`；issue #544 是"审计发现收集帖"；fork 里有 `eddoursul/Strata`。

## 2.7 下载源清单（全部可点）

| 类别 | 链接 | 说明 |
|---|---|---|
| 官方发布 | https://github.com/Niko1221/Strata/releases/latest | Windows setup / Linux AppImage / macOS dmg |
| 源码 | https://github.com/Niko1221/Strata | MIT |
| 基座模型（Qwen 官方） | https://huggingface.co/Qwen/Qwen3.8-Flash-Next | |
| 首推量化（ISTA-DASLab） | https://huggingface.co/ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-GGUF | Q2_0 / IQ2_XS / IQ3_XXS / IQ3_S |
| Coder 量化 | https://huggingface.co/ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-Coder-GGUF | |
| Unsloth | https://huggingface.co/unsloth/Qwen3.8-Flash-Next-GGUF | UD-Q4_K_XL … Q8_0 |
| Gyro（省内存/更慢） | https://huggingface.co/agentionai/Qwen3.8-Flash-Next-Gyro-GGUF | Gyro-S / Gyro-M |
| Swift 1.5 | https://huggingface.co/ukisai/Swift-1.5-Qwen3.8-Flash-Next-GSQ-RCO-GGUF | UkisAI 微调 |
| 打赏 | https://buymeacoffee.com/strataengine | `.github/FUNDING.yml` |

**ModelScope / HuggingFace 上的 Strata 本体仓库：未发现官方镜像。** 我 grep 了 clone 下来的 `README.md` + `docs/*.md`，`modelscope|ModelScope|discord|qq.com|t.me|stratat.com` **零命中**（只命中 HuggingFace 权重链接）。中文圈流传的下载包都是二道贩子整合包（见 2.9）。

## 2.8 关键判定：Strata 与沈三殊**不是同一作者**

### 证据 1：沈三殊自己的账号画像（https://api.github.com/users/1314521gjy）

```json
"login": "1314521gjy", "id": 299195089,
"name": "沈三殊",
"bio": "ai自媒体，输出内容为优秀技术的宣传与推广，本地部署方案的推荐，不接任何商业推广。",
"created_at": "2026-07-02T…",
"public_repos": 8, "followers": 27
```

**他自己写的 bio 是「自媒体 / 宣传推广 / 本地部署方案推荐」——身份定位是布道者，不是引擎作者。**

### 证据 2：他在 Strata 上只有一个 fork，★0

`GET /users/1314521gjy/repos` 返回 8 个仓库，其中 Strata 那条：

```
"name": "Strata", "full_name": "1314521gjy/Strata",
"fork": true,
"stargazers_count": 0,
"description": （与 Niko1221/Strata 的上游描述逐字相同）
"created_at": "2026-10-04…", "pushed_at": "2026-10-07…"
```

`fork: true` 是 GitHub 的硬标志——**这是上游仓库的分叉副本，不可能是原作者**。

### 证据 3：他的其余 7 个仓库全都指向「NInfer/KVMem/Bonsai + 中文部署」这条线

| 仓库 | 时间 | ★ | fork | 描述（原文） |
|---|---|---|---|---|
| `ninfer-fusion-kvmem` | 10-04→10-20 | 500 | false | 面向 Windows/NVIDIA 的长上下文推理实验，基于 NInfer 0.11.0 线 |
| `Strata` | 10-04→10-07 | 0 | **true** | 上游描述 |
| `cyber-on-strata` | 10-09→10-10 | 29 | false | 在 8 GB 显存的显卡上跑 35B MoE（Cyber-Tiel-Coder-35B-A3B）…Strata 引擎的 fork（MIT） |
| `ornith1.5-122B-on-Strata` | 10-21 | 4 | false | Ornith-1.5-122B … on Strata **poly branch**: prefill +171%, 8K TTFT -55% |
| `sage-a1.5-on-strata` | 10-21→10-22 | 0 | false | Sage-A1.5 … on **PolyStrata**/Strata: single 32GB GPU, 256K context |
| `nemotron-on-sss-strata` | 10-17→10-19 | — | false | WIP |
| `modelsmith` / `ComfyUI-Local-Infinite-Canvas` | — | 70 | false | 训练工作台 / ComfyUI |

⇒ 他对 Strata 做的事是 **fork + 自建 PolyStrata/SSS-Strata 分支 + 写中文部署方案**，典型「下游适配者」。而 Niko1221 名下只有 Strata 一个仓、账号 2021 年注册、位置斯洛文尼亚。

### 证据 4：两账号无任何硬关联

`id` 86886444 vs 299195089；created 2021-07-03 vs 2026-07-02；location 斯洛文尼亚 vs 中文圈；`public_repos` 1 vs 8。Strata 的 `docs/` 里也没有任何 `1314521gjy` / 沈三殊 / 中文作者署名（grep 零命中）。

### 结论（一句话）
**不同作者。Strata 是 Niko1221（斯洛文尼亚，MIT，单人主导 + 社区）的独立项目；沈三殊是它的中文布道者与 fork 维护者（PolyStrata 分支），同时是 NInfer/KVMem/Bonsai-27B 那条线的作者。**

> 混淆的成因很清楚：中文圈能搜到的 Strata 文档（`Strata-本地硬件适配指南-20261013.md` 那种"实验纪律手册"风格、依据引擎 0.1.43.1、不给具体数值）几乎都是沈三殊系写的；而**官方 `docs/` 是英文的**，并且明确把 ninfer 列为第三方思路来源。两条线在中文搜索里被搅成一团。

## 2.9 中文圈传播链（第三方，非官方）——顺带澄清两个流行视频

- **BV1PwHs6vEiY**「6G显卡能跑Qwen3.8 flash？热门项目Strata问题解答」→ UP 主 **AI观模者**（mid 19134148，33,813 播放 / 425 评论）。字幕原文：「上一期发布了关于这个 structure 的视频…我就针对大家最关心的一些问题来做一个解答」——第三方测评。
- **BV1HMHw6wETo**「strata 内存32G+8G显存>39G即可不读硬盘跑 iq3 级 85G 文件均速 66t/s-Gyro-M」→ UP 主 **国际米兰肠胃**（mid 52111407）——第三方实测。
- 其他教程都指向同一仓库：Smthem `BV1f3pM6jEoi`（描述里直接写 github.com/Niko1221/Strata）、九物AI生产力 `BV1Q2Hy6NE4k`（3060 12G+32G，IQ2_XS）、谢家貔貅 `BV1DEpw67EqP`、T8star-Aix `BV15bpy6rEJ7`（8G 整合包，31k 播放）、X超哥 `BV1iEnD6RE6y`（55k 播放）、十三玩AI `BV1v6xj6gEar`、禾雨生 `BV1FHxc6MEJy`。
- 图文：appinn（https://www.appinn.com/strata-0-2-3/）原文「Strata 是一款免费开源的本地大模型运行工具…最低只需要 8GB 显存…项目地址 https://github.com/Niko1221/Strata」；知乎 https://zhuanlan.zhihu.com/p/2089282096925878242 ；itbanana.com/blog/strata-app-guide/ ；eogee.com/article/184 。
- ⚠️ **stratat.com 未获证实**：站点自称"下载 Strata 引擎与桌面客户端"（https://www.stratat.com/zh/download），但**仓库 README / docs / FUNDING 里没有任何一处指向它**（grep 零命中）。判定：**第三方站，非官方**，来历不明，不建议作为下载源。

---

# 三、B 部分：8 GB 显存拿 128K/200K 的配方（带参数与实测）

## 3.1 总表（全部为作者自报实测；卡片/条件见各小节）

| # | 方案 | 卡 | 设备池 --kv-capacity | 主机 KV | --kv-dtype | --max-context | 投机 | 显存峰值 | decode | prefill |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Aurora 日常档 ★2 | **4060 Laptop 8G** | **12,800** | **3,328 MiB** | **rk2v4-e8** | 131,072 | MTP d4 win8 | 7,015 MiB | **63-72 tok/s** | 610-697 |
| 2 | Aurora 长档 ★2 | 同上 | **51,200** | **3,328 MiB** | **rk2v4-e8** | **262,144** | 无 | 7,171 MiB | **20 tok/s** | — |
| 3 | sm120a toolkit | RTX 5060 8G | **8,192** | **16,384 MiB** | `k8v4` | **262,144** | MTP d4 | 引擎自报 runtime 710 MiB | 54-99（中位 60） | 482-670 |
| 4 | 5258MF 8G 版 | 3060 12G 限 7.5G | KVMem 44K 档 | — | rk4v4 / rk8v4 | 128K | MTP | 7,628 MiB | 45.2-45.6 | — |
| 5 | bonsai-ada-surgery ★96 | **2060 SUPER 8G** | llama.cpp 无池概念 | KV 溢出到 pinned RAM | **q3_0** | **262,144** | MTP+lookup | 92,160 位置在显存 | 52.4 / 29.6 / 11.4 在 4k/128k/245k | 417 / 241 / 164 |
| 6 | cyber-on-strata（Strata 8G 档） | 4080S（按 8G 配） | Strata `--expert-cache` 3.0 GiB | KV 全在显存（fp16 21.6 KiB/tok） | — | 256K 级 | MTP | **7,260 MiB** | 57.7-63.5 | 1,736-2,203 |
| 7 | sage-a1.5 §9（8G 档） | 4080S 32G | 专家 2,396/10,240 驻留 4.3 GiB | — | — | 262,144 | MTP win4 | — | 58.35（profile 68.23） | 1,918-3,388 |
| 8 | paicat1 ★10 | 4090 24G | **229,376** | 8,192 MiB | **nvfp4** | **229,376** | DFlash2 K7 | — | 230-245（端到端） | 2,680-2,850 |
| 9 | CraneBW | 4090 200W | `--kv-device-tokens 36864` | `--host-kv-mib 0` + `--kvmem-budget 32768` | int8 | **212,992** | MTP15 | — | 197.6 在 32K | 1,431 |
| 10 | G0K0U（16 GB） | 4080 16G | — | — | GSQ | 131,072 | — | 14,777 MiB | 52.6 `60K / 56.5 `100K | — |

## 3.2 配方 1+2：Aurora-Serendipity/ninfer-8gb-playbook ——**同款卡（4060 Laptop 8 GB / sm_89），最该抄的一份**

URL：https://github.com/Aurora-Serendipity/ninfer-8gb-playbook （README + `docs/04-8GB显存档位适配.md`）
定位：「NInfer v2（KV 流式）引擎 + Bonsai 2 27B 三进制模型 + 网关 + 控制台，跑在 **RTX 4060 Laptop（8 GB / sm_89 / Windows）**」。

**两档对照（`docs/04` 原文表格）：**

| | 日常 `8g-daily` | 长上下文 `8g-longctx` |
|---|---|---|
| 设备池 `--kv-capacity` | **12,800**（200 页） | **51,200**（800 页） |
| `--kv-dtype` | **rk2v4-e8** | **rk2v4-e8** |
| `--host-kv-mib` | **3,328** | **3,328** |
| `--max-context` | 131,072（2,048 逻辑页） | **262,144**（4,096 逻辑页） |
| `--default-max-tokens` | 2,048 | 8,192 |
| MTP | `--spec mtp --draft-tokens 4 --mtp-attention-window 8` | **无** |
| 额外 | `--no-cuda-graph --default-reasoning-effort none` | 同左 |
| 显存峰值 | 7,015 MiB | **7,171 MiB** |
| decode | **63-72 tok/s** | **20 tok/s** |
| 实测证据 | 1,121 token 题面 TTFT 1.7 s；10,130 token 中段针命中 | **48,062 token 题面中段针命中**（TTFT 78.7 s）；`max_tokens=8192` 吐满 8,192（约 6 分 45 秒） |

**原文启动行（`docs/04` 摘录）：**
```
--kv-capacity 12800 --kv-dtype rk2v4-e8 --host-kv-mib 3328 ^
--max-context 131072 --default-max-tokens 2048 ^
--no-cuda-graph --default-reasoning-effort none ^
--spec mtp --draft-tokens 4 --mtp-attention-window 8

--kv-capacity 51200 --kv-dtype rk2v4-e8 --host-kv-mib 3328 ^
--max-context 262144 --default-max-tokens 8192 ^
--no-cuda-graph --default-reasoning-effort none
```

**必须项（原文「必须项与退档阶梯」节）：**
- `--no-cuda-graph`：**不加首启 FATAL**，日志报 runtime reservation > available；「CUDA Graph 预留 1,426 MiB，8 GB 卡放不下」——和我们实测 1,863,978,752 → 1,010,437,888 B 是同一个病根。
- **出厂 `--draft-tokens 1` 只有 36-37 tok/s；改 4 提到 63-72，且显存不变**（他们最关键的一条提速）。
- `--max-shared-prefixes 0` 必须恰好出现一次且 = 0。
- 「网关输入预算 = 池 − 输出 − 512 slack」：日常 `12800−2048−512=10240`，长档 `51200−8192−512=42496`。
- **判活必须真发请求**：`GET /v1/models` 返回 200 **不算数**（worker 崩了照样 200）。

**对着我们的账本看（重要）：**
- 他们 `--host-kv-mib` 只给 **3,328**，我们给 **6,144**。262,144 逻辑窗在 v2 引擎上只需 3,296 宿主页 ⇒ **我们可以把 host-kv 从 6144 降到约 3,330，省下 2.8 GiB 主机内存**（不影响显存，但给 Windows 留出余量）。
- 我们 40,000 池 / 97-98 tok/s 的形态落在这两档之间：**比他们日常档（63-72）快、比长档（20）快 5 倍**，代价是逻辑窗覆盖不如长档稳。
- 他们的长档 decode **20 tok/s** 与我们"51200 池 prefill 崩到 180、关 MTP 后 32 tok/s"量级完全吻合 ⇒ **51200 池的慢是形态特性，不是配置错误**。要拿 262,144 窗口就得吃这个速度。

## 3.3 配方 3：ninfer-sm120a-8gb-toolkit（RTX 5060 8 GB，容量算术最好的一份）

URL：https://github.com/ （本地 clone：`repos/ninfer-sm120a-8gb-toolkit`，六档 .bat 启动器 + `records/` 逐轮读数）

**启动行（`start-ptq1-mtp-8gb.bat` 原文）：**
```
ninfer-serve-120a.exe %MODEL% ^
  --host 127.0.0.1 --port 8095 --model-id qwen3.8-27b ^
  --max-context 262144 --kv-capacity 8192 --kv-dtype k8v4 --host-kv-mib 16384 ^
  --spec mtp --draft-tokens 4 --no-cuda-graph ^
  --default-max-tokens 4096 --default-reasoning-effort none ^
  --max-shared-prefixes 0 --presence-penalty 0 --temperature 0.7 --top-p 0.9 --top-k 20
```
环境变量（原文）：`NINFER_KV_WINDOW=16384`（**KVMem 开关键**，删了退回词法排序）、`NINFER_KV_RETRIEVE=8192`、`NINFER_KV_RING=1`、**`NINFER_HOST_PAGEABLE=1`（Windows 必需：钉住的主机内存会映射进 GPU 地址空间、与显存抢地盘）**、`NINFER_KV_REUSE_HOSTBACKED=1`、`NINFER_TERNARY_PTQ1_FAST=1`。

**容量算术（引擎启动强制，页 = 64 token）：** 主机池页数 + 设备池页数 ≥ 逻辑上下文页数；主机开销 **25.12 KiB/token**（`host_kv_page_group_bytes = 1,646,592 B / 64 token`）⇒ `262144→6.28 GiB`、`524288→12.56`、`786432→18.84`、`1048576→25.12 GiB`、`2097152→50.25`。

**三条不能删的参数（每条都有被拒原文）：**
| 参数 | 引擎默认 | 依据 |
|---|---|---|
| `--kv-capacity 8192` | 默认 = `--max-context`（1M） | 删了池变 1M token，8 GB 装不下 |
| `--no-cuda-graph` | **默认开** | 关掉才把运行时预留从 `1,863,978,752` 降到 `1,010,437,888` B；否则启动即被拒 |
| `--default-max-tokens 4096` | 8192 | 手册 §1-11：`max_tokens ≤ 池`；客户端要 32,000 → **worker 崩溃**（`Paged KV reservation invariant was violated`，2/2 复现，而 `/v1/models` 仍 200） |

**实测（RTX 5060 8 GB，驱动 591.86）：** prefill 482-670 tok/s · decode 54-99（同配置重复测出 **54.7 与 80.0**，差 46% ⇒ 单次读数不可作准，要取中位）· MTP 接受 780/875 = 89.1% · 1000 进/1000 出 约 19 s。
**一条 8 GB 铁律（实测）：** 「一张 8 GB 卡只跑一个实例」——第二个实例经 WDDM over-commit"加载"后在 D3D12 arena 里死掉。
**不用共享显存：** `--wddm-evictable-budget` 需要 `NINFER_D3D12_RESIDENCY=ON` 的构建，这个 exe 没编进去。

## 3.4 配方 5：professorpalmer/bonsai-ada-surgery —— 不是 KVMem，是 llama.cpp + q3_0 KV 把 262K 全窗口塞进 8 GB

URL：https://github.com/professorpalmer/bonsai-ada-surgery （`docs/8gb/README.md`，★96）

机制原文：「On an 8 GB card the launcher serves the **full 262,144-token window** with a **q3_0** K/V cache. **About 92,160 positions stay in VRAM; the rest of the cache is in pinned system RAM and is read over PCIe.**」
- 8 GB 预设自动开：`BONSAI_8GB=1`，启动打印 `window 262144 / q3_0 (8 GB default)`；**262K 窗需 ≥24 GB 系统内存 + MTP head 文件，否则退回 131,072**。
- 需要 `make_mtp_q4head.ps1` 把 MTP 头压到 Q4（省 214 MiB）。

**实测（RTX 2060 SUPER 8 GB，Turing，PCIe 3.0 ×16，显示器还插在这张卡上）：**
| 深度 | 4k | 64k | 128k | 160k | 245k |
|---|---|---|---|---|---|
| decode tok/s | 52.4 | 39.9 | 29.6 | 18.6 | **11.4** |
| 冷读 prefill tok/s | 417（9.7 s） | 309 | 241（529 s） | — | 164（**1,489 s**） |

- 质量：q3_0 下 HumanEval **163/164**；245k 处精确代码抄写 20/20、needle 23/24（与 dense 读逐项相等）；对 f16 KV 的漂移：16k 平均 KL 0.008（q4_0 0.0021 / q8_0 0.00024），top token 与 f16 一致率 96%。
- **最值钱的工程经验**：「A cold read of a long prompt is slow on this card」，但 **Saved conversations** 把重启后的重读压到秒级：~199k 文档冷读 1,069 s，重启后 **5.3 s**；131k 文档 561 s → 6.25 s；245k 会话 1,689 s → 5.2 s。
- 两周演进（他们自己的标注）：窗口 65,536 → 262,144（4×），4k decode 37.2 → 52.4（+41%），120k 处 3.0 → 29.6（9.9×）。

⇒ 启示：**8 GB 卡上 200K 的真实瓶颈不是 decode（11-30 tok/s 能用），而是「冷读一次 20 分钟」**。谁能把 prefill 复用 / saved-conversation 做出来，谁才真正可用。

## 3.5 其余生态仓库（照任务清单逐个核过）

- **CraneBW/ninfer-ternary-bonsai-ada**：sm_89 调优线（双 V100 attention split-vector、GDN FP32 预归一化，两开关默认 0）。4090 200W 下 `--max-context 212992 --kv-device-tokens 36864 --host-kv-mib 0 --kvmem --kvmem-budget 32768 --kv-dtype int8`：**32K/MTP15 decode 197.57 tok/s、prefill 1,431**；同条件 4.6K 输入 decode 中位：AR 44.5 / MTP4 80.0-142.3 / MTP15 45.7-217.1 / DFlash2 K3 92.2-134.3。**213K 逻辑上下文是它能诚实跑到的位置（256K 只在显式 `--checkpoint-load-pipeline` 下）**，213K 时加载权重中位 10.4 s。教训：MTP 长生成越过 32K 工作集会触发双 KV 回收失败（已修）。
- **paicat1/Bonsai-27B-NInfer**（★10）：`--kv-dtype nvfp4 --kv-capacity 229376 --max-context 229376 --spec dflash2 --draft-tokens 7`，**229K 满上下文 nvfp4**；prefill 峰值 2.85k（A3 token-grid 调度移植，+31%），端到端 230-245 tok/s（180K 档）；**已验证最大档 = 200K（204,800）+ 视觉，余量 779 MiB，182 个真实请求仅 1 次停滞**。⚠️ 主机内存账：**启动会锁 9.2 GiB pinned**（`host state 1.15 GiB + host KV 8.00 GiB`），16 GB 内存机器启动即失败；降配 `--host-kv-mib 2048` / `--host-state-slots 4`。**这才是 200K 在 8 GB 卡上最硬的约束：主机内存，不是显存。**
- **ygxiuming/ninfer-bonsai-4070ti**（★6）：4070 Ti 12 GB + Linux + Docker 容器化部署实录，容器化跑法参考，非 8 GB。
- **G0K0U/kvmem-agent-16gb**：4080 16 GB，**128K 跑满峰值 14,777 / 16,376 MiB**，100,084 token 检索 **56.5 tok/s**、60K 检索 52.6 tok/s；另有 Bonsai 2 CRACK PQ2 档「262144 context on RTX 4080 16GB，100+ tok/s」。⇒ 16 GB 卡才是 128K+ 的舒适区。
- **Continuum-AI-Corp/OrcaBonsai-27B-Uncensored**：模型发布向，无 8 GB 配方。

## 3.6 关于「是否分片」

- **8 GB 档几乎全是单卡单实例**，没有一条 8 GB 配方用分片；两个 8 GB 实测（sm120a、playbook）都明写「一张卡只能一个实例，第二实例必崩」。
- 要堆容量/显存的现实路径只有三条：① 引擎侧 KV 分层（KVMem 环 / host KV / 磁盘 KV 层，sm120a 的 disk-kv 64 GiB 档）；② 换 llama.cpp 路线让 KV 溢出到 pinned RAM（3.4）；③ **多卡**：`mmknet2025/ninfer-line-8091-dual-card-tp2`（NInfer 双卡 TP2）、Strata 的 `docs/MULTI_GPU.md` / `SPLIT_SERVE.md` / `SECOND_GPU.md`。8 GB 单卡谈分片没有意义。

## 3.7 落到我们这台机器（4060 Ti 8 GB / 32 GB DDR5）的判定

| 配方 | 能否直接落 | 依据 |
|---|---|---|
| Aurora 日常档 12800+3328/131072 | ✅ 直接可试 | 同架构同 dtype；我们的引擎已有 `--host-kv-mib`，把 6144 降 3328 即可 |
| Aurora 长档 51200+3328/262144 | ⚠️ 能起，慢 | 我们实测 51200 池「起得来但 prefill 崩到 180」，与他们长档 decode 20 tok/s 同量级；**要接受 20-30 tok/s** |
| sm120a 8192+16384/262144 | ✅ 可试（dtype 需换） | 我们模型是 PTQ1 ternary，dtype 按自家模型选；重点是三条不能删的参数与我们完全一致 |
| bonsai-ada-surgery 262144/q3_0 | 🔶 需换引擎 | 那是 PrismML llama.cpp 分支，不兼容 .ninfer 权重；要重下 GGUF（PTQ1_0, 5.9 GB）+ MTP head |
| cyber-on-strata 8G 档 | 🔶 换模型 | 那是 35B MoE + Strata 引擎，不是 27B ternary，且 16 GB 内存都不够（专家银行 18.32 GiB） |

---

# 四、三条最值钱的结论（按可落地程度排序）

1. **`--host-kv-mib` 从 6144 降到 ~3328 就够了。** Aurora 用 3,328 MiB 支撑 262,144 逻辑窗（原文：262,144 逻辑窗需要 3,296 宿主页），我们多给了 2.8 GiB 主机内存却没换来显存。省下的 RAM 正好给 Windows/文件缓存，缓解 `NINFER_HOST_PAGEABLE=1` 下"钉住内存抢 GPU 地址空间"的老问题。
2. **`--draft-tokens` 从 1（出厂默认）改到 4 是 8 GB 卡上最大的单点提速**：Aurora 实测 36-37 → **63-72 tok/s，显存不变**；我们现役已是 draft4，方向对。**但长档（51200 池）必须关 MTP**——草稿权重要吃 0.5-1 GiB，长档没有余量。
3. **200K 的真实瓶颈是主机内存和冷读，不是显存也不是 decode。** paicat1 的 229K 档要**锁 9.2 GiB pinned**（16 GB 机器起不来）；bonsai-ada-surgery 冷读 245K 要 **1,489 秒**，靠 saved-conversation 才降到 5.3 s。我们 32 GB 内存够用，但**"第一次喂 200K 文档"这一下必须按分钟级预期**，客户端超时 ≥300 s（Aurora 原文建议）。

---

# 五、不确定项 / 需要后来人复核

- `stratat.com` 与 https://www.stratat.com/zh/download ：**仓库里零指向**，判定第三方站，未验证其二进制来源。要下载只用 GitHub Releases。
- Strata 在 ModelScope 上是否有官方镜像：**未查到**（仓库内零引用；未做 ModelScope 站内搜索——该站需登录且无稳定公共 API）。
- Strata 的 `--peer-*` 参数我未逐一在 docs 里定位到条目（只在多机/交换相关章节零星出现），需有人在 0.2.8 上实测确认语义。
- 配方 4/5 的 decode 前提不同（显示器在卡上/不在卡上/已扣除），横向比较注意口径；Aurora 与 sm120a 都专门强调了这一点。

---

## 附：本次侦察的可复现命令
```bash
export HTTP_PROXY=http://127.0.0.1:7897 HTTPS_PROXY=http://127.0.0.1:7897
curl -s https://api.github.com/repos/Niko1221/Strata            # 体量/许可/时间
curl -s https://api.github.com/users/Niko1221                   # 作者画像
curl -s https://api.github.com/users/1314521gjy                 # 沈三殊画像
curl -s https://api.github.com/users/1314521gjy/repos           # 8 个仓 + fork 标志
curl -s "https://api.github.com/search/repositories?q=ninfer&sort=updated&per_page=25"
git clone --filter=blob:none --sparse https://github.com/Niko1221/Strata
```
