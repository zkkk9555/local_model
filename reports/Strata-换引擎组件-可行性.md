# Strata「换引擎组件」可行性核查（一页）

日期：2026-10-30 10:00 左右｜本地引擎：`components/engine/0.1.54-windows-x86_64-cuda-cuda13/`（strata 0.1.54，cuda13，sm_75/86/89/120）

## 结论（先看这个）

1. **不存在"q38 / Flash-Next 专用引擎组件"可换。** 官方 feed 的 `engine.packages` 共 **13 条**，全部按 **backend × 格式** 分（windows: cuda12 / cuda13 / hip rdna2 / rdna3 / rx9070；linux: cuda12 / cuda13 / hip halo / rx6000 / rx7900 / rx9070 / sycl；mac: metal）。`variant` 字段的语义是"同一 backend 的多个构建"，**没有 by-model-family 的变体**。
2. **全量引擎已经在本地这个 exe 里**（`strata.exe` 内含两套程序），换组件不会带来"另一支引擎"；能不能用 `--kv k8v4` / `--kv-resident` / `--expert-cache` / `--expert-profile`，取决于**模型制品的形态**（Flash-Next 的 pack vs 纯 GGUF），不取决于组件版本。
3. ⇒ 对 Qwen3.6-35B-A3B（纯 GGUF）**换组件无解**，它在 8 GB 上永远是 q36 迷你引擎、永远没有 KV 流式（上下文上限 ≈1K，见 `reports/Strata-q36-8G-首次启动.md`）。**唯一可能有解的是 Flash-Next 制品**（现在只有 Gyro-S 58.49 GB 在本机装得下）。

## 证据

- `strata_control/engine_component.py` 明说 **There is no download path**；组件只由 `strata update` / `setup.py`（`strata install` 要源码树）/ 桌面版 Update engine 从签名 feed 拉取。本机组件与 feed 的 `windows-x86_64 cuda cuda13` 包（620,425,196 B）对应。
- 全量引擎开关的写入口（Windows 主流程，`app/control/setup.py`）：
  - `9840-9851`：`model_args = ["--pack", pack, "--native", dense, "--native-dense-gguf", dense, "--ple-gguf", ple, ...]`；`args = [*model_args, "--expert-profile", data/expert-profile.bin, "--expert-cache", "auto", "--prefill", "auto", "--spec", "4", ...]`
  - `9938`：`args += ["--kv-resident", "32768"]`（条件 `ctx >= 65536` 且 RAM 够 KV 流式；`--kv-streaming on|off` 可覆盖）
  - q36 own-path 分支 `7939-7943`：`args = ["--native", gguf, "--max-context", ctx, "--prefill", "auto", "--mtp", mtp]`（+ 可选的 `--expert-vram`，仅当显式给 `--vram-reserve-mib` 时）——**从不写 `--kv-resident` / `--expert-cache` / `--kv`**
- 实测印证：走 GGUF 直喂时，引擎逐条回 `strata-q36: ignoring --kv k8v4 / --kv-resident 20480 / --expert-cache 512 / --resident-experts (not an option of this engine)`；28 臂因此全部无效（台账见 `reports/Strata-8G实测-Qwen36起不来.md`）。

## Flash-Next 侧的数字（决定"值不值得换"）

| 制品 | 下载/装盘 | 需要的内存口径 | 本机 31.1 GB RAM + 8 GB VRAM = 39.1 GB |
|---|---|---|---|
| ISTA-DASLab Q2_0 | 66–76 GB | RAM+VRAM 37.6 GB（专家 34 GB）| 卡边（规则要求 RAM ≥ 专家 + ~10 GB）⇒ **装不下** |
| IQ2_XS | 同上 | 39.2 GB（专家 35.5）| 装不下 |
| IQ3_XXS / IQ3_S | — | 47.0 / 54.8 GB | 装不下 |
| Coder IQ1_M（专家 29.6 GB）| — | RAM ≥ 39.6 GB | 勉强不行，不作首选 |
| **Gyro-S（TQ1_0，58,487,015,808 B）** | 58.49 GB | **VRAM+RAM 合计 27.6 GB**（专家 25.8 GB）| **唯一装得下**（质量 lower）|
| DeepSeek V4.1-Flash | 239–274 GB | ≥12 GB 显存 + ≥46 GB RAM | 排除 |

## 风险 / 待验

- Gyro-S 走全量引擎 + `--kv-resident` 时，PR #1496 的成功样本是 **8 GB 卡 + 64 GB RAM（33 GiB 专家 arena 常驻 pinned RAM）**；本机 31.1 GB ⇒ 大约差 1 GiB 的 arena，可能起得来但更依赖 SSD 读取（setup 已自动选 low-RAM：「experts (26 GB) are read from the model folder through the OS file cache」）。
- `STRATA_ARENA_PIN_GIB`（Windows 默认 **29** GiB）在这台机器上会直接炸，必须先压到 12–14 或 `auto`。
- 换组件本身不花显存、不改血统，但**引擎降级会让 Gyro 打不开**（引擎早于 trellis kernels 时会在加载期拒收，setup.py:8685 注释），所以别回滚引擎。

## 建议

1. 等 Gyro-S 下完（58.49 GB），用现成 run config（全量引擎 + `--kv-resident 32768` 只在 ctx ≥ 65536 才写，届时先 32K）实测一次；`STRATA_ARENA_PIN_GIB` 从 `auto` → 12 两档。
2. q36 这条线定案：**8G 上只有 1K 上下文**，不要作为日常；保留 `reports/Strata-q36-8G-首次启动.md` 的读数即可。
3. 不做 `strata components update/rollback`（会触发引擎测试启动；且没有 q38 变体可得）。
