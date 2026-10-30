# 从零重建：把这条 8 GB 显存上的本地模型链重新装起来

> 这个仓库只放**能放的东西**：脚本、工具、文档、实测报告、配置样例、校验值。
> 引擎（0.8–1.4 GB）、模型权重（6.4 GB）、llama.cpp bundle（0.6 GB）都超过 GitHub 单文件限制，**没有**放进仓库，
> 它们的**下载地址 + 字节数 + SHA-256** 全部列在 §3 / §4 里，照着下、照着校验即可。

---

## 0. 这份仓库能恢复到什么程度

| 项 | 能不能恢复 | 依据 |
| --- | --- | --- |
| NInfer 引擎（sm_89 / 4060 Ti 档） | ✅ 可恢复 | 官方 GitHub Release 或作者网盘，§3.1 |
| 模型 bonsai2_27b_ternary_ptq1_native_mtp.ninfer | ✅ 可恢复 | 作者网盘分发包内，§3.2 |
| 9 个运行期 DLL | ✅ 可恢复 | §3.3 给了每个 DLL 的来源与 SHA-256 |
| llama.cpp 262K 路线（bundle + GGUF） | ✅ 可恢复 | HuggingFace 公开仓库，§4 |
| 起服脚本 / 换档脚本 / 分片代理 / 控制台 | ✅ 仓库内直接可用 | `scripts/`、`tools/` |
| DSH（DeepSeek Harness）里的四个模型条目 | ✅ 配置样例 | `config/dsh-providers.example.yml` |
| 全部实测读数与结论 | ✅ 仓库内 | `reports/`、`docs/` |
| 原始日志（23 MB）与抓取到的网页/JSON 原件 | ⚠️ 只留了报告里引用的片段 | 未全部入库 |

---

## 1. 机器要求（缺一条就跑不起来）

| 项 | 要求 | 本机（参考） |
| --- | --- | --- |
| GPU 架构 | sm_80 / sm_86 / sm_89 / sm_120a 之一；**4060 Ti 是 sm_89** | RTX 4060 Ti 8 GB（AD106, 10DE:2803） |
| 显存 | ≥ 8 GB（官方四档里最小一档） | 8,188 MiB |
| 内存 | ≥ 16 GB，建议 32 GB（host KV 层、页回迁都吃内存） | 31.1 GB DDR5-6000 |
| 系统 | Windows 10/11 x64；**路径必须纯 ASCII、不含空格** | Win11 Pro 26100，`C:/Project/local_model` |
| 驱动 | NVIDIA ≥ 570（含 CUDA UMD 13.x）。**不要装 CUDA Toolkit、不要装 cuDNN** | 616.92 / UMD 13.4 |
| VC++ 运行库 | `msvcp140.dll`、`vcruntime140.dll`、`vcruntime140_1.dll`（VC++ 2015-2022 Redistributable） | System32 里已有 |
| 工具 | bash（Git for Windows）、Python 3.10+（只用标准库） | git 2.56 / Python 3.12.10 |

> 关键认知：**这套东西不需要编译**。作者发的是预编译 exe（每个架构一支），我们没有 CUDA Toolkit / VS Build Tools 也跑起来了。

---

## 2. 目标目录结构

```
C:/Project/local_model/            ← 路径必须与这里一致，脚本里 ROOT 是硬编码的
  engine/                          ← 引擎 + 9 个 DLL（约 1.4 GB）
    ninfer-serve-89.exe
    cudart64_13.dll  cublas64_13.dll  cublasLt64_13.dll
    avcodec-63.dll  avformat-63.dll  avutil-61.dll  swscale-10.dll  swresample-7.dll
    libcurl-x64.dll
  models/                          ← 权重（6.4 GB）
    bonsai2_27b_ternary_ptq1_native_mtp.ninfer
  llama8g/bundle/                  ← 【可选】llama.cpp 262K 路线
    bin/llama-server.exe  models/…gguf  artifacts/api_key.txt
  scripts/  tools/  docs/  reports/  logs/  tmp/
```

**如果你不想放在 `C:/Project/local_model`**：把 `scripts/serve2.sh`、`scripts/switch.sh`、`scripts/longctx.sh`、
`scripts/console.sh`、`scripts/llama-*.sh` 顶部的 `ROOT=` / `ROOT_DIR=` 常量改成你的路径（全局搜 `local_model` 即可）。

---

## 3. NInfer 路线（主力）：要下的三样东西

### 3.1 引擎（二选一）

**选 A（推荐，一次到位）**：作者网盘 `ninfer-engine-packs-3arch-20261013/engine-pack-sm89`

- 链接：<https://pan.quark.cn/s/5af2f61bc482>（夸克，需登录才能下载，匿名只能列目录）
- 内容：`engine/ninfer-serve-89.exe` + 12 个 DLL + `SHA256SUMS.txt`（16 条）+ `README-pack.md`
- 引擎：**795,030,528 B**，SHA-256 `9fa7490bcbc4825a77673c5f8c6ffdbf25aab5b3e768a54d8bcebd7161ca41eb`
- 校验：进目录后 `sha256sum -c SHA256SUMS.txt`，应 16 条全 OK

**选 B（GitHub 官方 Release，只有 exe，没有 DLL）**

- <https://github.com/1314521gjy/ninfer-fusion-kvmem/releases/tag/engine-v0.11.0-kvmem-20261008>
- 资产 `ninfer-serve-89.exe`：**801,324,544 B**，SHA-256 `3b6f9af936a1e20520c3de3a4185f627ba59481139659cf3104bdead815ef6e4`
- DLL 要按 §3.3 自己配齐，否则启动直接 `0xC0000135`（找不到 DLL）

> 两支 exe 是不同构建（差 6 MB）。8 GB 卡上我们实测的主力是 B 支（`engine/ninfer-serve-89.exe`），
> A 支是作者 2026-10-13 的更新构建，带 8 GB 档修复；换引擎前后请按 `reports/` 里的同一套基准复测。

### 3.2 模型权重

| 文件 | 字节 | SHA-256 |
| --- | --- | --- |
| `bonsai2_27b_ternary_ptq1_native_mtp.ninfer` | 6,394,697,216 | `5c4486c8a52687e3f62072c7dd2a320546d0e00d1c019bf137eb02cc944e21b8` |

来源：这份 PTQ1 件**公共 HuggingFace 上没有**（HF 只有 8.87 GiB 的 PQ2 全件，8 GB 卡装不下），只存在于作者分发包里。两条路：

1. 网盘 <https://pan.quark.cn/s/d4a29bfcb547> → `infer-27b-kv-stream-3arch-20261019-r3.zip`（约 2.09 GB）：
   解开后 `model/bonsai2_27b_ternary_ptq1_native_mtp.ninfer` 就是它，另外还带 sm89 引擎与 runtime DLL —— **这条路最省事，模型 + 引擎一次拿全**。
2. 网盘 <https://pan.quark.cn/s/4c7d9e017d98>（aivault 的引擎/模型分目录）也收着同族模型件。

### 3.3 九个运行期 DLL（官方 Release 不带，必须自备）

| DLL | 字节 | SHA-256 | 从哪里来 |
| --- | --- | --- | --- |
| `cudart64_13.dll` | 551,024 | `b00ca6f53699120da815bf3e06e2e4285fae2f201235b883dcbb50eec51e2a2a` | PyPI `nvidia-cuda-runtime-cu13` 13.3.29 win-x64 |
| `cublas64_13.dll` | 51,870,320 | `f1d500d0cd892f5b8c6b6cdbffd82d0c55d5f5427215668e7ceb55aeeccc1b63` | PyPI `nvidia-cublas-cu13` 13.5.1.27 win-x64 |
| `cublasLt64_13.dll` | 460,301,424 | `b592cd016d7673e9cb97716a22b27c4010ee635377a3ba28f37070a9bdb76a68` | 同上 |
| `avcodec-63.dll` | 91,810,816 | `1ab43ac33e92aad9f29e82e6b4f57e06ff3537097d71908786d1388a6032ea45` | BtbN FFmpeg-Builds `ffmpeg-n9.0-latest-win64-lgpl-shared` |
| `avformat-63.dll` | 23,003,136 | `1082bdcb0fd3bb62205a2be123350f2f4fa67a1478bb0162989d65c1463d29ef` | 同上 |
| `avutil-61.dll` | 3,025,408 | `aabe139afdf6c3277d490faddaac739c8ed616739bd9287cd53a7a56ba919022` | 同上 |
| `swscale-10.dll` | 2,343,936 | `c10c48b8003ed5730b3ece95009a2db5c5e49c40c0a0b07c3b305ddc7fcc01f4` | 同上 |
| `swresample-7.dll` | 747,008 | `dc8594e1c7cc627a2f2a1510c98a6b823a8dff95455684aafcfd3514dc12eb93` | 同上 |
| `libcurl-x64.dll` | 3,722,344 | `d8bfa3e3ed29c29dc4db02afda0355f4a67990e93a3a4ecb089bf09a6071131d` | curl.se `curl-8.23.0_6-win64-mingw` |

前三个 CUDA DLL 与作者 `SHA256SUMS.txt` 逐字节相同；FFmpeg 五个与 libcurl 是**不同构建**（大版本号一致、ABI 兼容），哈希与作者清单不同 —— 我们实测可用。

### 3.4 起服

```bash
cd /c/Project/local_model
bash scripts/switch.sh ninfer        # 40K 日常档：池 40,000 + MTP draft4 + rk2v4-e8 KV，显存约 7,570 MiB
bash scripts/switch.sh long72        # 72K 长文档档：关 MTP，池 72,000，显存约 7,301 MiB
bash scripts/switch.sh llama         # 换 llama.cpp 262K 路线（需要 §4 的件）
bash scripts/switch.sh status        # 看谁在 8091 / 显存多少
```

底层就是（`scripts/serve2.sh` 的 `max` 档）：

```bash
export NINFER_KV_WINDOW=16384 NINFER_HOST_PAGEABLE=1 NINFER_KV_REUSE_HOSTBACKED=1 NINFER_TERNARY_PTQ1_FAST=1
export unset NINFER_KV_RETRIEVE    # 留空 = 引擎自动给证据预算（池的一半）；写死会少 3.9 倍
engine/ninfer-serve-89.exe models/bonsai2_27b_ternary_ptq1_native_mtp.ninfer \
  --host 127.0.0.1 --port 8091 --model-id bonsai27b-ptq1-mtp-rk2v4-40k \
  --max-context 262144 --kv-capacity 40000 --kv-dtype rk2v4-e8 --host-kv-mib 6144 \
  --max-concurrency 1 --max-shared-prefixes 0 --derive-session-keys \
  --prefill-chunk 1536 --cuda-graph-allowance-mib 16 --ngram-draft-tokens 0 \
  --device-state-slots 0 --gdn-state-fp16 --spec mtp --draft-tokens 4 --mtp-attention-window 8 \
  --default-reasoning-effort none --default-max-tokens 8192
```

### 3.5 验收（30 秒）

```bash
curl -s http://127.0.0.1:8091/v1/models                                   # 应看到 model id
curl -s http://127.0.0.1:8091/v1/chat/completions -H "Content-Type: application/json" \
  -d "{\"model\":\"bonsai27b-ptq1-mtp-rk2v4-40k\",\"messages\":[{\"role\":\"user\",\"content\":\"从1数到50\"}],\"max_tokens\":200}"

bash tools/verify_all.sh          # 一次性探活：引擎 / 网关 / 分片代理 / DSH 配置一致性
bash scripts/console.sh open      # 打开控制台（亮色网页，127.0.0.1:8090）
```

期望读数（4060 Ti 8 GB，40K 档，温度 0）：计数 110 tok/s、代码 75 tok/s、散文 39 tok/s，首字 0.2–0.5 s。

---

## 4. 【可选】llama.cpp 262K 路线

| 文件 | 字节 | SHA-256 | 来源 |
| --- | --- | --- | --- |
| `bonsai-bundle-win-x64.zip`（llama-server.exe build 10807 + 依赖） | 616,671,821 | `6285cd5d6ef72e9e13ffadefb20b1ef91dd90afe80e53f3375bae268454e79ce` | <https://huggingface.co/CaryPalmer/Ternary-Bonsai-2-27B-262k-GGUF> |
| `Ternary-Bonsai-2-27B-PTQ1_0-mtp-procreations.gguf` | 6,397,970,272 | `5f212d02ff57cb8eaad260fd7ff57bfaff87ae2bc9183a21dd2f127c27252505` | 同上仓库 `resolve/main/` |
| `start-server.ps1` | 小 | — | 同上仓库 |

```bash
mkdir -p llama8g/bundle && cd llama8g/bundle && unzip ../bonsai-bundle-win-x64.zip
mv <下载的 gguf> models/Ternary-Bonsai-2-27B-PTQ1_0-mtp-procreations.gguf
mv <下载的 start-server.ps1> .
cd /c/Project/local_model && bash scripts/switch.sh llama   # 起 8089（262K 窗口）
```

模型 id = `bonsai-2-27b`；`/v1/models` 要带 `Authorization: Bearer <llama8g/bundle/artifacts/api_key.txt 里的 key>`。
**llama-server 不校验 model 名**（随便写都 200），NInfer 则逐字强校验（对不上直接 404）。

实测（本机）：150K 单遍 prompt 151,873 token → prefill 582.9 tok/s（268 s）、decode 12.6 tok/s、8/8 命中。

---

## 5. 三层端口（谁在哪儿）

| 端口 | 进程 | 作用 | 谁需要它 |
| --- | --- | --- | --- |
| 8091 | `ninfer-serve-89.exe` | 引擎本体（OpenAI 兼容） | 直接调用 / 网关 |
| 8081 | `tools/chat_gateway.py` | 护栏网关（死循环、复读、超池裁剪） | DSH 的 `ninfer` provider |
| 8086 | `tools/longctx_proxy.py` | 超池分片代理（>池自动切片取证） | DSH 的 `ninfer-long` provider |
| 8089 | `llama-server.exe` | llama.cpp 262K 路线 | DSH 的 `llama` provider |
| 8090 | `tools/console.py` | 本机控制台（网页） | 人 |

> **一张 8 GB 卡同时只能起一个引擎实例**（9091 与 8089 抢显存），换档＝停旧的起新的（10–25 秒，期间请求 502 属正常）。

---

## 6. 接进 DSH（DeepSeek Harness）

1. 打开 `~/.dsh/profiles/desktop/cordis.patch.yml`，找到 `plugin: llm-pi-ai` 那条的 `config.providers`。
2. 把 `config/dsh-providers.example.yml` 里的 `ninfer` / `llama` / `ninfer-long` 三段贴进去（缩进对齐 `opencode-go` 同级）。
3. 在 `~/.dsh/.credentials.yaml` 里加 `LOCAL_LLM_KEY` 与 `LLAMA_API_KEY`（本地随便填，引擎不校验；网关会透传）。
4. 重启 DSH 应用与宿主，模型选择器里应出现四条：

| DSH 里的 id | 窗口 | 需要什么在跑 |
| --- | --- | --- |
| `bonsai27b-ptq1-mtp-rk2v4-40k` | 38,000 | 8091 的 40K 档 + 8081 网关 |
| `bonsai27b-ptq1-nomtp-rk2v4-72k` | 80,000 | 8091 的 72K 档 + 8081 网关 |
| `bonsai27b-ptq1-nomtp-rk2v4-shard200k` | 200,000 | 72K 档 + 8086 分片代理 |
| `Ternary-Bonsai-2-27B-PTQ1_0-mtp-262k` | 262,144 | 8089 llama-server |

> `models[].id` 会被原样发成请求里的 `model` 字段，NInfer 按 `--model-id` **逐字**校验，改 id 必须同时改启动时的 `MODELID`。

---

## 7. 十个必须知道的坑（每条都踩过）

1. **prompt 超过 KV 池 = 答案不可信**：引擎会打 warning（`prompt exceeds the resident Device KV pool`），但 HTTP 仍 200、答案看着正常。**没有 warning 也不等于安全**。超池就得分片（8086 代理）。
2. **一张卡一个引擎**：同时起两个会互相抢显存，后起的 `spill VRAM to system RAM` 然后进程消失。
3. **`--host-kv-mib` 是主机内存**，不是显存；`--max-context` 恰好等于池 ⇒ 环被关。
4. **环只支持 `--max-concurrency 1`**，且必须 `--max-shared-prefixes 0`，否则起服即炸。
5. **不要开 `--kv-lease-growth`**（也不存在 `--no-kv-lease-growth`，写了直接启动失败）。
6. **`NINFER_KV_RETRIEVE` 留空**让引擎自动给预算；写死 8192 只有 128 页证据。
7. **路径纯 ASCII**：中文路径会让引擎抛 JSON UTF-8 异常。
8. **不带 `max_tokens` 会被截到 8192**（`--default-max-tokens`）。
9. **thinking 要显式关**：llama.cpp 用 `reasoning_effort: none`；`chat_template_kwargs.thinking=false` 无效。
10. **首读长文很慢**：NInfer prefill ≈1,000 tok/s（24K 提示 23 s），llama.cpp 是 O(n²)（150K 要 268 s）。读一次就进前缀缓存，第二次快 100 倍以上。

---

## 8. 数字去哪查

| 想知道 | 看 |
| --- | --- |
| 三条路线（NInfer 40K / 72K / llama 262K / 分片 150–200K）的对照与代价 | `docs/两条路终极对照-20261030.md`、`docs/上下文手册-20261030.md` |
| 150K / 200K 到底行不行、每档读数 | `reports/上下文-150K-200K-实测-20261030.md` |
| 40K 档极限优化（96 组扫描） | `reports/极限优化-实测.md` |
| GPU 解锁（UEFI / 驱动级）值不值得 | `reports/UEFI解锁-Windows-对首字影响.md` |
| 全部报告的索引 | `docs/20261030-结论与索引.md` |

---

## 9. 校验清单（重建完对一遍）

```bash
python tools/restore_check.py            # 查文件在不在、字节数对不对（加 --deep 顺便算 SHA-256）
bash tools/verify_all.sh                 # 探活四层端口 + DSH 配置一致性
```

全部 OK 的标准：`verify_all.sh` 输出 0 FAIL，控制台 8090 打开能看到四个档位，DSH 里四条模型都能选且首字 0.3 s 左右。
---

## 10. 存档：可以删什么、必须留什么、以后怎么恢复

### 10.1 本机实测体积（2026-10-31）

| 目录 | 体积 | 是什么 | 删了会怎样 |
| --- | --- | --- | --- |
| `models/` | 21 GB | 权重（在用 6.4 GB + `_archive/` 里 v3 全件 9.5 GB、自打包件 6.4 GB） | 重下 2.09 GB 包即恢复；`_archive/` 永久没用了 |
| `incoming/` | 6.8 GB | 下载的原始分发包（③省显存档等） | 想回头试省显存路线要重下 |
| `llama8g/` | 7.4 GB | llama.cpp bundle + 6.4 GB GGUF | 从 HuggingFace 重下（§4） |
| `engine/` | 1.4 GB | 引擎 + 9 个 DLL | 按 §3.1 / §3.3 重下 |
| `pack/` | 1.4 GB | 2.09 GB 包解开后的副本 | 可删，包里内容与 `engine/`+`models/` 重复 |
| `tmp/` | 1.3 GB | 实验 fixture、截图、抓取缓存 | 可删（报告里已固化读数） |
| `logs/` | 23 MB | 历史运行日志 | **建议留**：每个读数都靠它追溯 |
| `tools/ffmpeg/` | 194 MB | 便携 ffmpeg（从 LosslessCut 复制） | 与推理无关，可删 |
| `repo/` | 4.7 MB | 本仓库工作副本 | 可删，GitHub 上有 |

⇒ 全删约省 **39.7 GB**（C 盘 302 GB 里当前剩 132 GB）。

### 10.2 建议保留的最小集（约 25 MB）

```
repo/            （或直接 git clone 回来）
logs/            23 MB，实测证据（可选）
```

### 10.3 恢复流程（删完之后照这个做，约 20 分钟，其中 15 分钟是下载）

1. `git clone https://github.com/zkkk9555/local_model.git C:/Project/local_model/repo`（或直接看网页）
2. 按 §3 下 `infer-27b-kv-stream-3arch-20261019-r3.zip`（2.09 GB，夸克）
3. 解开后把 `model/*.ninfer` 放进 `models/`，`engines/sm89/*` + `runtime/*.dll` 放进 `engine/`
4. `python tools/restore_check.py --deep`（校验字节数与 SHA-256）
5. `bash scripts/switch.sh ninfer` → `bash scripts/console.sh open`

### 10.4 什么时候值得再捡起来

| 触发条件 | 那时能期待什么 |
| --- | --- |
| 出现 NVFP4 / MXFP4 权重的 27B–35B 件 | 8 GB 上权重压到 ~4.5 GB，KV 池能翻倍到 8–9 万 token |
| 引擎支持 INT4 KV + 更好的 host 页回读 | 150K 单遍才有希望（现在还差 1.2 GB） |
| 换 16 GB 卡（4060 Ti 16G / 5060 Ti 16G） | 同样模型可以 200K 单遍 + 双倍 decode 余量 |
| 只是想过几个月再试一次 | 现在这套一条命令就能回来，不用重新研究 |