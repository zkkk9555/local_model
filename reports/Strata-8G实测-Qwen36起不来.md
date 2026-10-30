# Strata 在 8 GB 显存上的实测结论（Qwen3.6-35B-A3B）

日期：2026-10-30 09:00–09:20（窗口 40 分钟）
机器：RTX 4060 Ti 8 GB（8,188 MiB，sm_89）、Ryzen 7 7800X3D、31.1 GB DDR5、Win11、驱动 616.92
引擎：Strata engine 0.1.54 (windows-x86_64-cuda-cuda13, commit 8c1aea4bca1b, archs sm_75/86/89/120)
模型：Qwen3.6-35B-A3B UD-Q4_K_XL（22.85 GB）+ mmproj-F16（0.86 GB），arch `qwen35moe`

## 1. 结论（一句话）

**起不来。** Qwen3.6-35B-A3B 在这张 8,188 MiB 的卡上，把上下文压到 2K、KV 换 q4_0、关视觉、关 MTP、专家槽压到 1，引擎仍然报

```
strata-q36: not enough VRAM left for the hybrid experts' buffers and slots
  (1159 MiB needed, 917 MiB free after the weights, the context and the sessions)
```

即**缺 242–418 MiB，而且无论怎么压都补不上**（详见 §3）。这不是「慢」，是「不上卡」。

## 2. 窗口操作与恢复记录（生产链路已还原）

| 步骤 | 命令 | 结果 |
| --- | --- | --- |
| 让卡 | `taskkill //PID 7740 //F`（ninfer-serve-89）、`//PID 31524 //F`（网关 8081） | nvidia-smi 7,459 → **0 MiB** |
| 测试 | `serve/server.py --engine strata --config <cfg> --port 8080 --parallel 1` | 共 28 臂，全部 EngineDied |
| 收尾 | 8080 上所有 LISTENING pid 全 `taskkill //T //F` | `no strata process`，8080 空 |
| 恢复 | `PROFILE=max FORCE=1 GW=1 PORT=8091 MODELID=bonsai27b-ptq1-mtp-rk2v4-40k bash scripts/serve2.sh` | **8091=200、8081=200（5 秒内）、nvidia-smi 7,459 MiB** |

恢复后的进程：8091 = pid 28720，8081 = pid 29688；`api base http://127.0.0.1:8091/v1`，model `bonsai27b-ptq1-mtp-rk2v4-40k`。

## 3. 显存账（这张卡的硬算术）

引擎在加载完权重、上下文和会话之后，打印「还剩多少 VRAM」，再拿它和「混合专家缓冲 + 槽」的需求比：

| 上下文 | 权重上卡后剩余 | 引擎需求（默认 auto 槽） | 缺口 |
| --- | --- | --- | --- |
| 32K | 0.00 GiB | 1159 MiB | 全部 |
| 16K | 0.21 GiB（217 MiB） | 1159 MiB | 942 MiB |
| 8K | 0.60 GiB（617 MiB） | 1159 MiB | 542 MiB |
| 4K | 0.80 GiB（817 MiB） | 1159 MiB | **342 MiB** |
| 2K | 0.90 GiB（917 MiB） | 1159 MiB | **242 MiB** |

权重那一步的原文：

```
strata-q36: 753 tensors (layout checked), 4.40 GiB on the GPU in 3.6 s
  (the routed experts are placed after the engine's buffers)
```

要点：

- **每减半一次上下文只回收 200–400 MiB**（32K→16K +217、16K→8K +400、8K→4K +217、4K→2K +100），所以从 32K 一路压到 2K 只换来 917 MiB，而需求量是 1159 MiB，**天生差 242 MiB**。
- 需求量本身**压不下去**：`--expert-slots N` 只会让它变大（1→1235、2→1310、4→1460、8→1759、32→3559 MiB），默认 auto 已经是最小值 1159。

## 4. 28 臂台账（全部 EngineDied，8–10 秒内）

| 臂 | 上下文 | 额外配置 | 剩余 VRAM | 需求 | 结果 |
| --- | --- | --- | --- | --- | --- |
| A | 32K | 原样（setup 生成的 run config） | 0.00 GiB | 1159 MiB | 死 |
| B | 16K | 去 `--vision` | 0.21 GiB | 1159 | 死 |
| C | 16K | + `STRATA_ARENA_PIN_GIB=auto` | 0.21 GiB | 1159 | 死 |
| D | 16K | + `STRATA_ARENA_PIN_GIB=14` | 0.21 GiB | 1159 | 死 |
| E | 16K | 真去 `vision` 段 + 去 `--mtp` | 0.21 GiB | 1159 | 死（MTP block 仍加载） |
| F | 8K | 去 vision/MTP + PIN=14 | 0.60 GiB | 1159 | 死 |
| G | 16K | `--kv q4_0` | 0.21 GiB | 1159 | 死（无变化） |
| H | 8K | `--kv q4_0` | 0.60 GiB | 1159 | 死 |
| I | 4K | `--kv q4_0` | 0.80 GiB | 1159 | 死 |
| J | 4K | `--conversation-cache-slots 1` | 0.80 GiB | 1159 | 死（无变化） |
| K | 4K | 1 槽 + `--trim-stage-weights` + `STRATA_EMBED_VRAM=0` | 0.80 GiB | 1159 | 死（无变化） |
| L/M/N | 4K/8K/16K | `--no-capture` | 0.80/0.60/0.21 GiB | 1159 | 死（无变化） |
| O/P | 8K/16K | `--expert-slots 32` | 0.60/0.21 GiB | 3559 | 死 |
| Q | 16K | `--expert-slots 8` | 0.21 GiB | 1759 | 死 |
| R | 4K | `--expert-slots 4` | 0.80 GiB | 1460 | 死 |
| S | 4K | `--expert-slots 2` | 0.80 GiB | 1310 | 死 |
| T | 4K | `--expert-slots 1` | 0.80 GiB | 1235 | 死（差 418 MiB） |
| U/V/W | 16K/8K/2K | `--mmap-experts`、`--resident-cpu-experts` | 0.21/0.60/0.90 GiB | 1159 | 死（引擎原文 `ignoring --mmap-experts (not an option of this engine)`） |

（同一配置重复次数未计入，实际起服尝试 28 次，全部在同一处失败。）

## 5. 为什么压不动（机制）

- **权重刚性**：35B 的稠密部分（含 MTP 块、mmproj）就是 4.40 GiB，必须上卡；引擎没有「把多少层放 CPU」的旋钮（`--mmap-experts` / `--resident-cpu-experts` 是 control 层的旧名字，0.1.54 引擎原文 `ignoring ... (not an option of this engine)`）。
- **MTP 是权重里的一块**：去掉 `--mtp` 也不省显存，日志照样打 `MTP block loaded`。
- **KV 不是瓶颈**：Qwen3.6 的 KV 是 45,056 B/token（10 个注意力层 × 2 KV 头 × 256 × K/V × 4 B），32K 才 1.44 GB；`--kv q4_0` 实测连 1 MiB 都没变（这条路径在 `qwen35moe` 上不走）。
- **需求侧 1159 MiB 是「混合专家的缓冲 + 槽」**，是 arch 决定的固定开销，只能靠更多显存或更小的模型解决。

## 6. 和 NInfer 现役方案比：值不值

**不值，而且不需要比速度——它根本起不来。**

| | NInfer（现役 8091） | Strata + Qwen3.6-35B-A3B |
| --- | --- | --- |
| 8 GB 起服 | 可以，常驻 7,459 MiB | **不行**，缺 242–418 MiB |
| 上下文 | 池 32,000（计数）/ 262,144 ctx 声明 | 理论上 32K，实际连 2K 都进不去 |
| decode | 计数 98 tok/s（散文 48.5–50.0） | 无读数 |
| 权重放哪 | 5.54 GiB 常驻 + KV 池，专门为 8 GB 调过 | 4.40 GiB 上卡后没有余量给专家缓冲 |

## 7. 还没试的那一档：Gyro-S（下个窗口）

- Gyro-S = Qwen3.8-Flash-Next 的 TQ1_0 档，58.49 GB，`mem_total: True`（VRAM+RAM 合计 27.6 GB），setup 自动选了 **low-RAM 模式**：
  `Gyro-S's experts (26 GB) are read from the model folder through the OS file cache instead of a copy in RAM (31 GB); the GPU holds ~8% of them`
  —— 即**专家靠 SSD 页读、GPU 只放 8%**，这是唯一一条绕开「权重+专家缓冲」死结的设计。
- 下载状态：09:01 起，09:15 到约 7%（~5 MB/s，比文档估的 5.8 MB/s 还慢），ETA 3 小时上下；日志 `C:/Project/local_model/strata/logs/model-install-gyro-s.log`。
- 下一窗口的判据和这一轮相同（起得来/起服墙钟/decode/TTFT/显存峰值），但预期 decode 会很低（专家走 SSD）。

## 8. 复现命令

```bash
# 1) 让卡（生产链路 pid 会变，务必先 netstat 确认）
taskkill //PID <ninfer-serve-89 pid> //F
taskkill //PID <8081 gateway pid> //F

# 2) 单臂试起（8–10 秒出结论，不占卡）
cd /c/Project/local_model/strata/app/control
./python/python.exe serve/server.py --engine strata \
  --config C:/Project/local_model/strata/install/q36-C-16k.json --port 8080 --parallel 1
```

配套脚本：`strata/tools/strata_try.sh`（单臂）、`strata/tools/ladder*.sh`（臂序列）、`strata/tools/mkcfg*.py`（改 `args` 与 `args_written`，并把 `vision` 段整段删掉，否则 `serve/server.py:3191` 会把 `--vision` 补回来）。

恢复：见 §2 最后一行。

## 9. 补记：唯一没试的显存旋钮为什么也不是解（算过账，未实测）

`strata.exe --help` 里唯一能把 KV 从显存挪走的开关是 `--kv-resident N`（原文：`KV streaming: keep N cells of each QSA layer in VRAM (min 20480) and the whole K/V in pinned RAM; the freed VRAM goes to expert slots`；且「A context of N cells or fewer is not streamed」）。

代进去算：

- Qwen3.6 的 KV = 45,056 B/token ⇒ 32K 的 KV 在显存里是 1.44 GiB；`--kv-resident 20480` 之后显存里只剩 20,480 × 45,056 B = **922 MB**（省 518 MiB）。
- 但 32K 的基线是「剩 0 MiB」，省出 518 MiB 后仍是 518 MiB < 需要 1159 MiB ⇒ **还是差 641 MiB**。
- 而且 4K 上下文本来就不触发流式（`N cells or fewer is not streamed`），4K 下的 817 MiB 不会因为这条开关变多。

另外从 2K 那一臂可以反推「权重 + 上下文 + 会话」之外的固定成本：8,188 − 917 = 7,271 MiB 被吃掉，其中权重 4,506 MiB、KV 92 MiB ⇒ **会话/缓冲约 2.6 GiB 是引擎自身的固定开销**，这部分没有开关可压。

⇒ 结论加固：**8 GB（8,188 MiB）不是「调参能过」的边界，而是缺一整档**（缺 240–420 MiB 的专家缓冲，且被 2.6 GiB 的固定会话开销压在下面）。

