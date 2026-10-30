# NInfer-KVMem on an RTX 4060 Ti 8 GB — deployment analysis

**Target machine**: Windows 11 Pro 26100 x64 · Ryzen 7 7800X3D (8C/16T, Zen4, 96 MB L3) · 32 GB DDR5-6000 (2×16) · Gigabyte B650M AORUS ELITE AX ICE · RTX 4060 Ti 8 GB (Ada, sm_89, 34 SM, 288 GB/s), driver 616.92 / CUDA UMD 13.4, **also the display card** (OBS, QQ, GameViewer running).

**Repo under analysis**: `repos/ninfer-fusion-kvmem` @ local clone (2776 files, Apache-2.0). All `file:line` citations are relative to that repo root unless prefixed with `src-tree/fusion-engine-src/` (engine source). Nothing was executed on the target machine — every number below is either quoted from the repo's own receipts or explicitly derived, and is tagged.

**Evidence tags used throughout**
- 【实测·本机】 = measured by the author on his RTX 4080 SUPER (sm_89, 16 GB) — the main local measurement card.
- 【实测·他机】 = measured on a *different* machine in a receipt shipped with the repo (RTX 4070 Laptop 8 GB, RTX 5070 Ti 16 GB, RTX 5060 Ti 16 GB, vendor runs).
- 【外推】 = my own arithmetic from measured numbers (bandwidth / host-overhead scaling), not in the repo.
- 【未验】 = the repo itself marks it unverified, or no measurement exists.

---

## 0. Verdict (read this if you read nothing else)

| Question | Answer | Basis |
|---|---|---|
| Is the engine **supported** on sm_89 / 4060 Ti? | **Yes, compiled-in and whitelisted** — sm_89 is a first-class arch (`CMakeLists.txt:3`, `CMakeLists.txt:14-18`), and every sm_89 binary includes the arch-89 code path. But the 4060 Ti is a **non-tuned** card: it is absent from `device_profiles.json`, so it self-calibrates on first start (20–40 s) and runs on *measured-at-runtime* route tables (`src-tree/fusion-engine-src/docs/device-profiles.md:23-31`). | 【实测·源码】 |
| Is it **verified** on an 8 GB card? | **Yes, on exactly one 8 GB card** — RTX 4070 Laptop 8 GB (sm_89), full end-to-end receipt `verify/回执-外部-8G-完整测试-20261008.md` (233 lines): 12/12 quality, 11/11 structured errors, context ceiling **38,016 tokens**, decode **45–84 tok/s**. **Not verified on a 4060 Ti, and never with a compositor + OBS + QQ resident.** | 【实测·他机】 |
| Can the user **get the artifacts**? | **This is the blocker, not the GPU.** Repo and public Release ship **no weights** (`README.md:100`). The one artifact that fits 8 GB — `bonsai2_27b_ternary_ptq1[_native_mtp].ninfer`, 5.52 / 5.94 GiB — is *reproducible* from public inputs via the `bonsai2_27b_ternary` recipe (`src-tree/fusion-engine-src/docs/weight-conversion.md:116-152`), **but this host could not confirm those inputs exist**: `huggingface.co` resolves to a non-public IP here and `web_search` has no API key. Conversion also needs Python 3.11 + PyTorch and a third input (base Qwen3.8-27B config/tokenizer). | 【实测·本机环境】 + 【未验】 |
| Do the **other artifacts** fit 8 GB? | **No.** v3 ternary 7.28 GiB ⇒ ❌ “可用 − 权重 = 0.12–0.32 GiB < 固定开销”，池建不起来（外推）(`配方-8GB档-实测支撑-20261008.md:87`). PQ2+dflash2 8.16 GiB, GSQ/Swift 13.4 GiB ⇒ 直接排除 (`docs/12-给接收方-agent-的操作手册.md:85,90`). | 【未验/外推】 |
| Will it run **with OBS/QQ/GameViewer up**? | **Not reliably.** The engine sizes its pool from *post-weights free VRAM* (`--kv-capacity auto`; `docs/05-已知问题与禁忌.md:60-61`) and the reference 8 GB run only had **291 MiB** of desktop baseline (`verify/回执-外部-8G-完整测试-20261008.md:17`). Every 1 GiB the compositor/OBS holds costs roughly 900 pages ≈ 58k tokens of pool. Expect a start FATAL or a pool under 20k. | 【外推，机制已实测】 |
| Realistic **decode** on the 4060 Ti | **≈55–90 tok/s** with `--spec mtp` (median ~70), **≈35–50 tok/s** without, **≈700–1,000 tok/s** prefill at 20k prompt (chunk 512), TTFT 20k ≈ **20–30 s**. | 【外推】 from `verify/回执-外部-8G-完整测试-20261008.md:127-141` |
| **Recommendation** | Usable as a **single-user, single-request, ≤38k-context, text-only** assistant with a 27B ternary model — *if* a PTQ1 artifact can be obtained. For anything agentic/multi-turn/tool-chain, the author's own field verdict is negative (`docs/04-卡死与循环的防治.md:213`). Budget a day of build + calibration work first. | synthesis |

---

## 1. What this engine actually is

- **A from-scratch C++/CUDA inference engine, not a llama.cpp fork and not vLLM.** Single resident model on one GPU; `--max-concurrency` bounded FIFO 1–8 with no preemption; **no tensor parallelism** (only a Linux multi-GPU layer pipeline via `--devices`, ≤8 GPUs) — stated as the engine's design premise in `src-tree/fusion-engine-src/AGENTS.md`.
- **Lineage**: baseline `NInfer 0.11.0-rtx3090`; this repo is a *downstream derivative* that fuses three things — upstream NInfer (`Neroued/ninfer`, `ashalliants/ninfer-3090`, `iamwavecut/ninfer-3090`), the **KVMem ring** from `tancau/ninfer-kvmem-ring`, and the strategy layer `kvmem/kvmem-qw3` by Di Chai (`README.md:358-360`, `NOTICE.md`). Everything is Apache-2.0 except the model weights (`NOTICE.md:94`).
- **Architecture support**: `Qwen3_5ForCausalLM` / `Qwen3_5MoeForCausalLM` plus `Qwen4Exp` (`Architecture::Qwen4Exp`, `src/models/registry.cpp:15-20`, impl `src/models/qwen3_8_flash_next/`) — i.e. a Qwen3.5/3.6/3.8 family engine. The only artifacts that fit 8 GB are **ternary Bonsai 2 27B** builds of that geometry.
- **What "KVMem" adds** (the whole point of the project): a device KV pool far smaller than the logical context (README's canonical example: `--max-context 262144` with `--kv-capacity 17920` = 280 pages), with a host-backed KV layer (pinned RAM), content-scored page retrieval, and a sharded gateway that splits over-pool prompts. Page = 64 tokens (`src/core/paged_kv_cache.h:21`). Only 16 of 64 layers carry KV in the 27B ternary geometry (3 linear : 1 full attention), 25,728 B/token (`README.md:43`).
- **Release binary for this GPU exists**: `ninfer-serve-89.exe` (sm_89), tag `engine-v0.11.0-kvmem-20261003`, listed at `README.md:89-94`. **It is not a runnable kit**: no DLLs, no model (`README.md:96`), and the 2026-10-08 binary that the 8 GB receipt used (`795,030,528 B`, sha256 `9FA7490B…1CA41EB`, `verify/回执-外部-8G-完整测试-20261008.md:13`) is a **beta distribution build that is not the public asset** — source and Release must be judged separately (`README.md:98`).

---

## 2. Is a 4060 Ti 8 GB supported? (the exact whitelist chain)

| Gate | Content | 4060 Ti result |
|---|---|---|
| CMake arch guard | `FATAL_ERROR` unless `CMAKE_CUDA_ARCHITECTURES` is one of 80, 86, 89, 120a (`CMakeLists.txt:14-18`); header comment “supports Ampere sm_86 and early Ada sm_89, plus sm_80 (GA100) as an unmeasured compatibility target” (`CMakeLists.txt:3`) | ✅ 89 accepted |
| sm_8x compatibility macro | `NINFER_SM8X_COMPAT=1` defined globally for 80/86/89 (`CMakeLists.txt:33-38`); `NINFER_PDL` (programmatic dependent launch) requires 120a | ✅ compat paths compile in |
| Model registry whitelist | arch is a build-time property, not a per-card lookup; no 4060 Ti entry needed | ✅ no rejection |
| `device_profiles.json` (tuned route tables) | exactly 7 hardware classes: 3090-sm86 (82 SM), 4090-sm89 (128), 4080 SUPER-sm89 (80), 5090-sm120 (170), 3× RTX PRO 6000 sm120 (188 each) — `src/runtime/engine/device_profiles.json:334` for the 4080 SUPER “built in … calibrated on this machine 2026-09-30” entry | ❌ **no 4060 Ti, no 8 GB card at all, no laptop part** |
| Fallback behaviour | undocumented-but-supported cards “会出现自适应” — self-calibration at first start, 20–40 s before weights load, result cached to `%LOCALAPPDATA%\ninfer\device-profiles.json` (`docs/12-给接收方-agent-的操作手册.md:188`, `src-tree/fusion-engine-src/docs/device-profiles.md:23-31`) | ✅ runs **untuned (跑得起来、未调优)** |

**Consequence.** `README.md:252-253` states that outside the measured list “路由表是空表（Unmeasured）= 跑得起来、未调优”. So the 4060 Ti will run, but every op route is chosen by a one-shot 20–40 s calibration instead of a re-measured route table. The engine's own docs warn that inherited route tables are only valid for the exact card/config (`README.md:264`), and upstream's sm_120a schedules were off by 12–41 % when ported to sm_86 — expect a similar penalty here, not a rejection. **Nothing in the repo has ever executed on a 4060 Ti.**

---

## 3. Model artifacts: what exists, what fits, how it is obtained

### 3.1 The public artifact ledger (all 27B ternary/quantised, text-only)

| Artifact | Resident size | 8 GB verdict | Source |
|---|---|---|---|
| `bonsai2_27b_ternary_ptq1.ninfer` (the `start-8g.bat` default) | **5.52 GiB** | ✅ **the only sane target**: whole card 5.52 + 1.32 = **6.84 GiB**, “余 0.6–0.8 GiB” (`配方-8GB档-实测支撑-20261008.md:19,60`) | 【实测·他机】 |
| `bonsai2_27b_ternary_ptq1_native_mtp.ninfer` | **5.94 GiB** (`meta.size = 6,381,571,072 B`) | ⚠️ runs, but pool capped at **594 pages = 38,016 tokens** (vs 1,038 pages / 66,432 without the head) (`verify/回执-外部-8G-完整测试-20261008.md:14,30,206`) | 【实测·他机】 |
| v3 ternary (`…mtponly.ninfer`) | 7.13 GiB | ❌ no (fixed overhead does not fit) | 【外推】 |
| v3 ternary `…v3.ninfer` | 7.28 GiB | ❌ “可用 − 权重 = 0.12–0.32 GiB < 固定开销，池建不起来” (`配方-8GB档-实测支撑-20261008.md:87`) | 【外推】 |
| PQ2 + dflash2 | weights **8.16 GiB** | ❌ “PQ2 权重 8.16 GiB，8 GB 卡**本来就装不下**… 挤不进去就是挤不进去，别硬烧时间” (`docs/12-给接收方-agent-的操作手册.md:90-91`) | 作者明示 |
| GSQ / Swift (`swift-qwen38-rco-iq3s.ninfer`) | 13.4 GiB | ❌ excluded by size alone (`docs/12-给接收方-agent-的操作手册.md:85`) | 作者明示 |

**Two artifact lines must not be mixed**: the `rk2v4-e8` two-recipe line at `README.md:279-291` (2026-10-19) and the `rk4v4-e8` + `start-8g.bat` line at `README.md:293-299`. The README says so explicitly.

### 3.2 How to obtain it — three paths, in order of practicality

1. **Ask the distributor for the PTQ1 artifact** (what the docs assume: “模型如果不是随包来的（我们只发引擎 + 文档，模型给你下载链接）… 文件名必须逐字对上 `start-*.bat` 里引用 `models\<名字>`” — `docs/12-给接收方-agent-的操作手册.md:93-96`). No public URL is given anywhere in the repo or in the Release assets (`README.md:87-100`).
2. **Convert it yourself** (documented, CPU-only capable):

```
python -m tools.convert --model /path/to/Qwen3.8-27B --recipe bonsai2_27b_ternary
  --source ternary=/path/to/Ternary-Bonsai-2-27B-PQ2_0.gguf
  --source mtp=/path/to/Ternary-Bonsai-2-27B-MTP/model_mtp.safetensors --device cpu
```

   (`src-tree/fusion-engine-src/docs/weight-conversion.md:138-142`; `--device cpu` at :30; recipe table at :62-63.)
   Inputs: PrismML's `Ternary-Bonsai-2-27B-PQ2_0.gguf` (named at :119 but **not linked**), the MTP head from `huggingface.co/ProCreations/Ternary-Bonsai-2-27B-MTP` (:130), and a base `Qwen3.8-27B` directory that “**needs only the base checkpoint's configuration and tokenizer files**” (:191) — a few MB, not the 54 GB checkpoint. Output: every text projection as `t2_g128_fp16` = **2.125 bits/weight**, ternary codes + per-128 FP16 scales imported without rounding, Hadamard signs carried as auxiliaries and rotations applied to activations at runtime (:121-127). Toolchain: Python 3.11 + PyTorch + NumPy.
   **Verification gate**: `tools\自检-模型件.ps1 -Model <path> -VramGb 8` — at `-VramGb` ≤ 10 the tool prints `SMALL_CARD_RULE=USE --spec mtp ONLY. Do NOT enable dflash2.` (`docs/12-给接收方-agent-的操作手册.md:75-81`); a headless artifact returns `MODELCHECK_VERDICT=BARE` exit 3 (`README.md:103-107`).
3. **Do not** expect to reuse a llama.cpp GGUF directly: the engine only reads `.ninfer` v3 (multi-part, default max part 32,000,000,000 B). GGUF enters only as *conversion input*.

### 3.3 Licensing (the honest position)

- Engine + docs: Apache-2.0 (`LICENSE`, `NOTICE.md`); all five upstream engine repos verified Apache-2.0 via GitHub API on 2026-10-04 (`docs/09-声明与链接.md`).
- **Weights: unresolved and explicitly a customer decision** — `docs/09-声明与链接.md:67` “⚠ 模型权重许可未逐字核（属需求方裁决项）… 其上游（PrismML / Qwen）的再分发条款未逐条核对”; `NOTICE.md:94` “模型权重版权归其各自作者与上游（Qwen 体系等）所有”。 Separately, the community 3060 repo's model is under *UkisAI Swift Open License v1.0* (commercial use above USD 1M revenue needs a separate deal) — citable parameters, **not** Apache-2.0.
- Not shipped in the distribution package and must be added before any release: curl's licence text and the NVIDIA CUDA EULA (`docs/09-声明与链接.md:66`).

**Practical consequence**: for internal/personal use, converting locally is the low-risk path; redistributing the `.ninfer` to third parties is not cleared by anything in this repo.

---

## 4. The exact 8 GB launch configuration

### 4.1 What was actually run on an 8 GB card (highest-confidence config)

`verify/回执-外部-8G-完整测试-20261008.md:19-20` — RTX 4070 Laptop 8 GB (8,188 MiB), engine `ninfer-serve-89.exe` 795,030,528 B:

```bat
set NINFER_KV_WINDOW=65536
set NINFER_KV_RING=1
set NINFER_HOST_PAGEABLE=1
set NINFER_KV_REUSE_HOSTBACKED=1
set NINFER_TERNARY_PTQ1_FAST=1
set NINFER_KV_RETRIEVE=
rem  (leave EMPTY, do not set 0)
rem  line-wrapped for readability: the real argv is one line

ninfer-serve model.ninfer --host 127.0.0.1 --port 8095
  --kv-capacity auto --kv-headroom-mib 64 --kv-dtype rk4v4-e8
  --max-context 131072 --max-concurrency 1 --prefill-chunk 512
  --gdn-state-fp16 --no-cuda-graph --host-kv-mib 16384
  --spec mtp --draft-tokens 4 --ngram-draft-tokens 0
  --default-max-tokens 65536 --default-reasoning-effort medium --default-thinking-budget 1024
  --max-shared-prefixes 0
```

Startup banner to compare against (:30): `capacity | KV 38,016 tokens, rk4v4-e8, auto | pages 594/1,038 | runtime 916.9 MiB | free 60.0 MiB`, then `[ring] budgets: skeleton=4, evidence=0, recent=0, free=590 (pool 594)`.

### 4.2 The shipped launcher (`start-8g.bat`, 64 lines) — and the two things it omits

`start-8g.bat:35-44,58-63`: same env block, but `--kv-headroom-mib 1024`, `--prefill-chunk 256`, **no `--spec`**, `--max-context 131072`, `--host-kv-mib 16384`, model = the **5.52 GiB** PTQ1 artifact. Its own budget comment (:13-16) is “weights PTQ1 5.52 GiB + fixed ~0.50 GiB + KV 1004 pages × 1.1 MiB = ~7.1 GiB ⇒ fits 8 GB with ~0.4–0.5 GiB to spare”, and (:33-34) “raise [WINDOW] to 98304 only if the card has headroom, lower to 32768 if startup is refused”.

⚠️ **`start-8g.bat` does not pass `--max-shared-prefixes 0`, but both `docs/05-已知问题与禁忌.md:16-26` and `README.md:288` call it mandatory** — its default is `max(max-concurrency, 7)`, and an over-pool *byte-identical* resend then 500s the request and 503s *every* subsequent request (`worker crash: active KV snapshot full page is not stable`). The tested receipt *did* add it (:19). **Add it yourself; do not trust the launcher.** Cost of adding it: prefix reuse only on identical history (`cache_n=20`, common-prefix miss = 0) (`verify/回执-外部-8G-完整测试-20261008.md:96,216`).

### 4.3 Recommended starting point for **this** 4060 Ti (my synthesis, 【外推】 on measured constants)

```bat
rem 1) close OBS / GameViewer / QQ first — recover 600-1,000 MiB (README.md:290)
set NINFER_KV_WINDOW=49152
set NINFER_KV_RING=1
set NINFER_HOST_PAGEABLE=1
set NINFER_KV_REUSE_HOSTBACKED=1
set NINFER_TERNARY_PTQ1_FAST=1
set NINFER_KV_RETRIEVE=
ninfer-serve-89.exe D:\ninfer\models\bonsai2_27b_ternary_ptq1.ninfer
  --host 127.0.0.1 --port 8091 --model-id ninfer-local
  --kv-capacity 20480 --kv-dtype rk4v4-e8
  --max-context 131072 --max-concurrency 1 --prefill-chunk 512
  --gdn-state-fp16 --no-cuda-graph --host-kv-mib 6144
  --ngram-draft-tokens 0 --default-reasoning-effort none --default-thinking-budget 1024
  --max-shared-prefixes 0
```

Rationale, all from measured constants: 20,480 tokens = 320 pages × **1.1 MiB ≈ 0.35 GiB** of KV, which leaves room for 5.52 GiB weights + ~0.92 GiB runtime under a desktop that already holds ~0.4 GiB. Prefer **explicit `--kv-capacity`** over `auto` on a shared display card — `auto` sizes from post-weights free VRAM, so the pool silently changes every time OBS opens (`docs/05-已知问题与禁忌.md:60-61`). Start MTP-less: it is the only way to reach the 66,432-token pool class and it removes the `native_mtp` artifact dependency. If throughput matters more than context, switch to the 5.94 GiB `native_mtp` artifact + `--spec mtp --draft-tokens 4` and accept the 38,016 cap (`配方-8GB档-实测支撑-20261008.md:61`).

**`--kv-headroom-mib` is inverted from intuition** — the tested ladder was 1024 → **FATAL** (“requires 1073741824 bytes, but only 1022787584 bytes are available after weights”), 512 → 12,096 tokens, 64 → 38,016 tokens (`verify/回执-外部-8G-完整测试-20261008.md:48-49`). Smaller value = bigger pool = less safety margin.

**Precedence of VRAM levers** (measured, `README.md:290`): close external GPU processes (≈600–1,000 MiB) → shrink pool (−64 pages ≈ −53 MiB) → turn MTP off (≈551–970 MiB) → `--ngram-draft-tokens 0` (≈50–127 MiB). Do **not** try to save VRAM via `--draft-tokens`/`--mtp-attention-window`: measured difference **12 MiB** (`README.md:290`).

---

## 5. Measured numbers and how they scale to a 4060 Ti

### 5.1 The only 8 GB-card measurement in existence 【实测·他机】

`verify/回执-外部-8G-完整测试-20261008.md` — RTX 4070 Laptop 8 GB, 5.94 GiB mtp artifact, pool 38,016:

| Metric | Value | Line |
|---|---|---|
| Decode, short requests | **45 – 84 tok/s** (median ≈55) | :127 |
| Decode, long output (700–1,200 tok) | **45 – 50 tok/s** | :128 |
| Prefill, chunk 512 | 20k → **801.6**; 100k → **521.0** tok/s | :129 |
| Prefill, chunk 1024 | 20k → 859.3; 100k → 600.8 tok/s **but pool −17.5 %** | :131 |
| MTP accept rate | 2,650/5,939 = **44.6 %**; **2.76 tokens per round** | :133-134 |
| **Host cost per decode round** | **51.4 ms** | :135 |
| **GPU wait per round** | **0.62 ms** | :136 |
| GPU utilisation | 100 %, 7,525 / 8,188 MiB, 114 W, 67 °C | :137 |
| Reliable context | **≈38k**; beyond that “静默的概率召回”, 100k cold start 2/3 HIT | :196-211 |

**This is the single most important scaling fact**: on the 8 GB card the GPU was idle 98.8 % of decode time (`elapsed_seconds.program_submit = 81.35 s` of 81.81 s, :139). The bottleneck is **host-side submit** (CPU + driver), not GPU FLOPs or bandwidth. A 4060 Ti will *not* be faster than that laptop 4070 in proportion to its 288 vs 256 GB/s — decode is limited by the same per-round host cost.

### 5.2 Higher-VRAM reference points (for shape, not for absolute numbers)

| Machine | Context/config | Decode | Notes |
|---|---|---|---|
| RTX 4080 SUPER 16 GB sm_89 (author's machine) | new 8 GiB-tier fast recipe, engine 7,365 MiB | **100–275 tok/s** | 【实测·本机】 `README.md:43`; TTFT “10 s 量级” at 20K prompt |
| RTX 4080 SUPER, main-line PQ2+dflash2 | pool 17,920 / template | 276.8 tok/s typical; draft-12 corpus run **571.9 tok/s** (counting-corpus artifact, not general speed) | 【实测·本机】 `README.md:266-275` |
| RTX 5070 Ti 16 GB, *different distribution* (`kvmem-llama.cpp` RC2), 256k context | 255,973-token prompts, 32 tool rounds | **61.5–118.0 tok/s**, run means 79.5/80.0/79.8; no decay by context band (0–64k 94.5 → 192–256k 82.1) | 【实测·他机】 `verify/回执-外部-5070Ti-官方RC2-20261008.md:9,19-44`; peak VRAM 15,205/16,303 MiB |
| RTX 5060 Ti 16 GB (vendor run) | 261,528 input / 512 output, 32 rounds | weighted **41.58 tok/s**, MTP accept 45.5 % | 【实测·他机】 same file :514-532 — **and private commit peaked 33,552 MiB on a 32 GB host ⇒ it lived on the page file** |

That last row is the warning for this machine: **32 GB RAM is not automatically enough**, because the host KV layer is pinned RAM (`--host-kv-mib 16384` = 16 GiB, confirmed at `verify/回执-外部-8G-完整测试-20261008.md:46`). With OBS/QQ up, cut `--host-kv-mib` to 4,096–8,192.

### 5.3 4060 Ti projection 【外推 — my arithmetic, not in the repo】

Constants: 4060 Ti = 34 SM, 288 GB/s, 8 GB; the 8 GB reference laptop = 256 GB/s, 8,188 MiB.

| Step | Computation | Result |
|---|---|---|
| Weight-pass floor (MTP off) | 5.52 GiB = 5.93 GB ÷ 288 GB/s = 20.6 ms/token | **48 tok/s** hard ceiling |
| Weight-pass floor (MTP on) | 5.94 GiB = 6.38 GB ÷ 288 GB/s = 22.2 ms/round; 2.76 tok/round | **124 tok/s** hard ceiling |
| Host-side ceiling | if the desktop host is ~2× the laptop's 51.4 ms → 25 ms/round ⇒ 40 rounds/s × 2.76 | **≈110 tok/s** |
| **Realistic band, MTP on** | 60–75 % of min(124, 110) | **55–90 tok/s, median ~70** |
| **Realistic band, MTP off** | same ratios on the 48 tok/s floor | **35–50 tok/s** |
| Prefill | 801.6 tok/s × (34 SM × ~2.5 GHz) / (36 SM × ~1.7 GHz) ≈ ×1.4, discounted for host submit at chunk 512 | **≈700–1,000 tok/s** at 20k ⇒ TTFT **20–29 s**; 100k ≈ 500–700 tok/s ⇒ 143–200 s |
| Pool at equal free VRAM | same 1.1 MiB/page, same weight size | same **38k (MTP) / 66k (no MTP)** ceiling, minus whatever the desktop holds |

Sanity check against the author's own 8 GiB-tier claim on a 4080 SUPER (100–275 tok/s): that card has 736 GB/s and an idle desktop; a 4060 Ti at 288 GB/s with a compositor is 3–5× slower — consistent with 55–90 tok/s.

**What would falsify the projection**: a decode round where `decode_device_wait_microseconds_per_round` grows to a large share of the round (i.e. GPU-bound rather than host-bound). `/stats` exposes exactly that pair, so record it on the first run (`verify/回执-外部-8G-完整测试-20261008.md:135-136`).

---

## 6. Defects that hurt an 8 GB deployment most (ranked by damage)

1. **`--max-shared-prefixes 0` missing ⇒ instance bricked.** Over-pool byte-identical resend ⇒ 500, then every request 503, with `worker crash: active KV snapshot full page is not stable`. Default is 7; `start-8g.bat` omits the flag. (`docs/05-已知问题与禁忌.md:16-26`; root cause `kv_store.h:1506` / `capture.cpp`.)
2. **`NINFER_KV_RETRIEVE=0` ⇒ silent wrong answers, HTTP 200.** The ring's five switches are all required; with retrieval off, over-pool answers are plausible, wrong, and unlogged. `start-8g.bat:40-43` deliberately leaves the variable **empty** rather than 0 (`docs/05-已知问题与禁忌.md:28-40`, `README.md:307-321`). Same class: 100k-token prompts hit 2/3 cold starts only — “召回是概率性的且失败静默” (`verify/回执-外部-8G-完整测试-20261008.md:196`).
3. **Client `max_tokens` > pool ⇒ all requests 503 while `/v1/models` still returns 200** (the health check lies). Reproduced 2/2; 32,000 crashes, 64 survives. With a 38k pool this is trivially easy to trip — `--default-max-tokens` must be ≤ pool (`docs/04-卡死与循环的防治.md:46`).
4. **Over-pool prompts must go through the sharded gateway**, otherwise a single-request answer is untrustworthy and the engine emits an `unverified` warning (“no warning” ≠ safe) (`README.md:41,45`).
5. **`--kv-capacity auto` cannot even start when another process holds VRAM**, and silently re-sizes when OBS/QQ change footprint (`docs/05-已知问题与禁忌.md:60-61`).
6. **Disk KV layer is useless in this build**: rehydrating 40,058 tokens (≈984 MiB) took 22,925 ms ≈ 43 MB/s, the same as a full refill (22,840 ms) because `NINFER_DIRECTORSTORAGE=OFF`. Do not enable it as a capacity workaround (`docs/05-已知问题与禁忌.md:42-52`).
7. **CUDA-graph capture can fail** — recorded workaround is `--no-cuda-graph` (8 GB configs already use it; root cause unknown) (`README.md:137-143`).
8. **`--spec` on an artifact without the head is FATAL in 3.5 s** (`missing component mtp`); dflash2 costs 1.3–2.07 GiB extra versus MTP's 332–430 MiB ⇒ on ≤10 GB cards “只能用 MTP，绝不开 dflash2” (`docs/12-给接收方-agent的操作手册.md:70-81` — exact filename `docs/12-给接收方-agent-的操作手册.md`, `docs/05-已知问题与禁忌.md:54-59`).
9. **Context-cache pressure causes HTTP 429** even at 35 requests (44 checkpoint drops); restart recovers. Restrict client `max_tokens`, keep sessions short (`verify/回执-外部-8G-完整测试-20261008.md:143-144,198`).
10. **Agent-behaviour defects, not engine crashes**: vocabulary recursion / repeat loops; an **RTX 4060 machine** in the grey rollout showed 4 consecutive no-arg tool calls with verbatim repeats, greatly relieved by turning thinking off; the tester's own conclusion: “27B 当前定位：一次性手脚（单步工具调用 + 收尾可用），多步 agent 活不可用” (`docs/04-卡死与循环的防治.md:206-213`).

Two structural caveats: **`--max-concurrency 1` is a hard serial gate in ring mode** (two requests ≈ 2× time, `verify/回执-外部-8G-完整测试-20261008.md:210`), and **ring mode is incompatible with `--use-alt-prefix-caching`** (`README.md:307-321`).

---

## 7. Build cost (if the public sm_89 exe is not enough)

| Item | Value | Source |
|---|---|---|
| Driver | **≥ 580** required by CUDA 13.x (573.22 fails with `rc=35 CUDA_ERROR_INSUFFICIENT_DRIVER`); 616.92 ✅ | `编译指南-怎么编.md:20` |
| CUDA Toolkit | **13.3** (nvcc); CUDA 13 dropped Volta ⇒ sm_70 unsupported | `编译指南-怎么编.md:21` |
| MSVC | VS **18** BuildTools x64 (v145 14.50.35717 works; CUDA 12.8 hard-errors on v145 with C1189) | `编译指南-怎么编.md:22`, `src-tree/fusion-engine-src/AGENTS.md` |
| CMake / Ninja / vcpkg | CMake ≥ 3.28, Ninja, vcpkg manifest mode (network + ~30–60 min on first configure) | `README.md:211-258` |
| Full clean build, `-j 8` | **1,572 steps, ~48 min**, product `ninfer-serve.exe` = **795,030,528 B** (vs 1,511,941,632 B with `-lineinfo`, −47.4 %) | `编译指南-怎么编.md:62` |
| Do **not** use `-j` = core count | 24 logical / 16 physical ⇒ ~23 concurrent `ptxas` × ~2 GB each ⇒ 0.3 core each, 5 min of zero output. **8 is the recommended value** | `编译指南-怎么编.md:64` |
| arch 89 specifics | 764.2 MiB build tree, **389 `compute_89` objects**, same exe size class as the receipt binary | `README.md:239-243` |
| Traps | no sccache as `CMAKE_CUDA_COMPILER_LAUNCHER` (fatbinary fatal); a single multi-arch file would be 2.17 GiB > PE 2 GiB limit (LNK1248) ⇒ one exe per arch; `--split-compile=4` cut arch86 from 122.8 → 34.6 min | `README.md:245-250` |

**Verdict**: try the public `ninfer-serve-89.exe` first; note the DLL gap — CUDA runtime plus `FFmpeg`/`libcurl` DLLs must sit beside the exe (`README.md:96`). Build from source only if you need the 2026-10-07+ fixes — and record the exe SHA256 either way (`README.md:98`).

---

## 8. Numerics — does it use tensor cores properly on Ada?

- BF16 GEMM: `mma.sync.aligned.m16n8k16.row.col.f32.bf16.bf16.f32` with **FP32 accumulators**, operands staged via `ldmatrix.sync.aligned.m8n8.x4.trans.shared.b16` (`src-tree/fusion-engine-src/src/ops/common/mma.cuh:33-40`, `:27-31`). Same tile for FP16 (:42-49), plus an FP16-accumulate variant commented “twice the FP32-accumulator rate on GeForce parts” (:51-56).
- **TMA is not used on sm_89 — by construction.** `cp.async.bulk.tensor` needs Hopper+; the sm_8x build compiles the TMA path out entirely and routes to `launch_bf16_a16_mma<Bf16TmaFallbackSchedule<…>>`, which stages the same tile through `cp.async` (`src-tree/fusion-engine-src/src/ops/linear/bf16/bf16_a16_tma_mma.cuh:14-34,155-171`). So: tensor cores yes, TMA no, and MSVC even forces the fallback on 120a for `alignas(128)` by-value `__grid_constant__` args (C2719).
- Ternary weights: `t2_g128_fp16` = **2.125 bits/weight** (codes + per-128 FP16 scales), Hadamard rotations applied to activations at runtime, not baked into weights (`src-tree/fusion-engine-src/docs/weight-conversion.md:121-127`). Embeds/head at Q8; ftype of the reference artifact: `bf16+fp32+ptq1_g128_fp16+q8_g32_fp16`, `n_params 27,320,726,528`, `n_embd 5120`, `n_vocab 248320` (`verify/回执-外部-8G-完整测试-20261008.md:15`).
- KV dtype on 8 GB: **`rk4v4-e8`** — **1.1 MiB per 64-token page** versus 4.0 MiB for bf16 (`start-8g.bat:6-8`, `配方-8GB档-实测支撑-20261008.md:19`), quality cost **+0.30 % perplexity** (`README.md:293-299`). The 2026-10-19 line uses `rk2v4-e8` with a much smaller window (10,240) instead.
- ⚠️ **Two documents contradict each other on KV dtype availability**: `配方-8GB档-实测支撑-20261008.md:88` says “`k8v4`/`nvfp4` KV ⚠️ Blackwell 专属（sm_120）；Ampere/Ada 只能走 `rk*`”, while `docs/11-按卡差异速查.md:93-95` says on this same sm_89 machine “bf16/fp8/int8/rk8v4/rk4v4/nvfp4/k8v4 逐档都真跑过”. Unresolved; irrelevant for 8 GB (use `rk4v4-e8`/`rk2v4-e8`), but it shows the per-card quick-reference cannot be trusted as a capability table — author's own words at :94-95: “能力表要落到按卡表里，别靠默认配置赌”.

---

## 9. Concrete deployment plan for this machine

0. **Free the GPU**: close OBS, GameViewer, QQ; verify `nvidia-smi` shows ≤300 MiB used. Step zero, because pool sizing is post-weights free VRAM.
1. **Get an artifact** (`bonsai2_27b_ternary_ptq1*.ninfer`). Run `tools\自检-模型件.ps1 -Model <path> -VramGb 8` ⇒ expect `SMALL_CARD_RULE=USE --spec mtp ONLY…`, exit 0 or 3 (BARE).
2. **Engine**: try public `ninfer-serve-89.exe` + CUDA/FFmpeg/libcurl DLLs; check `Get-FileHash`. Fall back to a 48-min source build (CUDA 13.3 + VS18 + vcpkg).
3. **First start** with the §4.3 command line (explicit `--kv-capacity 20480`, MTP off, `--max-shared-prefixes 0`, `--no-cuda-graph`, `--gdn-state-fp16`).
4. **Acceptance gates — in this order, none skippable**:
   - banner: `capacity | KV … rk4v4-e8 … | runtime … | free …` and `[ring] budgets … == pool: yes`;
   - `[ninfer] reuse host-backed: on` + `pinning host KV` in the log;
   - `/v1/models` 200 with the requested `context_window` (proves nothing on its own);
   - **real generation**: “请算 17+25” must answer 42 (`README.md:165`);
   - a 12–20k-token prompt must answer correctly with retrieval ON (the silent-wrong-answer gate);
   - check `/stats`: `decode_host_microseconds_per_round` vs `decode_device_wait_microseconds_per_round` — this decides whether the projection in §5.3 holds;
   - restart and confirm the same pool number (proves the calibration cache is stable).
5. **Client discipline**: `max_tokens` ≤ pool tokens; one request at a time; thinking on only if needed (turn it off if you see repetition — `docs/04-卡死与循环的防治.md:206-213`); keep sessions short to avoid 429s.
6. **Record**: exe SHA256, artifact SHA256, banner, `/stats` snapshot. The repo's own rule is that readings only hold for the exact card/model/config (`README.md:264`) — your numbers would be the first 4060 Ti data point.

---

## 10. Unverified list that must ship with the recommendation

1. **No 4060 Ti has ever run this engine**; no 8 GB *desktop* card has either. The only 8 GB evidence is a laptop 4070 with a 291 MiB desktop (`verify/回执-外部-8G-完整测试-20261008.md:17`). 【未验】
2. The 8 GB tier's *pool ceiling is extrapolated* from real free VRAM; only the three levers are measured (−289.9 MiB total for `--gdn-state-fp16` + `--prefill-chunk 256` + `--no-cuda-graph`); “8 GB 配方仍需真机验证” (`README.md:313,320`; `docs/12-给接收方-agent-的操作手册.md:83` “⚠ 未验：我们没在 8 GB 卡上跑过本包”).
3. `docs/12-给接收方-agent-的操作手册.md:90` states flatly that “PQ2 权重 8.16 GiB，8 GB 卡本来就装不下” and “不许当已验读”, while `配方-8GB档-实测支撑-20261008.md` and README's 8 GiB tier assert a fitting 6.84–7.37 GiB budget. The reconciliation is that PQ2 (GGUF, 8.16 GiB) is not the PTQ1 `.ninfer` (5.52/5.94 GiB) — but the repo never says so in one place. Treat any “fits 8 GB” claim as artifact-dependent.
4. Public availability of PrismML's `Ternary-Bonsai-2-27B-PQ2_0.gguf` and the ProCreations heads could **not be verified from this host** (no search API key; `huggingface.co` blocked). The docs give links only for the MTP/DFlash2 heads (`src-tree/fusion-engine-src/docs/weight-conversion.md:130-131`) and merely *name* the PQ2 GGUF (:119).
5. Weight **redistribution** licensing is explicitly unadjudicated (`docs/09-声明与链接.md:67`; `NOTICE.md:94`).
6. The 5070 Ti / 5060 Ti receipts are a **different distribution** (`kvmem-llama.cpp` RC2, old parameter names) — cited for shape only, never as this engine's performance.
7. rk* KV dtypes are “officially unaccepted” (official combos are INT8/RK8V4) and are documented to fail over-pool when retrieval is off; `rk4v4-e8` is unaccepted, not unsupported (`verify/回执-外部-5070Ti-官方RC2-20261008.md:718-731`).
8. The author's own product verdict for the 27B: **single-step tool call + finishing, not multi-step agent work** (`docs/04-卡死与循环的防治.md:213`). Any plan that assumes agentic use is contradicted by the repo's own field data.

---

## 11. Bottom line for the Lead

- **Technically the 4060 Ti is inside the supported envelope** (sm_89, whitelisted, built), and one real 8 GB receipt proves the software path works at **38k context / 45–84 tok/s** on a laptop 4070.
- **Binding constraints, in order**: (1) obtaining a 5.52/5.94 GiB PTQ1 ternary artifact — nothing in the repo or Release ships it, and its documented provenance could not be confirmed from this machine; (2) **desktop VRAM** — this card is the display adapter running OBS/QQ/GameViewer, and the engine's pool is sized from whatever is left; (3) **host-side submit cost**, which is what actually caps decode; (4) 32 GB RAM shared with a pinned 16 GiB host-KV default (reduce it).
- **Expected user experience if it launches**: 27B-ternary quality, ~55–90 tok/s decode with MTP, ~20–30 s TTFT on a 20k prompt, ≤38k reliable context, one request at a time, no vision, single-step tool calling only.
- **Do not promise**: dflash2 on 8 GB (forbidden), long-context >38k reliability (probabilistic silent misses), multi-user/concurrency (hard serial), or “just works” — the repo's own docs rate the 8 GB tier as unverified on 8 GB hardware.

*Prepared from source + shipped receipts only; nothing was executed on the target machine. Report path: `docs/ninfer-analysis.md`.*
