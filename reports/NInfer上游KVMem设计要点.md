# NInfer 上游 KVMem 设计要点 —— 200K 到底该怎么配

侦察时间 2026-10-30。工作目录 `C:/Users/Administrator/Documents/deepseek-harness/default-workspace`，上游浅库在 `work/up/` 与 `work/kvmem/`。
全程未启动/停止任何引擎或服务，未触碰 `C:/Project/local_model` 下的配置脚本。

---

## 0. 结论先行

**结论一（构型）**：官方唯一成文的「设备池远小于逻辑上下文」配方是 **200K / 池 53,248 token（26%）/ 主机 12,288 MiB / 检索开**：

| 参数 | 值 | 说明 |
|---|---|---|
| Context (--max-context`) | **204800** | 200K |
| B (--kvmem-budget`) | **36864** | 设备上的「检索预算」= 576 页 × 64 token |
| R (--kvmem-gen-reserve`) | **16384** | 生成预留 = 256 页 |
| 设备池合计 B+R | **53248** | 204800 的 **26.0%**，3200 页里只用 832 页 |
| H (--kvmem-host-mib`) | **12288 MiB** | 主机 tier；启用后引擎默认 16384 |
| sink / recent | **12288 / 1024** | 12K sink + 1K recent，共 16 页 recent；两者都算在 B 里 |
| Prefill / 输出上限 / 思考预算 | 256 / 16384 / 8192 | |
| KV 精度 / 并行 | INT8 / **单路** | 多路要乘路数 |
| MTP / ngram | 自适应 ≤4 / 31·min12 | |

出处：[kvmem/kvmem docs/multi-backend-differences.md:157](https://github.com/kvmem/kvmem/blob/master/docs/multi-backend-differences.md)（"默认 ninfer 快捷脚本…Context=204800、B=36864、R=16384、Host=12288MiB…sink=12288、recent=1024 tokens（12K/1K，16页 recent）、单路、INT8、自适应MTP上限4、ngram31"）、[docs/graph-recall.md:4-7](https://github.com/kvmem/kvmem/blob/master/docs/graph-recall.md)（"The resource recipe in `start-ninfer.ps1` still follows 0.18: context 204800, B=36864, R=16384, host KV=12288 MiB, prefill=256, sink/recent=12288/1024, adaptive MTP4 and ngram31/minimum12"）。

**`NINFER_KV_RETRIEVE` 必须开**——同一提示同一池，关掉答不出、打开答对（A/B 见 §2.4），代价是几乎没有速度损失。

**结论二（分片）**：**没有任何文档级证据支持「超池请求必须分片」**。三个 NInfer 仓里 646 处「分片 / shard」全部指 artifact 文件分片、专家分片、layer pipeline 切分，与请求切分无关。超池的正统处置是**重选（reselect）+ 检索 + 主机区兜底**，不是切请求。真正会硬性拒你的是别的东西：stock dense 引擎在 `--kv-capacity < --max-context` 时**直接抛异常**（§3.2）。

---

## 1. 先纠正三个前提（否则会在错的仓库里找答案）

### 1.1 "上游 NInfer" 里有 KVMem 吗？—— 没有

| 仓库 | 版本 | 角色 | 有 KVMem/ring 吗 |
|---|---|---|---|
| [Neroued/ninfer](https://github.com/Neroued/ninfer) | `1882c6adbc98043fcf89f3589aa5addb3742777a` | **真上游** dense（sm_120a / 5090 线） | **无**。全库 `NINFER_KV_RING` 零命中；容量文档只有 `--kv-capacity auto`（`docs/performance/qwen3.6-27b.md:201`、`qwen3.6-35b-a3b.md:28/231`、`qwen3.8-27b.md:39/276-289`） |
| [iamwavecut/ninfer-3090](https://github.com/iamwavecut/ninfer-3090) | `d0da39796697b79fd08fc570e1781d75943dddb1` | **生产 3090 线**（franken/v0.11 家族） | **无**，且**硬拒**小池（§3.2） |
| [tancau/ninfer-kvmem-ring](https://github.com/tancau/ninfer-kvmem-ring) | `d6aa55a9a83fc31d984be5cd5dfefbcaa852e0ee` | **第三方移植**（KVMem 思想搬进 NInfer） | **有**，唯一有 `NINFER_KV_RING/KV_WINDOW/KV_RETRIEVE/HOST_PAGEABLE` 的仓 |
| [kvmem/kvmem](https://github.com/kvmem/kvmem) | master（未取到 SHA，API 限流） | **官方 KVMem**，把 NInfer 列为受支持后端 | 官方推荐构型的**唯一权威出处** |

官方自述（README）："keeps complete native KV history in system RAM… **The GPU holds the history needed for the current request and space for generation**"，并致谢 `Neroued/ninfer`、`iamwavecut/ninfer-all`；论文 arXiv 2609.04852。

> 换言之：**「上游 NInfer 官方推荐 200K 构型」这句话本身要先改成「上游 KVMem 给 NInfer 后端推荐的 200K 构型」**。NInfer 本体没有这个概念。

### 1.2 "evidence 预算" / "n_blocks" 不是上游术语

- `n_blocks`：三个仓合计**只有 2 处**（tancau `TODO.md`），不是可调参数。
- `evidence`：111 处，几乎全是 `AGENTS.md` 里"验证证据"的意思；`docs/graph-recall.md:200-207` 的 "negative evidence" 是打分算法术语。**都不是容量预算**。
- 正名对应关系：**evidence 预算 → `B` / `--kvmem-budget`（检索预算，同时是 sink/recent 的容器）**；**n_blocks → 页数 = tokens / 64**（ninfer 页面粒度固定 64 token，"未开放参数"，见 [docs/multi-backend-differences.md:20-26](https://github.com/kvmem/kvmem/blob/master/docs/multi-backend-differences.md)）。

### 1.3 200K 配方是 0.18 遗产

`docs/graph-recall.md:4` 明说配方"still follows 0.18"，且"Published 0.18 binaries retain their old LRFU/max ranking. **Rebuild both backend patches when using this source.**" ⇒ 抄数值可以，抄二进制行为不行。

---

## 2. 答案一：官方「设备池 << 逻辑上下文」构型

### 2.1 硬不变量（谁必须 ≤ 谁）

出处 [docs/native-cli-configuration-spec.md:18](https://github.com/kvmem/kvmem/blob/master/docs/native-cli-configuration-spec.md)：

> 取整后的 **Sink+Recent 必须不超过 Budget**，**Budget+Reserve 必须不超过 Context**。

配套约束（同文件 :279-280`、:380，以及 multi-backend-differences.md:20-26/34-44）：

- `B ≥ 128` 且 64 对齐；`R ≥ 64`、64 对齐、默认 1024。
- `--kvmem-host-mib` 启用后**默认 16384 MiB**，"为原生 KV payload 硬预算"——**明确不含整进程 RAM**，也不等于 `--host-cache-mib`（那是原生 prefix cache 的预算，:430-433）。
- **每条活动请求按 B+R 占一份设备页池，C 路并发就是 C×(B+R)**。所以 200K + 单路 = 832 页；两路 = 1664 页。
- 图片区域必须装进 B（多模态时 B 要留出视觉 token）。

⇒ 200K 的「官方形状」是 **池 = 26% 上下文**，而且这 26% 里 12K 是 sink、1K 是 recent，真正给"中段历史"的检索预算只有 `B - sink - recent = 36864 - 12288 - 1024 = 23552` token ≈ 368 页。

### 2.2 host tier 该多大 —— 两套算法，别混用

**A. 官方（kvmem/kvmem）口径：H 是"多历史"的钱，不是单请求的钱**

`docs/multi-backend.md:123` 给了每 token 的原生 KV 字节数：**INT8 528 B/token**、NVFP4 288 B/token、RK8V4 408 B、K8V4 402。
于是 204800 token × 528 B ≈ **103 MiB / 一份完整 200K 上下文**。
H=12288 MiB ≈ **119 份**满 200K 历史。
⇒ **单请求 200K 只要一百多 MiB 主机区；12 GiB 是为了多会话 / 长闲置历史 / 前缀复用买的**。（我按官方 B/token 做的算术，非文档原句。）

**B. 移植分支口径：checkpoint 副本让系数变成 2×～3×**

tancau 的 [bonsai-app/KVMEM-PORT-PLAN.md:533-552](https://github.com/tancau/ninfer-kvmem-ring/blob/d6aa55a9a83fc31d984be5cd5dfefbcaa852e0ee/bonsai-app/KVMEM-PORT-PLAN.md)（nvfp4，实测系数 **18432 B/token**）：

> 主机区需求 ≈ **(3 × 上下文 − 驻留窗口) × 18432 B**（原文：历史 + 已发布 checkpoint 的副本 + 新请求自己的副本）

按这条公式：
- 单请求 200K、窗口 96K：(2×204800 − 96000) × 18432 B ≈ 5.4 GiB
- 单请求 256K、窗口 96K：(2×262144 − 96000) × 18432 B ≈ 7.4 GiB
- 多轮 200K：(3×204800 − 96000) × 18432 B ≈ 8.9 GiB——8 GiB 主机区就**卡在门口**。
- 实测对照：主机区只有 2.0 GiB 时，"多轮上限约 **36K token**，60K 以上只能单请求"；实测 3×60K−27K≈153K tok≈2.8 GB > 2.1 GB 主机区 ⇒ **第二个请求被拒**。

（括号内换算是我按该系数算的；原文只给了 60K/2.0 GiB 那一组实测。）

**C. Windows 现实：pinned 内存是硬墙**

[tancau RELEASE_NOTES_0.10.0:181](https://github.com/tancau/ninfer-kvmem-ring/blob/d6aa55a9a83fc31d984be5cd5dfefbcaa852e0ee/docs/RELEASE_NOTES_0.10.0.md)：

> Windows 把 pinned host KV 限制在**几百 MiB**，这块卡上 device capacity 已经在决定决策。

所以 12 GiB 的 H 在 Windows 上必须走 `NINFER_HOST_PAGEABLE=1`（把主机 KV 区改成可分页 malloc，移植分支用它开了 8 GiB；`KVMEM-PORT-PLAN.md:515` 另提到 `NINFER_KV_HOST_OVERCOMMIT_MIB` 可放大）。**pinned 路线在 Windows 上撑不到 12 GiB。**

### 2.3 上游 dense 自己的 host tier 立场（顺带一条一手引文）

[iamwavecut/ninfer-3090 docs/maintainer/hybrid-prefix-cache-spec.md:219-220](https://github.com/iamwavecut/ninfer-3090/blob/d0da39796697b79fd08fc570e1781d75943dddb1/docs/maintainer/hybrid-prefix-cache-spec.md)：

> A host-resident prefix is about **300× cheaper to restore than to recompute**. **The host tier carries most of the reuse value. The device tier is a latency optimisation.**

同文件 §3.3 的预算表给了总线实测：PCIe5 x8 **24–27 GB/s**；H2D 传 100k token 的 INT8 KV（3.38 GB）≈ **68 ms**；27B prefill 约 4.2k tok/s（即 100k token 重算 ≈ 24 s）。⇒ **回搬比重算便宜两个数量级**，这就是"主机区该大方、设备池可以小"的物理依据。

### 2.4 要不要开 `NINFER_KV_RETRIEVE` —— 要，超池场景必须开

**语义**（[KVMEM-PORT-PLAN.md:449-475](https://github.com/tancau/ninfer-kvmem-ring/blob/d6aa55a9a83fc31d984be5cd5dfefbcaa852e0ee/bonsai-app/KVMEM-PORT-PLAN.md)）：给即将降级的页按 IDF 词法重叠打分（KVMem 原版是 mean-K 打分），**检索预算 = `min(NINFER_KV_RETRIEVE, 池/4)`**，命中的页 H2D 拉回并纳入注意力掩码。原文关键句：

> 掩码始终由「**实际驻留集合**」推导，而不是「意图」——降级或恢复失败**只会多隐藏，绝不会暴露陈旧设备槽位**。

**A/B（决定性）**：同一条 60K 提示、同一个 32K 池：

| 构型 | 藏针 `BLUEBIRD-42` |
|---|---|
| dense，上下文 131K（无环） | ✅ 答对 |
| 环模式 32K 池，**检索关** | ❌ "文本里没有这个码" |
| 环模式 32K 池，**检索开** | ✅ 答对 |

出处同上 :482-491。

**速度代价可忽略**（同处 :525-531，40K 深度）：dense 365 prefill / 85 decode t/s；环 + 检索关 307/49.6；环 + 检索开 ~240–310/~47–53。瓶颈在 kernel 的掩码求值，不在检索本身。

**已知缺陷（官方自认）**：[BENCH-RESULTS.md:843](https://github.com/tancau/ninfer-kvmem-ring/blob/d6aa55a9a83fc31d984be5cd5dfefbcaa852e0ee/bonsai-app/BENCH-RESULTS.md) 待办 B3：

> `NINFER_KV_RETRIEVE=12288` 是死的；简单问题和 200K 取证不该同预算。

⇒ **检索预算目前是手调常量，没有自适应**；低预算小池场景要自己压到 4096。

**不设环境变量时几乎等于关**：`src/models/qwen3_5/program/storage/context.cpp:1524-1528` 的 `proto_kv_retrieve_pages()` 读 `proto_env_pages("NINFER_KV_RETRIEVE")`（tokens/64 = 页），未设置时回落 **4 页 = 256 token**（同文件 :1516）。

### 2.5 移植分支已跑通的 200K/256K 生产构型（可对照）

- 启动脚本（`bonsai-app/Start-Bonsai-Ninfer-256K.bat:27-42`、`README.zh-CN.md:33-36`）：`CTX=262144 POOL=96000`，`NINFER_KV_WINDOW=96000 NINFER_KV_RETRIEVE=12288 NINFER_HOST_PAGEABLE=1`，nvfp4 KV，host KV **8 GiB pageable**，VRAM ~**10.2 / 12 GB**。
- 实测（[BENCH-RESULTS.md:274-299](https://github.com/tancau/ninfer-kvmem-ring/blob/d6aa55a9a83fc31d984be5cd5dfefbcaa852e0ee/bonsai-app/BENCH-RESULTS.md)）：**129,376 token（1.35× 池）** 藏针 `STARFRUIT-88` **PASS**；prefill 147.8/150.6 t/s，decode **18.3/19.5 t/s**，MTP 接受率 35.9/38.9%。池内 65,513 token：252.1 t/s / decode 37.2。池内零开销（4K 658.6 vs dense 662）。
- 256K 缩放（`KVMEM-PORT-PLAN.md:662`）：池 96K(1500 页) / 上下文 262144(4096 页) / 窗口 96K / 检索 12K / 主机 8 GiB，**152K 提示完成并答出针**，显存 10.2 GB。`README-RING.md` 另记 96K 池服务 152K 序列（1.6×）。

---

## 3. 答案二：超池请求「必须分片」吗？—— 无证据

### 3.1 三仓全文检索结论

- `分片` / `shard` 命中 **646 处**，逐条归类：artifact 容器文件分片（[docs/maintainer/artifact-container.md:94](https://github.com/iamwavecut/ninfer-3090/blob/d0da39796697b79fd08fc570e1781d75943dddb1/docs/maintainer/artifact-container.md) "默认 32 GB 分片上限"）、专家分片、layer pipeline 切层。**没有一处**讲"请求要切"。
- 上游没有任何 prompt-chunking 之外的请求切分机制；prompt chunk 是固定的 2048 token 前向分块，与上下文是否超池无关。

### 3.2 stock dense 的立场是"拒绝小池"，不是分片

[iamwavecut/ninfer-3090 src/serve/serve_options.cpp:1797-1801](https://github.com/iamwavecut/ninfer-3090/blob/d0da39796697b79fd08fc570e1781d75943dddb1/src/serve/serve_options.cpp)：

```cpp
if (options.max_context == 0) { throw std::invalid_argument("--max-context must be positive"); }
if (options.kv_capacity.mode == KvCapacityMode::Explicit &&
    options.kv_capacity.explicit_tokens < options.max_context) {
    throw std::invalid_argument("--kv-capacity must be at least --max-context");
}
```

⇒ **不装 KVMem = 池必须 ≥ 上下文**。200K 在 stock 引擎上要么显存够 3200 页，要么请求进不来。这与"分片"无关，是硬约束（也解释了为什么会出现"超池静默错误"那类问题：中间路线被走了）。

### 3.3 KVMem 的立场是"超池就重选"，不是切请求

[docs/multi-backend-differences.md:34-59](https://github.com/kvmem/kvmem/blob/master/docs/multi-backend-differences.md)：

> 生成时追加空间不足 → 归档到 Host 并以 **DecodePressure 对驻留工作集重选最多 B**，继续追加。
> 未选中的 KV 仍可保存在 Host，但**暂时不参与当前注意力**。

实测（同文件 :59）：RTX 5050 Laptop，B=256、R=128、NVFP4，请求生成 512 / 1024 token，途中各发生 **2 / 6 次重选**，Main 页池始终 384 token。⇒ **池小于生成长度也能跑，靠重选。**

### 3.4 真正的硬边界（比"分片"重要得多）

| 边界 | 证据 |
|---|---|
| **H 主机区容量**（多轮 ~3× 上下文系数） | KVMEM-PORT-PLAN.md:533-552，2.0 GiB 只能多轮到 ~36K |
| **Windows pinned 内存上限**（几百 MiB） | RELEASE_NOTES_0.10.0:181 ⇒ 必须 `NINFER_HOST_PAGEABLE=1` |
| **`--no-prefix-reuse` 与 ring 不兼容** | KVMEM-PORT-PLAN.md:557-558：会把地址空间按 `kv_capacity` 建 → `logical_capacity` 变 512 → 退化成 dense 映射并溢出 |
| **池与工作区抢同一块显存** | [ring-262K-ship-report.md:52-57](https://github.com/tancau/ninfer-kvmem-ring/blob/d6aa55a9a83fc31d984be5cd5dfefbcaa852e0ee/docs/maintainer/ring-262K-ship-report.md)：池 147456→172032 触顶→定 96K；"池和工作区抢同一块 3.69 GiB（每 chunk token 198 KB 工作区），`chunk=8192` 启动即被拒" |
| **池小 = 复用深度被砍，延迟变差** | [ring-device-footprint.md:88-98](https://github.com/tancau/ninfer-kvmem-ring/blob/d6aa55a9a83fc31d984be5cd5dfefbcaa852e0ee/docs/maintainer/ring-device-footprint.md)："With a 96K pool (1500 pages) the 98304 frontier (1536 pages) is declined, so the deepest banked anchor is 65536: a 127K session reuses ~51% and still spends **~9.5 minutes recomputing the tail**. With a 144K pool the endpoint itself fits… **Size the pool to the working session, not to the smallest value that avoids a crash.**" |

最后这条是整份报告最贵的一句：**池子省到极限不会崩，只会让你每轮重算尾巴（127K 会话 ≈ 9.5 分钟）。**

---

## 4. 对 200K 的落地建议（按你手里是哪个引擎分三档）

**档 A — stock dense（8091 / 8081 现状，未打 KVMem patch）**
`--kv-capacity` 只能 `auto` 或 ≥ `--max-context`。200K ⇒ 池 3200 页全驻留，显存按 528 B/token × 204800 × headroom 算。**不要**指望"小池 + 超池请求"能跑：引擎层直接抛异常，绕过它的路径就是之前那份超池 bug 报告的来源。此档没有"分片"选项。

**档 B — 装了 KVMem 的 ninfer worker**
原样抄官方 200K 配方：`--max-context 204800 --kvmem-budget 36864 --kvmem-gen-reserve 16384 --kvmem-host-mib 12288`，sink 12288 / recent 1024，单路 INT8，`NINFER_KV_RETRIEVE` 至少 4096（要答 200K 取证类问题给 12288）。多路要把 `--kvmem-host-mib` 按路数放大（H 是全局共享硬预算，不是每路）。

**档 C — tancau ring 分支（唯一能"200K 上下文 + 96K 池"实跑过的）**
`--max-context 262144 --kv-capacity 96000` + `NINFER_KV_RING=1 NINFER_KV_WINDOW=96000 NINFER_KV_RETRIEVE=12288 NINFER_HOST_PAGEABLE=1`，host pageable 8 GiB，实测 VRAM 10.2/12 GB、129K 藏针 PASS、decode 18–19 t/s。**代价**：多轮 / 多会话受主机区（3× 系数）限制；`--no-prefix-reuse` 不能同用；池压到 96K 时 127K 会话要重算尾巴。

---

## 5. 诚实清单：未核源与不确定项

1. **kvmem/kvmem 的 master SHA 没取到**（api.github.com 对本机出口 IP 限流，`repos/kvmem/kvmem` 与 `commits/master` 均 429）。引用按 `blob/master/...` 给，行号已用同日抓取的原文核对；若上游改动需重核。
2. **129,376 tok PASS / 18–19 t/s / 10.2 GB 这组数字来自第三方移植仓自己的 BENCH-RESULTS**，不是官方复现，也不是我实测（本轮禁止动引擎）。官方 KVMem 的 200K 配方只给了参数，没有给 200K 端到端性能表。
3. **主机区公式的系数 18432 B/token 是 nvfp4 + 该模型头的实测值**，换模型 / 换精度必须重算（官方对应值是 288 B/token nvfp4、528 B/token int8，两者口径不同：前者带 checkpoint 副本与 3× 历史，后者是纯 payload）。
4. **"Windows pinned 只能几百 MiB"没有具体数字**，是移植仓作者的结论性表述【未核源：无实测量】。
5. **200K 配方本身是 0.18 遗产**（graph-recall.md:4），官方同时要求"发布版二进制保留旧 LRFU/max 排序，用源码必须重建两个后端 patch"。
6. 上游 dense 的 `--kv-capacity auto` 到底按什么公式换算成页数，文档只写"auto"，没给公式；我未读实现，属**未核**。
7. `NINFER_KV_RETRIEVE` 无自适应的结论来自 BENCH 待办 B3 的一句自述，不是设计文档的正式声明。

---

## 6. 引用清单（URL 均已 curl 验状态码，走代理）

**200/301 可解析**：
- https://github.com/kvmem/kvmem/blob/master/docs/multi-backend-differences.md —— 200K 配方（:157）、262K 默认（:154）、页面粒度与 B/R 语义（:20-26、:34-44）、重选实测（:48-59）
- https://github.com/kvmem/kvmem/blob/master/docs/graph-recall.md —— 配方沿革（:4-7）、检索打分（:200-207）
- https://github.com/kvmem/kvmem/blob/master/docs/native-cli-configuration-spec.md —— 硬不变量（:18）、H 定义（:64、:279-280、:380）、原生 cache 预算不混用（:430-433）
- https://github.com/tancau/ninfer-kvmem-ring/blob/d6aa55a9a83fc31d984be5cd5dfefbcaa852e0ee/README-RING.md —— 环境变量与 `--kv-capacity < --max-context` 的门控
- https://github.com/tancau/ninfer-kvmem-ring/blob/d6aa55a9a83fc31d984be5cd5dfefbcaa852e0ee/bonsai-app/KVMEM-PORT-PLAN.md —— 检索语义（:449-475）、A/B（:482-491）、速度（:525-531）、主机区公式（:533-552）、`--no-prefix-reuse` 不兼容（:557-558）、256K（:662）
- https://github.com/tancau/ninfer-kvmem-ring/blob/d6aa55a9a83fc31d984be5cd5dfefbcaa852e0ee/bonsai-app/BENCH-RESULTS.md —— 129K PASS（:274-299）、检索预算待办（:843）
- https://github.com/Neroued/ninfer —— 真上游，无 KVMem
- （301 = GitHub 规范跳转，仍有效）https://github.com/iamwavecut/ninfer-3090/blob/d0da39796697b79fd08fc570e1781d75943dddb1/src/serve/serve_options.cpp —— 硬拒小池（:1797-1801）
- （301）https://github.com/iamwavecut/ninfer-3090/blob/d0da39796697b79fd08fc570e1781d75943dddb1/docs/maintainer/hybrid-prefix-cache-spec.md —— host tier 立场（:219-220）、总线与回搬成本（§3.3）

**本地副本（浅库，供复现 grep）**：`work/up/Neroued_ninfer`、`work/up/iamwavecut_ninfer-3090`、`work/up/tancau_ninfer-kvmem-ring`、`work/kvmem`（后者为 docs 抓取后的目录，文件名为 `docs_<name>.md`，其中 `.2` 后缀为二次抓取副本）。
