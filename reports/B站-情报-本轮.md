# B站情报 · 本轮（2026-10-30）— 4060Ti 8GB / NInfer KVMem / Strata / 算力解锁

> 采集窗口：2026-10-30 08:35–10:20（Asia/Shanghai）
> 采集人：bili-oct-scout（B站情报位）；任务：task-12
> 口径约定：**【实测】**= UP 主或评论者贴出自己的机器读数；**【口径】**= UP 主/厂商的宣发或主观结论，无原始读数；**【转述】**= 二手复述他人数据。
> 逐字稿与评论原始件见 §11；引用格式 = BV号 + 原话/评论楼层。
> 本机基线（对比锚点）：4060 Ti 8G + 7800X3D + 32G DDR5-6000；NInfer engine-v0.11.0-kvmem-20261003-98-g43c39c6 + Bonsai 27B ternary PTQ1；--kv-capacity 40000 --kv-dtype rk2v4-e8 --host-kv-mib 6144 --max-context 262144 + MTP draft4/win8；峰值 7,469 MiB、97–98 tok/s（散文 45.7）、37K prefill 963 tok/s。

---

## 0. 一页结论（先看这 9 条）

1. **B 站不存在 --fast-prefill-kernel / --prefill-chunk 这类参数的讨论**。10 组关键词 ×2 排序（263 个唯一 BV）零命中，搜到的全是刷机内核教程与 chunked-prefill 科普。→ 任务②的字面路径在 B 站无先例，prefill 提速只能从「引擎差异 / Windows 参数 / 算力解锁 / MTP」四个角度取证（§5）。
2. **本轮最大可操作发现：Strata 在 Windows 上 prefill 只有一半，罪魁是两个参数，不是 PCIe 带宽。** BV1VPs96qEjr【实测】4090 48G、IQ3_XXS、130K 上下文：默认 prefill 1900–2000；把 strata_arena_pin_gb 设 24（原本未设，显存只用 35G、专家缓存只装 1 万多槽）+ strata_prefer_ring 设 **384**（Windows 默认只有 96，Ubuntu 默认 384）后，130K→**4000+**，230K 仍 4000+。→ 同时解释「为什么云上/Ubuntu 快、Windows 慢」。
3. **算力解锁对 prefill 的收益被普遍高估，但确有一种情况有用。** BV1XnnZ6iELj【实测】2080Ti 22G Win10：**FP16 GEMM +81%、prefill +20%**；BV1d6xN66ECM【实测】4060 笔记本：四条读数均值 29.72→53.54（+80%）。但 BV1RRx36sEtR 作者**自己纠正**（7 赞自评）："今天又测了 Ubuntu 不解锁，prefill 也能到 5000 左右，所以比较了个寂寞" → **Windows 的 2000 是配置问题，不是算力问题**（与第 2 条互证）。解锁只放开 **BF16/FP16/TF32** 三种精度 GEMM（BV1AMHL6zEpx【口径】FP16≈50、BF16 约 80→160、TF32 42→82），**INT8/INT4/NVFP4 量化路径吃不到**。
4. **8G 卡跑 Strata 125B：能跑，但没有实用价值。** 两条同档实测互证：BV1fqxT6nEfz 评论【实测】"8+32 帮大家测过了，最低档位的，基本没用……加载到输出第一句话大概 2 到 3 分钟，大概 10 token/s 左右，实际只会更差，鹈鹕测试用了 20 多分钟，而且频繁爆显存"；BV1Zzpn61E7V 评论【实测】3050Ti 8G+24G 内存+40G 虚拟内存 → 20 tok/s 起步、稳定 12 tok/s。作者自述（BV1EEJ26LEXq【口径】）测试机是 **12G+64G**，8G+32G "可玩不代表速度快"。
5. **反向证据必须并列**：BV1Pgp26aE5U 评论【实测】"32+8G 也是 xxs，**128K 下平均 50 t/s**"（1 赞，参数不全）。与第 4 条矛盾，差异可能来自量化档/上下文/缓存命中 → 本轮无法裁决，标为**待验**（§3.3）。
6. **本机 200K 的瓶颈是「时间」不是「显存」**，两条独立交叉验证：BV1C1nT67T5E【实测，12G+32G 方案】**200K 首次预填充约 7 分钟**，完全重复（缓存命中）仅 **112 ms**；我们 37K prefill 963 tok/s 线性外推 200K ≈ 400 s ≈ 6.7 分钟，**两数吻合**。→ 再次确认 P0：**客户端超时必须 ≥10 分钟**，否则 DSH 5 分钟无 token 重发 → 双份 prefill → 必崩。
7. **KV 放内存 + kv 流式是 8G/32G 拿长上下文的现实路线**：BV1Pgp26aE5U 评论【实测】"96G 内存可以尝试开 kvint8 的 1M 上下文（吃满 800K 大概需要 90g 左右的内存），打开 kv 流式，**decode 不掉速**，仅 prefill 会稍微降一点，缓存命中也没有问题"。沈三殊 BV1JVJd66Esq【口径】引擎引入 **streamingkv**、KVMem 与 streaming 结合，**针对 8G 卡更深度优化、报错大幅减少**；BV1h8WA6XEFQ【口径】进一步省显存，**6G 卡也能跑，代价是内存**，提速约 10%。
8. **Strata 阵营漂亮的 prefill 数字都出现在「多专家 + 大显存 + 大内存」形态**：395 引擎 BV1kYp36fEiP【实测，128G 内存机】64K–128K prefill **1500–1600**、256K 仍近 1600，但 **Windows decode 只有 35–40**（后台抢内存带宽），接受率高时才 50+；评论者【实测】"win 下可以直接拉 **512K 上下文，显存用到 97GB**"。这些 8G 复刻不了。
9. **本机 97–98 tok/s 在 B 站同档里已是顶**：8–16G 档最好成绩是 4060Ti 16G + 64G 跑 Strata IQ3_XXS 的 **46–55 tok/s**（BV1Pgp26aE5U）、5060 16G 跑 NInfer+KVMem+ActKV **50+**（BV1Y8pH6rExF）、4080S 同栈 **35–36 tok/s**（旧版 25–29；40K prefill ≈65 s ≈ 615 t/s，BV1Y8pH6rExF 评论）。**没有一条 8G 实测超过我们。**

---

## 1. 方法与覆盖

- **关键词（10 组 ×2 排序）**：4060Ti 8G prefill / fast-prefill-kernel / prefill-chunk / Qwen3.8-Flash-Next 8G / strata 8G 显存 / UEFI 解锁 算力 显卡 / 沈三叔 / 沈三殊 / ninfer prefill 提速 / kvmem pool 8G 27B → 263 个唯一 BV（tmp/bili2/search_candidates.json）。
- **字幕**：22 条取到逐字稿（其中 3 条空字幕：BV1fqxT6nEfz、BV1JZnR6yEk7、BV1JBHN6ME3V），有效正文合计 **53,570 字**。
- **评论**：15 条视频共 **440 条**评论（tmp/bili2/c_<BV>.json），串行抓取、间隔 3–5 s、失败重试一次（并发会静默返回 0 条）。
- **元数据**：22 条视频 title/author/pubdate/view/like/reply/duration（tmp/bili2/meta.json，走 api.bilibili.com view 接口）。
- **已知局限**：①逐字稿为 AI 字幕，数字有误听，可疑数字已在正文标注；②低赞评论（0–8 赞）的实测可信度有限，已逐条标赞数；③B 站**没有**一条 4060Ti 8G 的解锁或 Strata 专项实测（评论区有人点名求测："**4060ti8g 的解开限制做一期呗**"，BV1fqxT6nEfz）→ 我们若做即首例。

---

## 2. 主表（本轮 22 条）

| # | BV | 日期 | UP | 播放 | 主题 | 一句话价值 |
|---|----|------|----|------|------|-----------|
| 1 | BV1d6xN66ECM | 10-27 | 小飞小飞允许起飞 | 86.7k | 解锁（任务点名） | 全平台开源解锁工具，4060 笔记本 +80% |
| 2 | BV1AMHL6zEpx | 10-25 | ThinkIn2024 | 10.2k | 解锁原理/注意事项 | 只解锁 BF16/FP16/TF32；受益卡型含 4060Ti 16G |
| 3 | BV1XnnZ6iELj | 10-26 | 杭古同学 | 8.5k | 解锁实测 | **FP16 GEMM +81%、prefill +20%**（2080Ti 22G） |
| 4 | BV1RRx36sEtR | 10-27 | 玩机视频 | 2.2k | 解锁 × prefill（含自纠） | 解锁后 prefill 4800，但作者承认 Ubuntu 不解锁也 5000 |
| 5 | BV1VPs96qEjr | 10-28 | 玩机视频 | 1.5k | **prefill 配置坑（本轮最有价值）** | ring=384 + arena-pin=24 修好 Windows prefill 2000→4000 |
| 6 | BV1kYp36fEiP | 10-11 | 防爆键盘 | 6.7k | prefill 引擎（395） | 64K–128K 1500–1600；Windows decode 35–40 |
| 7 | BV1Pgp26aE5U | 10-14 | 程序转圈圈 | 5.5k | **Strata 真读数（4060Ti 16G）** | 46–55 tok/s、专家 8.2G、KV 入内存、冷热缓存对照 |
| 8 | BV1C1nT67T5E | 10-18 | 月光下的豆豆乖 | 13.3k | **12G+32G 27B Agent** | 200K 首次 prefill ≈7 min、重复 112 ms |
| 9 | BV1LmHq6HEKb | 10-04 | X超哥来了 | 72.2k | Strata 教程（8G 口径） | 4080S 16G 跑 IQ3_S 52–63 tok/s；评论区 3070/3090Ti 读数 |
| 10 | BV1fqxT6nEfz | 10-27 | 零度解说 | 10.8k | Strata 8–12G 125B | 评论区 **8+32 实测 10 tok/s + 爆显存** |
| 11 | BV1Zzpn61E7V | 10-11 | 刘悦的技术博客 | 12.1k | Strata 8G | 评论区 3050Ti 8G 20→12 tok/s |
| 12 | BV1EEJ26LEXq | 10-16 | wangyi_AI_Studio | 2.6k | Strata 8G 整合包 | 作者机 12G+64G；8G+32G 仅"可玩" |
| 13 | BV1JVJd66Esq | 10-19 | 沈三殊 | 26.6k | **沈三殊系最新** | streamingkv、千问4架构、Nemotron 专武 |
| 14 | BV1h8WA6XEFQ | 10-13 | 沈三殊 | 22.6k | 沈三殊系 | moe 小专武、6G 卡可跑、提速 ~10% |
| 15 | BV1Y8pH6rExF | 10-12 | melis | 33.9k | **NInfer+KVMem+ActKV** | 256K 调工具 80 次/插针 33 次全召回 |
| 16 | BV1j6pu6jEfc | 10-14 | kris_yuu | 2.7k | NInfer+KVMem 部署 | 两项目都单卡优化 |
| 17 | BV19PJR6oEVk | 10-19 | kris_yuu | 1.4k | KVMem v0.18 | 融合 ninfer + actKV |
| 18 | BV1w8H26RENw | 10-08 | 杭古同学 | 5.1k | **Bonsai + 256K（同模型）** | 2080Ti 单卡 180+ tok/s，UP 自改引擎支持图灵 |
| 19 | BV1ZeJC6qEgS | 10-15 | newtypelv9 | 1.6k | NInfer 机制科普 | 一个 token 穿过 NInfer 的四段 |
| 20 | BV1WjHh6EEaz | 10-03 | 快乐的天才程序员 | 849 | RTX 4060 8G 编程实测 | 8G 上能用的编程模型清单（口径多、数字少） |
| 21 | BV1JZnR6yEk7 | 10-26 | 逻辑仓管AI运营 | 757 | 解锁（4060Ti 16G） | 空字幕，仅标题：ComfyUI 提升明显 |
| 22 | BV1JBHN6ME3V | 10-24 | 梦幻葱哥 | 305 | 4060Ti 16G + Strata | 空字幕，仅标题 |

---

## 3. 主题 A：8G / 4060Ti 同档实测读数总表

### 3.1 硬读数（按显存档位）

| 配置 | 场景/量化 | 读数 | 来源与性质 |
|------|-----------|------|-----------|
| **8G + 32G 内存** | Strata 最低档（Q2） | 首字 2–3 min；**≈10 tok/s**；鹈鹕 20+ min；频繁爆显存；**128K 与 256K 无差别** | BV1fqxT6nEfz 评论（4 赞）【实测】 |
| **3050Ti 8G + 24G + 40G 页文件** | Strata Q2 | 20 tok/s 起步 → **稳定 12 tok/s**；升 64G 或可稳 20 | BV1Zzpn61E7V 评论（2 赞）/BV1JVJd66Esq 评论【实测】 |
| **8G + 32G**（破绽公） | Strata xxs，128K | **平均 50 t/s** | BV1Pgp26aE5U 评论（1 赞）【实测，参数不全】—**与上两行冲突** |
| 3070 笔记本 + 64G DDR4 | Strata/3.8FN | 27 tok/s | BV1LmHq6HEKb 评论（6 赞）【实测】 |
| **4060Ti 16G + i3-12100 + 64G** | Strata IQ3_XXS、engine 0.1.43.1、专家 8.2G auto、MTP 3 | **46/48/55/51 tok/s**，波动 30–90；上下文 104K（也开过 256K） | BV1Pgp26aE5U【实测】 |
| 4080S 16G + 64G | Strata IQ3_S 最大档 + MTP Q2 | 52–63 tok/s（常态 ≈60） | BV1LmHq6HEKb【实测】 |
| 3060 12G + 32G | 27B 12G 方案（NInfer+KVMem） | **44 tok/s** | BV1C1nT67T5E 评论（9 赞）【实测】 |
| 3060 12G + 48G | Strata iq3_xxs，160K 上下文 | 平均 **45**，峰值 **70** | BV1fqxT6nEfz 评论（4 赞）【实测】 |
| 5070Ti + 96G | Strata udq4_k_xl | **58 tok/s**，读取 1600 tok/s | BV1fqxT6nEfz 评论（8 赞）【实测】 |
| 3090Ti 24G + 64G DDR5 | Strata/3.8FN | **77 tok/s** | BV1LmHq6HEKb 评论（6 赞）【实测】 |
| 4080S | ninfer+kvmem+actkv | 旧版 25–29 → **35–36 tok/s**（+20~40%）；**40K prefill ≈65 s（≈615 t/s）** | BV1Y8pH6rExF 评论（4 赞，附 40 系编译版仓库）【实测】 |
| 5060 16G | NInfer+KVMem+ActKV | **50+ tok/s**（llama.cpp 同机 33） | BV1Y8pH6rExF【实测】 |
| 5090 + 96G DDR5-7200 | Strata Q3_S | 110–140 tok/s，读取 1700–2000 | BV1Pgp26aE5U 评论（2 赞）【实测】 |

### 3.2 判读
- **8G 档真实甜点区是 10–20 tok/s（Strata）/ 44 tok/s（NInfer 12G）**，我们的 97–98 tok/s 是另一个量级。原因不神秘：Bonsai 27B PTQ1 权重仅 5.94 GiB 能整体进 8G 显存；Strata 的 125B MoE 即使 Q2 也要在内存↔显存搬专家。
- "8G 能跑"在 B 站基本等于"能出字"：8+32 跑 Q2 的实测是 10 tok/s 且**频繁爆显存**；只有 12G+64G 才是作者口径里的"流畅"。
- **质量塌方是该路线致命伤**（BV1LmHq6HEKb 评论 29 赞）："8G、16G 显存能用的 Q2 版本，模型都完全压傻了……除了能跑个鹈鹕、编个极简单的小程序外，毫无用处"；另一条 8 赞："Q2 版……让它写个小说，到第二轮对话它就已经开始只抄自己上一段写的，第三轮第四轮它就不吐字了"。

### 3.3 待验冲突
BV1Pgp26aE5U 评论的「32+8G、xxs、128K、50 t/s」与另两条 8G 实测（10–12 t/s）差 4–5 倍，且未给量化档与缓存状态 → 采信门槛不足，列为待验，不作为结论。

---

## 4. 主题 B：拿 200K+ 上下文的具体做法（逐条可对照）

### 4.1 「池 ≠ 逻辑上下文」，本轮三条独立佐证
- BV1Pgp26aE5U【实测】4060Ti 16G：**KV 放主机内存**（memory 用 53.1G/64G），上下文 104K 常态、也开 256K，**速度不受上下文影响**（原话"上下文其实影响不大"）；专家显存/内存来回跳是常态，CPU ~50%。
- BV1Pgp26aE5U 评论（3 赞）【实测/经验】"**96G 内存开 kvint8 的 1M 上下文**（吃满 800K 约需 90G 内存），打开 **kv 流式**，decode 不掉速，仅 prefill 稍降，缓存命中也没问题"。
- BV1JVJd66Esq【口径】沈三殊把 **KVMem 与 streaming 结合**成 streamingkv，目的是更稳的 KV 召回 + 更少报错，并"针对 8G 卡更深度优化"；BV1h8WA6XEFQ【口径】进一步把 KV 挪内存，**6G 卡能跑，代价是内存要求变高**，提速约 10%。
→ **对应本机**：--host-kv-mib 6144 方向正确，32G 内存还有余量可往上试；--kv-capacity 不要再加（51200 崩 prefill 已证伪）。

### 4.2 Windows 上的 prefill 参数坑（Strata，但方法论通用）
BV1VPs96qEjr 完整链条（【实测】4090 48G IQ3_XXS）：
- 症状：130K 上下文 prefill **1900–2000**，而云上/Ubuntu 同卡 **4000+**。
- 排错：不是 PCIe 4.0×4 的锅（专家缓存命中率高，x4 也能跑满）。
- 根因 1：**专家缓存没被钉住** → strata_arena_pin_gb 未设时 GPU 只用 ~35G、专家缓存只装 1 万多槽（<2 万）；设 **24** 后装 **21,767 槽**（设 28 则 22,553 槽）。
- 根因 2：**ring 槽位** strata_prefer_ring **Windows 默认 96，Ubuntu 默认 384**；改 **384** 后 prefill 直接 4000+，130K/230K 都稳。
- 附带：显存吃满后功耗从 200 多瓦升到 400W 档，说明在真干活。
> 参数名为字幕音译，落地前以 Strata README 为准；**方法论可移植**：Windows 版默认值常比 Linux 保守一倍，长上下文 prefill 卡在某个整数附近时，先怀疑"槽位/钉住大小"这类默认值，而不是算力。

### 4.3 「分片注入」的等价物：靠缓存命中摊掉 200K 的代价
BV1C1nT67T5E【实测，12G+32G 27B Agent 方案】：128K 任务、256K 逻辑满长度；**200K 首次预填充约 7 分钟，完全重复 112 ms**；检索索引从显卡搬进内存**省约 224 MB 显存**（对 12G 每 MB 都值钱），等待从 5.7 ms 降到 0.5 ms；累计生成 4.3 万 token 后首次响应 0.9 s、随后三轮 0.4 s。
→ 直接含义：**200K 不是"每次都要 400 秒"，只有冷启动要**。工程上应把长文档做成"预热一次 + 复用 KV/缓存"，而不是反复全量注入。反面教材（同视频评论 18 赞）："12+32 接入 agent 起码要先等一分钟才会开始干活，写个小作文 1000 字后就开始死循环"。

### 4.4 上下文长度的"假上限"
- BV1fqxT6nEfz 评论【实测】8G+32G 跑 Strata：**"128k 和 256k 上下文基本没啥差距"**（都停在 10 tok/s 级）→ 8G 拉逻辑上下文不解决任何问题。
- BV1kYp36fEiP 评论（3 赞）【实测】395 引擎 Windows："可以直接拉 **512K 上下文，显存用到 97GB**"、decode 近 40 tok/s——那是 128G 内存 + 大显存的形态，与 8G 无关。
→ 本机 200K 的正解仍是：**逻辑上下文靠 host-KV/换页撑，物理池维持 40K 级，速度靠 prefill 分段 + 缓存复用。**

---

## 5. 主题 C：prefill 提速的全部已知手段（含辨伪）

| 手段 | 证据 | 8G 可用性 |
|------|------|-----------|
| ① 换引擎（llama.cpp → NInfer / 395） | BV1Y8pH6rExF【实测】5060 16G：50+ vs 33；BV1kYp36fEiP【实测】395 在 64K–128K 有 1500–1600 | **已用（本机 963 tok/s @37K）** |
| ② Windows 参数默认值（ring / pin） | BV1VPs96qEjr【实测】2000→4000+ | Strata 专属；**NInfer 若有"槽位/钉住"类默认值值得查** |
| ③ 算力解锁（BF16/FP16/TF32 GEMM） | BV1XnnZ6iELj【实测】prefill +20%、FP16 GEMM +81%；BV1RRx36sEtR【实测】prefill 4800（作者自纠：Ubuntu 不解锁也 5000） | **理论可用**（三元 kernel 走 m16n8k16 FP16 张量指令），B 站无 4060Ti 8G 实测 |
| ④ MTP / 投机解码 | BV1kYp36fEiP 评论【实测】接受率 **84.4% → 50 t/s**、v007-fix2 预填充常见 1.2k t/s；BV1Y8pH6rExF 评论【实测】换 dlflash2 草稿 + ngram → 45–55 提到 55–61、峰值 110 | **已用（draft4/win8）**；可试 ngram 混合 |
| ⑤ kv-dtype 更省 + 大内存 | BV1Pgp26aE5U 评论：kvint8 + 1M 上下文 + kv 流式，decode 不掉速 | 已用 rk2v4-e8；若加内存可走 kvint8 |
| ⑥ 更大的 prefill chunk / --fast-prefill-kernel | **B 站零命中** | 无先例可借 |
| ⑦ 存储位置 | BV1LmHq6HEKb 评论（5 赞）【实测】4090 装机械盘 → **11 tok/s**；换盘后正常 | 我们在 NVMe，无此坑 |

**辨伪重点**：把 prefill 归因于"算力解锁"是 B 站当前最流行的错误归因。两条独立证据都指向**配置/引擎**才是 Windows 慢的原因：BV1VPs96qEjr（改两个参数 2000→4000，且当场声明"GPU 算力没有解锁"）、BV1RRx36sEtR 作者自纠（Ubuntu 不解锁也 5000）。**解锁的真实收益区间是 +20%（prefill，FP16 路径）到 +80%（FP16 GEMM 微基准），且只对 BF16/FP16/TF32 生效。**

---

## 6. 主题 D：UEFI / 算力解锁（任务点名 BV1d6xN66ECM）

### 6.1 是什么（原理，三处一致）
- BV1d6xN66ECM【口径】"它在**驱动加载前解除张量指令的发射限制**"；**不刷 BIOS、不永久改卡、关机断电即失效**；流程 = 固件启动环境准备显卡 → 加载签名固件 + 写入解锁载荷 → 读回验证 → 把启动流程交回系统；发布页三个文件放同一目录。
- BV1XnnZ6iELj【实测口径】"不是刷 BIOS，也不是永久改卡，只是这次启动把这张卡的张量状态打开"；**补丁不通用**，要按卡的真实参数适配并编译；双系统开机选。
- BV1AMHL6zEpx【口径】只解锁 **BF16 / FP16 / TF32**：FP16≈50、**BF16 约 80→160（翻倍）**、TF32 42→82；INT8/INT4/NVFP4 不在范围内。

### 6.2 实测读数
| 卡 | 读数 | 来源 |
|----|------|------|
| 4060 笔记本（8G 档） | 四条读数均值 **29.72 → 53.54（+80%）** | BV1d6xN66ECM【实测】 |
| 联想拯救者 Y7000P 2024 / 4060 | 提升约 **1.6 倍** | BV1AMHL6zEpx 评论（2 赞）【实测】 |
| 2080Ti 22G Win10 | **FP16 GEMM +81%，prefill +20%**（FP32 不变） | BV1XnnZ6iELj（标题+字幕）【实测】 |
| 4090 48G | prefill 2000→**4800@130K**，240K 仍 4872；LP32 160→337 | BV1RRx36sEtR【实测，含自纠】 |
| 3090Ti（训练） | yolo **+5%**、imagenet 分类 +15%、dino 自监督 +18% | BV1AMHL6zEpx 评论（2 赞）【实测】 |
| 4060Ti 16G | "对 ComfyUI 提升明显"（无数字） | BV1JZnR6yEk7【口径】 |

### 6.3 风险与反对意见
- BV1d6xN66ECM 评论（88 赞）："发射速率不会等于实际性能……**跑本地大模型也只有预填充会有一点提升**，comfyUI 提升会明显一点但也不是翻倍"。
- 同视频：仅解锁不超频，**4070TiS 热点温度 80→100**（53 赞）；"增加功耗、有损坏风险，老卡/备用卡可一试，新卡/主力机慎重"（138 赞）。
- BV1AMHL6zEpx UP 置顶风险提示（6 赞）："项目刚出，不稳定，**建议稳定后再使用，防止烧显卡**"。
- BV1XnnZ6iELj 评论：SageAttention2 在 20 系（sm75）别想；22G 卡已被炒到 3000+。

### 6.4 对本机的判据（重要）
我们的 NInfer 走 **sm_89 专卡编译 + 三元 m16n8k16 张量核**，指令路径正是 **FP16 张量发射**——按 BV1AMHL6zEpx 口径（只解 BF16/FP16/TF32 GEMM），**理论上吃得到这份红利**；但 B 站 **没有任何 4060Ti 8G 实测**（评论区反复求测："4060ti8g 的解开限制做一期呗"）。且解锁需**重启进固件流程**，会打断 8091/8081 现役服务 → **只能由 lead 排时间窗决策，本会话不擅自做**。

---

## 7. 主题 E：沈三殊系最近有没有新东西（有，三条）

1. BV1JVJd66Esq（10-19，26.6k 播）UP 置顶（49 赞）原文三条：①"新引擎引入了 **streamingkv** 机制，更加稳定，再次减少报错"；②"引擎适配**千问4预览架构**了，只待模型正式发布"；③"构造了**英伟达开源大模型专武引擎**（Nemotron），但模型偏科，硬件需求高，**至少 16G 显存 + 96G 内存**"。另：包内加一键启动；提及 coder-390-27B。评论（3 赞）"LLaMA 直接 5 倍速"。
2. BV1h8WA6XEFQ（10-13，22.6k）"moe 小专武"：修 NInfer bug；**8G 适配进一步优化（显存更宽裕）**；新增 KV 走内存路径，"**6G 显卡**也能跑，代价是**内存要求变高**"；提速约 10%；另给 agent 侧显存/内存监视工具。
3. 生态侧：BV19PJR6oEVk（kvmem v0.18）把 **ninfer 与 actKV 都融进 kvmem**；BV1Y8pH6rExF 提供 **40 系编译版**（github.com/btbbtwen/ninfer-kvmem-actkv-4080s）与 50/40/30 系 release 链接（kvmem-llama.cpp v0.18.0-ninfer-rc3）；BV1ZeJC6qEgS 是机制科普（权重读取 / 计算安排 / GPU 启动时机 / 已算信息保存四段，无数字）。

**判读**：沈三殊路线没变（仍是 NInfer + KVMem 系），增量在 **streamingkv 稳定性 + 8G/6G 下探 + 架构适配（千问4）**。对我们是"更省显存/更少报错"的收益，不是新范式。

---

## 8. 主题 F：两条路线在 8G 上的对比（B 站证据面）

| 维度 | NInfer + KVMem（现役） | Strata（125B MoE） |
|------|------------------------|---------------------|
| 8G 可跑性 | **已在跑**，峰值 7,469 MiB | Q2 能起；8+32 实测 10 tok/s + 频繁爆显存（BV1fqxT6nEfz 评论） |
| 8G 实测 decode | 本机 97–98（散文 45.7）；12G 档 44（BV1C1nT67T5E 评论） | 8G 档 10–20；12G 档 45–70；16G 档 46–55 |
| prefill | 本机 963 @37K（同档最优）；4080S 615 t/s @40K（BV1Y8pH6rExF 评论） | 395 引擎 1500–1600（128G 内存机）；4090 修参数后 4000+ |
| 200K 可行性 | 逻辑上下文可超池（host-KV/换页），200K 冷 prefill ≈400 s | 依赖大内存（96G 走 kvint8 1M）；8G 无意义 |
| 质量 | 27B ternary 质量可控（本机在用） | Q2/Q3 被指"压傻了"（29 赞评论）；IQ3 易死循环（3 赞） |
| 生态热度 | 沈三殊 + melis + kris_yuu + 杭古，10 月连更 | 教程/整合包铺天盖地，多为引流与"能跑"演示 |

**判决（B 站证据面）**：**8G 拿 200K 只能走 NInfer 系**。Strata 的价值在 12–24G 显存 + 64G 以上内存的机器（45–77 tok/s），在 8G 上是"技术演示"。若未来上 16G 卡，Strata IQ3_XXS 的 46–55 tok/s 与 NInfer 栈可比，但 NInfer 仍是 50+ 且上下文机制更成熟（BV1Y8pH6rExF 同机对比 llama 只有 33）。

---

## 9. 评论区的坑（可直接避雷）

1. **死循环/胡言**：BV1Pgp26aE5U 评论（3 赞）"**贪婪解码**不但导致发散性完全丧失，还是重复死循环的根源，**温度设成 1** 之后就一次都没出现过"；另一条（3 赞）"iq3 太容易无限循环了"。
2. **显存爆**：8+32 跑 Strata"**频繁爆显存**"；BV1Zzpn61E7V 评论"占了 21G 显存，同时开 comfyui 跑完切出来**死机**"。
3. **内存 99%**：BV1Zzpn61E7V 评论（3 赞）"和我一样的配置，用默认配置直接跑速度最高才 10，**内存直接 99% 占用**，你演示占用才 20 多 G 根本就不是一回事"← 演示机与零售机不同条件。
4. **机械盘**：BV1LmHq6HEKb 评论（5 赞）4090 装机械盘只有 11 tok/s。
5. **版本回滚**：BV1VPs96qEjr 评论"试了 0.2.4，比我之前 0.1.39 慢了很多，多半是参数没设对，还是果断回滚"← **Strata 版本间参数默认值会变**。
6. **多轮长对话截断**：BV1Y8pH6rExF 评论（20 赞）报 Bug——提示词 54,190 + 输出 16,824 时"思考未结束但对话已结束"，换 WebUI 复现 → 长上下文 + 长思考在 16G 档也会撞墙。
7. **下载链路**：多人在评论里被 HF 下载卡住（"用 AI 把地址换成国内镜像"）；BV1JVJd66Esq 评论"hugging face 翻烂了都没找到模型文件"。

---

## 10. 可照做清单（P0 → P2，参数级）

- **P0-1｜不动池，动 host**：--kv-capacity 40000 保持；--host-kv-mib 从 6144 分档上调（8192 → 12288），每档记录峰值显存与 200K prefill 时间，找"显存余量 ≥400 MB 不死谷"的最大值。
- **P0-2｜客户端超时 ≥10 分钟**：200K 冷 prefill 实测 ≈7 分钟（BV1C1nT67T5E）+ 我们 963 t/s 外推 ≈400 s，两条独立证据。DSH 5 分钟无 token 会重发 → 双份 prefill → 必崩。
- **P0-3｜200K 走"预热 + 复用"**：长文档先跑一次短任务预热（对应 BV1C1nT67T5E 的 112 ms 重复命中），避免每次全量注入；--max-context 262144 不必再改。
- **P1-1｜查 NInfer 有没有"槽位/钉住"类 Windows 默认值**：Strata 的教训是 Windows ring=96 vs Ubuntu 384（BV1VPs96qEjr）。用 --help 与二进制字符串搜 ring / pin / slot / chunk / prefill（本会话只读、不启动引擎，可由 ninfer-analyst 执行）。
- **P1-2｜MTP 追接受率而非追 draft 数**：84.4% 接受率对应 50 t/s（BV1kYp36fEiP 评论）；试"更匹配的草稿模型 + ngram 混合"（BV1Y8pH6rExF 评论 45–55→55–61、峰值 110）。我们已 draft4/win8，可小步试 win 与 ngram 权重。
- **P1-3｜升级到含 streamingkv 的 NInfer 前先定回滚点**：BV1JVJd66Esq / BV1h8WA6XEFQ 明确"更稳、更省显存、报错更少"，但 BV1VPs96qEjr 评论显示**新版可能更慢**（参数默认值变化）→ 升级后必须复跑 37K prefill 963 / decode 97-98 / 散文 45.7 三个基线。
- **P2-1｜算力解锁：值得做一次受控实验，但必须先排时间窗**。判据：只对 BF16/FP16/TF32 GEMM 生效（+20% prefill / +81% FP16 GEMM，BV1XnnZ6iELj）；我们三元 kernel 走 FP16 张量发射 → **理论吃得到**；风险：热点 80→100 ℃、功耗上升、项目不稳定（作者自警"防止烧显卡"）、需重启进固件流程（打断 8091/8081）。**B 站无 4060Ti 8G 先例。**
- **P2-2｜若哪天换 16G 卡**：Strata IQ3_XXS + 64G 内存是已验证形态（46–55 tok/s），但**务必先设 arena_pin 与 ring=384**，否则 Windows 上 prefill 只有一半。
- **P2-3｜内存 ≥64G 时**直接上 kvint8 + kv 流式（1M 上下文、decode 不掉速，BV1Pgp26aE5U 评论 3 赞）；这是"花钱最少、收益最大"的 200K+ 路线。
- **P2-4｜温度别用 0**：死循环根因是贪婪解码，0.8–1.0 更稳（BV1Pgp26aE5U 评论 3 赞 + 同视频另一评论，两条独立指向同一结论）。

---

## 11. 物证清单

- 字幕逐字稿（22 份）：tmp/bili2/<BV>.json（含 segments 段数与 text 全文；空字幕 3 份 len=0）
- 评论原始 JSON（15 份）：tmp/bili2/c_<BV>.json —— BV1d6xN66ECM、BV1XnnZ6iELj、BV1Y8pH6rExF、BV1LmHq6HEKb、BV1VPs96qEjr、BV1Pgp26aE5U、BV1JVJd66Esq、BV1kYp36fEiP、BV1AMHL6zEpx、BV1EEJ26LEXq、BV1C1nT67T5E、BV1RRx36sEtR、BV1Zzpn61E7V、BV1fqxT6nEfz、BV1WjHh6EEaz（该片 0 条评论）
- 搜索候选池：tmp/bili2/search_candidates.json（263 个唯一 BV）
- 元数据：tmp/bili2/meta.json（22 条，title/author/pubdate/view/like/reply/duration/desc）
- 抓取脚本：tmp/bili2/meta.py

---

## 12. 没人做过 / 未解的问题

1. **B 站没有 4060Ti 8G 的算力解锁实测**（多条评论在求）——我们若做即首例，且恰好是对"FP16 张量核受益"假设的直接检验。
2. **B 站没有任何 --fast-prefill-kernel / --prefill-chunk 的讨论**——若这条路径有效，只能从仓库源码/README 自证，属本项目的独立探索。
3. **8G 跑 Strata 的两组实测互相冲突**（10 tok/s vs 50 t/s）——差异变量不明（量化档？上下文？缓存命中？），不可采信任何一侧。
4. **streamingkv 版本是否有 8G 回归**（新版报错少但可能更慢，BV1VPs96qEjr 评论）——需本机 A/B 跑分，属 ninfer-analyst 的活。
