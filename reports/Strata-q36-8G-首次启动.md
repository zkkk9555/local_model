# Strata q36 在 8 GB 上首次真正启动（G 系列 15 臂）与"换引擎组件"核查

日期：2026-10-30 09:36–09:56（20 分钟窗口）｜机器：RTX 4060 Ti 8 GB（8,188 MiB）、Ryzen 7 7800X3D、31.1 GB DDR5
引擎：`components/engine/0.1.54-windows-x86_64-cuda-cuda13/strata.exe`（内含 q36 迷你引擎）
模型：`model-data/models/qwen36-UD-Q4_K_XL/Qwen3.6-35B-A3B-UD-Q4_K_XL.gguf`（22,853,663,008 B，753 tensors）

## 0. 结论（三句话）

1. **8 GB 能起，但上下文上限是三位数到 1K cell**：`--max-context 256/512/1024`（配 `--chunk 128 --no-graph`）都能到 `READY`，`--max-context 2048` 差 242 MiB 起不来。原因是引擎结构：**4.40 GiB trunk（常驻显存）+ 1.10 GiB staging ≈ 5.5 GiB**，8,188 MiB 卡再扣桌面 ~0.2 GiB 与 CUDA 基线 ~1.2 GiB，留给 KV/会话的只剩几百 MiB（KV 45,056 B/token）。
2. **速度能用但不是这个用法**：全部专家（18.75 GiB）在 pageable host memory、PCIe 全程喂专家，warm decode **tg8 35.3–42.1 tok/s**、pp32 **90–121 tok/s**（首轮冷 bench 只有 4.6）。对比现役 NInfer 8091：decode 98（计数）/48.5–50（散文）、prefill 965→842、上下文 262,144、池 32,000。
3. **不值得当日常**：上下文差两个数量级（1K vs 32K 池），decode 慢 ~2.3×，prefill 慢 7–8×，启动还要 **56–63 s** 预热（把 18.75 GiB 专家搬进 host 内存）。它的价值是证明"8G 能跑 35B-A3B"，不是可用配置。

## 1. 关键算术（写死，别再来回试）

引擎准入判定原文（失败时逐字打印）：

```
strata-q36: not enough VRAM left for the hybrid experts' buffers and slots
  (1159 MiB needed, 617 MiB free after the weights, the context and the sessions)
```

- `trunk 4.40 GiB` 由权重（dense + MTP 块 + attention）决定，**任何参数都压不下去**：`--expert-vram 0`、`--mtp 0`、`--hybrid-rows 64`、`--no-graph`、`--batch 1` 全部试过，weights 行始终是 `4.40 GiB on the GPU`。
- `needed 1159 MiB` 是 **staging（2×(最大层+MTP)）+ 输出缓冲 + Σ slots**，**与上下文几乎无关**：8,192 / 2,048 都是 1159；`--max-context 512 --chunk 256` 才降到 1143。
- `free` 只随上下文线性变化：2,048→917 MiB、8,192→617 MiB、`512/chunk256`→1,119、`512/chunk128`→1,178、`256/chunk128`→1,198。
- ⇒ **过线条件是 free ≥ 1143 MiB**：`--chunk 128`（不是 256）是那最后 24–59 MiB 的来源；`--no-graph` 不改变 free 的打印值但一起保留无害。
- `--expert-slots 1` 反向加需求（1159→1235），文案也多一句 "or fewer --expert-slots" ⇒ 默认槽已是最省。

## 2. 臂台账（15 条，全部原文可查 `strata/logs/g-*.log`）

| 臂 | 参数（除 `--model`） | 结果 | 关键读数 |
|---|---|---|---|
| G1 | `--max-context 8192 --chunk 512 --serve` | 败 | 617 free / 1159 needed，差 542 |
| G2 | + `--expert-vram 0` | 败 | 同上（--expert-vram 未改变 needed） |
| G2b | + `--expert-vram 0 --batch 1` | 败 | 同上 |
| G3 | 16384 / 1.5 / slots 2 | 未跑（G1 已证上下文无关） | — |
| G5 | 2048 / chunk512 | 败 | 917 free，差 242 |
| G6 | 2048 / chunk512 / `--expert-slots 1` | 败（更差） | 917 free / 1235 needed |
| G7 | 8192 / chunk512 / `--hybrid-rows 64` | 败 | 617 / 1159（无变化） |
| G8 | 8192 / chunk512 / `--mtp 0` | 败 | 617 / 1159（MTP 块仍 loaded） |
| G9 | 2048 / chunk512 / `--no-graph` | 败 | 917 / 1159 |
| G10 | 512 / chunk256 / `--no-graph` | 败（最接近） | **1,119 free / 1,143 needed，差 24 MiB** |
| G11 | 2048 / chunk256 / `--no-graph --batch 2` | 败 | `not enough VRAM for 2 slots at a context of 2048 (0.14 GiB each, 1.16 GiB free)` |
| **G12** | **256 / chunk128 / `--no-graph`** | **起** | `1.17 GiB of VRAM free`；`hybrid experts: 0 of 256 per layer in VRAM (0.00 GiB), all 18.75 GiB in pageable host memory, the rest of a batch of <= 128 rows on 8 CPU threads, bigger prompt chunks streamed (1.10 GiB staging); 63.4 s`；`warmed up in 3.3 s` |
| G13 | 512 / chunk128 / `--no-graph` | 起（未等 READY 就收） | `1.15 GiB of VRAM free` |
| **G14** | **512 / chunk128 / `--no-graph --expert-vram 0`** | **起** | `1.15 GiB free`；staging 1.10 GiB；prep 60.3 s；`warmed up in 6.1 s`；**运行中显存 7,069 MiB / 8,188** |
| **G15** | **1024 / chunk128 / `--no-graph --expert-vram 0`** | **起** | `1.13 GiB free`；prep 57.6 s；`warmed up in 4.3 s`；**运行中显存 7,085 MiB / 8,188** |

> 失败臂全部 `EXIT=1`，每次 8–10 s 内结束；成功臂进程常驻 11.6–11.9 GB 工作集（18.75 GiB 专家在 pageable host memory，靠 OS 文件缓存/页）。

## 3. 速度实测（--bench-pp / --bench-tg）

```
$ strata.exe --model <q36.gguf> --max-context 1024 --chunk 128 --no-graph --bench-pp 32 --bench-tg 8
strata-q36: context 1024 cells, prompt chunk 128, MTP block loaded, 1.13 GiB of VRAM free
strata-q36: hybrid experts: 0 of 256 per layer in VRAM (0.00 GiB), all 18.75 GiB in pageable host memory,
            the rest of a batch of <= 128 rows on 8 CPU threads, bigger prompt chunks streamed (1.10 GiB staging); 56.3 s
strata-q36: warmed up in 2.6 s (one prompt chunk, a decode step)
bench 0: pp32 4.6 tok/s, tg8 4.6 tok/s      <- 冷（专家还没进页缓存）
bench 1: pp32 90.2 tok/s, tg8 35.3 tok/s
bench 2: pp32 120.9 tok/s, tg8 42.1 tok/s   <- warm，取这个
strata-q36: hybrid experts: 0 of 38400 batch entries on the GPU (0.0%), 38400 on the CPU pool in 7950 ms
```

- **warm decode 35–42 tok/s**（context 1,024、0 专家在卡上、8 CPU 线程）
- **warm prompt 90–121 tok/s**（pp32 只有 32 token 的提示，太小，真实长提示会更低）
- 冷启动第一轮 4.6 tok/s ⇒ 首次提问必须预热
- 对比：NInfer 8091 decode 98（计数）/ 48.5–50（散文）、prefill 965→842、上下文 262,144、池 32,000

## 4. 为什么"以前 28 臂全败"而不是参数写错（§0 结论置顶的那条）

- `strata.exe` 里有**两个程序**：全量引擎（`--pack/--native/--ple-gguf/--expert-profile/--expert-cache/--kv k8v4/--kv-resident`）与 **q36 迷你引擎**（`usage: strata-q36 --model GGUF [--max-context 32768] [--chunk 512] [--no-graph]`）。GGUF 直给 `--model` 只会走后者。
- 迷你引擎的白名单：`--model --max-context --chunk --no-graph --no-warmup --mtp --draft-vocab --expert-vram --cpu-threads --expert-slots --hybrid-rows --batch --batch-mtp --emb/--vision --bench-pp/--bench-tg --serve --n/--force --dump-full-logits`；其余一切被 `strata-q36: ignoring ... (not an option of this engine)` 丢弃。⇒ 28 臂里 `--kv k8v4`、`--kv-resident`、`--expert-cache`、`--resident-experts`、`--memory-limit-mib` **全部无效**，不是参数拼错。
- `--serve` 不是 HTTP 服务，而是 **stdin 命令 REPL**（打印 `READY <ctx> stop` 后即读 stdin）；后台 `< /dev/null` 会立刻 EOF 退出（G12 就是这个形态），要量速度用 `--bench-pp/--bench-tg`。

## 5. "换引擎组件"这条路：核查结果（m00830 问题）

- **没有 q38/flash-next 专用引擎组件可换**。`strata-feed.json` 的 `engine.packages` 共 **13 条**，按 backend/格式分：`windows-x86_64`：cuda12（902,226,219 B）、cuda13（620,425,196 B）、hip rdna2/rdna3/rx9070；`linux-x86_64`：cuda12/cuda13/hip halo/rx6000/rx7900/rx9070/sycl；`macos-arm64`：metal。`variant` 字段只表达"同一 backend 的多个构建"，**没有 by-model-family 的变体**。
- `engine_component.py` 开头明说 **There is no download path**；组件来源只有 `strata update`、`strata install`（需源码树 setup.py）、桌面版 Update engine，全部拉 feed 的同一批 tar.gz。
- 全量引擎的开关只在 **Flash-Next pack 路径**里被写进配置（`setup.py:9840-9851`：`--pack ... --native ... --native-dense-gguf ... --ple-gguf ...`，`setup.py:9938`：`args += ["--kv-resident", "32768"]`，条件 `ctx >= 65536` 且 RAM 容得下 KV）。q36 的 own-path 分支（`setup.py:7939-7943`）只写 `--native <gguf> --max-context --prefill auto --mtp`，**从不写 `--kv-resident`**。
- ⇒ 想在 8 GB 上用 `--kv-resident`/`--expert-cache`/K8V4，**只能跑 Flash-Next 制品**（ISTA-DASLab 四档 44–55 GB RAM 装不下；**Gyro-S 58.49 GB 下载中，是唯一可试的**）。换组件这条路对 q36 无解。
- 另一个副产品：`setup.py` 里 `--expert-vram` 只在显式给 `--vram-reserve-mib` 时才写（`max(vram-3.0-reserve, 0)`）——我们装模型时没给，所以初始 run config 没有它；但实测它**不影响 1159 MiB 这个 need**（见 §2）。

## 6. 复现命令（含让卡/返还）

```bash
# 让卡：只杀生产引擎，网关留着
taskkill //F //IM ninfer-serve-89.exe      # pid 16404 -> nvidia-smi 0 MiB

# 能起的最小配置
EX=/c/Project/local_model/strata/components/engine/0.1.54-windows-x86_64-cuda-cuda13/strata.exe
MD=/c/Project/local_model/strata/model-data/models/qwen36-UD-Q4_K_XL/Qwen3.6-35B-A3B-UD-Q4_K_XL.gguf
$EX --model $MD --max-context 1024 --chunk 128 --no-graph --expert-vram 0 --serve

# 量速度（不要用 --serve）
$EX --model $MD --max-context 1024 --chunk 128 --no-graph --bench-pp 32 --bench-tg 8

# 返还
taskkill //F //IM strata.exe
PROFILE=max FORCE=1 GW=1 PORT=8091 MODELID=bonsai27b-ptq1-mtp-rk2v4-40k bash scripts/serve2.sh
# 实测还原：scripts/restore-8091.sh -> "restored in 10s: 8091=200 8081=200" / nvidia-smi 7,459 MiB
```

## 7. 一句话取舍

8 GB 上 q36 的可用上限 ≈ **1K 上下文 / 35–42 tok/s decode / 90–121 tok/s prefill / 56–63 s 启动**；现役 NInfer 是 **32K 池（262K ctx） / 98 / 842 / 秒级**。除非要"用 Strata 的 API 形态跑 35B-A3B"，否则**没有实用价值**；真正值得等的是 Gyro-S（58.49 GB，跑全量引擎 + `--kv-resident`，PR #1496 的 3070 Ti 8G 32K 案例可参照，但那台机器 64 GB 内存，我们 31.1 GB 差约 1 GiB）。
