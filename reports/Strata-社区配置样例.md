# Strata 社区真实配置样例（GitHub 一手证据）

侦察日期：2026-10（本机 0.2.8 / engine 0.1.54，仓库 HEAD 870aedd，main 分支）
采集范围：`github.com/Niko1221/Strata` 的 `bench/results/` 社区提交（150+ 目录，每个含 README + 真实 config json + 引擎日志）与 issue 追踪器。
所有结论都附 URL；没有数字、没有出处的说法单独标 **【未核源】**。

---

## 0. 一句话结论

1. **8–12 GB 显存机器上 `--resident-experts` / `--resident-budget-gib` / `--mmap-experts` 的真实用法，只存在于 Qwen3.8-Flash-Next / DeepSeek 这条"基础引擎"路径**；我们本机报错的 Qwen3.6-35B-A3B（`strata-q36`）引擎**根本不解析这些 flag**，只会打印 `ignoring … (not an option of this engine)`。这解释了为什么本机 q36-S / q36-T / q36-U 三份 config 的报错数字一模一样（1159 MiB needed / 217 MiB free）。
2. 社区里"expert slots 不足 / not enough VRAM left for the hybrid experts' buffers and slots"报错**全部出现在 q36 路径**（#4215、#2633、#4458、#3687、#3574），且**没有一个人是靠调 resident/mmap 解决的**；能复现的两条解法是：把 vision 挪到 CPU（只成功过 2 次，随后无限加载，属"单次成功"而非稳定）、以及 `STRATA_EMBED_VRAM=0`（省约 0.08 GiB，恰好越过门槛，属"单次/少数次成功"）。
3. 真正能改变 q36 报错算术的旋钮只有：`--max-context`、`--batch`(`--slots`)、`--expert-slots`、`--expert-vram`、`--prefill`(chunk)、`--cpu-threads`、`--hybrid-rows`。`--kv` / `--kv-resident` / `--vram-reserve-mib` / `--resident-*` / `--mmap-experts` / `--expert-cache` 在 q36 上一律无效。

---

## 1. 核心判据：q36 引擎到底认哪些 flag

参数解析器在 `src/qwen35/q36_engine.cu`（第 3730–3795 行，[源码](https://github.com/Niko1221/Strata/blob/main/src/qwen35/q36_engine.cu#L3727-L3795)）。白名单实为：
`--model/--native`、`--max-new`、`--no-token-graph`、`--pool-workers`、`--gpu`、`--greedy`、`--serve`、`--max-context|--ctx`、`--chunk|--prefill`、`--tokens`、`--n`、`--force`、`--emb`、`--dump-full-logits`、`--bench-pp`、`--bench-tg`、`--no-graph`、`--no-warmup`、`--mtp`、`--draft-vocab`、`--vision`、`--batch|--slots`、`--batch-mtp`、`--expert-vram`（GiB，第 3765 行）、`--cpu-threads`、`--expert-slots`、`--hybrid-rows`。

其余任何 `--` 开关，在 serve 模式下走第 3773 行：
```
strata-q36: ignoring <arg> <val> (not an option of this engine)
```
然后跳过，**不致命**。于是 `--resident-experts`、`--resident-budget-gib`、`--mmap-experts`、`--kv`、`--kv-resident`、`--vram-reserve-mib`、`--expert-cache` 在 q36 上全部是空转——本机日志与社区 issue #4215、#3687 的日志逐字印证（见 §4）。

### 1.1 报错的算术（同一文件第 2896–2917 行）

- `staging = E.use_mmq && E.main_hybrid ? 2 * (max_layer + kMmqTail) : 0`（第 2896 行）
- `need = staging + tmax*top_k*n_embd*4 + tmax*top_k*4 + Σ_layers (S * L->stride + kMmqTail)`
- `S = slots > 0 ? min(ne, slots) : min(ne, slot_bytes / per_slot)`，`slot_bytes = budget2 - staging`
- 与 `fr`（放完权重、上下文、sessions 之后剩下的空闲 VRAM）比较，`need > fr` 才报错：
```
not enough VRAM left for the hybrid experts' buffers and slots (N MiB needed, F MiB free after the weights, the context and the sessions): use fewer slots ("parallel" / --batch), a shorter --max-context
```
（第 2914 行；若传了 `--expert-slots` 再追加 `, or fewer --expert-slots`。）
- 另一条分支：**全部** routed expert 都塞得进显存时，打印 `strata-q36: every routed expert in VRAM (X GiB) in N s`（第 2878 行）并跳过此检查。
- 上游自测脚本 `tools/qwen35/q36_vram_refusal.py` 声称对每组配置"要么 READY、要么以数字拒绝"，其五组矩阵为：`--max-context 8192 --batch 8 --expert-slots 256`、`32768 --batch 8 --expert-slots 256`、`8192 --batch 8`、`32768 --batch 8`、`131072 --batch 8`（[文件](https://github.com/Niko1221/Strata/blob/main/tools/qwen35/q36_vram_refusal.py)）。

**关键观察（对本机最有价值）**：need 的大头是 `staging`，它与上下文、与 sessions **无关**——所以 #4215 在 `--max-context 8192` 下报的也是 **1159 MiB**，与本机数字完全一致；#4458 实测 `--parallel 1` 也不能把 1256 MiB 降下来。要越过门槛只能"腾出 fr"，不能"减小 need"（除非改成 S=0，即 `--expert-vram 0`/装不下时的 staging-only 分支）。

---

## 2. 8–12 GB 机器的完整启动样例（原样）

### 2.1 RTX 3060 12 GB / Windows 11 —— 唯一"跑了 86 次启动"的 12 GB 全量记录

目录 [`bench/results/2026-10-09-community-rtx-3060-0141/`](https://github.com/Niko1221/Strata/tree/main/bench/results/2026-10-09-community-rtx-3060-0141)，版本 0.1.41（tag `fb58e0d`），硬件 12,288 MiB VRAM / driver 610.62 / i7-12700 / 2×32 GiB DDR4-3200 / Windows 11 Pro 26300。
launch 20（`id: 020-iq3_s-131072`，[`launches.json` 第 194–246 行](https://github.com/Niko1221/Strata/blob/main/bench/results/2026-10-09-community-rtx-3060-0141/launches.json#L194-L246)）原文参数顺序：

```
--pack          <workspace>\Strata-data\packs\iq3_s
--native        <workspace>\Strata-data\models\IQ3_S\Qwen3.8-Flash-Next-GSQ-RCO-IQ3_S-00001-of-00002.gguf
--ple-gguf      <workspace>\Strata-data\models\IQ3_S\Qwen3.8-Flash-Next-GSQ-RCO-IQ3_S-00002-of-00002.gguf
--expert-profile <workspace>\Strata\data\expert-profile.bin
--expert-cache  auto
--prefill       auto
--spec 4 --spec-min-p 0.5
--mtp           <workspace>\Strata-data\mtp\rt
--max-context   131072
--kv int8 --kv-resident 32768
--resident-experts --resident-budget-gib 20
```
`environment`: `STRATA_RESIDENT_HEADROOM_GIB=12`；`gpu: 0`、`parallel: 1`、端口 18080。
README 另写：IQ3 的 resident 跑法要再加 `STRATA_UNBUFFERED_LOAD=1`；Q2_0 / IQ2_XS 不用 resident 池（启动即把全部权重载入，IQ3_XXS 启动日志报 33.02 GiB loaded）。
**模型是 Qwen3.8-Flash-Next-IQ3_S，不是 q36** —— 这条正是"12 GB 上 resident 专家池真实可用"的证据。

### 2.2 RX 6800M 12 GB / Windows / 自建 HIP —— `--resident-experts` 的 12 GB AMD 例

[`bench/results/2026-10-06-community-rx-6800m/README.md`](https://github.com/Niko1221/Strata/blob/main/bench/results/2026-10-06-community-rx-6800m/README.md)（作者 Hugua700，32 GB RAM，gfx1031 自编译）。第 66–68 行命令行：

```
--expert-profile F:\Strata\data\expert-profile.bin --expert-cache auto --prefill auto …
--max-context 65536 --kv int8 --kv-resident 32768 --resident-experts --vision
```
结论（第 53 行）：专家装不进 RAM 就从 GGUF 流式读；CPU 无 AVX-512 走 AVX-2。prefill 50–114 tok/s、decode 9–27 tok/s（模型同为 Flash-Next 家族）。

### 2.3 RTX 2080 Ti 11 GB —— 不用 resident 的对照

[`…/2026-10-02-community-rtx2080ti-11gb/strata-iq3_s.json`](https://github.com/Niko1221/Strata/blob/main/bench/results/2026-10-02-community-rtx2080ti-11gb/strata-iq3_s.json)：
`--max-context 262144 --kv int8 --kv-resident 32768 --vision --vram-reserve-mib 700 --expert-cache auto --prefill auto --spec 4 --spec-min-p 0.5 --mtp`（无 `--resident-experts`）。
说明 11 GB 上不给 resident 池、靠 `--expert-cache auto` + 700 MiB 预留，也能跑 256K 上下文。

### 2.4 RTX 5080 16 GB + RTX 4060 Ti **8 GB** 当 helper —— 8 GB 卡的真实分工

[`…/2026-10-09-community-rtx-5080-4060ti-0.1.41/`](https://github.com/Niko1221/Strata/tree/main/bench/results/2026-10-09-community-rtx-5080-4060ti-0.1.41)（KarlGrier，0.1.41）。`config-stock.json`：

```
--pack … --native <IQ3_S shard1> --ple-gguf <IQ3_S shard2> --expert-profile data/expert-profile.bin
--expert-cache auto --prefill auto:16384 --spec 4 --spec-min-p 0.5 --mtp <mtp/rt>
--max-context 131072 --kv int8 --kv-resident 32768 --pcie-frac 0 --ple-inflight 128
--vram-reserve-mib 713 --expert-cache-device1 3300
```
env：`CUDA_VISIBLE_DEVICES=<5080>,<4060Ti>`、`STRATA_IO_THREADS=64`、`CUDA_MODULE_LOADING=LAZY`、`STRATA_GR_V3=1`、`STRATA_PF_FUSED=1`、`STRATA_MMVQ_IL=1`、`STRATA_ADAPT_LAG=2`、`STRATA_DISJOINT_ADAPT=1`。
日志 `engine-start-stock.txt`：`expert cache auto: 9.48 GiB free, 713 MiB reserved (+86 MiB for the draft head) -> 3508 slots / expert cache 4560 slots, 8.70 GiB of VRAM`；`CUDA1: 3300 additional experts, 6.21 GiB`；`541 MiB of VRAM free with everything loaded`。
8 GB 卡在这个配置里是"额外 3300 个专家"的位置（`--expert-cache-device1 3300`），不是主卡。

### 2.5 2× RTX 3080 20 GB —— `--memory-limit-mib` 的唯一原样用例

[`…/2026-10-08-community-2x-rtx3080-20gb-ud-q4-k-xl-512k-pool/start-command.txt`](https://github.com/Niko1221/Strata/blob/main/bench/results/2026-10-08-community-2x-rtx3080-20gb-ud-q4-k-xl-512k-pool/start-command.txt)（`/proc/<pid>/cmdline` 实录）：

```
strata-w7 --serve --pack /opt/strata-ssd/packs/ud-q4_k_xl
  --native .../Qwen3.8-Flash-Next-UD-Q4_K_XL-00001-of-00004.gguf
  --expert-profile …/expert-profile.bin --expert-cache auto --spec 4 --spec-min-p 0.5
  --mtp …/mtp/rt --max-context 262144 --kv int8 --kv-resident 32768 --kv-pool-tokens 524288
  --resident-experts --ple-io direct --trim-stage-weights --vram-reserve-mib 1500 --vision
  --batch-mtp --pcie-frac 0.1 --expert-profile-save …/expert-profile.learned.bin
  --adapt-every 2 --adapt-async 1 --conversation-cache-mib 4096 --conversation-cache-slots 3
  --memory-limit-mib 101376 --aux-cpus auto --prefill auto:16384
  --conversation-cache-min-free-mib 2048 --layer-split 23 --batch 2
```
`--memory-limit-mib 101376` 的含义（[README 第 92、110 行](https://github.com/Niko1221/Strata/blob/main/bench/results/2026-10-08-community-2x-rtx3080-20gb-ud-q4-k-xl-512k-pool/README.md#L92)）：**不是提速项**，而是让 parking 与会话保存读到容器真实可用 RAM；同一 README 记录 `78000` 时容器被判超限、8 次 parking 全被跳过（decode 中位 79.6 tok/s 未受影响）。作者还提了 PR [#1601](https://github.com/Niko1221/Strata/pull/1601)。

### 2.6 低内存机（16 GB RAM）—— `--low-ram on` 自动带 `--resident-experts`

[`…/2026-10-04-community-v100-16gb-ram/README.md` 第 25、35 行](https://github.com/Niko1221/Strata/blob/main/bench/results/2026-10-04-community-v100-16gb-ram/README.md#L25)：
`--mtp …/mtp/rt --max-context 131072 --kv int8 --resident-experts --vision --vram-reserve-mib 700`，并注明"这是 setup 的低内存选择 `--low-ram on` 自动加上的"。

### 2.7 `STRATA_ARENA_PIN_GIB` —— 只找到一个带数值的用法

[`…/2026-10-11-community-rtx3090-5600x-arena-pin-by-need/strata_ab2.py` 第 74–95 行](https://github.com/Niko1221/Strata/blob/main/bench/results/2026-10-11-community-rtx3090-5600x-arena-pin-by-need/strata_ab2.py#L74-L95)：`{"STRATA_IQ3S_MT1": "1", "STRATA_PIN_BY_NEED": "1", "STRATA_ARENA_PIN_GIB": "29"}`（另有 `STRATA_PCIE_MIN1: "1"` 变体），README 第 8 行同写 `STRATA_PIN_BY_NEED=1 STRATA_ARENA_PIN_GIB=29`。宿主是 **RTX 3090 24 GB + 48 GB RAM**，不是 8–12 GB 级机器；仓库其余 11 处只出现变量名不出现数值。→ 对 8–12 GB 无直接可抄的数字，**【未核源】**（未找到该值的语义/单位说明）。

---

## 3. `--mmap-experts` / `--resident-cpu-experts` 的真实边界

- [`…/2026-10-01-community-rtx-pro-4500/README.md` 第 77 行](https://github.com/Niko1221/Strata/blob/main/bench/results/2026-10-01-community-rtx-pro-4500/README.md#L77)：四个 GGUF shard 用 `--mmap-experts` **就地映射**，不产出 77 GB 的 `experts.bin`；第 193 行重申这种模式不需要 `experts.bin`。
- 同一 README 第 465–467 行：`--resident-budget-gib 100` 在该版本会**隐式带上** `--resident-cpu-experts`，而引擎直接拒绝启动：`--resident-cpu-experts does not support layer splits or remote expert caches`（`strata generate` exit 2；作者因此把双卡 config 的 resident 预算去掉了）。→ **多卡/layer-split 与 resident-cpu-experts 互斥**。
- [`…/2026-09-29-layer-split-limits/README.md` 第 26、59 行](https://github.com/Niko1221/Strata/blob/main/bench/results/2026-09-29-layer-split-limits/README.md#L26)：`--mmap-experts` + native pack 会在启动时明确报错，必须用 canonical pack 里的 `experts.bin`。
- 宿主端实现：`apps/host/server/native-ds-args.mjs:14` 把 `'--mmap-experts'` 列入参数；`native-resources.mjs:80` 注释 `--resident-budget-gib, which implies --mmap-experts`；`native-resources.mjs:131` 对含 `--resident-experts`/`--mmap-experts` 的 args 返回 `null`（不再套 RAM 规则）。

---

## 4. 「expert slots 不足」报错合集（我们本机的核心报错）

| issue | 状态 | 机器 / 版本 | 数字 | 结果 |
|---|---|---|---|---|
| [#4215](https://github.com/Niko1221/Strata/issues/4215) | open | Windows，engine 0.1.50，Q4_K_XL，`--max-context 8192 --prefill auto --pool-workers 15 --vision --vram-reserve-mib 512 --resident-budget-gib 8` | `context 8192 cells, prompt chunk 512 … 0.66 GiB of VRAM free` → **1159 MiB needed / 674 MiB free** | 日志明确 `ignoring --vram-reserve-mib 512` 与 `ignoring --resident-budget-gib 8`；无解帖（后被格式机器人提示补全） |
| [#2633](https://github.com/Niko1221/Strata/issues/2633) | closed | RTX 5060 Ti 16 GB，Win11 LTSC 24H2，i5-11400F，80 GB DDR4，0.1.45 | `context 131072 cells, prompt chunk 2048 … 0.67 GiB free` → **1256 MiB needed / 684 MiB free** | 作者把 **vision 放 CPU 后成功启动 2 次，随后一直无限加载**（单次成功≠稳定）；维护者只回"0.1.44.1/0.1.45 还不支持 3.6" |
| [#4458](https://github.com/Niko1221/Strata/issues/4458) | open | RTX 3060 **12 GB** + 64 GB DDR4，Terminal 0.2.7 / engine 0.1.52，`--max-context 65536 --mtp 2` | 0.1.44.1 只上卡 2.62 GiB、3.23 GiB 空闲、hybrid 放 **18/256 experts (1.32 GiB) + 1.10 GiB staging** 能跑；0.1.52 上卡 4.40 GiB → **1256 MiB needed / 1240 MiB free** | 实测 `--parallel 1` 不降 need、`--set batch=64` 完全不生效、`--kv q4_0`/`STRATA_KV_GROW=1` 无效；**唯一让它启动的是 `STRATA_EMBED_VRAM=0`**（strings 扫二进制发现，文档无载），省约 0.08 GiB 恰好过线，之后 0/256 experts 在显存，decode 仍 50.9 tok/s greedy |
| [#3687](https://github.com/Niko1221/Strata/issues/3687) | open | 2× RTX 3060 12 GB，48 GB RAM，engine 0.1.46，Q6_K_XL，`--max-context 32768 --mtp 2 --vision --pool-workers 19 --resident-budget-gib 28 --vram-reserve-mib 700` | 日志先 `ggml_cuda_init: failed to initialize CUDA: no CUDA-capable device is detected`；另有 `1760 MiB needed / 0 MiB free` | 维护者要求补 nvidia-smi 与新版日志；同帖他人贴了 `strata launch` 的 config json（family gyro，extra: `kv k8v4`、`kv-resident 20480`、`vram-reserve-mib 900`、`vram-reserve-later-mib 1400`、`idle-unload 600`、`min-free-vram-mib 11000`、`expert-cache 12000`，`gpu_roles {0:main,1:off,2:helper}`） |
| [#3574](https://github.com/Niko1221/Strata/issues/3574) | closed | L4 22.5 GiB，qwen35moe 122B（48 层，256 experts top-8，FF 1024） | `staging: 2 x the largest layer's experts, which is the MTP block (1.27 GiB) | 2.53`；打包副本模式停在 `2784 MiB` | 指出两个代码级阻塞：`kNativeHBytes=1024` 只够 FF 640；`STRATA_D_FMTS` 缺 IQ3_XXS/IQ3_S downs（FF 1024 行为 FF 640 而起，维护者说 122B 暂不在计划内） |

**归纳**：五例中没有任何一条是靠 `--resident-*` / `--mmap-experts` / `--expert-cache` 解决的（q36 不认）；`--parallel`/`--batch` 只改变 sessions 占用的那部分 KV，压不动 need 的 staging 大头；`--max-context` 从 131072 降到 8192 也只把 free 从 684 变到 674（说明上下文不是瓶颈）。

同族相关 issue（值得一起看）：
- [#3303](https://github.com/Niko1221/Strata/issues/3303) open —— q36 的 `--kv`/`--kv-resident` 根本没被解析，KV 恒为 fp32，256K 在 16 GB 卡上 OOM。
- [#4346](https://github.com/Niko1221/Strata/issues/4346) open —— hybrid 模式下打包的 Q8_0 decode 副本比 expert slots 更费显存（66→92 of 256，decode +9–10%）。
- [#4167](https://github.com/Niko1221/Strata/issues/4167) open —— `strata launch` 在 32 GB 卡上默认 `--parallel 4`，decode 掉 3–5%。
- [#3693](https://github.com/Niko1221/Strata/issues/3693) open —— 显式 `--expert-cache N` 不是上限（4497→5118 slots）。
- [#3692](https://github.com/Niko1221/Strata/issues/3692) open —— Windows HIP 下 `expert cache auto` 只给 ~3,100 slots 而 4.4 GiB 空闲。

---

## 5. 对 8–12 GB 机器的可执行清单

**A. 如果模型是 Qwen3.6-35B-A3B（q36 路径，本机现状）**
1. 别再加 `--resident-experts` / `--mmap-experts` / `--expert-cache` / `--kv` / `--vram-reserve-mib` / `--resident-budget-gib`——日志只会多几行 `ignoring …`，数字不变（本机 3 份 config 数字相同即此因）。
2. 先腾 fr（报错里的 free），再谈 slots：降 `--max-context`（8192/16384）、降 `--prefill`（512 或 `STRATA_Q36_CHUNK=512`）、`--vision` 改 CPU、关掉别的占卡程序。
3. 降 S：`--expert-vram 0`（或小值）让 S=0 走 staging-only 检查；`--expert-slots` 只在需要限上限时才传（传了报错会多一句 `, or fewer --expert-slots`）。
4. 社区唯一实测能过线的是 `STRATA_EMBED_VRAM=0`（#4458，省约 0.08 GiB，12 GB + 64 GB 机，v0.1.52）；**属"一次成功"级证据，需自测**。
5. 上游文档自己说：混合模式在 12 GB 上 `4 slots at 8K, none at 32K`（`docs/QWEN36.md` 第 82–85 行）——**12 GB 跑 q36 32K 以上，本质上就没有 slots 可用**。

**B. 如果模型是 Qwen3.8-Flash-Next / DeepSeek（基础引擎路径）**
12 GB 的直接抄 §2.1（`--resident-experts --resident-budget-gib 20` + `STRATA_RESIDENT_HEADROOM_GIB=12` + `--kv int8 --kv-resident 32768`），11 GB 抄 §2.3（`--vram-reserve-mib 700`，不加 resident）。

---

## 6. 证据 URL 一览

- 仓库主干：https://github.com/Niko1221/Strata （0.2.8 / engine 0.1.54，与本机同版本）
- q36 参数白名单与 ignore 分支：https://github.com/Niko1221/Strata/blob/main/src/qwen35/q36_engine.cu#L3727-L3795
- q36 显存拒绝算术与原文：https://github.com/Niko1221/Strata/blob/main/src/qwen35/q36_engine.cu#L2896-L2917
- q36 自测矩阵：https://github.com/Niko1221/Strata/blob/main/tools/qwen35/q36_vram_refusal.py
- 12 GB resident 全量记录（86 次启动）：https://github.com/Niko1221/Strata/tree/main/bench/results/2026-10-09-community-rtx-3060-0141
- 该记录 launch 020 原文：https://github.com/Niko1221/Strata/blob/main/bench/results/2026-10-09-community-rtx-3060-0141/launches.json#L194-L246
- 12 GB AMD HIP：https://github.com/Niko1221/Strata/blob/main/bench/results/2026-10-06-community-rx-6800m/README.md
- 11 GB 2080 Ti config：https://github.com/Niko1221/Strata/blob/main/bench/results/2026-10-02-community-rtx2080ti-11gb/strata-iq3_s.json
- 5080 + 4060 Ti 8 GB helper：https://github.com/Niko1221/Strata/tree/main/bench/results/2026-10-09-community-rtx-5080-4060ti-0.1.41
- `--memory-limit-mib` 实录：https://github.com/Niko1221/Strata/blob/main/bench/results/2026-10-08-community-2x-rtx3080-20gb-ud-q4-k-xl-512k-pool/start-command.txt
- `--low-ram on` → resident：https://github.com/Niko1221/Strata/blob/main/bench/results/2026-10-04-community-v100-16gb-ram/README.md#L25
- `STRATA_ARENA_PIN_GIB=29`：https://github.com/Niko1221/Strata/blob/main/bench/results/2026-10-11-community-rtx3090-5600x-arena-pin-by-need/strata_ab2.py#L74-L95
- `--mmap-experts` 与 `--resident-cpu-experts` 限制：https://github.com/Niko1221/Strata/blob/main/bench/results/2026-10-01-community-rtx-pro-4500/README.md
- layer-split 限制：https://github.com/Niko1221/Strata/blob/main/bench/results/2026-09-29-layer-split-limits/README.md

**说明**
- 「单次首发成功」vs「反复正确」：本文件里 §2.1（86 次启动 + 每次日志）、§2.5（`/proc/cmdline` 实录）、§2.4（启动日志逐行）属反复验证；§4 里的"`--vision` 转 CPU 起了 2 次"、"`STRATA_EMBED_VRAM=0` 起了一次"属单次/少数次，已在文中标注。
- 未找到任何 GitHub 上的 8–12 GB 机器**用 q36 模型 + `--resident-experts` 成功启动**的记录：因为该 flag 在 q36 引擎上不存在。
- `STRATA_ARENA_PIN_GIB` 的语义与推荐值：**【未核源】**（只找到 24 GB 卡上的 `=29` 一处数值）。
