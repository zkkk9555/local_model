# NInfer host-kv 语义与超池可复问性

侦察日期：2026-10-30 ｜ 执行：情报侦察子代理 ｜ 范围：本地只读仓 + GitHub 上游一手材料
硬约束遵守情况：未启动/未停止任何引擎或服务（8091/8081 未触碰）、未修改 C:/Project/local_model 下任何配置脚本、所有结论附 URL 或本地 file:line。

---

## 0. 结论速览

| 问题 | 结论 | 置信度 |
|---|---|---|
| ① --host-kv-mib 是钉住还是上限 | **是真实 pinned 主机内存容量**（走 cudaMallocHost），但在 Windows/WDDM 上会被运行时**钳到 (free VRAM − 1 GiB)/2**，所以「设 8192 就得到 8 GiB」在 Windows 不成立 | 高（文档 + 源码 + 实测表） |
| ② 有「KV 全量放主机、显存只留固定窗口」的配置吗 | **概念上不成立**：attention 每一步都要在 device 上读 K/V，主机只能是溢出层。「小 device 池 + 大 host 层」确实存在，但只在 **3090/ring 衍生线**；上游主干（Neroued）**根本没有 host 层** | 高 |
| ③ 上游有「超池 + 反复问仍正确」吗 | **只有单发超池**（1.35×、4×），**没有一条公开记录是「超池 + 同一会话反复问」通过**；作者自己声明对全历史不等价、有损 | 高 |
| ④ 「超池只可信一次」上游知道吗 | **知道，而且被写成了 ring 线的硬约束**：主机区需求 ≈ (3×上下文 − 驻留窗口) × 18432 B，超了**第二个请求直接被拒**；真正的修法**未做**，**没有安全开关** | 高 |

**一句话判定**：在 Windows + 8 GB 卡上，超池「可复问」**不能靠调大 --host-kv-mib 达成**——这条线上的 host-kv 是「**溢出层 + 受显存反噬的钳制项**」，不是可独立放大的内存池。可复问需要三个条件同时成立（见 §6），缺一个就退化成「只可信一次」甚至 429。

---

## 1. 证据面

| 来源 | 性质 | 取用方式 |
|---|---|---|
| repos/ninfer-fusion-kvmem（本地只读，remote = https://github.com/1314521gjy/ninfer-fusion-kvmem ，HEAD 9a5a920） | 我方已打补丁的 NInfer-all 树（VERSION 0.11.0-rtx3090） | 读源码/文档，行号标注 |
| https://github.com/tancau/ninfer-kvmem-ring | 环 + 检索线的独立移植仓（16★），带完整基准与移植日志 | raw master 直读 |
| https://github.com/Neroued/ninfer （issue #362 / PR #345） | 上游提案与审查记录（**未合并**） | 页面快照 + PR diff |
| https://github.com/Neroued/ninfer （master） | 上游主干 | raw 直读 + grep |

环境注记：GitHub HTML/raw/API 均可通（HTTP_PROXY=http://127.0.0.1:7897）；raw 的 main 分支 404、master 可用；api.github.com core 配额已耗尽（403），search 仍有额度。

---

## 2. ① --host-kv-mib 的语义：真钉住，但 Windows 上被钳制

### 2.1 声明语义

src-tree/fusion-engine-src/docs/serving.md:1251：

> | --host-kv-mib N | shared pinned Host Main/Backend KV byte capacity in MiB | 8192 |

docs/serving.md:34-35 补充：--host-state-slots 与 --host-kv-mib 是**两份独立分配**，二者之和才是进程钉住的 Host RAM。

代码侧：patches/changed-files/src/serve/serve_options.cpp:860-868 把 --host-kv-mib 直接写成 context_cache.host_kv_capacity_bytes = mib << 20（:1072 置 0，:1093-1095 与 --host-cache-mib/--host-state-slots 互斥）。分配路径真实存在 cudaMallocHost：src-tree/fusion-engine-src/src/core/arena.cu:657,673，错误串「cudaMallocHost failed to pin 」。

⇒ **不是「上限/水位线」，是真的把主机内存钉住（page-locked）**。这一点对我方「大 host-kv 换容量」的直觉是有利的——Linux 上它真能钉住 8 GiB（docs/release-archive-linux.md:100-101）。

### 2.2 但 Windows 把这张牌废掉了

src-tree/fusion-engine-src/docs/maintainer/launcher-profiles.md:412-416（§「Pinned host KV on Windows」）原文：

> --host-kv-mib 8192 is not 8 GiB on Windows. WDDM maps a pinned host allocation into the GPU's address space and charges it against the card, so **the runtime clamps the request to (free VRAM − 1 GiB) / 2 before the first cudaMallocHost** — it cannot ask and back off, because one failure poisons every later attempt in the process.

同处给出的实测表：

     profile                              free after startup   pinned host KV
     qwen38-27b tuned (MTP profile)              1.59 GiB           302 MiB
     qwen36-35b-a3b tuned                     184-344 MiB           0 -- none at all

**这是本次侦察最有杀伤力的一条事实**：host KV 的可用额度与「剩余显存」成**正比**。也就是说——

- 显存越紧张（正是我们想开大 host 层的时候），host KV 被钳得越小；
- 在 8 GB 卡跑 27B/35B 时，实际拿到的是 **302 MiB 或 0**，不是 16384 MiB。

按 18432 B/token 折算：302 MiB ≈ **17.2K token** 的溢出容量；0 就是**一点溢出都放不下**。我方 8G 档配方里的 --host-kv-mib 16384（start-8g.bat:63、配方-8GB档-实测支撑-20261008.md:49）在这条钳制下**拿不到 16 GiB**；而 verify/回执-外部-8G-完整测试-20261008.md:46 只核到 host_kv_bytes=17,179,869,184 这个**请求值**生效，:227 明写「**未压测** --host-kv-mib 16384 的宿主内存压力（只验证了单请求长 prompt 不崩）」。⇒ 我们自己的验证链在这里是**断的**：请求值 ≠ 实际钉住值。

### 2.3 顺带核到的启动守卫（不是 bug）

src-tree/.../program/planning/startup.cpp:1837：

> NINFER_KV_WINDOW (KVMem ring) needs a Host KV tier that can hold every page the ...

即 host_pages + pool_pages ≥ logical_pages 否则**启动即拒**（我方 README.md:187 记 startup.cpp:1806-1840）。我方文档已定性为「特性不是故障」（docs/02-排错手册:33、docs/01-部署与编译总白皮书.md:511）。**含义**：想「减小 device 池、靠 host 补足逻辑上下文」，必须让 host 层容量真的够——而 §2.2 说 Windows 上它被钳住了。这正是「小池 + 大 host」在 8G 卡上过不去的根。

---

## 3. ② 「KV 全量放主机、显存只留固定窗口」——严格说不存在，近似物在 ring 线

### 3.1 概念纠正

attention 的每一步都要在 device 上读 K/V。所以「KV 全量放主机」无法字面实现；能实现的只有「**device 上常驻一个工作集（窗口），其余页溢出了主机，按需回捞**」。上游的表述就是这个意思（--kvmem-window-pages = 「retrieval-managed GPU working set」）。所谓「固定窗口」，就是**驻留窗口**，而它必须是完整 attention 工作集，不是随便一个小数。

### 3.2 ring 线（tancau/ninfer-kvmem-ring）的做法与自述

https://raw.githubusercontent.com/tancau/ninfer-kvmem-ring/master/README-RING.md ：

> the device KV pool may be smaller than the logical context, KVMem-style: the device pool is the attention window, evicted pages spill **losslessly to host RAM**, and a retrieval scorer brings relevant pages back (H2D). Verified on **RTX 3060 12GB / sm_86 / Windows 10**: 96K device pool serves 152K-token sequences (1.6x) at ~10.2 GB VRAM; dense 160K config stays bit-identical (PPL 5.639521, 62/62 sample points, delta 0).

开关（全部 opt-in）：

     NINFER_KV_RING=1  NINFER_KV_WINDOW=32768  NINFER_KV_RETRIEVE=4096
     NINFER_HOST_PAGEABLE=1  --kv-capacity 32768

> Without NINFER_KV_RING=1, --kv-capacity < --max-context is rejected and the engine behaves exactly as upstream.

### 3.3 上游主干（Neroued）没有 host 层

- raw master docs/serving.md（78,320 B）grep host-kv-mib / host-state-slots / Host KV = **0 命中**；master README 亦然；master 的 src/serve/serve_options.cpp 是 404（路径不同）。
- ⇒ --host-kv-mib / --host-state-slots 属于 **3090/ring/fusion 衍生线**，不在 Neroued 主干。
- 上游只有一份**未合并**提案：https://github.com/Neroued/ninfer/issues/362 （open，2026-10-04）+ PR #343/#344/#345（#345 open，https://github.com/Neroued/ninfer/pull/345 ）。

其文档（PR diff，docs/maintainer/kvmem-audit.md、docs/maintainer/paged-kv-cache.md）把边界写得比我们更狠：

> --kvmem-window-pages opts Qwen-family inference into a retrieval-managed GPU working set. Zero retains dense execution. ... **Logical context capacity does not imply that all history is resident.**

> Host replicas retain the packed device representation. Page tables mark absent pages with kPagedKVPageHole; **attention never dereferences or assigns probability mass to such pages.**

> Main physical 最小需求为 min(L, window_pages + ceil(effective_prefill_chunk / 64) + 16)，auto 使用该固定有界容量。逻辑地址仍覆盖 L 页，Device working set 以外的已提交页由 Host 副本持有，执行表发布 hole。

> **长请求的稀疏 continuation 暂不进入前缀缓存。**

限制：只支持 1–2 lane；DFlash2 需 draft 全 local attention；拒 DFlash 一代、full-attention draft、scoring、>2 lane。

**读法**：这套设计是「**窗口常驻 + hole 标记 + 检索回捞**」，被标 hole 的页**永远不参与 attention**。所以它**不是 dense 等价**，只是「在被选中的 KV 集上数值正确」。这正是它无法承诺「反复问仍正确」的根。

---

## 4. ③ 上游谁做到了「超池 + 反复问仍正确」

**答案：没有人公开做到。已有的超池证据全部是单发（single-shot）。**

### 4.1 ring 线基准矩阵（唯一带数字的超池实验）

https://raw.githubusercontent.com/tancau/ninfer-kvmem-ring/master/bonsai-app/BENCH-RESULTS.md §8.1（RTX 3060 12G、rk8v4、MTP3、数据取自引擎自报 req#N done）：

| # | 内容 | prompt tokens | 超 96K 池? | 结果 |
|---|---|---|---|---|
| T3 | **藏针召回** STARFRUIT-88 | 129,376 | **是（1.35×）** | ✅ PASS |
| T4 | 双轮记忆 PARROT-31 | 65 → 88 | **否** | ✅ PASS（cache 68.2% turn closure） |

§8.2 服务端权威数：129,376 token 环通路 prefill **147.8 / 150.6 t/s**、TTFT **14m20–36s**、decode **18.3 / 19.5 t/s**、MTP 接受率 35.9 / 38.9%。

**关键观察**：超池的那条（T3）是**单发藏针**；唯一的多轮测试（T4）**根本没超池**。⇒ 「超池 + 反复问」在这份最完整的基准里**是空白**。

### 4.2 上游 PR #345 的自述验证

> Seventy real-model case checks passed across ordinary/MTP/DFlash2 K7, vision/replay, concurrency, cancellation and Host-claim release. ... **Most used a 16K logical context and a 4K device window**（= 4× 超池）

但作者同页明确免责：

> **Sparse attention excludes some historical tokens and is potentially lossy relative to full-history attention. Numerical correctness over the selected KV set is not proof of dense-model equivalence.**

> retrieval-selected attention is not mathematically equivalent to dense attention over all history ... do not establish broad quality equivalence.

⇒ 即使 70 例全过，作者也只主张「**在被选中的 KV 集上数值正确**」，**不主张**对全历史等价。这是 ③ 的官方答案：**条件性正确，且条件是「答案不依赖被丢弃的历史」**。

### 4.3 我方那一支「超池也能复用正确」的读数

repos/ninfer-fusion-kvmem/实测回执与反馈.md:570（A 级本机）：**超池 ≠ 降质**——198,128 token 夹具、唯一变量=池：池 17,920 首发 200 / 284.4 s，**复用 200 / 16.8 s，口令 ✅、重复窗口 0、复述 0**。

⇒ 检索开着、且预算真实时，超池的**第二轮**可以是正确的。这与「超池只可信一次」并不矛盾——它们分属不同配置（见 §6 的三条件）。

---

## 5. ④ 「超池只可信一次」：上游已知，且是文档化的硬约束

### 5.1 决定性一手：ring 线自己写的「主机区容量需求」

bonsai-app/KVMEM-PORT-PLAN.md §「⚠️ 主机区容量需求（环模式多轮对话的硬约束）」（https://raw.githubusercontent.com/tancau/ninfer-kvmem-ring/master/bonsai-app/KVMEM-PORT-PLAN.md）：

     环形降级页（历史）              ≈ (上下文 − 驻留窗口) × 18432 B
     已发布的 checkpoint 副本        ≈ 上下文 × 18432 B（一整份）
     新请求自己的 checkpoint 副本    ≈ 上下文 × 18432 B（一整份）
     ───────────────────────────────────────────────────────────
     主机区需求 ≈ (3 × 上下文 − 驻留窗口) × 18432 B
     本机实测：3×60K − 27K ≈ 153K token ≈ 2.8 GB   而主机区上限只有约 2.1 GB → 第二个请求被拒

诊断命中 pressure.cpp:2350 → physical_peak_fits 的 host.kv_bytes 维度，报错 isolated-feasible ... idle Engine。

> **⇒ 结论（Windows）**：环模式的**多轮对话**需要 3 份上下文的主机空间，而主机区受 free_device − 余量 限制。本机 2.0 GiB 主机区对应的多轮上限约 **36K token**；**60K 以上只能单请求**。

> **真正的修法（未做，属引擎深度改动）**：让 checkpoint **直接引用环形已在主机的那些页**，而不是复制一份——需要状态/检查点子系统理解环形的 host extents。

这正是「**超池只可信一次**」的机制级解释：第一问能用（只有一个 checkpoint 副本 + 环形降级页），第二问要再复制一整份上下文 → 撞穿主机区 → 拒绝（1.35× 那种场景只需 ~2.8 GB，而 8G 卡上主机区只有 ~2.1 GB）。

### 5.2 已排除 / 试过失败

- 主机区放大到 2.02 GiB（仍不够）
- 设备状态槽 3
- 禁 publish_continuation → 破坏前缀簿记（PrefixShortlistDigests::at 越界），**连第一个请求都失败，已回退**

### 5.3 旁路开关：有，但都不安全

| 开关 | 来源 | 效果 | 问题 |
|---|---|---|---|
| NINFER_KV_HOST_OVERCOMMIT_MIB | ring 线 KVMEM-PORT-PLAN 的「配置 B」 | 放大主机区 | **我方全仓 grep 无命中**——我们的树没携带这个 env（需另核是否只存在于 tancau 仓） |
| --no-prefix-reuse | 同处「配置 A」 | 少一份 checkpoint 副本 | **与环不兼容**：地址空间按 kv_capacity 而非 max_context 构建 → logical_capacity 变 512 → 退化 dense 并溢出 |
| --max-shared-prefixes 0 | **我方** B01 处方 | 治「逐字节重发必崩/实例打砖」 | **不治**「只可信一次」，只是绕开 shared prefix 路径 |

⇒ **没有既保留环/检索、又能安全放大主机区的开关**。

### 5.4 检索自身的泄漏（会让「第二次」更糟）

KVMEM-PORT-PLAN.md §「调试链（检索功能的 4 个真实缺陷）」（实为 6 条）：

| # | 症状 | 根因 | 修法 |
|---|---|---|---|
| 2 | materialize count 16 > free 15 | **host+device 双副本的页被降级准入排除**（!host_resident）→ 取回过但不再被选中的页**永久常驻 = 真实泄漏** | 双副本页直接释放 device 副本 |
| 5 | logical KV batch materialization exceeds descriptor capacity | materialization_scratch_ 只按物理池 512 页预留，逻辑 2048 页 → 一次映射跨 >512 逻辑页溢出 | reserve(logical_capacity) |
| 1 | materialize_one 无空闲页 | 预算零余量 | 8 页 slack + free_runs()（拿不到就跳过=只隐藏，安全） |
| 3 | 掩码漏选「本来就常驻」的检索页 | restore_* 只返回「恢复成功」的 | 改为返回「检索后实际设备常驻」 |
| 6 | reuse 被拒 isolated-feasible ... idle Engine | 主机区容量（实测需 1.71 GB、可用 1.53 GiB） | 配置 A / B |

⇒ 泄漏 + 主机区容量共同解释「第一问可、第二问崩/错/拒」。

### 5.5 上游主干侧的同类症状（可引 URL，均为 Neroued 仓 issue）

- https://github.com/Neroued/ninfer/issues/394 （open）「Context cache: once full, a plain multi-turn chat resumes only from the engine-discovered system prefix」——满缓存下 ~5.7K system message 连问三个问题复用 **0/0/0**，第四个才复用 5,738 token（修正门控后 0/0/5,740）。这就是「多轮复用失效」的干净复现。
- https://github.com/Neroued/ninfer/issues/135 （closed）「Host KV cache terminates the inference engine: materialization pressure owner is duplicated」——作者自更正：--host-kv-mib 0 --host-state-slots 0 **仍复现**，Host KV 只是**降低触发阈值**；故障后**永久 503**（req122 error → req123 起 service_unavailable）；**114k–152k prompt 必现**，45k 在 Host KV 开时 40–45 s 复现；启动账本示例 device-state=0-cache+4-active host-state=0 host-kv=0.00 MiB。
- https://github.com/Neroued/ninfer/issues/339 （serve 全 503 wedge）、https://github.com/Neroued/ninfer/issues/414 （并发共享前缀「KV write exceeds its page reservation」回归）、https://github.com/Neroued/ninfer/issues/378 （Host context tier 按空闲字节判容量、放置连续）。

---

## 6. 我方证据的交叉核对：那个 429 可能就是「主机区容量」

我方 docs/51-诊断与修复方法-只能服务第一条请求-20261012.md §0-§3（A 级本机）：起得来、/health 通、**req#1 200（0.32 s），req#2/3/4 全 429（0.01 s，准入阶段，日志无一条 error，进程不崩）**，响应体：

     {"error":{"code":"server_overloaded","message":"context cache exhausted: an idle Engine found no placement"}}

该串在我方树内：src-tree/fusion-engine-src/src/runtime/engine/engine_core.h:1943。
当时结论（**单变量对照**：换随包件 engine-v0.11.0-kvmem-20261003 = 4/4 全 200，本仓 2026-10-12 构建 = 1/4）⇒ 判为**引擎代码问题**，14 项逐条排除（池大小/复用/环/host 后备/检索/并发/KV 精度/投机/状态槽）。

**但要提示父代理**：这条 429 的语义是「**placement 找不到位置**」，而 ring 线把「第二个请求被拒」也归到 physical_peak_fits 的 host.kv_bytes 维度（报错同为 ... idle Engine）。两条线索**同一家族**。两个解释并不互斥：新构建可能抬高了宿主保留/放置约束，于是在 8G 上第二问放不下。**一个便宜的判别实验**（不需要我起引擎，交父代理决定）：用新构建 + --host-kv-mib 0 --host-state-slots 0 跑同一组 4 请求；若 req#2 变 200，则「只可信一次」是**主机区容量**而非纯代码回归，处方方向完全不同。

---

## 7. 可复问的三条件（可操作结论）

要「超池 + 反复问仍正确」，以下必须**同时**成立：

1. **检索必须真开、且有预算**：NINFER_KV_RETRIEVE > 0（我方 B28：rk4v4 池 8192 下，显式 0 ⇒ **0/6 全静默错**；8192 ⇒ **6/6 命中**；95k 多针 23× 超池：开 3/3、关 0/3）。B32 已让「环开 + RETRIEVE 未设」自动给预算（context.cpp:2685-2693），但**显式 =0 仍被尊重**——8G 档务必不要写 NINFER_KV_RETRIEVE=0（HTTP 200、答案貌似合理但是错）。
2. **主机区容得下 ≈3× 上下文**：Windows 上主机区 ≈ (free VRAM − 1 GiB)/2，且 8G 卡跑 27B/35B 时常被钳到 **302 MiB / 0**（launcher-profiles.md:412-416）。实操含义：**多轮可复问的上限远低于「池 + host」算出来的名义容量**；按 ring 线实测，2.0 GiB 主机区 → 多轮 ~36K，60K 以上只能单请求。
3. **不要逐字节重发同一超池题面**：我方硬边界——超池题面逐字节相同重发 ⇒ **必崩/实例打砖、此后全 503**，处方 --max-shared-prefixes 0（B01）。另有 --host-kv-mib 64 + 环 + 池 1,024 + 40k 题面 ⇒ req#1 即 worker crash: Paged KV reservation invariant was violated + HTTP 500（复现白皮书 §5.142）。

**反直觉提醒**：调大 --host-kv-mib 在 Windows 上是**零收益甚至负收益**——它先被钳到 (free VRAM−1 GiB)/2，再与 --host-state-slots 抢同一笔额度（serving.md:34-35），开得越大越容易把启动守卫（startup.cpp:1837）或 placement 逼死。

---

## 8. 未核 / 存疑清单

- NINFER_KV_HOST_OVERCOMMIT_MIB 只在 tancau 仓的移植日志里出现，**我方树 grep 无命中**；是否真在其代码里、语义如何，**未核**。
- ring 线 README 的「96K 池服务 152K（1.6×）@ ~10.2 GB VRAM」与 BENCH 的「129,376 = 1.35×」是**两组不同实验**，未核是否同一配置。
- 我方 --host-kv-mib 16384 的实际钉住值**从未测过**（回执只记了请求值 host_kv_bytes=17,179,869,184）。按 §2.2，8G 卡上大概率被钳到几百 MiB —— **这条需要实测，属最该补的一个数**。
- 姊妹仓 melis2023/ninfer-kvmem-actkv（87★）、CSUNX233/...-5070tilaptop（72★）、paicat1/Ninfer-KVMem-Async（10★）等**均未逐个核证**；【未核源】。
- Neroued 主干 issue 的数量与状态取自页面快照，未做全量枚举。

---

## 9. 引用清单（一手 URL）

1. https://github.com/tancau/ninfer-kvmem-ring —— README-RING.md（环 + 检索的 opt-in 开关与 1.6× 实测）
2. https://raw.githubusercontent.com/tancau/ninfer-kvmem-ring/master/bonsai-app/BENCH-RESULTS.md —— §8.1 超池矩阵（T3 129,376 = 1.35× PASS；T4 未超池）、§8.2 曲线
3. https://raw.githubusercontent.com/tancau/ninfer-kvmem-ring/master/bonsai-app/KVMEM-PORT-PLAN.md —— 「⚠️ 主机区容量需求」(3×上下文−窗口)×18432 B；6 条检索缺陷；配置 A/B
4. https://github.com/Neroued/ninfer/issues/362 —— opt-in retrieval KV windows（open，未合并）
5. https://github.com/Neroued/ninfer/pull/345 —— --kvmem-window-pages、--host-kv-mib 2048、hole 语义、70 例自述 + 免责声明
6. https://github.com/Neroued/ninfer/issues/394 —— 满缓存多轮复用 0/0/0
7. https://github.com/Neroued/ninfer/issues/135 —— Host KV 只是降低阈值；永久 503；114k–152k 必现
8. https://github.com/Neroued/ninfer/issues/339 / https://github.com/Neroued/ninfer/issues/414 / https://github.com/Neroued/ninfer/issues/378 —— 503 wedge / 页预留回归 / Host tier 容量判据

本地 file:line（只读引用，未修改）：

- repos/ninfer-fusion-kvmem/src-tree/fusion-engine-src/docs/serving.md:34-35,1251
- .../docs/maintainer/launcher-profiles.md:412-416（Windows 钳制 + 实测表）
- .../docs/release-archive-linux.md:100-101
- .../src/core/arena.cu:657,673
- .../src/runtime/engine/engine_core.h:1943
- .../program/planning/startup.cpp:1837
- repos/ninfer-fusion-kvmem/docs/51-诊断与修复方法-只能服务第一条请求-20261012.md §0-§3
- repos/ninfer-fusion-kvmem/实测回执与反馈.md:570
- repos/ninfer-fusion-kvmem/verify/回执-外部-8G-完整测试-20261008.md:46,227
- repos/ninfer-fusion-kvmem/patches/changed-files/src/serve/serve_options.cpp:860-868,1072,1093-1095
