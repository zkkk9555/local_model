# Strata 实测执行手册（go 之后照这个跑）

> 目的：给「NInfer 现役 vs Strata」两条路一张可比表。所有命令都在 `C:/Project/local_model` 下执行。
> 硬约束：只碰 **8080**（Strata）；**绝不碰 8091/8081**（生产链路，NInfer 引擎+网关）。测完必须把 8091 起回去。

## 0. 前置检查（每轮开始前）
```bash
nvidia-smi --query-gpu=memory.used --format=csv,noheader          # 期望 0 MiB（否则有别人的引擎在跑）
netstat -ano | grep LISTENING | grep -E ":(8080|8081|8091|8092)\b"   # 期望无 8080
tr "\r" "\n" < strata/logs/model-install-gyro-s.log | tail -1       # Gyro 下载进度，别让它抢带宽
```

## 1. 让出卡（lead 说 go 之后）
```bash
# 找出 8091 的 PID 并连同子进程一起杀掉（这是 NInfer 生产引擎，占 ~7.3 GiB）
PID8091=$(netstat -ano | grep LISTENING | grep ":8091 " | awk "{print \$5}" | head -1)
taskkill //PID "$PID8091" //T //F
sleep 3; nvidia-smi --query-gpu=memory.used --format=csv,noheader   # 期望回落 < 500 MiB
```

## 2. 三档 ARENA_PIN（31.1 GB 机器最容易炸的点）
每档：起服 → 轮询 `/v1/models` 计时 → 跑 10 题 → 记显存峰值 → 关。
```bash
# 2.1 起（label=pin<auto|14|12>），脚本自带 nohup + pid 文件 + 日志
bash strata/tools/strata_start.sh pin-auto auto
bash strata/tools/strata_start.sh pin-14 14
bash strata/tools/strata_start.sh pin-12 12

# 2.2 起服墙钟：从发起到 /v1/models 200 的秒数
T0=$(date +%s.%N); until curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8080/v1/models | grep -q 200; do sleep 0.5; done; echo "ready_in=$(echo "$(date +%s.%N) - $T0" | bc)"

# 2.3 采样峰值（另一个窗口/后台 job，跑 1 秒 1 次）
python tools/sample_peak.py --out reports/data/peak-pin-auto.csv --seconds 600 --match "strata|python"

# 2.4 跑同一批题（判分与 NInfer 完全同口径）
python tools/bench_strata.py --base http://127.0.0.1:8080 --model qwen3.6-35b-a3b-ud-q4_k_xl \
  --label strata-pin-auto --out reports/data/strata-cmp-pin-auto.json

# 2.5 收（含子进程树）
bash strata/tools/strata_stop.sh pin-auto
```
判据：起飞失败（OOM / pinned-memory-exhausted / 引擎退出）也算一条结论，要抓 `strata/logs/strata-pin-*.log` 里的原文。

## 3. 三个工程数字
| 数字 | 怎么取 |
| --- | --- |
| 起服到 `/v1/models` 可用的墙钟 | §2.2 的 `ready_in` |
| 24K 长文档 prefill tok/s + TTFT | `python tools/bench_strata.py --longdoc 24000 --label strata-longdoc --out reports/data/strata-longdoc.json`（脚本内置「最后一段编号是多少」的自检题） |
| 显存峰值 + 进程 WS(RAM) | `tools/sample_peak.py` 的 `peak_gpu_mib` / `peak_ws_bytes`，同时取一次推理瞬间的 `nvidia-smi` |

## 4. `--prefill-head-alias` A/B
```bash
bash strata/tools/strata_start.sh headalias auto strata/install/strata-qwen36-headalias.json
python tools/bench_strata.py --longdoc 24000 --label strata-headalias-longdoc --out reports/data/strata-longdoc-headalias.json
bash strata/tools/strata_stop.sh headalias
```
对手口径：8 GB 卡上 prefill 从 306 → 667 tok/s（+118%），decode 不变、代价是 ≤512 token 的短提示多 0.6–0.75 s。我们验的是同一条。

## 5. 恢复生产链路（**必做**）
```bash
cd /c/Project/local_model
PROFILE=max FORCE=1 GW=1 PORT=8091 MODELID=bonsai27b-ptq1-mtp-rk2v4-40k bash scripts/serve2.sh
# 若 max 档没落盘（起不来）改：PROFILE=ctx40 FORCE=1 GW=1 PORT=8091 MODELID=bonsai27b-ptq1-mtp-rk2v4-40k bash scripts/serve2.sh
until curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8091/v1/models | grep -q 200; do sleep 1; done; echo RESTORED
```
然后 `send_message` 给 lead：「已恢复」（附 `/v1/models` 200 + 显存读数）。

## 6. 已知坑（来自安装阶段实测）
- `STRATA_ARENA_PIN_GIB` Windows 默认 **29 GiB**，31.1 GB 内存照抄必炸；本机可试上限 ~12–14。
- 引擎 argv 里的 `--prefill-head-alias` 必须整体出现在 args 里；用 `--set` 时写法是 `--set=--prefill-head-alias=on`（空值会被静默丢弃）。
- run config 里 `--max-context 32768`；prompt 超上下文会被 **400 拒绝**（不截断），24K 提示要留够 `max_tokens` 余量。
- `serve/server.py` 单序列 FIFO，`--parallel` 默认按卡自适应；并发会各吃 ~1.5 GB 显存，8 GB 卡只跑 1 路。
- Gyro-S 在 setup 阶段已自动选 **low-RAM（专家走 OS 文件缓存、GPU 只放 ~8%）**，官方原文警告「most of the experts are read from the SSD while it answers: expect it to be much slower」。
## 7. 已做的零 GPU 冒烟验证（这条管线是通的，不是纸上方案）
- `serve/server.py --engine mock --port 8080` 起得来：`/v1/models` 立即 200，负载 `{"id": "qwen3.8-flash-next", "n_ctx": 32768}`
- `tools/bench_strata.py` 打它 10 题全流程跑通：stream 解析、`usage.prompt_tokens/completion_tokens`、TTFT 计时、`must_contain/must_not_contain` 判分都正确（mock 只会回 "Hello from the mock engine."，所以 9 FAIL / `neg1` 因无 must_contain 而 PASS —— 符合判分规则）
- `--longdoc` 模式跑通（mock 报的 prompt_tokens 是假的，真值等真引擎）
- 冒烟后已按端口精确 `taskkill`，`8080 free`，`8091/8081` 原样未动
- 冒烟结论：真引擎接上 8080 后，一条命令就能出表；不需要在窗口里现场调试脚本