# GitHub 情报：NInfer 生态 + Strata 生态 + 提速技巧（2026-10-30）

侦察员：sm120a-scout（共享任务 task-14）｜方法：`export HTTP_PROXY/HTTPS_PROXY=http://127.0.0.1:7897` 后 `git clone --depth 1` 9 个仓到 `C:/Project/local_model/tmp/gh/<仓名>`，另做**只读**字节扫描与源码核对；**全程没有启动任何 GPU 引擎**（铁律：只有 ninfer-limit/ninfer-analyst 能起引擎，8091/8081 在服务用户）。

标注约定：**【实测】**=某台机器上真跑出来的数（注明是谁的机器）｜**【口径】**=文档/代码声明，未在我们这台卡上验证｜**【推算】**=我按公式算的，不是实测。

## 0 · 五条结论（先看这个）

1. **我们卡上的 `--fast-prefill-kernel` 其实早就生效了**。引擎首次启动自动校准了 52 条 route，profile 里 `attn_prompt_fast = on`、`attn_pv_f16 = on`、`gdn_two_stage = on`。⇒ `docs/200K可行性-结论与优化-20261030.md:61/88` 里那条待办「试 `--fast-prefill-kernel`」可以划掉；反过来，**做基准时别随手 `--device-profile off`，那会把这份加速一起关掉**。
2. **真正没试过的 prefill 大杠杆是 `--prefill-cublas`**（本机 help 有、`cublas64_13.dll` 已在 engine 目录、脚本里从没用过）。上游同 build 同卡 A/B：prefill **+42.8% / +82.9% / +73.5% / +53.5%**（1k/4k/16k/51k），decode 不动，代价 +0.156% 困惑度、workspace +505.6 MiB。
3. **长 prefill 里有一段纯浪费的 H2D**：`NINFER_KV_PREFILL_NO_RESTORE=1` 让 prefill 阶段跳过 evidence 页的逐块回写主机→显存。上游注释原话：`measured: ~280 s of one 250K prefill is this H2D`。默认 OFF，本机二进制有这个名字。
4. **队友发现的「evidence 预算写死 128 页、从不借 free」有现成 env 可调**，不用改代码：`NINFER_KV_EVIDENCE_AUTO=1`（把池里空闲页全给检索，保留 10 页安全线，启动打印 `[ninfer] evidence auto: pool=… skeleton=… evidence=… reserve=… free=…`）、`NINFER_KV_EVIDENCE_SHARE=0..90`（覆盖默认 50% 份额）、`NINFER_KV_EVIDENCE_RESERVE=N`。
5. **8 GB 单卡的 200 K 结论没被 GitHub 上的任何证据推翻**：Aurora（4060 Laptop 8GB 同族卡）最好一档是池 12,800 / 逻辑窗 131,072；他们的长档池 51,200 靠**关 MTP** 换来的，作者自己写「它不会让解码更快」。上游最强的「200,000 tokens, verified by loading it」是 24 GB 3090 的配方（rk8v4 + embedding-q4 + lm-head-q6 + chunk 2048），其中两条在本机产物上**直接不可用**（见 §3）。

## 1 · 能直接用的（本机可执行，改一个 env / 一个 flag 就行）

### 1.1 `--prefill-cublas`：prefill +43%~+83%（本轮第一优先实验）

- 出处：`tmp/gh/ninfer-bonsai-4070ti/vendor/ninfer-fusion-kvmem/src-tree/fusion-engine-src/docs/performance.md:96-125`、`:404`；`RELEASE_NOTES_0.11.0.md:46-58`（即 0.11.0 的正式功能，我们 build 是 `engine-v0.11.0-kvmem-20261003-98-g43c39c6-dirty`，同版本线）。
- **【实测】上游：单张 RTX 3090，Qwen3.8-27B groupwise-int，`--kv-dtype int8`，同 build 同卡同一次会话 A/B**：

| prefill tok/s | 1k | 4k | 16k | 51k |
|---|---:|---:|---:|---:|
| 出厂整数激活路线 | 1,666.6 | 1,634.4 | 1,503.9 | 1,240.8 |
| `--prefill-cublas --prefill-chunk 4096` | **2,379.8** | **2,988.7** | **2,609.0** | **1,904.1** |
| 变化 | +42.8% | +82.9% | +73.5% | +53.5% |

- 同页：decode 45.1 vs 45.7 tok/s（基本不动，路由只对宽 token 数生效）；**workspace 155.6 → 661.2 MiB**。
- 代价（`performance.md:108-125`）：困惑度 4.343155 → 4.346284（+0.072%，只把 MLP/out_proj 上这条路）→ 4.349944（+0.156%，再把 attention 与 GDN 输入投影也放上去）。想省质量就用 `--no-prefill-cublas-projections`。
- 本机适配性：`engine/help-full.txt:41-43` 有该开关；`engine/` 里已经有 `cublas64_13.dll` / `cublasLt64_13.dll`（不必再装 CUDA Toolkit）。**脚本里从没出现过**（全仓 grep 只有 `scripts/fetch_runtime.sh:16,23` 下载 DLL 那两处）。
- **【推算】8 GB 上的显存账（这条最关键）**：现役峰值 7,469 MiB，卡 8,188 MiB，红线 7,488（Aurora 口径 = 8,188−400−300，见 `tmp/gh/ninfer-8gb-playbook/docs/04-8GB显存档位适配.md:71-79`）。rk2v4-e8 每页 0.8357 MiB ⇒ 多要 505.6 MiB 就得让出 **≈605 页 ≈ 38,720 token**；现役池只有 40,000 ⇒ 直接不可行。上游自己也是这么选的（`performance.md:393-394`：chunk 4096 比 2048 多 ~300 MiB workspace，「at this context that is the binding constraint」）。
- ⇒ **可行组合只有一个**：`池 16,000 + --prefill-cublas --prefill-chunk 2048`（让出 384 页 ≈ 321 MiB，chunk 2048 的 workspace 估计 ~200-360 MiB，见上一条 chunk 差值推算）。一句话试法：

```bash
cd /c/Project/local_model && PROFILE=fast CHUNK=2048 FORCE=1 \
  EXTRA="--prefill-cublas" bash scripts/serve2.sh      # fast 档 = 池 16,000 / rk2v4-e8 / host-kv 4,096
# 对照臂：去掉 EXTRA 再跑一遍；验收：prefill tok/s ≥1.3×（上游最低 +43%）且 0 条 "prompt exceeds"
```

- 若这次撞显存：先 `--no-prefill-cublas-projections` 只让 MLP 上路，或把 `CHUNK` 降到 1024 复测（上游说这条路要 chunk 才付得起，1024 可能白跑）。

### 1.2 `NINFER_KV_PREFILL_NO_RESTORE=1`：长 prefill 省掉纯浪费的 H2D

- 出处：`https://github.com/1314521gjy/ninfer-fusion-kvmem` → `src-tree/fusion-engine-src/src/models/qwen3_5/program/storage/context.cpp:2598-2606`。代码注释原文：

> NINFER_KV_PREFILL_NO_RESTORE (default OFF, byte-for-byte unchanged when unset/0): during PREFILL the retrieval window is not needed yet, so the per-chunk H2D restore of the preferred (evidence) pages is pure cost -- **measured: ~280 s of one 250K prefill is this H2D**. Only the evidence restore is skipped; mapping (ensure_mapped_to_tokens), the sink, and the host write-through are untouched.

- 本机二进制里有这个名字（`NINFER_KV_PREFILL_NO_RESTORE`，见 §4 清单）⇒ 一个 env 就能试。**对 37K 题面（963 tok/s）也应该有收益**，越长的题面越多；风险面很窄（只跳过 evidence 的 H2D，不动 sink / write-through / mapping）。
- 注意：这条会让「prefill 期间 device 上缺 evidence 页」，对**单问**无影响（prefill 不检索），对**边 prefill 边被别的请求检索**的并发场景要复测答案正确性（我们是 `--max-concurrency 1`，风险低）。

### 1.3 evidence 预算 / 最近页保护：把队友发现的 bug2 变成旋钮

同一份 `context.cpp` 里，全部**本机二进制都存在**：

| env | 作用 | 源码行 |
|---|---|---|
| `NINFER_KV_EVIDENCE_SHARE=0..90` | 覆盖「池的多少比例给检索」，默认是 `proto_kv_retrieve_share_percent()`（默认一半）；生效时打印 `[ninfer] evidence share clamped: …` | `context.cpp:2619-2636` |
| `NINFER_KV_EVIDENCE_AUTO=1` | 把池里**空闲页**全给检索，保留 `reserve`（默认 10 页）安全线；打印 `[ninfer] evidence auto: pool=… skeleton=… evidence=… reserve=… free=… kv_retrieve_pages=…` | `context.cpp:2635-2672` |
| `NINFER_KV_EVIDENCE_RESERVE=N` | 上面那条的保留页数（默认 10，注释写「long-output safety line (measured)」） | `context.cpp:2646-2654` |
| `NINFER_KV_RECENT_PAGES=N` | 最新 N 页在**两轮逐出里都保护**，像 attention sink 一样（0=出厂行为）——正对我们「长输出时 free 页 <10 会缺号/回卷」那个坑 | `context.cpp:2026-2031` |
| `NINFER_KV_NEIGHBOR_PAGES=0/1/2` | 被选中的页要不要把**左右邻页**一起搬回（默认 1；0 是这条修复的反向对照） | `context.cpp:1695-1700` |
| `NINFER_KV_PROTECT` / `_FRAC` / `_RESCUE` | 环里绝不逐出的页比例（1..50%）；注释警告「protecting the whole window cost 9% decode」 | `context.cpp:2117-2150` |

- 另有 B32 默认检索预算的事故记录（**这不是传闻，是上游自己量的**）：`context.cpp:2675-2696`，「budget 0 时 0/6 命中，手给 8192 token 时 6/6」；⇒ 若我们显式把 `NINFER_KV_RETRIEVE=0` 拿来「省事」，答案是**静默错的**。
- **【实测·本机】我们的启动脚本已经设了 `NINFER_KV_RETRIEVE=8192`**（`scripts/serve2.sh:60`）→ 这一层是安全的。

### 1.4 8 GB 档最完整的现成配方（Aurora，同族卡 RTX 4060 Laptop 8GB / sm_89）

- 出处：`https://github.com/Aurora-Serendipity/ninfer-8gb-playbook` → `docs/04-8GB显存档位适配.md:35-45`（两档参数）、`:129-154`（完整命令行）、`:252-296`（profiles.json）。
- 【实测】他们两档的 capacity 行与峰值：daily「KV 12,800 tokens, rk2v4-e8, explicit | pages 200/2,048 | runtime 675.6 MiB | free 340.0 MiB」，峰值 7,015 MiB；longctx「KV 51,200 … pages 800/4,096 | runtime 1.11 GiB | free 310.0 MiB」，峰值 7,171 MiB。
- 【实测】速度（计数语料 temp 0）：daily decode 63.3-71.6 tok/s、prefill 640-697、TTFT(1,121 token) 1.7 s；longctx decode 20.3-21.4、prefill 610-675。长题面：daily 10,130 token ⇒ TTFT 15.0 s；longctx 48,062 token ⇒ TTFT 78.7 s。
- 可直接抄的三条差异（我们没这么配）：①**长档关 MTP**（`--spec` 整条去掉）；②`--host-kv-mib 3328`（理由是 262,144 逻辑窗要 3,296 宿主页，出厂 2,816 只剩 42 页余量）；③`--prefill-chunk 1024` 当出厂值不动。
- 退档阶梯（`docs/04:181-197`，每步省多少都标了）：每 −64 页省 53 MiB；关 MTP 省 551-970 MiB、decode 掉到 45-100；`--ngram-draft-tokens 0` 省 50-127 MiB、速度≈1.01×；dtype 容量倍率 k8v4/rk4v4/rk4v4-e8/rk2v4-e8 = 1.00/1.436/1.861（他们表里 nvfp4 1.396）；加大 `--host-kv-mib` **不省显存**只解 429。
- **禁区**（同文件）：池 <8 页拒启；长输出 free 页 <10 会缺号；别想用 `--draft-tokens` / `--mtp-attention-window` 省显存（实测只差 12 MiB）。

### 1.5 池 = 前缀时买的是「延迟」不是「能不能复用」

- 出处：`tmp/gh/ninfer-fusion-kvmem/docs/03-基础部署后的调优方案.md:104-116`、`docs/11-按卡差异速查.md:104-106`。**这解释了为什么加大池对 200K 没帮助、但对重复提问有帮助**：4080 SUPER 上池 152 页（auto）40k 提示第二轮 TTFT 154 ms；池 640 页（`--kv-capacity 40960`）TTFT 118 ms；**两档复用比都 99.9%（cache 40,068）**。
- ⇒ 我们的 40,000 桶已经能吃掉「同题面第二轮」的全部收益；再加池只省 36 ms 级延迟。

## 2 · 需要验证的（有量化的预期，但本机没有实测；每条给验收口径）

| # | 做法 | 出处 | 预期（口径/实测归属） | 风险/代价 | 验收 |
|---|---|---|---|---|---|
| V1 | `--prefill-cublas --prefill-chunk 2048` @池 16,000 | 上游 `performance.md:96-125`【实测·3090】 | prefill ×1.43~1.83；decode 不变 | +0.156% ppl；workspace +205~506 MiB【推算】 | 同题面 prefill tok/s ≥1.3×，答案逐字对比 |
| V2 | `NINFER_KV_PREFILL_NO_RESTORE=1` | `context.cpp:2598-2606`【口径+上游测得 250K 里 ~280 s 是这段 H2D】 | 长题面 prefill 变快，越长越多 | 并发检索时答案要复测 | 37K 题面 prefill tok/s 前后对比 |
| V3 | `NINFER_KV_EVIDENCE_AUTO=1`（+`_RESERVE=10`） | `context.cpp:2635-2672` | 超池题面的「中段内容」可行；日志给出四元账 | 只借「已经空闲」的页，不会让全局计数题变可答（注释明说） | `[ring] budgets` 行 + 双针命中 |
| V4 | `NINFER_KV_RECENT_PAGES=64` | `context.cpp:2026-2031` | 长输出后内容不再缺号/回卷 | 占池页 | 2,048 输出后逐字校验 |
| V5 | `--device-profile calibrate` 重跑校准 | `tmp/gh/ninfer-bonsai-4070ti/vendor/.../docs/device-profiles.md:23-31`；本机 `logs/ab_d4p32.log:6` 已 52 键 | 换开关组合后 route 可能不同；校准要 20-40 s 且要空闲卡 | 会覆盖 `%LOCALAPPDATA%\infer\device-profiles.json` | 校准后同题面 A/B |
| V6 | 老三洋 `NINFER_PTQ1_WIDE_T` / `_WIDE_T_MIN` / `NINFER_PTQ1_TILE_MIN` / `NINFER_T2_*` 调 ternary prefill 内核 | 本机二进制存在（§4）；paicat1 提到「prefill 内核 S8 最快 / wide / mma」`https://github.com/paicat1/Bonsai-27B-NInfer` README:40-50 | 未知，方向对（PTQ1 就是我们模型的主路径） | 可能变慢；需一臂一臂测 | 4k/16k prefill tok/s |
| V7 | 前缀快照（把 213K 冷读换成载入快照） | `https://github.com/CraneBW/ninfer-ternary-bonsai-ada` README【实测·4070Ti SUPER sm_89】 | load 中位 24.32→10.77 s；首 TTFT 47.42→34.16 s（−27.6%）；canonical-ready 快照 35.54→13.11 s（−63%） | 固定题面才能用；要 `NINFER_KVMEM_CANONICAL_QUERY_REUSE=1`（**本机二进制没有这个名字**） | 长文重复问答的场景才值得 |
| V8 | 磁盘 KV 层 `--disk-kv-path` | 本机 help `logs/help.txt:147-153`；Aurora `start-ptq1-mtp-diskkv.bat` 文档组 | 只买容量与跨重启，**永不提速** | 慢 | 只在「必须跨重启保留上下文」时用 |

注：V1 是唯一一条**同时满足「本机可执行、有上游同 build 实测倍数、没试过」**的选项，优先级最高。

## 3 · 明显不可用的（有硬证据，别再花时间）

| 项 | 证据 | 结论 |
|---|---|---|
| `--lm-head-q6` / `--lm-head-q4` | 本机实跑报错：`logs/probe_x.log:8-9`「`--lm-head-q6 requires text/output_head to be stored as row-split Q8_G32`」；源码 `src/models/qwen3_5/load/storage_trades.cpp:20-28` | 我们这个产物里 `weight/000258`（=output_head，`[248320,5120] ptq1_g128_fp16`）不是 Q8 ⇒ **FATAL，不可用**。上游「+12.9K token」的账跟我们无关 |
| `--embedding-q4` / `--embedding-q6` | 同一 transcode 通道（`storage_trades.cpp:31-36`）；产物清单里 token_embedding 也是 `ptq1_g128_fp16`（`weight/000258/000259` 各 278,118,400 B） | **同样会 FATAL**，上游「+24.3K tokens」不成立；别把它算进 200K 方案 |
| `NINFER_GGUF_LARGE_PREFILL` / `NINFER_GGUF_SILU_MMQ` / `NINFER_GGUF_MMQ_BF16` / `NINFER_GGUF_IQ3_S_MMQ_I64` | CraneBW 的 prefill +3.2~3.9% / +0.69% 全靠这几个（`https://github.com/CraneBW/ninfer-ternary-bonsai-ada` README:70 与实验段）；**本机二进制 0 命中** | 那是 GGUF/MMQ 路线；我们是 PTQ1 ternary 产物，**开关不存在，不可转录** |
| `NINFER_TERNARY_S8=1`（paicat1 的 2.85k prefill）、`NINFER_TERNARY_SMALL_T_ROWS`（ygxiuming）、`NINFER_SM89_SHARED_VECTOR`、`NINFER_PROMPT_I8_PIPELINE` | 本机二进制 0 命中（§4） | 需要换引擎二进制/重新编译，不是 env 能开 |
| 重新编译带 `SM_COUNT=60` 的 A3 引擎（ygxiuming，prefill 1759→2191 +24.57%） | `https://github.com/ygxiuming/ninfer-bonsai-4070ti` `docs/性能实测.md:5-14` | 我们是 34 SM（`device-profiles.json` 的 `multiprocessors: 34`），60 是 4070 Ti 的数；**照抄无意义**，但「按实际 SM 数重编」这个方向可以记一笔 |
| Strata 跑我们的 27B ternary | 见 §5 | Strata 的容量机制是**专家流式**（MoE）；27B 稠密 ternary 必须整份驻留 ⇒ 8 GB 装不下（权重 5.94 GiB + 运行时 = 6.95 GiB 固定开销，我们自己的账） |

## 4 · 本机二进制的权威开关清单（只读字节扫描，未启动引擎）

`C:/Project/local_model/engine/ninfer-serve-89.exe`（801,324,544 B，`engine-v0.11.0-kvmem-20261003-98-g43c39c6-dirty`）一共 **137** 个 `NINFER_*` 名。分族（全部可 env 直开）：

- **prompt/prefill**：`NINFER_PROMPT_FAST`、`NINFER_PROMPT_PACK_GQA`、`NINFER_PROMPT_PV_F16`、`NINFER_SMALLT_PV_F16`、`NINFER_PREFILL_ALIGN`、`NINFER_PREFILL_CHUNK_AUTO`
- **ternary 内核**：`NINFER_TERNARY_PTQ1_FAST`、`NINFER_PTQ1_WIDE_T`、`NINFER_PTQ1_WIDE_T_MIN`、`NINFER_PTQ1_TILE_MIN`、`NINFER_T2_A8_MIN/_PAIR/_RASTER/_TILE/_DEBUG`、`NINFER_T2_DECODE`、`NINFER_T2_I8_SMALL`、`NINFER_T2_SMALLT`、`NINFER_T2_V2`
- **KVMem/环**：`NINFER_KV_WINDOW`、`NINFER_KV_RETRIEVE(+_AUTO/_SHARE)`、`NINFER_HOST_PAGEABLE`、`NINFER_KV_REUSE_HOSTBACKED`、`NINFER_KV_HOST_WRITETHROUGH`、`NINFER_KV_NEIGHBOR_PAGES`、`NINFER_KV_RECENT_PAGES`、`NINFER_KV_SINK`、`NINFER_KV_PROTECT(+_FRAC/_RESCUE/_DBG)`、`NINFER_KV_PREFILL_NO_RESTORE`、`NINFER_KV_AUTO_RESERVE_MIB`、`NINFER_KV_EVIDENCE_AUTO/_SHARE/_RESERVE`、`NINFER_KV_DTYPE_AUTO`、`NINFER_TERNARY_KVMEM(+_SCORE/_SCORE_BUDGET/_SCORE_MAXQ/_SCORE_RECENT/_SCORE_SINK/_SCORE_SPAN_*)`
- **其它**：`NINFER_GDN_TWO_STAGE`、`NINFER_DIRECTSTORAGE`、`NINFER_DEVICE_PROFILES`、`NINFER_RANKING_PATH`、`NINFER_D3D12_RESIDENCY`、`NINFER_CUDA_SYNC`、`NINFER_PROTO_SELECT`、`NINFER_MAT_DEBUG`，以及整族 `NINFER_FLASH_NEXT_*`（CPU 专家服务，MoE 专用，我们不用）

**不存在**（别人文档里有的，本机 0 命中）：`NINFER_KV_RING`、`NINFER_TERNARY_S8`、`NINFER_TERNARY_SMALL_T_ROWS`、`NINFER_GGUF_LARGE_PREFILL`、`NINFER_GGUF_SILU_MMQ`、`NINFER_GGUF_MMQ_BF16`、`NINFER_SM89_SHARED_VECTOR`、`NINFER_PROMPT_I8_PIPELINE`、`NINFER_KVMEM_CANONICAL_QUERY_REUSE`、`NINFER_ARENA_PIN_GIB`（Strata 的）、`NINFER_R27_BUNDLE`/`NINFER_R29_BUNDLE`、`NINFER_KVMEM_SOURCE_*`。

**`--device-profile` 已经替我们做过的事**（`%LOCALAPPDATA%\infer\device-profiles.json`，`origin: calibration`，`multiprocessors: 34`，52 条 route）：

```
attn_prompt_fast   [[1, "on"]]        ← fast prompt-attention kernel 已在用
attn_pv_f16        [[1, "on"]]
gdn_two_stage/h32  [[2147483647, "on"]]   gdn_two_stage/h48 [[2147483647, "on"]]
attn_i8_small/h24/rk2v4-e8/w1..w8  37 条（含 8K/64K/1M 三段窗）
t2_i8_route [[48,""],[64,"tile"],[192,""]]   t2_i8_small/5120x6144 [[8,"r32c8k4"],[16,"r32c16"],[32,""]]
```

⇒ 结论：**「换 route 拿 prefill」这条路我们已经吃到一半了**；剩下的空间在 `--prefill-cublas`（换 GEMM 后端，profile 管不到）和 KVMem 侧（§1.2/1.3）。

## 5 · Strata 侧：8 GB 到底有什么证据、怎么配、坑在哪

### 5.1 8 GB 的三条真数据（全部是别人的机器）

| 证据 | 硬件 | 数 |
|---|---|---|
| `docs/BATCHED_DMA.md:47-52,71-73`【实测】 | **RTX 4070 Laptop 8 GB / Win / CUDA 13.4** | 64K 上下文 Swift 1.5 IQ3_XXS：decode 30.3 tok/s；**57,750-token 题面读入 78.414 s ⇒ ≈736 tok/s**；侧调用后恢复 57,745 token 只要 0.301 s |
| `docs/OLDER_GPUS.md:338-339`【实测】 | RX 5500 XT 8GB / RX 5700 XT 8GB（AMD！） | IQ3_S 8K decode 15.3 tok/s；Coder IQ1_M 32K：prompt 115/144/149、decode 18.0/20.3/23.3，6/6 needle |
| `bench/results/2026-10-09-community-rtx-3060-0141/README.md`【实测】 | RTX 3060 12GB / **Win11 26300** | 260,000 token 上下文：prompt 863.2 tok/s、decode 37.4、TTFT 301.4 s；128K 时 933.5/38.6/137.3 |

⇒ **NVIDIA 8 GB 单卡 → 27B ternary 的组合，GitHub 上没有一条实测**。官方口径写得很直白：`docs/OLDER_GPUS.md:30`「A card needs enough VRAM to be useful. **12 GB or more is recommended**」。AMD 8 GB 的两行说明这台档位的 Strata decode 就是 15-23 tok/s 量级。

### 5.2 值得抄的 Strata 开关（按对我们的价值排序）

| 开关 | 作用 | 出处 | 备注 |
|---|---|---|---|
| `--prefill-head-alias` | 读 prompt 时把输出头（Q5_K head 417 MiB）显存借给 prompt 缓冲，读完 255 ms 装回 | `docs/PREFILL_HEAD_ALIAS.md` 全文【实测·RTX PRO 2000 Blackwell Laptop 8,151 MiB/Win11/sm_120】 | **8 GB 卡上 prefill 从 256→583 tok/s（+125%）**；chunk 定标 256=185.5 → 2048=667.1 tok/s；代价：短读变慢（1-64 新 token 671→1,311 ms），收益从 513 token 起 |
| `STRATA_KV_PREFETCH=1` | 下一层 KV 上传放独立 stream 与当前层计算重叠 | `docs/KV_PREFETCH.md:1-57`【实测·2×3080】 | 32K prefill −5.3%、64K −4.1%，decode 无收益；默认 off |
| `STRATA_PIN_BY_NEED=1` | WDDM 下按 rank 只钉**非驻留**专家，别把 pin 预算浪费在前缀上 | `src/program/generate.cpp:6588-6607` | 注释原文点名 WDDM：`layers 32-47 stay 100% CPU while ~10 GiB of pinned blobs sit in GPU-resident experts no DMA ever reads` |
| `STRATA_ARENA_PIN_GIB` | WDDM 多卡专家 arena pin 上限（默认 8 GiB） | `generate.cpp:6580-6581` | 单卡用不上，但解释了 WDDM 记账 |
| `--vram-elastic` + `POST /v1/vram` | 把专家缓存分 512 MiB 段交还系统 | `docs/VRAM_ELASTIC.md`【实测·RTX 5070】 | **交还 4.3 GiB ⇒ decode 44→33 tok/s（−25%）**，调用 78 ms；回收后答案逐 token 一致 |
| `--prefill-chunk` 的显存账 | `pf_mib = 160 + chunk*680/1024` | `generate.cpp:6621` | chunk 1024 ≈ **840 MiB**、2048 ≈ 1,520 MiB 预留 —— 8 GB 卡上 chunk 直接吃掉半个池 |
| `STRATA_DMA_BATCH=1`（实验） | 用 `cudaMemcpyBatchAsync` 合并专家上传 | `docs/BATCHED_DMA.md` | 提交延迟 −82.7%，**总传输只 −1.3%，生成速度无收益**；作者自己写「This evidence does not justify changing the default」 |

### 5.3 Strata 的坑（8 GB / Win11 专属）

1. **WDDM 会替你换页**：`docs/DETAILS.md:391-392` 原文——Windows 上引擎对「该留多少余量」按 **1 GiB** 扣（别处 512 MiB），不够就报 `LOW: requests may stall; add --vram-reserve-mib N`。对策：`--vram-reserve-mib` 上调、降 `--max-context`/`--batch`，或把 NVIDIA 驱动的 `CUDA - Sysmem Fallback Policy` 关掉。
2. **chunk 越大越吃预留**：见上表公式，8 GB 上 chunk 1024 就是 840 MiB，等于我们整只池的 1.6 倍。
3. **专家缓存不是免费的**：`VRAM_ELASTIC` 实测交还 4.3 GiB 掉 25% decode；`PIN_BY_NEED` 那段注释说明 WDDM 的 pin 预算是会被前缀偷走的。
4. **8 GB 官方不推荐**：`OLDER_GPUS.md:30`。
5. **架构/构建**：`docs/OLDER_GPUS.md:98-99` CUDA 12 引擎覆盖 sm_60→sm_89 且带 PTX；Windows 安装包 `Strata-0.2.8-windows-x64-setup.exe` 自带「按卡下发引擎」（`docs/INSTALL.md:41-45`），老 N 卡走 CUDA 12 引擎。（本机 `C:/Project/local_model/strata/` 下已有 0.2.8 安装器与 `components/`，另见队友 `docs/Strata对照-8G能跑多大-20261030.md` 的 B 站实测汇总。）

### 5.4 两条路线怎么比（把话说明白）

- **NInfer + 27B 稠密 ternary**：权重必须整份在显存（5.94 GiB），固定开销 ≈6.95 GiB ⇒ 只剩 ~1.2 GiB 给 KV ⇒ **物理天花板 ≈94.7K token**（还要关 MTP 掉到 32 tok/s）；现实可用 40,000 池 / 97-98 tok/s。它的加速手段是**减少搬运**（KVMem 分层、快照、cublas GEMM）。
- **Strata + MoE**：每 token 只激活一部分专家，非驻留专家放内存/SSD 按需调 ⇒ 8 GB 也能开 128K-256K，代价是 **20-40 tok/s**（社区 8 GB 共识，见队友那份文档的评论汇总）与 85-105 GB 权重。
- ⇒ 对用户的诉求「可接受速度下的 200K」：**不换模型就没有 200K**（这不是调参问题，是 5.94 GiB 权重 + 2.6 GiB KV > 8,188 MiB 的算术），GitHub 侧没有任何反例。真正能在 8 GB 上拿 200K 的是「换 MoE 模型 + Strata」，速度 20-30 tok/s。

## 6 · 非多卡加速思路（本轮收集到的，与卡数无关）

| 思路 | 数 | 出处 |
|---|---|---|
| 前缀快照恢复代替冷 prefill | 213K：load 24.32→10.77 s、首 TTFT 47.42→34.16 s；canonical-ready：35.54→13.11 s（−63%）；续问 145.23→36.11 s、单题 TTFT 22.06→0.404 s | CraneBW README【实测·4070Ti SUPER sm_89】 |
| 前缀复用比（不用快照也能吃） | 40,068 token 复用 99.9%，第二轮 TTFT 154→118 ms（池 152→640 页） | fusion-kvmem `docs/03…md:111-116`【实测·4080S】 |
| 把 GEMM 交给 cuBLAS | prefill ×1.43~1.83 | 上游 `performance.md:96-125`【实测·3090】 |
| 跳过 prefill 期的 evidence H2D | 250K prefill 里 ~280 s | `context.cpp:2598-2606`【口径+上游实测】 |
| 磁盘 KV / directstorage | 只买容量与跨重启，永不提速 | 本机 help `logs/help.txt:147-153`；Aurora diskkv 文档组 |
| CPU 侧检索（索引搬出显存） | 256K 下 256.25 MiB 索引 + 144 MiB 查询暂存移出显存（AVX2/FMA） | `https://github.com/5258MF/ninfer-rtx3060-27b` `README-8GB.md:29`【口径·3060 12GB】 |
| 分片/多进程读长文（我们已有） | 每片 ≤池，端到端可验 | `tools/longdoc.py`（本机，含 `--selftest`） |

## 7 · 来源索引（本地 clone 路径 + 上游 URL）

| 仓 | clone 位置 | 本轮用到的关键文件 |
|---|---|---|
| CraneBW/ninfer-ternary-bonsai-ada | `tmp/gh/ninfer-ternary-bonsai-ada` | `README.md:70,164-184`（213K 启动命令）、GGUF/MMQ 实验段、快照恢复段 |
| Aurora-Serendipity/ninfer-8gb-playbook | `tmp/gh/ninfer-8gb-playbook` | `docs/04-8GB显存档位适配.md:35-45,71-79,104-118,129-154,181-197,252-296,302-308`、`docs/01-方案总览.md:58-60` |
| 5258MF/ninfer-rtx3060-27b | `tmp/gh/ninfer-rtx3060-27b` | `README-8GB.md:29,40-44,62-67,120-148,164-169` |
| 1314521gjy/ninfer-fusion-kvmem | `tmp/gh/ninfer-fusion-kvmem` | `docs/03-基础部署后的调优方案.md:55-116`、`docs/11-按卡差异速查.md:86-106`、`src-tree/fusion-engine-src/src/models/qwen3_5/program/storage/context.cpp:1695-1700,2026-2031,2117-2150,2598-2700` |
| ygxiuming/ninfer-bonsai-4070ti | `tmp/gh/ninfer-bonsai-4070ti` | `docs/性能实测.md:5-31`、`vendor/.../docs/performance.md:96-125,377-412`、`docs/device-profiles.md:1-96`、`docs/serving.md:1193,1223`、`RELEASE_NOTES_0.11.0.md:46-58,168,210` |
| paicat1/Bonsai-27B-NInfer | `tmp/gh/Bonsai-27B-NInfer` | `README.md:22,40-50`（nvfp4 229K + prefill 2.85k） |
| G0K0U/kvmem-agent-16gb | `tmp/gh/kvmem-agent-16gb` | 16 G 检索型 agent 配方（本轮未取到新数，属参考） |
| professorpalmer/bonsai-ada-surgery | `tmp/gh/bonsai-ada-surgery` | llama.cpp chunked FA 补丁组（0051/0054/0061），与本项目引擎无关 |
| Niko1221/Strata | `tmp/gh/Strata` | `docs/BATCHED_DMA.md:47-73`、`docs/OLDER_GPUS.md:30,98-99,338-339`、`docs/PREFILL_HEAD_ALIAS.md`、`docs/KV_PREFETCH.md`、`docs/VRAM_ELASTIC.md`、`docs/DETAILS.md:386-392`、`src/program/generate.cpp:6580-6621`、`bench/results/2026-10-09-community-rtx-3060-0141/README.md`、`bench/results/2026-10-05-community-e5-2673v3-rtx-4060ti/README.md` |

本机侧引用：`engine/help-full.txt:27,32,37-48,91,147-153`、`scripts/serve2.sh:24,28-44,58-63,71-78`、`logs/ab_d4p32.log:6`、`logs/probe_x.log:8-9`、`%LOCALAPPDATA%\infer\device-profiles.json`、`models/bonsai2_27b_ternary_ptq1_native_mtp.ninfer` 的 objects 清单（790 项：ptq1 5,605.5 MiB / q8 430.31 MiB / bf16 50.1 MiB）。