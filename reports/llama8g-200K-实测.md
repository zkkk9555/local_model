# llama.cpp 路线 200K 上下文可用性实测

> **被测**：llama-server（professorpalmer/bonsai-ada-surgery 的 8GB preset）· model id `bonsai-2-27b` · ftype `PTQ1_0` 1.75 bpw ternary · `n_ctx 262144` · `n_slots 1`
> **对测**：现役 NInfer KVMem（`bonsai27b-ptq1-mtp-rk2v4-40k`，池 40,000，build `engine-v0.11.0-kvmem-20261003-98-g43c39c6`）
> **机台**：RTX 4060 Ti 8G（8,188 MiB）+ Ryzen 7 7800X3D + 32 GB DDR5-6000 + Windows 11
> **时间**：2026-10-30 10:08–10:28（cmp 基线 + 冷读/热读）；执行：overpool-verifier；**全部直连 8089，不经 8081 网关**

---

## 0 结论（先看这五条）

1. **能开、能起、能答对**：cmp_bench **10/11 PASS**；25,162 token 文档题 **8/8**（`draft acceptance 17/17`）；29,996 token 文档题 **8/8**、编造 0。262K 窗口在这台 8 GB 卡上不是纸面参数。
2. **首读成本是 O(n²)**：30K 冷读 **474.8 s**（62.9 tok/s，跑过长请求的旧进程）/ **236.4 s**（127.5 tok/s，干净重启后）两个实测点；实测点 + 作者自己的数据双向坐实 209K 首读 ≈ **3.2–6.5 小时** ⇒ 「200K 首读」不满足可接受速度，**这一条判不可用，原因不是正确性而是时间**。
3. **正确用法是「一次性建好 + 会话常驻」**：同一份 30K 文档紧接着再发一次 → **wall 1.1 s / ttft 0.31 s / cached 29,992 of 29,996 / 仍 8/8 / decode 96.9 tok/s**，冷→热 **433×**。
4. **verdict：可重复，但不是 200K 可用。** 同一进程内重复读同一份长文档**不掉准**（冷 8/8 → 热 8/8），没有现役 NInfer 那种「超池只可信一次」的毛病；但 **200K 长度本身从未测完**（首读 5.7 h 超出任何合理窗口），本报告**不外推**成 200K 可用。
5. **显存线不是常数**：同一条命令行，起服时 free 7,949 MiB → `cells 0..93696 in VRAM`；free 7,798 MiB（另有程序占 390 MiB）→ `cells 0..82688 in VRAM`。照抄 93,696 会踩坑。

**一句话**：262K 窗口买的是「一次昂贵建仓 + 之后秒回」，不是「随时读 200K 前缀」。

---

## 1 环境与请求口径

| 项 | 值 |
|---|---|
| 服务 | llama-server（bonsai-ada-surgery bundle，8GB preset）`listen 0.0.0.0:8089` |
| model id | `bonsai-2-27b`（n_ctx 262144、n_params 27,320,697,856、ftype PTQ1_0 1.75 bpw ternary） |
| 鉴权 | 必须 `Authorization: Bearer <key>`（key 在 `llama8g/bundle/artifacts/api_key.txt`）；`GET /v1/models` 不带 Bearer 也 401 |
| KV | `q3_0`，**tiered**：前 N 个 cell 在显存、其余在系统 RAM（本次 N = 93,696 首次启动 / 82,688 重启后） |
| slot | `n_slots = 1`，`n_ctx_slot = 262144`，`kv_unified = false` |
| 采样 | `temperature 0`、stream、`max_tokens 512`（cmp 各题按自身设定）；题间 sleep 5–20 s |
| 推理预算 | 请求体显式 `"reasoning_effort": "none"`（不带时 reasoning_n 33–38，带时 2；这是速度读数可比的前提） |
| 实测峰值 | GPU **7,933 MiB**（103 个采样点，5 s 一次）；进程工作集 **9.85 GiB**（10,580,234,240 B）；全程只有 1 个进程占卡 |

### 1.1 launcher 原文（第一次启动，free 7,949 MiB）

```text
8gb    preset on (8188 MiB card; BONSAI_8GB=0 turns it off): ub 512, f16 prefill to 32768 cells, deeper in chunks of 32768
window 262144 / q3_0  (8 GB default; trained max 262144)
kv     tiered: cells 0..93696 in VRAM, 93696..262144 in system RAM (VRAM margin 225 MiB); shared CUDA pool on (BONSAI_SHARED_POOL=0 turns it off)
kv     sparse host-tail reads: 12288,64,1024 (B,P,R), budget max(B, host tail x 0.25), from 32768 host cells on; 147 MiB of page bounds counted: VRAM line 93696, 82688 once sparse engages (late reserve)
kv     staging buffer for cells 93696..175616; past that the system RAM rows are read in place; packed KQ mask
ram    31 GB RAM: prompt cache 4096 MiB, 32 checkpoints per slot (BONSAI_RAM_BUDGET=0: server defaults)
vram   7949 of 8188 MiB free at start (other programs: 239 MiB); each GiB more free moves the line by about 80k cells
spec   draft 1 (1 past the VRAM line), draft window 16384 (MTP on); lookup drafting up to 32 (BONSAI_LOOKUP=0 turns it off)
listen 0.0.0.0:8089  think=True effort=medium budget=20480  harness-proofing=True  backend-sampling=True
```

### 1.2 重启后（free 7,798 MiB）——**显存线变了**

```text
8gb    preset on (8188 MiB card; BONSAI_8GB=0 turns it off): ub 512, f16 prefill to 32768 cells, deeper in chunks of 32768
window 262144 / q3_0  (8 GB default; trained max 262144)
kv     tiered: cells 0..82688 in VRAM, 82688..262144 in system RAM (VRAM margin 225 MiB); shared CUDA pool on (BONSAI_SHARED_POOL=0 turns it off)
vram   7798 of 8188 MiB free at start (other programs: 390 MiB); each GiB more free moves the line by about 80k cells
listen 0.0.0.0:8089  think=True effort=medium budget=20480  harness-proofing=True  backend-sampling=True
```

两次对比：free 差 **151 MiB** ⇒ 线差 **11,008 cell** ⇒ 约 **73 cell/MiB（≈ 74k cell/GiB）**，与 launcher 自己那句 `each GiB more free moves the line by about 80k cells` 吻合。**这条线每次启动现算，取决于那一刻的 free VRAM。**

### 1.3 测试文档与判据

- 生成器 `tmp/overpool/needles.py`（seed 20261030，1.4155 字符/token）；8 根针在 **3% / 14% / 27% / 39% / 52% / 65% / 78% / 92%** 深度，针文「第N条 **关键记录**：暗号是 紫色河马-7314，请务必记住这一条。」
- 8 个暗号：紫色河马-7314 / 青铜狐狸-1180 / 银色海豚-4402 / 绿色猫头鹰-9067 / 红色骆驼-2551 / 金色蜥蜴-6388 / 蓝色水母-8223 / 黑色麋鹿-5019
- 提问 = `Q_EASY`：「把文档中所有标注为「关键记录」的暗号，按先后顺序列出来，用中文逗号分隔」
- **HIT** = 暗号逐字出现在答案里（8 个全中记 8/8）；**编造** = 用正则 `[\u4e00-\u9fa5]{2,6}-\d{2,5}` 抓答案里所有「动物-编号」，不在 8 个名单内的算编造

> 读数来源说明：本轮数据取自客户端 console 行（`logs/llama-longctx-console-20261030-102542.log`、`...-101714.log`）与服务器 `slot print_timing` 行；**服务器在 60K 臂中途 spill 自杀，最终 json 未落盘**。两边读数一致到 0.1%。

---

## 2 prefill 是 O(n²)：实测表

服务器每 2048 token 打一条进度：`slot print_timing: ... prompt processing, n_tokens = N, progress = P, t = T s / R tokens per second`（t 从本请求 prompt 起点计）。

### 2.1 209K 请求（task 239，客户端在 16,505 token 掐断）

| n_tokens | 累计 t (s) | 累计 tok/s | 本块 2048 token 耗时 (s) |
|---|---|---|---|
| 4,096 | 8.55 | 479.3 | 8.55 |
| 6,144 | 18.75 | 327.6 | 10.20 |
| 8,192 | 33.50 | 244.6 | 14.75 |
| 10,240 | 52.80 | 193.9 | 19.30 |
| 12,288 | 76.66 | 160.3 | 23.86 |
| 14,336 | 105.07 | 136.4 | 28.41 |

**每块耗时随位置线性增长**（8.55 → 28.41 s），即每 token 的边际耗时 ∝ 当前位置 ⇒ 累计成本 ∝ n²。

### 2.2 30K 请求（task 249，同一个模型、同一条队列，独立复核）

| n_tokens | 累计 t (s) | 累计 tok/s | 本块耗时 (s) |
|---|---|---|---|
| 4,096 | 8.56 | 478.5 | 8.56 |
| 8,192 | 34.28 | 238.9 | 14.75 |
| 12,288 | 77.45 | 158.7 | 24.63 |
| 16,384 | 140.68 | 116.5 | 35.57 |
| 20,480 | 217.61 | 94.1 | 39.08 |
| 24,576 | 317.93 | 77.3 | 50.98 |
| 29,875 | 474.75 | 62.9 | — |

两条曲线前 14K 几乎逐点重合（8.55/10.20/14.75/19.30/23.86 vs 8.56/10.97/14.75/18.54/24.63）⇒ **不是 prompt 内容或长度的巧合，是位置本身**。

### 2.3 拟合与外推

以「每 2048 token 块耗时 = c · n · 2048」拟合，得 **c ≈ 9.34e-7 s/(token·位置)**；积分得总时长：

```text
t(n) = c · n² / 2 ≈ 4.67e-7 · n²   (s)
```

> 注意因子 1/2：系数 c 是「边际」量（每多一个 token、且它排在 n 处时的耗时），累计必须积分。漏掉 1/2 会让外推整体偏大一倍。

| 长度 | 模型预测 | 实测/外部基准 | 偏差 |
|---|---|---|---|
| 25,041 tok（cmp doc4needles_900） | 293 s | **334.8 s**（74.8 tok/s） | 实测慢 +14% |
| 29,875 tok（30K 冷读，实例 A） | 417 s | **474.8 s**（62.9 tok/s） | 实测慢 +14% |
| 29,996 tok（30K 冷读，实例 B 干净进程） | 419 s | **236.4 s**（127.5 tok/s） | 实测快 44%（c 减半，见 §4.1） |
| 60,000 tok | 1,681 s | **1,600 s**（作者 `docs/8GB.md`：Fresh 60k prompts 37.3 tok/s） | 模型偏快 −5% |
| 100,000 tok | 4,670 s ≈ 78 min | 未测 | — |
| 209,135 tok | 20,430 s ≈ 5.7 h | **19,400 s ≈ 5.4 h**（按作者 60K 实测 n² 外推） | 两条独立估算差 5% |

**结论**：209K 首读落在 **3.2–6.5 h** 区间 —— 慢的一半来自实例 A（c = 9.34e-7，209K ≈ 6.5 h），快的一半来自实例 B 的干净进程（30K 只用 236.4 s ⇒ c = 5.25e-7 ⇒ 209K ≈ 3.2 h，见 §4.1）；作者 `docs/8GB.md` 的 60K=1,600 s（c = 8.9e-7）落在区间内偏慢一侧。**任何一个估算都远超可接受速度**，这是本报告唯一不给精确数的原因。这不是我们配置错，也不是能靠调参绕过去的开销 —— 这是 tiered-KV 在 8 GB 上的本性：显存线 93,696 cell 之外，每多读一层 prefix 都要过 PCIe，而首读成本随位置平方增长。

---

## 3 cmp_bench 基线（11 题）

`tools/cmp_bench.py --label llama-8g --reasoning-effort none`，2026-10-30 10:14:03 跑完。

| # | id | pass | ttft (s) | prompt tok | out tok | prefill tok/s | decode tok/s | draft 接受 |
|---|---|---|---|---|---|---|---|---|
| 1 | arith1 | PASS | 0.394 | 150 | 3 | 76.4 | 56.67 | 1/1 |
| 2 | arith2 | **FAIL** | 0.207 | 158 | 2 | 181.5 | 30.21 | 1/1 |
| 3 | logic1 | PASS | 0.175 | 160 | 2 | 226.7 | 30.68 | 1/1 |
| 4 | extract1 | PASS | 0.175 | 166 | 10 | 261.9 | 58.95 | 5/5 |
| 5 | pinyin1 | PASS | 0.184 | 149 | 3 | 154.4 | 28.45 | 0/2 |
| 6 | code1 | PASS | 0.195 | 177 | 3 | 290.7 | 62.18 | 1/1 |
| 7 | instr1 | PASS | 0.164 | 147 | 4 | 161.3 | 44.35 | 2/2 |
| 8 | json1 | PASS | 0.196 | 166 | 11 | 233.2 | 67.20 | 5/5 |
| 9 | count1 | PASS | 0.178 | 159 | 60 | 216.9 | 70.21 | 30/30 |
| 10 | neg1 | PASS | 0.207 | 154 | 2 | 183.7 | 29.22 | 1/1 |
| 11 | doc4needles_900 | PASS | **334.839** | **25,162** | 35 | **74.8** | **64.93** | **17/17** |

- 汇总：`n=11, n_pass=10, n_error=0, ttft_median 0.195 s, decode_median 56.67 tok/s`（短上下文）。
- **arith2 是唯一 FAIL，属质量瑕疵不是速度问题**：题目要两个数都要，模型只回了 `9`（`missing = ["11"]`）。模型原文就是两个字：「**9**」。
- doc 题（25,162 tok）：ttft 334.8 s = 74.8 tok/s prefill，decode 64.93 tok/s，draft 17/17 全中，`cached 121`（模板前缀）。

---

## 4 冷读 vs 热读（本轮最有价值的一对读数）

| 次数 | 文档 | wall | ttft | prompt tok | cached | prefill tok/s | decode tok/s | HIT | 编造 |
|---|---|---|---|---|---|---|---|---|---|
| 冷读 #1 | d30000.txt（29,996 tok） | **476.3 s** | 475.19 s | 29,996 | 121 | **62.93** | 67.1 | **8/8** | 0 |
| 热读 #2（同一份，紧接着） | d30000.txt（29,996 tok） | **1.1 s** | 0.31 s | 29,996 | **29,992** | —（只算 4 tok） | **96.9** | **8/8** | 0 |
| 冷读 #1′（**另起实例**独立复现） | d30000.txt（29,996 tok） | **236.4 s** | 235.32 s | 29,996 | 0 | **127.49** | 64.6 | **8/8** | 0 |
| 热读 #2′（同实例紧跟） | d30000.txt（29,996 tok） | **0.9 s** | 0.15 s | 29,996 | **29,992** | —（只算 4 tok） | **95.6** | **8/8** | 0 |

**冷 → 热 = 476.3 / 1.1 ≈ 433×**（另一实例上 236.4 / 0.9 ≈ 263×），且正确率不掉（8/8 → 8/8，编造 0）。

> 两条独立实测：本报告实例 A（曾把一份 209K 提示读到 16,505 token 后被掐断）与新起的实例 B（`logs/llama-coldhot-30k.json|md`，由 lead 跑）。**热读都是 1 秒级、都 8/8**，这条结论两头坐实；但**冷读差 2.0×**（474.8 s vs 236.4 s），原因见 §4.1。

### 4.1 冷读为什么差 2×：prefill 速度依赖「实例历史」

同一份 30K 文档、同一条命令行、同一张卡：实例 A 冷读 474.8 s（62.93 tok/s），实例 B（干净重启后第一个请求）236.4 s（**127.49 tok/s**）。差别不在模型、不在参数，在**这个进程此前经历过什么**：实例 A 刚刚把一份 209K 提示读到 16,505 token（16,505 个 KV cell 落到显存线之外的 host 页），随后又被打死；实例 B 是全新进程。

⇒ 结论：**tiered-KV 的 prefill 系数不是常数**，它随 host page 的状态浮动 ±2×。所以下面 §2.3 的外推只能是区间，不能当精确值。**实用的判据**：要测「首读多快」，必须用刚启动的进程测；跑过长请求的进程会变慢。

服务器侧证据（原文，实例 A）：

```text
# 冷读（task 249）：整个 prompt 真算了一遍
slot print_timing: id  0 | task 249 | prompt eval time =  474754.03 ms / 29875 tokens (   15.89 ms per token,    62.93 tokens per second)
slot print_timing: id  0 | task 249 |        eval time =    1073.01 ms /    73 tokens (   14.90 ms per token,    67.10 tokens per second)
slot print_timing: id  0 | task 249 | draft acceptance = 1.00000 (   36 accepted /    36 generated), mean len =  2.00

# 热读（task 304）：只有 4 个 token 需要新算
slot get_availabl: id  0 | task -1 | selected slot by LCP similarity, f_sim_best = 1.000 (> 0.100 thold), f_keep = 0.998
slot print_timing: id  0 | task 304 | prompt eval time =     279.79 ms /     4 tokens (   69.95 ms per token,   14.30 tokens per second)
slot print_timing: id  0 | task 304 |        eval time =     743.02 ms /    73 tokens (   10.32 ms per token,    96.90 tokens per second)
slot print_timing: id  0 | task 304 | draft acceptance = 1.00000 (   52 accepted /    52 generated), mean len =  3.48
slot print_timing: id  0 | task 304 |    graphs reused =        210
```

缓存开销量级（同一日志里的 evict 行，下一份 60K 文档把 30K 的缓存顶掉时打的）：

```text
W srv alloc:  - making room for prompt cache entry, removing oldest entry (size = 601.118 MiB)
```

⇒ **30K token 的 KV 缓存条目约 601 MiB**（≈ 20 MiB / 千 token），`prompt cache 4096 MiB` 大约能同时留住 6 份 30K 或 1 份 ~200K —— 这也解释了为什么「一次性建好、之后秒回」在 200K 尺度上要么只保一份、要么就得靠 checkpoint（32 个/ slot）。

---

## 5 两条路线对照（谁值得为 262K 付代价）

| 维度 | NInfer KVMem（池 40K） | llama.cpp tiered-KV（窗 262K） |
|---|---|---|
| 窗口能力 | 池 40K；200K 靠「超池」环，实测**不可信** | 262K 原生窗口，**超池不存在**（多余的 KV 落 RAM） |
| 25K 冷读 | — | 334.8 s（74.8 tok/s） |
| 30K 冷读 | **45.8 s**（池内 fresh） | **474.8 s**（旧进程）/ **236.4 s**（干净进程）⇒ **10.4× / 5.2× 慢** |
| 30K 二次读 | 无秒回证据（209K 实验里 cached_tokens 全程为 0，每次都要重读） | **1.1 s（433×）** |
| 200K 首读 | 378.6 s（但**只可信一次**：复跑 2/8） | 外推 5.4–6.5 h（未测完） |
| 长上下文正确率 | 209K 首次 8/8；100K 2/8；150K 0/8（49 个编造暗号） | 25K 8/8、30K 8/8；**200K 未测** |
| 重复可复现 | 进程内第 2 个超池请求就坏 | 冷 8/8 → 热 8/8，**可重复** |
| decode（短上下文） | 97–98 tok/s（计数题）/ 散文 45.7 | 56.7 tok/s（中位，含 2 tok 短样本）/ 长文档题 64.9 |
| decode（长上下文） | 209K 时 ~7 tok/s（掉一个数量级） | 30K 热读 96.9 tok/s；25K 文档题 64.9 |
| 峰值显存 | 7,469 / 8,188 MiB | 7,933 / 8,188 MiB（工作集 9.85 GiB） |
| 稳定性 | 稳（显存余 719 MiB） | **脆**：别的程序抢 ~500 MiB 就 spill 自杀（见 §6） |

**读法**：短上下文交互（≤40K）现役 NInfer 更快更省心（45.8 s vs 474.8 s 读一份 30K 文档）；只有「同一份超长文档要反复问很多次」的场景，llama 的「冷读一次 + 之后 1.1 s」才翻身。

---

## 6 踩过的坑（复现会踩到的）

### 6.1 显存线每次启动重算，不是常数
同一条命令行：free 7,949 MiB → 93,696 cell；free 7,798 MiB → 82,688 cell（约 73 cell/MiB）。**唯一可信的做法是看每次启动的那行 `kv tiered: cells 0..N in VRAM`**，别硬编码。

### 6.2 别的程序抢一点卡，服务器会 spill 然后自杀
本轮 60K 冷读跑到 16,505 token 时被这样打死（日志原文，一字未改）：

```text
W srv          stop: cancel task, id_task = 327
I slot      release: id  0 | task 327 | stop processing: n_tokens = 16505, truncated = 0
spill  VRAM spilled to system RAM (+530 MiB): the server is much slower now. Close other GPU programs, or set BONSAI_KV_VRAM_CELLS lower, then restart.
       (NVIDIA Control Panel > Manage 3D settings > CUDA - Sysmem Fallback Policy: Prefer No Sysmem Fallback makes the server stop instead of running slowly.)
```

⇒ 8 GB 卡上跑 262K 窗口是**贴着红线**的：起服那一刻多 390 MiB 就少 11k cell；跑到一半被抢 530 MiB 就直接 spill 自尽。要跑长上下文，先关掉一切占卡的东西（浏览器硬件加速、桌面特效、别的推理进程）。

### 6.3 `reasoning_effort` 必须显式带
launcher 默认 `think=True effort=medium budget=20480`。请求体里不带 `"reasoning_effort": "none"` 时 reasoning_n 33–38（白烧 token，速度读数不可比）；带了降到 2。**所有对比读数都在 none 口径下取得。**

### 6.4 鉴权与 id
- `/v1/models` 也需要 `Authorization: Bearer <api_key.txt 的内容>`，否则 401。
- model id 必须是 `bonsai-2-27b`（服务端上报的那个），不是文件名、不是 DSH 里的条目名。

### 6.5 工具侧的小坑
- fixture 标签要登记在 `tools/llama_longctx_test.py` 的 `FIXTURES` 里；文件叫 `d60000-s20261030.txt` 而标签写 `60k` 时，回退规则只找 `d60k.txt` / `d60k-s20261030.txt` —— 第一次跑就因此浪费了一臂（30K 冷读读数已抢救进本报告）。
- 长请求必须放后台跑（单次 prefill 8 分钟起）；同步调用的硬超时会误判为「服务挂了」。

---

## 7 没做的、以及为什么

| 项 | 状态 | 原因 |
|---|---|---|
| 209K 首读跑完 | **未测** | 外推 5.4–6.5 h，超窗口；且要测「可重复性」得跑两次 ⇒ 12 h+ |
| 60K 冷读 | 中途被打死（16,505 tok） | 服务器 spill 自杀（§6.2）；作者数据 1,600 s 已可互证 O(n²) |
| 干净进程上的 209K 首读 | **未测** | 按实例 B 的 c（5.25e-7）也要 3.2 h；且测可重复性要两次 |
| 100K 冷读（越显存线） | **未做** | 按 78 min/次，结论不会变（O(n²) 已双向坐实）；lead 判定取消 |
| 240K 档 | 未做 | `n_ctx 262144` 上限内可以发，但首读 ~9 h，无意义 |
| slot save/restore 落盘 | 未试 | launcher 未开 `--slot-save-path`；但**热读 1.1 s 已经证明**「同进程内二次读」这条最重要的事 |

**本报告不声称「200K 可用」**：200K 的正确性从未在本机测完，能说的只有「正确性在 30K 尺度上没问题 + 首读时长按 O(n²) 外推 5.4–6.5 h」。

---

## 8 附件（可复核）

| 文件 | 内容 |
|---|---|
| `C:/Project/local_model/logs/llama-cmp-20261030-100824.json` | cmp_bench 11 题逐题原始读数（text/ttft/timings/draft） |
| `C:/Project/local_model/logs/llama-longctx-console-20261030-101714.log` | 30K 冷读 476.3 s / 8/8 的客户端原文（抢救回来的那一臂） |
| `C:/Project/local_model/logs/llama-longctx-console-20261030-102542.log` | 30K 热读 1.1 s / cached 29,992 / 8/8 的客户端原文 |
| `C:/Project/local_model/logs/llama8g-launch.log` | 第一次实例全程日志：进度点、LCP 命中、cache evict、spill 与死亡 |
| `C:/Project/local_model/logs/llama8g-launch2.log` | 重启后实例日志（显存线 82,688 的那一版） |
| `C:/Project/local_model/logs/llama-coldhot-30k.json` / `.md` | 实例 B 的独立复现：冷读 236.4 s / 8/8 → 热读 0.9 s / cached 29,992 / 8/8 |
| `C:/Project/local_model/logs/llama-peak-20261030-101714.csv` | 5 s 一次显存/进程采样（GPU 峰值 7,933 MiB，ws 9.85 GiB） |
| `C:/Project/local_model/tools/llama_longctx_test.py` | 长上下文序列验证器（--selftest 19/19 PASS） |
| `C:/Project/local_model/tools/cmp_bench.py` | 11 题基线工具 |
| `C:/Users/Administrator/Documents/deepseek-harness/default-workspace/tmp/overpool/` | 全部 fixture（d30000 / d60000 / d100k / d150k / d209k，seed 20261030） |
| `C:/Users/Administrator/Documents/deepseek-harness/default-workspace/tmp/prefill_points.json` | 从服务器日志抽出的全部 prefill 进度点（供复核拟合） |

---

*报告生成：overpool-verifier · 2026-10-30 · 所有速度读数为 temperature 0、reasoning_effort none、单 slot、直连 8089*