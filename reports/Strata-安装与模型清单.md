# Strata 安装与模型清单（本机：RTX 4060 Ti 8GB / Ryzen 7 7800X3D / 31.1GB DDR5 / Win11）

> 状态：**安装全部完成并校验；Qwen3.6-35B-A3B UD-Q4_K_XL（22.85 GB + mmproj 0.9 GB）已下完、run config 已生成**（见 §3.1）。
> **实测结论（2026-10-30 09:20 窗口）：这个档在本机 8 GB 卡上起不来** —— 权重 4.40 GiB 上卡后，引擎还差 242–418 MiB 才能分配「混合专家缓冲 + 槽」（28 臂全 EngineDied）；详见 `reports/Strata-8G实测-Qwen36起不来.md`。
> 还剩一档没试：**Gyro-S**（58.49 GB，setup 自动进 low-RAM 模式，专家靠 OS 文件缓存读、GPU 只放 ~8%），正在后台下载 —— 它是 8 GB 上唯一还没被否掉的路。
> 纪律：GPU 卡归 ninfer-limit 独占，本任务**全程没有启动任何会加载模型的引擎进程**；唯一的引擎启动是 `strata update` 的 `--version` 冒烟（60s 超时、不加载模型、不占显存）。
> 一切落点都在 `C:\Project\local_model\strata` 之下（见 §2 重定向三条环境变量）；除桌面版的 Win32 快捷方式/卸载项外没有写到别处。

---

## 1. 装了什么（版本全部 0.1.54 / app 0.2.8 内核）

| 组件 | 版本 | 路径 | 体积 | 校验 |
|---|---|---|---|---|
| 桌面版（GUI） | 0.2.8 | `C:\Project\local_model\strata\app\\` | 612 MB | setup.exe sha256 `f6860ba0…24c30c` = 官方 SHA256SUMS.txt |
| 桌面版自带 control bundle（**关键**） | 0.1.54 / commit 36f6663c… | `C:\Project\local_model\strata\app\control\\` | 230 MB | 含 setup.py + tools/ + 自带 Python 3.12.15 |
| 终端版（strata-control） | 0.1.54 | `C:\Project\local_model\strata\data\terminal\{0.1.54,current\}\\` | 70 MB | `Checksum ok. / Signature ok. / Installed.` |
| 引擎组件（CUDA 13） | 0.1.54，build `8c1aea4bca1b+cuda13.0` | `C:\Project\local_model\strata\components\engine\0.1.54-windows-x86_64-cuda-cuda13\\` | 945 MB | ed25519 签名 key_id `5d1bc23abbeffd0d`；archs sm_75/86/89/120；min_driver 580.65（本机 616.92 ✔） |
| 官方文档快照 | — | `C:\Project\local_model\tmp\strata-docs\\` | 20 篇 md | 全部 HTTP 200 |

引擎目录明细：`strata.exe` 272,742,400 B（sha256 `107ef7fa…a40f080`）、`strata-vision.exe` 108,196,864（图片读入器，**已随组件附带，0.9 GB 不用单独下**）、`strata_kq.dll` 34,449,920、`cublasLt64_13.dll` 478,140,016、`cublas64_13.dll` 51,776,624、`BUILD.json`、`engine-component.json`。

引擎自检（**不加载模型**）：
```
C:\...\components\engine\0.1.54-windows-x86_64-cuda-cuda13> strata.exe --version
strata 0.1.54
> strata.exe --families
qwen4exp qwen35moe          <- qwen35moe = Qwen3.6 家族，引擎原生支持
```

可执行入口：
- 终端 CLI：`C:\Project\local_model\strata\data\terminal\current\bin\strata.cmd`（自带 `python\python.exe` = 3.12.15）
- 桌面 GUI：`C:\Project\local_model\strata\app\strata-desktop.exe`

---

## 2. 怎么让"一切落在仓库里"（lead 要求③的答案）

三条环境变量即可把全部落点收进 `C:\Project\local_model\strata`，**已实测生效**（`components engine`、`models list`、`update` 都改口了）：

```bash
export STRATA_COMPONENTS_DIR="C:\Project\local_model\strata\components"   # 引擎组件（默认 %LOCALAPPDATA%\Strata\components）
export STRATA_INSTALL_DIR="C:\Project\local_model\strata\install"         # 模型 run config（strata-*.json）与安装态
export STRATA_DATA_DIR="C:\Project\local_model\strata\data"               # 终端本体（装终端时用）
```
模型大文件另有独立开关：`setup.py --data-dir`（模型库，~70–120 GB）、`--models-dir`（GGUF 子目录）、`--gguf-dir`（复用已有 GGUF）、`strata models move`、`setup --move-data`。
另有：`strata update --components-dir`、`strata models list --install-dir`。

**桌面版 GUI 没有等效开关**（它固定用 `%LOCALAPPDATA%\Strata\components`），所以「全部落进仓库」只有**终端版**做得到；桌面版用的是安装器 `/S /D=C:\Project\local_model\strata\app` 强行改安装目录。
装桌面版留下的、无法重定向的 Win32 痕迹：桌面快捷方式 `Strata.lnk`、开始菜单 `Strata.lnk`、HKCU 卸载项（DisplayVersion 0.2.8，InstallLocation 已指向仓库）。

---

## 3. 下载了什么模型（在跑到哪一步）

**Qwen3.6-35B-A3B UD-Q4_K_XL**（Unsloth Dynamic，Apache 2.0；35B 总参 / 3B 激活 / 256 专家 / top-8）
- 目标路径：`C:\Project\local_model\strata\model-data\models\Qwen3.6-35B-A3B-UD-Q4_K_XL.gguf`
- 体积：**22,853,663,008 B (22.85 GB)**，sha256 `55983c5a75a1ab969824077b3bb3de4146e82a9234072b48ad4e8f92ad3fe9f1`（来自 setup.py:632 `QWEN36_FILES`，比文档更硬）
- 附带 mmproj：`mmproj-F16.gguf` 899,283,584 B (0.9 GB)
- 日志：`C:\Project\local_model\strata\logs\model-install-qwen36.log`

装前预检原文（照抄，报告用）：
```
[!] less than 12 GB of VRAM: Strata will run, but most experts stay on the CPU and it will be slow
[ok] RAM: 31 GB
[ok] CPU: AMD Ryzen 7 7800X3D 8-Core Processor (AVX-512)
[ok] PCIe: 4.0 x8
1) UD-Q4_K_XL 4-bit (Unsloth Dynamic), the smallest; download 22.9 GB   <- needs 32 GB RAM, you have 31
2) UD-Q6_K_XL 6-bit ... download 32.6 GB <- needs 44 GB RAM
3) Q8_0 8-bit ... download 37.8 GB <- needs 52 GB RAM
[!]  UD-Q4_K_XL needs about 32 GB of RAM; this PC has 31 GB: the OS may page and it may not start
[!]  installing UD-Q4_K_XL with 31 GB of RAM, as you chose
Context length ... Its cache takes 1.4 GB of VRAM per 32K tokens, room the experts would use:
  1) 8K  2) 32K (recommended for your GPU)  3) 64K  4) 128K  5) 200K  6) 256K
[ok] context: 32768 tokens
Images: ... the encoder runs on the CPU (the GPU encoder would take ~1.4 GB of VRAM from the experts on this card)
[ok] images: on (encoder on the CPU)
engine component: 0.1.54 (windows-x86_64-cuda) in C:\Project\local_model\strata\components\engine\0.1.54-windows-x86_64-cuda-cuda13
image encoder: ...\strata-vision.exe (carried by the engine component)
```
即：**官方针对本机配置自己给出的推荐是 32K 上下文 + 图片走 CPU 编码器**（依据 `own_path_context()`：≤16.5 GB 显存 → 推荐 32K）。

实际下的命令（等价于 `SETUP.bat`，用 CONTROL 模式跑，不编译、不装 Python 包、`--no-start` 不启动模型）：
```bash
export HTTP_PROXY=http://127.0.0.1:7897 HTTPS_PROXY=http://127.0.0.1:7897
export STRATA_CONTROL_INSTALL=1
export STRATA_INSTALL_DIR="C:\Project\local_model\strata\install"
export STRATA_COMPONENTS_DIR="C:\Project\local_model\strata\components"
cd C:\Project\local_model\strata\app\control
./python/python.exe setup.py --family qwen36 --model UD-Q4_K_XL \
    --data-dir "C:\Project\local_model\strata\model-data" --no-start --yes
```
> 坑：`strata install` 会直接报 `this folder has no installer (setup.py)` —— 它只在 `STRATA_INSTALL_DIR` 下找 setup.py（cli.py:2068），而终端包里没有 setup.py。**桌面版的 `app\control\\` 就是那个 full Strata folder**，所以要么用 `app\control\setup.py`，要么把 `STRATA_INSTALL_DIR` 指向它。

### 3.1 落地结果（下载 + 准备已跑完，EXIT=0）

日志：`C:/Project/local_model/strata/logs/model-install-qwen36.log`（Step 1~7 全过，无 Error/Traceback）。

| 落地文件 | 体积 | 说明 |
|---|---|---|
| `C:/Project/local_model/strata/model-data/models/qwen36-UD-Q4_K_XL/Qwen3.6-35B-A3B-UD-Q4_K_XL.gguf` | **22,853,663,008 B** | 与 setup.py 里钉死的字节数、sha256 完全一致；已有 `.done` 标记 |
| 同目录 `mmproj-F16.gguf` | 899,283,584 B | 图片编码器权重（`--vision on` 但编码跑 CPU） |
| `C:/Project/local_model/strata/model-data/packs/qwen36-ud-q4_k_xl/tokenizer/` | 9.7 MB | Step 6 从 GGUF 现做：`vocab 248320, merges 247587, pre qwen35, specials {eos 248046, padding 248055, bos 248044}` |
| `C:/Project/local_model/strata/install/strata-qwen36-ud-q4_k_xl.json` | 1,318 B | **run config**（引擎 argv、端口、tokenizer、日志路径、vision 段） |
| `C:/Project/local_model/strata/install/run-qwen36-ud-q4_k_xl.bat` | 371 B | Step 7 生成的启动脚本 |

`model-data/models` 合计 **23 GB**，C: 盘空闲从 157 GB 降到 **137 GB**。装完 `strata models list` 输出：

```
qwen36-ud-q4_k_xl  present  qwen3.6-35b-a3b-ud-q4_k_xl
```

Step 2 的预检顺带报的引擎侧事实：`[ok] GPU: NVIDIA GeForce RTX 4060 Ti, 8.0 GB VRAM, compute capability 8.9, driver 616.92`、`[ok] llama.cpp source downloaded`（3cf0325，只给 gguf-py 准备工具用，不编译引擎）。

> **本次全程没有启动任何引擎**：`--no-start`，且引擎更新器的 `default_test_start()` 在"没装模型"时只跑 `引擎.exe --version`（updater.py:944→763），不加载模型、不占显存。GPU 显存占用始终 0（卡归 ninfer-limit）。
---

## 4. 服务口径（起服务 + 客户端怎么接）

| 项 | 值 |
|---|---|
| 默认端点 | `http://127.0.0.1:8080` |
| OpenAI 兼容基址 | `http://127.0.0.1:8080/v1`，POST `/v1/chat/completions` |
| Anthropic 兼容 | 服务器根 + `/v1/messages` |
| 健康检查 | `GET /health`、`GET /v1/models`（`curl -fsS http://127.0.0.1:8080/v1/models`） |
| 监听范围 | `--access local`（默认，仅本机）/ `lan` / `cloudflare` / `tailscale` |
| 鉴权 | `--api-key K` / `--api-key-env NAME` / `--new-key` / `--no-api-key`（无 key 只警告不拒绝） |
| 端口冲突 | 8091 归 ninfer 现役服务，Strata 用 8080 或另指 `--port` |

**真实生效的引擎 argv**（来自 `strata-qwen36-ud-q4_k_xl.json`，setup 自己写的，不是我拼的）：
```
strata.exe --native <model-data>\models\qwen36-UD-Q4_K_XL\Qwen3.6-35B-A3B-UD-Q4_K_XL.gguf --max-context 32768 --prefill auto --mtp 2 --vision
```
外层服务器（`serve/server.py`，做 OpenAI/Anthropic 兼容层、聊天页、图片分发）：
```
python.exe serve\server.py --engine strata --config <install>\strata-qwen36-ud-q4_k_xl.json --port 8080 --open
```
等价 bash（把生成的 .bat 翻译过来，去掉 `--open` 免弹浏览器）：
```bash
export STRATA_INSTALL_DIR="C:\Project\local_model\strata\install"
export STRATA_COMPONENTS_DIR="C:\Project\local_model\strata\components"
cd /c/Project/local_model/strata/app/control
./python/python.exe serve/server.py --engine strata \
  --config "C:\Project\local_model\strata\install\strata-qwen36-ud-q4_k_xl.json" --port 8080
```
或走终端版的引导式启动（自己读 run config，还能加 `--set`）：
```bash
strata.cmd launch --model ud-q4_k_xl --family qwen36 --context 32k --vision off \
  --access local --port 8080 --tune skip \
  --set STRATA_ARENA_PIN_GIB=auto \
  --set=--prefill-head-alias=on
```
> 端口纪律：**8091 是现役 ninfer，绝对不要动**；Strata 用 8080。两者不要同时跑（8 GB 卡放不下两套专家缓存）。


常用 flag：`--plan`（只打印计划）、`--yes`、`--no-tui`、`--restart`、`--stop/--status/--show-key`、`--context 32k|64k|128k|256k|N`、`--kv int8|q4_0|k8v4|fp16`、`--vision off|on|gpu|cpu`、`--parallel 1~8`、`--mtp on|off`、`--drafting auto|mtp|dflash2|off`、`--tune quick|thorough|skip`、`--set KEY=VALUE`、`--preset/--save-preset`、`--output human|json`。
客户端接线：`strata connect <opencode|codex|claude|omp|pi|hermes|openclaw|deepseek-harness> [--write|--check]`。

---

## 5. lead 要求的三段 CLI 原文（照抄）

### 5.1 `strata launch --plan`
```
Plan for 'UD-Q4_K_XL 32K':
  model     qwen36 UD-Q4_K_XL
  context   32K    pictures off    parallel fit to your card
  download  Nothing to download: the model is already on this computer.
  drafting  MTP
  tuning    skip    access This computer only, port 8080
  same as   strata launch --model ud-q4_k_xl --family qwen36 --context 32k --vision off --tune skip --access local --port 8080 --set STRATA_ARENA_PIN_GIB=14 --set STRATA_PREFILL_RING=384
Nothing was changed.
```
`--output json` 里这些设置落在 `plan.settings.extra`：
```json
"settings": { "family": "qwen36", "model": "UD-Q4_K_XL", "context": 32768, "vision": "off",
              "tune": "skip", "access": "local", "port": 8080,
              "extra": { "STRATA_ARENA_PIN_GIB": "14", "STRATA_PREFILL_RING": "384" } },
"download": { "gb": 0, "engine_missing": false, "engine_usable": true,
              "text": "Nothing to download: the model is already on this computer." }
```
> 注意：**plan 的 download 段对 qwen36 不可信**（`model_gb: null, own_files: false` 而 `models list` 当时是空的），真实体积见 §3 的 22.85 GB。

### 5.2 `strata models list`（模型还没装完时）
```
No installed models found. Looked in: C:\Project\local_model\strata\install. If your models are somewhere else, add
--install-dir FOLDER (the folder with the strata-*.json files), or run `strata launch` to set one up.
```

装完之后（同一个命令，只读 `STRATA_INSTALL_DIR`）：
```
qwen36-ud-q4_k_xl  present  qwen3.6-35b-a3b-ud-q4_k_xl
```

### 5.3 `strata connect deepseek-harness --check`
```
DeepSeek Harness  (the Strata app; built into the Strata app (tested))
[!] No running Strata server was found, so this uses the default address. Start one with: strata launch

Good to know:
  - DeepSeek Harness is Strata's own coding harness inside the Strata app: nothing to write here.
  - Its package default compaction headroom (64K) is larger than a 32K window; the app's bridge sets it for you.

Checking: one prompt and one tool call, sent the way this app sends them (this can take a minute).
FAIL prompt: The server could not be reached. Is it running (strata launch --status)? (2 s)
FAIL tool call: The server could not be reached. Is it running (strata launch --status)? (2 s)
```
（`--check` 是只读检查，没有写任何客户端配置；两个 FAIL 只是因为没有服务在跑。）

---

## 6. 核实 B 站那两个"调参"变量（lead m00299）

**结论：视频里的 `strata_arena_pin_gb` / `strata_prefer_ring` 都不是引擎认识的名字。** 引擎里是 585 个 `STRATA_*` 环境变量（`grep -aoE 'STRATA_[A-Z0-9_]+' strata.exe | sort -u` 可复现），且**没有 `STRATA_PREFER_RING`**。对应真名是：

| 视频里说的 | 真实名字 | 形态 | 默认 | 本机该设多少 |
|---|---|---|---|---|
| `strata_arena_pin_gb`（钉住的 arena 大小） | **`STRATA_ARENA_PIN_GIB`** | 环境变量（`--set STRATA_ARENA_PIN_GIB=N` → 写进 run config 的 `env`） | **Windows 默认 29 GiB**；支持 `auto` | **12～14**（不要抄 24） |
| `strata_prefer_ring`（环大小） | **`STRATA_PREFILL_RING`**（另有 `STRATA_RING_BYTES`、`STRATA_STAGER_RING`、`STRATA_SPLIT_RING`） | 环境变量 | 由 prefill 规划器定（日志里见过 `ring 96`） | 先不动；要 A/B 再设 384 |

依据（官方 DETAILS.md 与二进制内文逐条）：
- `docs/DETAILS.md:257`：「Windows, opt-in: `STRATA_PIN_BY_NEED=1` … registers the profile's non-GPU-resident experts by rank up to **`STRATA_ARENA_PIN_GIB` (29 by default on Windows)** instead of the first ~30 GiB.」
- `docs/DETAILS.md:258`：「Windows CUDA keeps 640 MiB then 160 MiB of page-lockable memory free while the arena pins（`STRATA_PIN_RESERVE_MIB=N`）」
- `docs/DETAILS.md:260`：爆了会报 `[pinned-memory-exhausted]`，错误信息「names the `STRATA_ARENA_PIN_GIB` to start with」
- 引擎内文：`STRATA_ARENA_PIN_GIB=auto; N sets a cap; #243`（**支持 auto**）、`the expert arena's pinning is capped`、`cudaHostRegister of the whole arena FAILED … the arena is NOT pinned`、`the whole expert arena is pinned`、`STRATA_ARENA_LOCK=0`、`STRATA_RESIDENT_PIN=0`
- `docs/DETAILS.md:285-290`（ring 的正式身份）：「a planner picks the chunk and ring … It prints `chunk 8192 -> 3840, ring 96 -> 96: …` … It does nothing when the GPU holds every expert, when the file set fits the cache, **and on Windows**. `STRATA_PREFILL_HOST_PLAN=0` turns it off; `--prefill N` and `STRATA_PREFILL_RING` always win.」
  ⇒ **96/384 是 prefill 流式 ring 的深度数字，而且这个规划器在 Windows 上根本不跑**，所以视频里 Windows 上的 prefill 提速更可能来自 arena 钉住（那条在 Windows 上确实生效）+ 提示分块。

### 本机换算（8 GB VRAM / 31.1 GB RAM）
- 总内存 31.1 GB：Windows+桌面常驻实测约 5 GB（Chrome/League 之类），UD-Q4_K_XL 22.85 GB 里 GPU 只放得下 2～3 GB 专家，**可能常驻 RAM 的专家 ~18–20 GB**，再扣 KV 的 host 副本与工具进程 ⇒ 页锁定（不可换出）最多给 **12～14 GiB** 才安全。
- **抄 24 或默认 29 必炸**：31.1 GB 机器锁 24–29 GiB 页锁定内存 ⇒ 直接 `[pinned-memory-exhausted]`，或把 OS 拖进换页（4090 48G/128GB 那台机器才有那个余量）。
- 保守顺序：先 `STRATA_ARENA_PIN_GIB=auto` 让它按可用内存自己算；稳定后试 14，再试 12 对比 tok/s。

### 怎么落地、怎么在 --plan 里核对
```bash
strata.cmd launch --plan --model ud-q4_k_xl --family qwen36 --context 32k --vision off \
  --set STRATA_ARENA_PIN_GIB=14 --set STRATA_PREFILL_RING=384
```
`--set` 的机制（`strata_cli/launch/settings.py:286 as_argv_changes`）：**键名不以 `--` 开头 → 进引擎环境变量**；`--` 开头 → 进引擎 argv；值 `off/false/no/none` → 删除该条。落盘位置是模型 run config 的 `"env"`（`strata-*.json`，在 `STRATA_INSTALL_DIR`）。`strata launch --help` 原文：`an advanced engine setting or STRATA_* variable, e.g. prefill=65536 (repeat); unknown names get a warning, not a refusal`。
plan 的 `plan.settings.extra` 与 `flags` 两处都能核对到，见 §5.1。

### 对 8 GB 卡真正有据的三个杠杆（比上面两条更值）
1. **`--prefill-head-alias`** —— 官方文档专门为 8 GB 卡写的（`docs/PREFILL_HEAD_ALIAS.md`，实测卡是 8,151 MiB 的 8 GB 级、Win11 WDDM）：把输出头的 VRAM 借给提示路径，提示分块从 512 → **2,048 token**，prefill **306 → 667 tok/s**；代价是 ≤512 token 的短提示多花 0.6–0.75 s，且解码时剩余显存 0 MiB。要求 `--serve`、单卡、MTP 开、非 split。
2. **`STRATA_KVA=1`**（界面上的 "Faster long prompts"，**0.2.8 默认关**）：长提示近似加速，代价是长文档细节可能丢/串。
3. **`STRATA_ROUTE_PRIOR=1.5`**（"Faster answers on 12 GB NVIDIA cards"，**0.2.8 起默认关**，因长会话重复与质量下降被作者收回）：RTX 3060 12 GB 上 story +15% / code +37%，但 agent 任务 4.5/10 vs 5.6。**本机不建议默认开**。

#### 启用 `--prefill-head-alias` 的确切写法（有坑，已实测）
```bash
strata.cmd launch --model ud-q4_k_xl --family qwen36 --context 32k --vision off \
  --set=--prefill-head-alias=on --set STRATA_ARENA_PIN_GIB=auto
```
- **值必须写 `on`（或 `yes`/`true`）**。实测 `strata_cli/launch/settings.py:286 as_argv_changes` 的三种值：空值 `''` → `args {}`（**被当成"无变化"悄悄丢掉**，flag 根本不会下发）；`on` → `{'--prefill-head-alias': True}`（正确，裸 flag）；`1` → `{'--prefill-head-alias': '1'}`（错误，会变成 `--prefill-head-alias 1` 带值形态）。复现脚本：`C:/Project/local_model/strata/tmp/probe_alias.py`。
- `--prefill-head-alias` **不在 `strata_control/tune_knobs.py:49` 的 `BOOL_FLAGS` 里**（那 14 个是 `--kv-grow --trim-stage-weights --no-host-worker --no-pool --mmap-experts --resident-experts --prompt-cache-tail --vram-elastic --split-skip-if-fits --resident-cpu-experts --no-hit-poke --expert-cache-per-layer --batch-mtp`），所以只能靠 `on` 这个值把它认成裸 flag。
- 注意：`--plan --output json` 里 `plan.flags` 回显行会把键名的 `--` 去掉（显示成 `--set prefill-head-alias`），**别照抄那一行**——那样会变成环境变量名。核对请看 `plan.settings.extra` 的键（带 `--`）。

---

## 7. 本机可行档位表（依据 docs/MODELS.md + setup.py 里钉死的字节数）

判据：Strata 的 Qwen3.8-Flash-Next 要「RAM ≥ 专家 + 约 10 GB」；Gyro 两档的口径是 **VRAM+RAM 合计**（`mem_total: True`）。

| 档位 | 下载 | 内存需求 | 本机（31.1 GB RAM + 8 GB VRAM） | 结论 |
|---|---|---|---|---|
| **Qwen3.6-35B-A3B UD-Q4_K_XL** | **22.85 GB**（+mmproj 0.9） | setup 按 32 GB RAM 计划 | 差 1 GB，官方警告「可能换页/起不来」；官方 RTX 3060 12G 实测 **59.7 tok/s**（多数专家在 CPU） | **首选档（已装好，见 §3.1）** |
| Qwen3.6-35B-A3B IQ3_S | 12.74 GiB（HF，lead 提供） | 更低 | 更宽松，专家更少放 GPU | 备选，UD-Q4 起不来时降级用 |
| Qwen3.6 UD-Q6_K_XL / Q8_0 | 32.6 / 37.8 GB | 44 / 52 GB RAM | ✘ | 排除 |
| Qwen3.8-Flash-Next **Gyro-S** | 58.49 GB（+draft 5.2 +视觉 0.9） | VRAM+RAM **27.6 GB** | ✔ 装得下（39.1 GB 总量） | **唯一能跑的 125B 级全专家档**，质量 lower；8 GB 卡上实测口径分歧很大，见 §8 注 |
| Qwen3.8 Gyro-M | 91.97 GB | VRAM+RAM **35 GB** | ✔ 39.1 GB 总量够（35 < 39.1），盘要 92+6 GB | 第三方面证据说 32G+8G 可跑（B站 BV1HMHw6wETo：`>39G 即可不读硬盘跑 iq3 级 85G 文件均速 66 t/s`），**未验证** |
| Qwen3.8 ISTA Q2_0 / IQ2_XS / IQ3_XXS / IQ3_S | 66–94 GB | 专家 34/35.5/43/50 GB | ✘（要求 RAM ≥ 专家 + 10） | 排除 |
| Qwen3.8 Coder IQ1_M | 专家 29.6 GB | ≈39.6 GB | ✘（差 8 GB） | 排除 |
| DeepSeek V4.1-Flash | 239–274 GB | **≥12 GB 显存 + ≥46 GB RAM** + NVMe | ✘ 显存不够 | 排除 |

盘位：模型库放 `C:\Project\local_model\strata\model-data`（C: 盘装前剩 157 GB；22.85+0.9 GB 后仍有余量，Gyro-S 58.5 GB 也能塞下）。

**要下 Gyro-S 的话就这一条**（engine 要求 `GYRO_ENGINE = (0, 1, 45, 1)`，本机 0.1.54 满足，不需要另下引擎包）：
```powershell
$env:STRATA_CONTROL_INSTALL=1
$env:STRATA_INSTALL_DIR="C:/Project/local_model/strata/install"
$env:STRATA_COMPONENTS_DIR="C:/Project/local_model/strata/components"
cd C:/Project/local_model/strata/app/control
./python/python.exe setup.py --family gyro --model Gyro-S --data-dir C:/Project/local_model/strata/model-data --no-start --yes --vision off
```
`--vision off` 只省 0.9 GB（mmproj）；连 draft 层一起省再加 `--mtp off`（省 5.2 GB，但 8 GB 卡上 MTP 是主要加速手段，不建议）。58.49 GB 按本机实测 **~8 MB/s**（09:01 起，09:16 已 7.05 GB / 12%）≈ 2 小时，下完 C: 盘约剩 72 GB。
> Gyro 的 TQ1_0/TQK6 张量 llama.cpp 不认（setup.py:8685：引擎必须带 trellis kernel，低于 0.1.45.1 加载时直接拒），所以引擎别再往下降级。

---

## 8. 上下文与吞吐的预期（写清依据，不吹）

- **上下文**：Qwen3.6 的 KV 是 **45,056 B/token ≈ 44 KB/token**（10 个注意力层 + MTP 块，2 KV 头 × 256，K/V 均 fp32）⇒ 32K ≈ 1.44 GB 显存、64K ≈ 2.9 GB、128K ≈ 5.8 GB。setup 的 `own_path_context()` 对 ≤16.5 GB 显存的机器**推荐 32K**；8 GB 卡上 64K 就要从专家缓存里抢走约 1.5 GB，128K 基本等于放弃专家缓存。**结论：32K 是甜点，64K 可试（专家命中率下降），128K 不要想**。
- **吞吐**：官方 RTX 3060 12 GB（多数专家在 CPU）**59.7 tok/s**；本机显存只有 8 GB、能放卡的专家更少，PCIe 4.0 x8，8 核 AVX-512 ⇒ 合理预期 **20–40 tok/s 量级**（未实测，卡被 ninfer-limit 占用；实测需等窗口）。
- **prefill**：默认分块在 8 GB 卡上只有 256–768 token（官方 8 GB 级卡实测 185–387 tok/s），开 `--prefill-head-alias` 后 2,048 token、约 667 tok/s。

> **注（社区实测与「10 tok/s」口径冲突，必须自己量）**：队友 community-scout 的侦察报告（[社区侦察-Strata出处与8G长上下文.md](社区侦察-Strata出处与8G长上下文.md) §3.1 第 6 行）记录了 `cyber-on-strata` 的 8 GB 档：**4080 SUPER 按 8 GB 显存配置 + 32 GB RAM，Strata `--expert-cache 3.0 GiB`，KV 全在显存，显存峰值 7,260 MiB，decode 57.7–63.5 tok/s、prefill 1,736–2,203 tok/s**（跑的是 125B 级 Qwen3.8-Flash-Next）。同表第 7 行 `sage-a1.5 §9` 8 GB 档：58.35 tok/s、prefill 1,918–3,388。
> 这与「8G + 32G 跑 125B 级只有 ~10 tok/s、频繁爆显存」的口径**差 5–6 倍**。差异可能来自专家缓存大小（3.0 GiB vs 更小）、KV 是否 fp16 全驻、以及卡型（4080 SUPER 物理 16 GB 假扮 8 GB，带宽 736 GB/s，是 4060 Ti 288 GB/s 的 2.5 倍）。
> ⇒ **结论只能靠本机实测**：先在本机跑通 Qwen3.6（22.85 GB 档）拿到基线，再决定是否为 125B 级下 58.5 GB 的 Gyro-S。

---

## 9. 与现役 ninfer / 其他路线的取舍（一句话版）

- Strata=通用 OpenAI/Anthropic 兼容服务 + MoE 专家分层（VRAM 缓存 / RAM / SSD），强项是**长上下文 + 生态轮子**；ninfer 现役档强项是**已调好的 98 tok/s / 池 32,000**。
- 在 8 GB 卡上两者都要把专家放 CPU 内存，Strata 的额外价值在 `--prefill-head-alias` 这类为 8 GB 卡写的机制与 32K/64K 上下文的通用客户端接入；成本是 22.85 GB 盘 + 峰值 25+ GB RAM。
- 建议：Strata 作为**第二条腿**共存（不同端口 8080），不与 8091 抢卡；能不能当主力取决于下一窗口的实测 tok/s。

---

## 10. 待办 / 未验证（下一窗口清单）

0. **起一次服务量 tok/s（唯一还没做的）**：卡空出来时跑 §4 的 bash 启动命令，用 `/v1/chat/completions` 打 1,500 token 提示 + 500 token 生成，记 `timings` 里的 `prompt_per_second` / `predicted_per_second`；再分别开关 `--prefill-head-alias` 与 `STRATA_ARENA_PIN_GIB=auto|14|12` 各测一轮。**在这之前，本文所有 tok/s 都是官方/社区口径，不是本机读数。**
1. ~~模型下完后跑 models list 确认 run config~~ **已完成**（run config = `C:/Project/local_model/strata/install/strata-qwen36-ud-q4_k_xl.json`，命令报 `qwen36-ud-q4_k_xl  present  qwen3.6-35b-a3b-ud-q4_k_xl`）。
2. `STRATA_PREFILL_RING=384` 在 Windows 上是否有任何效果（文档说 host 规划器在 Windows 不跑，预期无效果）——用日志里是否出现 `ring` 字样判定。
3. `strata connect deepseek-harness --write` 只在真要接线时执行（会改客户端配置）。
