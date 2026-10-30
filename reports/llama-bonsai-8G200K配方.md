# llama.cpp 路线：8 GB 显存跑满 262K 窗口的配方（Bonsai 2 27B ternary PTQ1_0）

> 侦察日期：2026-10-30　侦察对象：`professorpalmer/bonsai-ada-surgery`（浅克隆 2713 文件，docs 51 MB）
> 本机：RTX 4060 Ti 8 GB（AD106 / sm_89 / PCIe 4.0 **x8**）+ 31.1 GB DDR5-6000 + Ryzen 7 7800X3D，显示器由 AMD 核显驱动
> 证据规则：只采信带 URL 的一手材料；无数字的听说法标【未核源】。

---

## 0. 一句话结论

**8 GB 跑 262,144 不是把模型变小，而是把 KV cache 拆成「显存里一段 + pinned RAM 里一段」，再配 4 个针对性 patch 把 262k 窗口的固定开销压下去。** 具体是六件事叠加：

1. **分层 KV（tiered KV）**：`--kv-vram-cells N` 把 KV 的第 0..N 个位置放显存、N..Ctx 放 pinned 系统内存，越过 N 的注意力读走 PCIe（patch 0028）；
2. **q3_0 KV 量化**（3.5 bpw，14,336 B/位置，patch 0056）——f16 要 65,536 B/位置，4.6 倍差距；
3. **partial staging**（patch 0047）：任意窗口只常驻 81,920 个位置的搬运缓冲区；
4. **packed 1-bit KQ mask**（patch 0048/0049）：262k×ubatch 的 f16 mask 要 256 MiB，压缩后 1/16；
5. **稀疏 host-tail 读**（patch 0055/0059）：只读相关 page，245k 处 decode 5.3 → 14.2 tok/s；
6. **MTP 投机 + lookup drafting + replay rollback**（0039/0070）：每步多出 token，rollback 只花 7 MiB/位置而不是 150 MiB。

在 2060 SUPER 8 GB 上这套组合给出：窗口 262,144 / 显存里 92,160 个位置 / decode 52.4 · 39.9 · 29.6 · 11.4 tok/s @4k · 64k · 128k · 245k；245k 精确抄写 20/20、needle 23/24、HumanEval 163/164。

**但必须先说清一件事**：这套东西**不能读我们的 `.ninfer` 制品**，要用官方 `PTQ1_0` GGUF（或已嫁接 MTP 头的 6.40 GB 版本）。详见 §5。

---

## 1. 一手证据清单（URL）

| # | 内容 | URL |
|---|---|---|
| 1 | 仓库主页 / 分数卡 / Quick start | https://github.com/professorpalmer/bonsai-ada-surgery |
| 2 | 8 GB 路线全部数据（窗口、位置数、decode 表、内存预算） | https://github.com/professorpalmer/bonsai-ada-surgery/blob/main/docs/8gb/README.md |
| 3 | 启动器旋钮默认值表 | https://github.com/professorpalmer/bonsai-ada-surgery/blob/main/docs/build/KNOBS.md |
| 4 | 72 个 patch 清单（编号 + 说明） | https://github.com/professorpalmer/bonsai-ada-surgery/blob/main/docs/build/PATCHES.md |
| 5 | 唯一文档化的完整 llama-server 命令行（12 GB / q8_0 例，第 112-117 行） | https://github.com/professorpalmer/bonsai-ada-surgery/blob/main/docs/build/README.md |
| 6 | 启动器本体（795 行，显存定格公式在这里） | https://github.com/professorpalmer/bonsai-ada-surgery/blob/main/start-server.ps1 |
| 7 | MTP 头嫁接脚本（含 donor URL） | https://github.com/professorpalmer/bonsai-ada-surgery/blob/main/build/make_mtp_procreations.ps1 |
| 8 | 官方权重（PTQ1_0 5.95 GB） | https://huggingface.co/prism-ml/Ternary-Bonsai-2-27B-gguf |
| 9 | 现成的「PTQ1_0 + MTP 头 + Windows bundle」 | https://huggingface.co/CaryPalmer/Ternary-Bonsai-2-27B-262k-GGUF |
| 10 | GSQ-RCO 变体（6.50 GB，PTQ1_0） | https://huggingface.co/ProCreations/bonsai-2-27b-gsq-rco-gguf |
| 11 | MTP 头 donor（PQ2_0+MTP，7.66 GB） | https://huggingface.co/ProCreations/Ternary-Bonsai-2-27B-MTP |

---

## 2. 它到底怎么做到的：逐项字节账

### 2.1 每位置 KV 字节（16 层注意力 × K/V × 4 头 × 256 维）

| KV 类型 | 每位置字节 | bpw | 262,144 位置全进显存需要 |
|---|---:|---:|---:|
| f16 | 65,536 | 16.0 | 17.2 GB |
| q8_0 | 34,816 | 8.5 | 9.1 GB |
| q4_0 | 18,432 | 4.5 | 4.8 GB |
| **q3_0** | **14,336** | **3.5** | **3.76 GB** |

（patch 0056 引入 q3_0；q3_0 相对 f16 KV 的漂移：KL 0.008 @16k、pPL +0.45%；q4_0 0.0021、q8_0 0.00024）

### 2.2 8 GB 卡上 262k 的三处硬改动（docs/8gb 原文点名的 patch 0047-0049）

| 机制 | patch | 它省了什么（262k 尺度） |
|---|---|---|
| packed 1-bit KQ mask（`--kq-mask-packed`） | 0048 / 0049 | f16 mask = Ctx×ubatch×2 B = **256 MiB** → packed 后 **16 MiB**（131k 时 128 → 8 MiB） |
| 共享 CUDA pool（主上下文与 MTP draft 共用一个 VMM pool） | 0037 / 0045 / 0046 | ~**48-51 MiB**（2060S 实测省 51 MiB，直接换成更高的显存线） |
| partial staging（`GGML_CUDA_KV_TIER_STAGING_FRAC`） | 0047 | 不再给「整个窗口」留搬运缓冲区，只 stage **81,920** 个位置 → 262k 时省约 **1.0 GB** |

### 2.3 显存线的定义

`--kv-vram-cells N` = 前 N 个位置（dense，常驻显存），N..Ctx 在 pinned RAM。
2060 SUPER 8 GB + q3_0 的 N = **92,160**；对应 pinned tail =(262,144−92,160)×14,336 B ≈ **2.44 GB**（这就是「需要 ≥24 GB 系统内存」的来源）。
官方文档原句（docs/8gb/README.md 第 5 行）：

> "About 92,160 positions stay in VRAM; the rest of the cache is in pinned system RAM and is read over PCIe."

### 2.4 稀疏读（能到 245k 的关键，patch 0055/0059）

`GGML_CUDA_FA_SPARSE=B,P,R`：host tail 按 P=64 个位置一页，只读需要的 page。
8 GB 预设默认 **auto**（每 16k 带实测 dense vs sparse，快 >3% 才切），标定文件 `%LOCALAPPDATA%\bonsai\sparse-calib.txt`。
2060S 实测：160k 9.1 → 19.6 tok/s，245k 5.3 → 14.2 tok/s；4070 160k 13.6 → 27.6。

---

## 3. 完整启动参数（8 GB 预设，复刻版）

启动器 `start-server.ps1` 第 760 行的真实调用形式：

~~~powershell
& .\llama-server.exe @SlotArgs @TierArgs @RamArgs @SpecArgs @BsArgs @BudgetMsgArgs @HarnessArgs @MmprojArgs @FitArgs `
  --reasoning-budget 20480 -n 24576 -m <model> -ngl 99 -fa on -c 262144 -np 1 -b 2048 -ub 512 `
  -ctk q3_0 -ctv q3_0 --host 127.0.0.1 --port 8080 --alias bonsai-2-27b --jinja --prio 2 --poll 100 `
  --metrics --api-key <key> --temp 1.0 --top-p 0.95 --top-k 20
~~~

把上面那些 splat 数组展开成**等价的一条完整命令行**（8 GB 卡 + MTP 头 + 31 GB 内存 → 走到 262k 分支）：

~~~bat
set LLAMA_MTP_DRAFT_UBATCH=256
set GGML_CUDA_FA_PREFILL_F16=32768
set GGML_CUDA_FA_CHUNK=32768
set LLAMA_ARG_CHECKPOINT_EVERY_NT=8192
set LLAMA_ARG_KQ_MASK_PACKED=1
set GGML_CUDA_SHARED_POOL=1
set GGML_CUDA_BATCH_INVARIANT=1
set LLAMA_RS_REPLAY=1
set GGML_CUDA_KV_TIER_STAGE_MIN_Q=9
set GGML_CUDA_KV_TIER_STAGING_FRAC=0.312500
set GGML_CUDA_FA_SPARSE=12288,64,1024
set GGML_CUDA_FA_SPARSE_FAST=1
set GGML_CUDA_FA_SPARSE_MIN_HOST=16384
set GGML_CUDA_FA_SPARSE_AUTO=1
set GGML_CUDA_FA_SPARSE_FRAC=0.25
rem GGML_CUDA_KV_TIER_DEMOTE_FRAC 由启动器算：(dense线−sparse线)/262144

llama-server.exe ^
  -m models\Ternary-Bonsai-2-27B-PTQ1_0-mtp-procreations-q4head.gguf ^
  --kv-vram-cells <N> ^
  -ngl 99 -fa on -c 262144 -np 1 -b 2048 -ub 512 -ctk q3_0 -ctv q3_0 ^
  --spec-type ngram-mod,draft-mtp --spec-draft-n-max 1 --spec-draft-n-max-tail 2 ^
  --spec-draft-window 16384 --spec-lookup-n-max 32 -ctkd q3_0 -ctvd q3_0 ^
  --reasoning-effort-allow medium --reasoning-effort-fallback medium ^
  --reasoning-max-tokens-floor 24576 --reasoning-budget 20480 ^
  --reasoning-budget-message "Now produce the complete answer." ^
  --backend-sampling --cache-ram 4096 --ctx-checkpoints 32 --fit off ^
  --host 127.0.0.1 --port 8080 --alias bonsai-2-27b --jinja --prio 2 --poll 100 --metrics ^
  --temp 1.0 --top-p 0.95 --top-k 20 -n 24576
~~~

> `--kv-vram-cells` 的 N 不要手填，让启动器按当次空闲显存算；手填时按 §6 公式或从 92,160 起步。
> `GGML_CUDA_KV_TIER_STAGING_FRAC = 81920 / Ctx` = 0.312500 @262k，0.625 @131k。

**官方文档里唯一一条成文的 llama-server 全命令**（Linux / 12 GB / q8_0 例，docs/build/README.md:112-117）：

~~~bash
llama-server -m Ternary-Bonsai-2-27B-PTQ1_0-mtp-procreations.gguf -ngl 99 -fa on -c 262144 -np 1 \
  -ctk q8_0 -ctv q8_0 --kv-vram-cells 110000 \
  --spec-type draft-mtp --spec-draft-n-max 2 --spec-draft-n-max-tail 4 --spec-draft-window 16384 \
  -ctkd q8_0 -ctvd q8_0 --reasoning-effort-allow medium --reasoning-max-tokens-floor 24576 \
  --reasoning-budget 20480 --chat-template-kwargs '{"reasoning_effort":"medium"}' \
  --jinja --host 127.0.0.1 --port 8080
~~~

### 3.1 模型文件候选（启动器 models\ 目录，按序取第一个满足最小字节的）

| 文件名 | 最小字节 | 说明 |
|---|---:|---|
| `Ternary-Bonsai-2-27B-PTQ1_0-mtp-procreations-q4head.gguf` | 6.18e9 | **8 GB 预设优先**，MTP 头从 Q8_0 重压成 Q4_0，省 214 MiB |
| `Ternary-Bonsai-2-27B-PTQ1_0-mtp-procreations.gguf` | 6.39e9 | 官方 trunk + Q8_0 MTP 头 |
| `Ternary-Bonsai-2-27B-PTQ1_0-mtp-lean.gguf` | 6.29e9 | 精简头 |
| `Ternary-Bonsai-2-27B-PTQ1_0.gguf` | 5.9e9 | 无 MTP 头 → 不能投机、自动降 131k |
| `Ternary-Bonsai-2-27B-PQ2_0.gguf` | 7.1e9 | 更高质量量化 |

找不到就抛：`No complete Bonsai 2 GGUF in models\`。

### 3.2 开启 262k 的四个前置条件（缺一即降 131,072）

`$Small262 = $Small && $Tier && $Has262 && $RamGiB ≥ 24 && $Spec ≠ 0 && 文件名匹配 '-mtp'`

1. 显存总量 ≤ **8,704 MiB**（或 `BONSAI_8GB=1` 强制）；
2. 二进制自检：`llama-server --help` 里有 `--kq-mask-packed`，且 `ggml-cuda.dll` 字节串含 `GGML_CUDA_KV_TIER_STAGING_FRAC`；
3. **系统内存 ≥ 24 GB**；
4. 模型文件名含 `-mtp`（有嫁接的 MTP 头）。

---

## 4. 补丁说明（72 个 patch，基于 PrismML-Eng/llama.cpp @ adfffbe）

分支：`professorpalmer/llama.cpp-ada-ternary`，线 `bonsai-q8-product`；`build/build_linux.sh` 用 `git am` 全量打。

| patch | 内容 | 相关开关 |
|---|---|---|
| 0028 | **tiered KV**：KV cache 分显存段 + 系统内存段 | `--kv-vram-cells`（上游 PR #285，拆成 #319/#320/#321/#322/#323） |
| 0037 | 主上下文与 MTP draft 共用一个 CUDA VMM pool | `GGML_CUDA_SHARED_POOL=1` |
| 0038 / 0043 | prefill 走 f16 路径 | `GGML_CUDA_FA_PREFILL_F16` |
| 0039 | 稀疏 lookup 投机（ngram 字典草稿） | `--spec-lookup-n-max` |
| 0041 | tiered prefill（分段写 KV） | — |
| 0045 / 0046 | 共享 pool 与 MTP 双流排序；每 N token 存 checkpoint | `--checkpoint-every-nt` |
| **0047** | **partial staging**：只常驻 stage 缓冲区 | `GGML_CUDA_KV_TIER_STAGING_FRAC`、`GGML_CUDA_KV_TIER_STAGE_MIN_Q` |
| **0048 / 0049** | **packed 1-bit KQ mask** | `--kq-mask-packed` / `LLAMA_ARG_KQ_MASK_PACKED` |
| 0051 | chunked FA（分块遍历长尾） | `GGML_CUDA_FA_CHUNK` |
| 0053 | host tail 时关闭 CUDA graph | — |
| **0055** | **稀疏 host-tail 读** | `GGML_CUDA_FA_SPARSE=B,P,R`、`_FAST`、`_MIN_HOST` |
| **0056** | **q3_0 KV 类型**（3.5 bpw） | `-ctk q3_0` |
| **0059** | 稀疏 auto 标定 + late reserve | `GGML_CUDA_FA_SPARSE_AUTO`、`GGML_CUDA_KV_TIER_DEMOTE_FRAC`、`GGML_CUDA_FA_SPARSE_FRAC` |
| 0060 / 0061 | Turing 上 NCOLS2=2 的 FA 配置 | — |
| 0062 / 0063 | slot draft sidecar（存档时保存草稿状态） | — |
| **0070** | **recurrent replay**：rollback 只保留一块 144 MiB 平面 | `LLAMA_RS_REPLAY=1` |
| 0072 | quantized-KV FA 走 MMA、去 pipeline stage | — |

---

## 5. 兼容性判定：我们的制品能不能直接喂给它？

### 5.1 结论表

| 制品 | 能不能直接用 | 依据（我读 GGUF 头得到的硬数据） |
|---|---|---|
| **我们的 `bonsai2_27b_ternary_ptq1_native_mtp.ninfer`**（6,394,697,216 B，magic NINFER） | ❌ **不能** | 不是 GGUF 容器；仓库里对 `ninfer`/`NINFER` 的引用数为 **0**（全仓 grep 无命中），也没有任何转换脚本 |
| **`prism-ml/Ternary-Bonsai-2-27B-PTQ1_0.gguf`**（5.95 GB） | ✅ 能（trunk 一致） | 官方 PTQ1_0，fork 的 `GGML_TYPE_PTQ1_0=143` kernel 直接吃 |
| **`CaryPalmer/...-PTQ1_0-mtp-procreations.gguf`**（6.40 GB） | ✅ **最推荐**：已嫁接 MTP 头 | v3 / 866 张量（851 + `blk.64.nextn.*` 15 个）/ 类型 {0 F32, 8 Q8_0, 30 BF16, 143 PTQ1_0} / ctx 262144 |
| **`ProCreations/bonsai-2-27b-gsq-rco-PTQ1_0.gguf`**（6.50 GB） | ⚠️ 能加载 trunk，但**没有 MTP 头** | v3 / 851 张量 / arch qwen35 / ctx 262144 / 类型 {0, 2 Q4_0, 30 BF16, 143 PTQ1_0} / **无 `blk.64.*`** → `$Spec=0`，启动器不给 262k，decode 掉一半（官方记录：138k 处有 MTP 25 tok/s vs 无 MTP 11.6 tok/s） |
| 原版 stock llama.cpp | ❌ 不行 | 权重带 `prism.hadamard.*` 元数据（block_size 1024、normalized-sylvester-walsh-hadamard、`inverse_weight_names=[token_embd.weight]`、`gdn_v_grouped=True`），必须 fork 的 Hadamard 处理才正确 |

> GSQ-RCO 那个 6.50 GB 文件是同一 base（`prism-ml/Ternary-Bonsai-2-27B-gguf` + `Qwen/Qwen3.8-27B`）上的第三方 ternary 精调：主格式同为 **PTQ1_0 / group 128**，另把少数整矩阵换成 Q4_0 以压进 6.5 GB；自报 WikiText-2 PPL 8.1627 vs 原版 8.6690（−5.84%），但四个基准的配对置信区间都含 0，作者自己写「不构成统计上明确的精度提升」。**可当 trunk，不能当 262k 配方**（没头）。

### 5.2 官方 MTP 头嫁接配方（build/make_mtp_procreations.ps1，一手）

~~~powershell
# donor = ProCreations/Ternary-Bonsai-2-27B-MTP 的 PQ2_0+MTP（7.66 GB），只稀疏抓 blk.64.*（约 450 MB）
$Donor = "https://huggingface.co/ProCreations/Ternary-Bonsai-2-27B-MTP/resolve/main/Ternary-Bonsai-2-27B-PQ2_0-MTP-Q8_0.gguf"
python surgery\hf_sparse_fetch.py $Donor models\donor\procreations-pq2-mtp.sparse.gguf "blk.64."
python <bonsai2-small-gpu>\graft\tools\extract_head.py <sparse> <head> --no-embed-tokens
python <bonsai2-small-gpu>\graft\tools\merge.py models\Ternary-Bonsai-2-27B-PTQ1_0.gguf <head> models\Ternary-Bonsai-2-27B-PTQ1_0-mtp-procreations.gguf
# 证明：--strip 掉头以后，文件 SHA256 必须等于官方 PTQ1_0
~~~

再跑 `build\make_mtp_q4head.ps1` 把 `blk.64.*` 从 Q8_0 重压成 Q4_0（省 214 MiB，8 GB 预设首选）。两个脚本都要求 `vendor\prism-llama\gguf-py` 存在（我们的浅克隆里没有这个目录，要按 docs/build 的构建流程拉）。
**省事路径**：直接下 `CaryPalmer/Ternary-Bonsai-2-27B-262k-GGUF` 里已经嫁接好的 6.40 GB 文件 + `bonsai-bundle-win-x64.zip`（0.62 GB，含编好的 `llama-server.exe`/`ggml-cuda.dll`，带 sm_75/86/89 + compute_89 PTX，Ada 直接可用）。

---

## 6. 我们机器（4060 Ti 8 GB + 31 GB）上的推算

> 以下全部是**按启动器公式算出来的**，不是实测。公式来自 `start-server.ps1` 第 356-391 行；我用它反推 2060 SUPER 得到 92,160，与官方文档一致（对应 FreeMiB ≈ 7,791），说明公式复刻正确。

8 GB / 有 MTP（$Spec=1, $SpecDeep=2, $Replay=1）时的固定开销：

~~~text
FixedMiB = 6531
         + (-142 + 7×(max(1,2)-1))             = 6531 - 135 = 6396   # replay：每个 draft token 省 142 MiB
         + (MaskMiB - 131072×ub×2/1MB - Pool)  = -160 → 6236         # packed mask 16 MiB，基线项 128 MiB，pool 48
         + 64（稀疏 page bounds 预留）         → 6300
Margin     = 225 MiB（有投机时）
StageCells = 81,920；staging = 81920×14336/16 = 70 MiB
SparseCellBytes = 16×4×(2×256+2)/64 = 514 B/位置
dense 线 = floor(((Free−225−6236+64)×1MB − 70MiB) / 14,336 / 256)×256
~~~

| 启动时空闲显存 | dense 显存线（位置） | 稀疏线（late reserve 后） | pinned RAM tail |
|---:|---:|---:|---:|
| 7,300 MiB | 56,064 | 43,520 | 2.95 GB |
| 7,500 MiB | 70,656 | 58,880 | 2.75 GB |
| 7,700 MiB | 85,504 | 73,984 | 2.53 GB |
| **7,791 MiB（= 2060S 实测点）** | **92,160** | 80,896 | 2.44 GB |
| 7,900 MiB | 100,096 | 89,088 | 2.32 GB |
| 8,000 MiB | 107,264 | 96,768 | 2.22 GB |

**本机两条实测输入（2026-10-30 09:3x）：**

~~~text
nvidia-smi : RTX 4060 Ti, 8188 MiB total, 7459 MiB used, 491 MiB free
             driver 616.92, compute_cap 8.9, PCIe 4.0 x8
OS         : 系统内存 31.11 GB，空闲 commit 15,259 MiB
~~~

解读：

- **眼下没法测**：7,459 MiB 已被占用（生产引擎在 8091/8081）。这时启动器要么抛 `Tiered KV: only N cells fit in VRAM...`，要么掉到 131k。要测必须先空出显存——那等于停生产，本报告**不执行**，也建议你不要在同一个窗口里做。
- **空出来以后**：我们是 headless（显示走 AMD 核显），空闲显存应能到 ~7,900-8,000 MiB，比 2060 SUPER 的 7,791 略高 → dense 线预计 **~98k-107k**（比 92,160 高 6-16%），pinned tail **2.2-2.3 GB**。
- **131k 几乎是全在显存里的档**：线在 ~100k 时，131,072 只有 ~30k 个位置落到 RAM（≈0.4 GB），decode 基本不吃 PCIe。**先验 131k，再上 262k。**
- **内存够但卡边**：31 GB 过了 24 GB 硬门槛，但 24-47 GB 档固定 `--cache-ram 4096 --ctx-checkpoints 32`（32×~170 MiB ≈ 5.4 GB）+ 模型 mmap 5.9 GB + tail 2.3 GB ≈ 13.6 GB；当前空闲 commit 只有 15.2 GB。先验阶段建议 `BONSAI_RAM_BUDGET=0`（回服务器默认）或手填 `--cache-ram 1024 --ctx-checkpoints 8`。
- **PCIe 是短板，而且 4060 Ti 只有 x8**：文档写 "RTX 4060 / 4060 Ti / 5060-class cards use 8 lanes, which on a PCIe 4.0 board is about the same link as this card"（≈2060 SUPER 的 13 GB/s）。所以 **245k 深水区 decode 大概率还是 11-14 tok/s，不会因为我们代数新而更快**。稀疏 auto 在 Ada 上的收益（4070: 160k 13.6→27.6）比 Turing 明显，这是我们唯一可能反超 2060S 的地方。

---

## 7. 最小可复现验证步骤（只写，不执行）

> 前置禁令：全程不碰 8091 / 8081；新服务只绑 127.0.0.1、端口用 **18080**；不改 C:/Project/local_model 下任何配置脚本；仓库放**纯 ASCII 短路径**（如 C:\bonsai\，避开中文路径与 MAX_PATH）。

### 阶段 A：拿二进制与权重（约 7 GB 下载，1 次）

1. `git clone --depth 1 https://github.com/professorpalmer/bonsai-ada-surgery C:\bonsai\srv`（走代理）。
2. 下 bundle：Release 页的 `bonsai-bundle-win-x64.zip`（README Quick start 第 1 步），或镜像 `https://huggingface.co/CaryPalmer/Ternary-Bonsai-2-27B-262k-GGUF/resolve/main/bonsai-bundle-win-x64.zip`（0.62 GB），解压进 `C:\bonsai\srv`。
3. 下权重（**用已嫁接 MTP 头的那个**）：`https://huggingface.co/CaryPalmer/Ternary-Bonsai-2-27B-262k-GGUF/resolve/main/Ternary-Bonsai-2-27B-PTQ1_0-mtp-procreations.gguf`（6.40 GB）→ `C:\bonsai\srv\models\`。想再省 214 MiB 就按 §5.2 跑 `make_mtp_q4head.ps1` 生成 `-q4head.gguf`。
4. 自检（不发请求、不起服务）：`C:\bonsai\srv\llama-server.exe --help | findstr /C:"kq-mask-packed" /C:"kv-vram-cells" /C:"q3_0"` → 三个都命中才算 bundle 版本对；再 `findstr /C:"GGML_CUDA_KV_TIER_STAGING_FRAC" ggml-cuda.dll`（启动器的 Has262 自检就是这么做的）。

### 阶段 B：131k 冷启（先证明能跑，不追 262k）

5. 先看显存：`nvidia-smi --query-gpu=memory.total,memory.free --format=csv`。**free < 6,500 MiB 就别往下走**（会抛 cells 不足）。
6. 干跑：把 §3 的完整命令行**手抄一份**（不用启动器），只改 `-c 131072`、`--port 18080`、`--kv-vram-cells` 按公式算的值，先不加 `--api-key`，确认参数被接受（这一步就是"干跑"，不依赖启动器有没有 dry-run 开关）。
7. 起 131k：`set BONSAI_CTX=131072` + `set BONSAI_PORT=18080` + `set BONSAI_SLOT_SAVE_PATH=off`，然后 `powershell -File start-server.ps1`。
   **验收断言（启动日志逐条对）**：
   - `8gb    preset on (8188 MiB card; ...)`
   - `window 131072 / q3_0 (...)`
   - `kv     tiered: cells 0..N in VRAM, N..131072 in system RAM (VRAM margin 225 MiB); shared CUDA pool on; packed KQ mask (M MiB saved)`
   - `kv     staging buffer for cells N..N+81920 ...`
   - `spec   draft 1 (2 past the VRAM line), draft window 16384 (MTP on); lookup drafting up to 32`
   - `ram    31 GB RAM: prompt cache 4096 MiB, 32 checkpoints per slot`
8. 冒烟：`curl http://127.0.0.1:18080/v1/models` → 应见 `bonsai-2-27b`；再发一条 32 token 的 `/v1/chat/completions`，看返回里的 `timings.predicted_per_second`。

### 阶段 C：262k（只有 B 全绿才做）

9. `set BONSAI_CTX=262144`（其实不必设：满足 §3.2 四条会自动 262,144），重启同一条命令。
   **验收断言**：`window 262144 / q3_0 (8 GB default)`、`kv tiered: cells 0..N ...`（N 应在 85k-107k）、`kv sparse host-tail reads: auto (dense line N; ...)`。
10. 量三个深度（同一段可复现 prompt，取 `timings.predicted_per_second`）：
    - 4k：期望 ~45-55 tok/s（2060S 52.4，同链路）；
    - 128k：期望 ~25-30；
    - 245k：期望 ~10-14（PCIe x8 上限）。
    单条 245k prompt 的 prefill 要跑约 25 分钟（2060S 1,489 s / 164 tok/s），**先确认愿意等**。
11. 功能对拍（10 分钟版）：一条 200k 级 haystack 放 8 个 needle、问 8 个问题，记命中数；再让它逐字抄写一段 2k token 代码，逐字节比对。2060S 基线：needle 23/24、抄写 20/20。
12. 「不值得」判据：若 245k decode < 8 tok/s 或 needle < 6/8，就停在 131k（此时 tail 几乎为 0，PCIe 不参与），200k 交给现在的 native 路线。

### 阶段 D：清理

13. 关掉 18080 的服务（Ctrl+C 或关窗口），`nvidia-smi` 确认显存回到测试前水平，确认 8091/8081 从未被触碰。

---

## 8. 风险与限制

1. **不能和 .ninfer 混用**：容器不同（NINFER vs GGUF），仓库里没有转换器。要么下 GGUF，要么放弃这条路。
2. **必须用 fork 二进制**：权重带 `prism.hadamard.*`，stock llama.cpp 会算错（不是"效果差"，是"输出乱"）；也别拿别的 llama.cpp 二进制凑。
3. **PCIe x8 是硬天花板**：深水区 decode 由 PCIe 决定，不是 GPU 算力。4060 Ti 与 2060S 同级链路，别期待 245k 处更快。
4. **内存卡边**：31 GB 刚过 24 GB 门槛，而 4096 MiB cache + 32 checkpoints + 5.9 GB mmap + 2.3 GB tail ≈ 13.6 GB，当前空闲 commit 15.2 GB。先用小 cache 跑。
5. **3.5 bpw KV 的质量代价**：q3_0 相对 f16 KV：KL 0.008 @16k、pPL +0.45%；官方在 245k 仍给出抄写 20/20、needle 23/24。我们的任务若对逐字精确敏感，先在 16k 做 A/B。
6. **单槽（-np 1）**：这是单会话配方，不适合并发服务。
7. **换权重不等于免费升级**：GSQ-RCO 的 PPL 改善置信区间含 0，属"可试不可赌"。
8. **Windows 特有坑**：长路径（用 C:\bonsai\）、中文路径、OneDrive 同步目录、Defender 实时扫描 6 GB 文件会拖慢首次加载。
9. **本报告没有执行任何启动/停止动作**；§6 的本机显存线是公式推算，标记为**未实测**。

---

## 9. 关键数字速查

| 项 | 2060 SUPER 8 GB（官方实测） | 我们 4060 Ti 8 GB（推算/待测） |
|---|---|---|
| 窗口 | 262,144 | 262,144（需 ≥24 GB 内存 + `-mtp` 文件） |
| KV 类型 / 每位置 | q3_0 / 14,336 B | 同 |
| 显存线（位置） | 92,160 | ~98k-107k（free 7.9-8.0 GB 时） |
| pinned tail | 2.44 GB | 2.2-2.3 GB |
| decode 4k / 64k / 128k / 245k | 52.4 / 39.9 / 29.6 / 11.4 | 待测（期望 ~50 / ~38 / ~28 / ~12） |
| prefill 4k / 245k | 417 / 164 tok/s | 待测 |
| 245k 质量 | 抄写 20/20、needle 23/24 | 待测 |

---

## 10. 未核源 / 待核项

- **GitHub Releases 资产清单**：`api.github.com` 返回 403（rate limit），只从 README 与 HF 镜像确认 `bonsai-bundle-win-x64.zip`（0.62 GB）存在；Release 页确切 tag 与资产名**未逐条核对**。
- bundle 是否需要 VC++ 运行库、解压后是否真含 sm_89 的 `ggml-cuda.dll`：docs/build/README.md 称含 sm_75/86/89 + compute_89 PTX，**未在本机解压验证**。
- `start-server.ps1` 是否有 dry-run 开关：**未核**（阶段 B 第 6 步给了不依赖它的替代路径）。
- 4060 Ti + PCIe 4.0 x8 上稀疏 auto 的实际收益曲线：官方只有 2060S 与 4070 数据，**Ada + x8 组合无官方数据**。
- 启动器会不会把 31.11 GB 读成 31（`[math]::Round` → 31，过 24 GB 门槛）：**未在本机跑启动器验证**。
- 「8 GB 两周从 65,536 → 262,144」的时间线来自 docs/8gb 的自述，未与 git 历史逐条比对。
