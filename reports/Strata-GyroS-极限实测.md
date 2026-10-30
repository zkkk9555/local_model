# Strata Gyro-S 极限实测（2026-10-30，RTX 4060 Ti 8 GB / 31 GB）

被测：`Qwen3.8-Flash-Next-Gyro-S-TQ1_0.gguf`（58.49 GB，mmap-experts + 专家缓存 + MTP draft 4），
控件：`strata/app/control/python/python.exe serve/server.py --engine strata --config <cfg> --port 8095`。

## 0. 三个数（先给结论）

| 指标 | 实测值 | 依据 |
|---|---|---|
| **上下文上限** | **32,768 起得来**（8 K / 16 K / 32 K 全 READY；32 K 带 images on） | 三条起服日志 + `context 32768 tokens` |
| **decode** | **19.0 – 24.4 tok/s**（8 K 臂 19.0 / 24.4；32 K 臂 22.3） | 引擎自报 `N generated in M ms` |
| **首字** | warm 短问 **1.30–3.52 s**；冷 10.59 s；2.2 k 汉字 **21.1 s**；7.4 k 汉字 **28.7 s** | `bench_gyro.py` stream TTFT + 引擎 `prompt ... read in` |

结论：**留作长上下文备胎，不顶替 NInfer。** 现役 8091 是 98 tok/s、池 32,000；Gyro-S 慢 4–5 倍，
上下文并没更大（32 K vs 32 K），只有「整篇吞 > 5k token 且可等 20–30 s」这一种场景划算。

## 1. 怎么跑起来（复现命令）

```bash
# ① 腾卡：停 NInfer（本次用 kill 8091，未动 switch.sh 的 profile）
taskkill //F //IM ninfer-serve-89.exe
# ② 生成 ctx 变体（原 config 是 32768/--vision，我另做 8k/16k 档）
cd C:/Project/local_model/strata && ./app/control/python/python.exe tools/mk_gyro_ctx.py 8192
# ③ 起服（注意：CFG 必须写正斜杠，反斜杠在 ${VAR:-word} 里会被吃掉）
CFG=C:/Project/local_model/strata/install/strata-gyro-gyro-s-8k.json PORT=8095 bash tools/start_gyro.sh
# ④ 测速
./app/control/python/python.exe tools/bench_gyro.py http://127.0.0.1:8095 short 96
./app/control/python/python.exe tools/bench_gyro.py http://127.0.0.1:8095 mid 32
# ⑤ 还原生产
taskkill //F //IM strata.exe; bash C:/Project/local_model/scripts/switch.sh ninfer
```

起服器环境：`STRATA_COMPONENTS_DIR=C:/Project/local_model/strata/components`、`STRATA_INSTALL_DIR=.../install`、
`STRATA_ARENA_PIN_GIB=auto`、`STRATA_EXIT_WITH_PARENT=0`、`nohup`（git-bash 无 setsid）。

## 2. 起服读数（日志原文）

| ctx | 就绪行 | GPU used | 引擎 free 提示 | 起服耗时 |
|---|---|---|---|---|
| 8192 | `ready: http://127.0.0.1:8095/v1 ... context 8192 tokens` | 6,684 MiB | `719 MiB of VRAM free with everything loaded` | < 50 s |
| 16384 | `... context 16384 tokens` | 6,641 MiB | 719 MiB | < 70 s |
| 32768 | `... context 32768 tokens, images on` | 6,899 → 7,045 MiB | 719 MiB | < 70 s |

（耗时是 sleep 粒度上限：50 s / 70 s 后已 READY；启动器自己先打印 `YOUR PC CAN BE SLOW OR STOP
RESPONDING FOR 1-3 MINUTES NOW - this is normal.`）

显存不是瓶颈——三档 free 都是 719 MiB，KV 用 int8 且按需分配。压着的是内存：

```
strata serve: conversation cache sized from the free RAM: 6400 MiB for up to 4 parked conversations
strata serve: conversation cache: parked 157 tokens in 46.7 ms; parked=1 bytes=238574308 evictions=0
windows commit: 24.9 GiB left of a 54.1 GiB limit
```

32 K 臂进程：`strata.exe` WS **21,312,944 K ≈ 21.3 GB**，`strata-vision.exe` 1,085,408 K。

## 3. 请求实测

### 3.1 短问（59 prompt tok，max_tokens 96）

```json
{"ttft_s": 10.59, "wall_s": 11.78, "usage": {"completion_tokens": 69}}   # 冷
{"ttft_s": 1.30,  "wall_s": 3.12,  "usage": {"completion_tokens": 56}}   # warm
{"ttft_s": 2.19,  "wall_s": 3.35,  "usage": {"completion_tokens": 72}}   # warm2
```

### 3.2 中档（2,207 prompt tok / 3,362 汉字，问一道算术，答对 60）

```
prompt 2207 tokens = 0 reused + 2207 read in 18528 ms (119.1 tok/s),
  48 generated in 2531 ms (19.0 tok/s), drafts accepted 29 of 36
decode expert cache hit rate: 23.8%
expert tiers: ... since the start RAM 0 blobs, files 0 blobs 148125.8 MB read
```
TTFT **21.09 s**，wall 21.09 s。

### 3.3 长档（7,447 prompt tok / 11,402 汉字）

```
prompt 7447 tokens = 0 reused + 7447 read in 27349 ms (272.3 tok/s),
  32 generated in 1311 ms (24.4 tok/s), drafts accepted 19 of 22
decode expert cache hit rate: 42.5%
expert tiers: ... files 0 blobs 367696.9 MB read      <-- 一轮读盘 368 GB
```
TTFT/wall **28.72 s**。

### 3.4 32 K 臂（context 32768）

```
短问 warm: ttft 3.52 s / wall 4.82 s（96 tok）；另一次 ttft 7.53 s / wall 8.99 s
mid 2207 tok: prompt ... read in 19782 ms (111.6 tok/s), 32 generated in 1434 ms (22.3 tok/s),
              drafts accepted 21 of 27, hit rate 16.0%
```

## 4. 与 NInfer 现役对照

| | NInfer 8091（现役） | Gyro-S 8095 |
|---|---|---|
| decode | **98 tok/s**（计数型）/ 48.5–50 散文 | 19–24 tok/s |
| 上下文 | 池 32,000（KV 落盘 3.0 GiB） | 32,768 |
| 首字 warm 短问 | 亚秒 | 1.3–3.5 s |
| 首字 7 k 汉字 | 数秒 | 28.7 s |
| 显存 | 7,074 / 8,188 MiB | 7,045 / 8,188 MiB |
| 额外成本 | — | 7.4 k 提示读盘 368 GB |

## 5. 判定

- **可行、但不划算**：8 GB 能跑 32 K，代价是 4–5 倍慢 + 每轮几十 GB 读盘。
- **建议用法**：日常 8091；需要一次吞整篇长材料（>5 k token、可等 20–30 s）时临时切 8 K 或 16 K 臂。
- **不建议** 32 K 常态跑：free 只剩 573 MiB，引擎自己都在喊 `Add --vram-reserve-mib 1152`。
- **还原已做**：`switch.sh ninfer` → 8091=200、8081=200、GPU 7,637 MiB、`ninfer-serve-89.exe` pid 3612。
  （遗留：8081 有重复 LISTENING pid 33232/3588，不影响推理，建议清一次。）