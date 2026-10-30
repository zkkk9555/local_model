# Strata 配置键 → 引擎参数 映射表，以及 "ignoring --mmap-experts" 的来源

- 侦察对象：本地安装树 `C:/Project/local_model/strata`（app 0.2.8 / control 0.1.54 / engine 0.1.54-windows-x86_64-cuda-cuda13）
- 侦察时间：2026-10-30
- 证据等级：本机代码与二进制字符串为**一手**（含行号/偏移）；官方文档为**一手**（带 URL）；无数字的说法标【未核源】。
- 全程只读：未启动/未停止任何引擎或服务，未改动 `C:/Project/local_model` 下任何配置脚本。

---

## 结论（三句话）

1. **没有"映射表"文件。**config json → 引擎命令行的唯一漏斗是 `app/control/serve/server.py` 里的 `engine_args()`（3161-3213 行）：起点是 config 的 `"args"` **原样透传**，之后是 11 条"派生规则"（下表 1–11b）往里加参数；其余键（`exe/cwd/port/host/gpu/vision/log/env...`）根本不进引擎命令行，是控制层自己用的。
2. **`ignoring --mmap-experts (not an option of this engine)` 是引擎自己打的**——整个安装树里这句格式串只存在于 `strata.exe` 的字符串区（offset 8947816），`app/control` 与 `app/host` 的 .py/.js/.json **零命中**。它是 `strata-q36` 这条**独立引擎路径**的前端在丢弃它不认识的参数，只警告、不退出。
3. **在 qwen36（GGUF arch `qwen35moe`）上，无论 config 怎么写，`--mmap-experts / --resident-cpu-experts / --expert-profile` 都不会生效**：这三个选项只存在于同一个 exe 里**另一条（pack/native 通用）路径的选项表**中。q36 路径对应的语义旋钮是 `--expert-vram / --expert-slots / --hybrid-rows / --cpu-threads / --prefill(--chunk)`。

---

## ① 哪些 config 键会变成引擎命令行参数

### 1.1 出命令行的那一行

```
app/control/serve/server.py:1063
    self.proc = popen("the Strata engine", [exe, "--serve", *args], cwd=cwd, stdin=subprocess.PIPE, ...)
```

即：**引擎 argv = `strata.exe` + `--serve` + `engine_args(cfg)`**。
调用点：`app/control/serve/server.py:9024` → `StrataEngine(exe, engine_args(cfg) + (effort_end or []), cwd=cfg.get("cwd"), ...)`。
引擎与控制层之间走 stdin/stdout 管道协议，引擎**不吃 `--port`**；`port` 是控制层自己的 OpenAI 兼容口。

### 1.2 映射表（`engine_args()`，app/control/serve/server.py:3161-3213）

| # | config 键 | 变成的引擎参数 | 代码位置 | 何时不加 |
|---|---|---|---|---|
| 0 | `"args"` （数组） | **原样、逐字**上命令行（含顺序） | server.py:3165 | 永远是起点 |
| 1 | `"user_args"` | 覆盖式合并：同一 flag 用户值赢 | server.py:3169 → `strata_control/user_args.py` | 键不存在 |
| 2 | `"drafting"`: `auto/mtp/dflash2/off` | `--draft*`/`--draft-model` 等（`drafting.apply`，先剥掉旧 draft flag 再按决策追加） | server.py:3174 → `strata_control/drafting.py:215-230` | 无 `"drafting"` 且 Auto=mtp 时**完全不碰 args** |
| 3 | `"mtp": false` | 反过来**删掉**草稿层相关参数 | `draft_layer.is_off(cfg)` | — |
| 4 | `"vision"`（dict） | `--vision`；若 `vision.gpu` 且 args 里无 `--vram-reserve-mib`，再补 `--vram-reserve-mib 700` | server.py:3192、3195 | args 里已有 `--vision` |
| 5 | `"layer_split"` | `--layer-split <值>` | server.py:3200（`layer_split_value`） | 键空/为假 |
| 6 | `"split_skip_if_fits"`: true | `--split-skip-if-fits` | server.py:3203 | 非 true |
| 7 | `"vram_elastic"`: true / `"vram_segment_mib"` | `--vram-elastic` / `--vram-segment-mib N` | server.py:3207、3210 | 非 true |
| 8 | `"parallel"`: 整数 2..8 | `--batch N` | `parallel_args`，server.py:3219-3240 | args 已有 `--batch` 或 `--slots`；N≤1 或非整数（类型错打 `[strata] "parallel" must be a whole number of requests (2..8)`） |
| 9 | `"pool_cores"`: `"0,2,4,6"` / `"2-14:2"` / 列表 | `--pool-cores <文本>` | `pool_cores_args`，server.py:3246-3266 | 正则 `_POOL_CORES_OK` 不过则不加 |
| 10 | `"expert_profile_save"`（字符串路径） | `--expert-profile-save <path>` | `learned_profile_args`，server.py:3284-3304 | args 里已有该 flag |
| 11 | `"expert_profile_save_every"`（≥0 数字） | `--expert-profile-save-every N` | 同上，server.py:3294-3296 | 与 10 同生共死 |
| 11b | （自动改写）args 里已有 `--expert-profile` 时 | 若两份 profile 头 shape 相同（读 24 字节 `STRP` 头），**把 `--expert-profile` 的值替换成 save 路径** | server.py:3297-3303 | shape 不同则保留原值 |

> 关于 `"parallel"`：`PARALLEL_MAX = 8`。

### 1.3 不进引擎命令行的键（控制层自用）

`exe`（支持 `"component:strata-engine"` 引用，走 `strata_control/engine_component.py` 展开）、`cwd`、`port`、`host`、`api_key/token`、`tokenizer`、`model_name`、`arch`、`log`、`lib_dirs`、`env`（进**进程环境**，例如 `STRATA_Q36_CHUNK`、`STRATA_RESIDENT_HEADROOM_GIB`）、`gpu`/`gpus_asked`/`hip_ordinal`（→ **进程环境** `CUDA_VISIBLE_DEVICES` / `HIP_VISIBLE_DEVICES`，见 server.py:3591-3597、`hip_visible` :3307-3313）、`aliases`、`sampling`、`vision`（除 `--vision` 开关外的其余键只给视觉侧车用）、`args_written`。

**`args_written` 不是参数**：它是"setup/app 上次写进去的 args 全量副本"，用来识别"人手工改过的项"（`strata_control/user_args.py`，注释引用 #3216 #3215 #3270）。

### 1.4 视觉侧车另有一张表（`Vision.reader_args`，server.py:2723-2736）

```
vision.exe → 可执行文件；vision.mmproj → --mmproj；vision.model → --model
vision.gpu → --gpu；vision.threads → --threads；vision.max_tokens → --max-tokens（默认 GPU 1024 / CPU 300）；
vision.min_tokens → --min-tokens
```
（以下 `elastic / elastic_mib / elastic_idle_s` 是控制层自己的显存弹性卸载策略，不上命令行。）

### 1.5 配置是谁写的（谁可能把 `--mmap-experts` 塞进 config）

- `app/host/server/native-resources.mjs:80-92`：内存/资源档里 `--resident-budget-gib` **implies `--mmap-experts`**；:85 判定 `['--resident-experts','--mmap-experts','--resident-budget-gib'].some(f=>args.includes(f))`；:131 在 saferStart 里再检查这两个 flag（已有则不再降级重试）。**这些写入口不看模型 family**，所以在 qwen36 配置上也会写出 q36 不认识的开关。
- `app/host/server/native-ds-args.mjs:12-14`：带值/布尔 flag 清单，含 `'--mmap-experts'`。
- `app/host/server/native-control.mjs:91`：`lowRamMode: cfg.args?.includes('--resident-experts')?'resident':cfg.args?.includes('--mmap-experts')?'mmap':'auto'`（UI 回显用）。
- `app/control/serve/runconfig.py`（191 行）：只是 Settings 界面视图（`EDITABLE` 约 18 键，`vram_reserve_mib` 声明为 `("arg","--vram-reserve-mib")`），不产生引擎参数。
- `app/control/strata_control/doctor.py:20-27` `PATH_FLAGS`：只是路径清单 `{"--pack":"directory","--native":"file","--ple-gguf":"file","--expert-profile":"file","--mtp":"directory","--control-vector-scaled":"file_with_scale"}`，其中就有 `--expert-profile` —— 说明控制层把它当"通用引擎的路径参数"，但**没有任何地方按模型 family 校验它能不能用**。

**因此：整条链路上没有任何"这个引擎支持这个开关吗"的门禁。**写错的键一路透传到引擎，唯一的反馈就是引擎自己那行 warning。

---

## ② `ignoring --mmap-experts (not an option of this engine)` 是谁打的

### 2.1 grep 结论

```
grep -rln "not an option of this engine" C:/Project/local_model/strata   →  只命中 strata.exe 与 logs/*.log、install/*.log
grep -rn  "not an option" app/control app/host                          →  0 命中（.py/.js/.json 全无）
```

控制层**既不产生**这句、**也不过滤**它，更不会因为这句话做任何事（不重试、不改配置、不告警）。

### 2.2 二进制里的定位（strata.exe，272,742,400 B）

- offset **8947816**：`strata-q36: ignoring %s%s%s (not an option of this engine)` —— **全 exe 唯一一处**。
  邻居字符串（同一个错误段）：
  - 8947192 `strata-q36: %s needs a value`
  - 8947632 `strata-q36: ignoring --mtp %s (this family's MTP is the GGUF's own block: --mtp N drafts)`
  - 8947888 `usage: strata-q36 --model GGUF [--max-context 32768] [--chunk 512] [--no-graph]`
  - 8947968 `(--serve | --tokens IDS [--n 64] [--force IDS] [--dump-full-logits F] | --bench-pp N --bench-tg N)`
  - 8948080 `strata-q36: --model is required`
- **q36 前端认识的选项名**（字符串簇 8947520–8947792，共 12 个）：
  `--force, --emb, --dump-full-logits, --bench-pp, --bench-tg, --no-graph, --no-warmup, --draft-vocab, --expert-vram, --cpu-threads, --expert-slots, --hybrid-rows`
  → **`--mmap-experts`、`--resident-cpu-experts`、`--expert-profile` 都不在这 12 个里**。
- q36 专用环境变量：`STRATA_Q36_CHUNK`(8948264)、`STRATA_Q36_PLACE_DEBUG`(8948288)、`STRATA_Q36_DRAFT_VOCAB`(8948424)、`STRATA_Q36_OLD_KERNELS`(8947224)、`STRATA_Q36_VERIFY`(8947248)、`STRATA_MMQ_KQ`(8948120)、`STRATA_Q8_PACKED`(8948136)；符号 `q36_engine.cu`（"q36_engine" 在 exe 内出现 **1591** 次）。
- **同一个 exe 里还装着通用引擎**（pack/native 路径）的大选项表，offset 8764800–8766560，逐项可读：
  `--expert-profile`(8766096)、`--expert-profile-save`(8766120)、`--expert-profile-save-every`(8766144)、`--gpu-stages`、`--mmap-experts`(8766192)、`--shared-expert-arena`(8766208)、`--resident-cpu-experts`(8766232)、`--resident-experts`(8766256)、`STRATA_RESIDENT_PIN`、`STRATA_RESIDENT_HEADROOM_GIB`、`--resident-budget-gib`(8766336)、`--stats`、`--expert-cache-per-layer`、`--no-hit-poke`、`--peer-*`、`--adapt-swaps`、`--kv-resident`、`--kv-grow` …
  紧邻的 8766584 是**通用路径**的报错格式 `unknown argument: %s`。
- **两条路径的容错风格不同**：通用路径遇到不认识的参数 → `unknown argument: %s`（报错退出）；q36 路径 → `ignoring … (not an option of this engine)`（警告后继续跑）。
- 计数：全 exe 内 `mmap-experts` 出现 11 次、`resident-cpu-experts` 4 次、`expert-profile` 20 次、`not an option of this engine` **1** 次。

### 2.3 日志实锤（参数确实进了 argv，是引擎丢弃的）

`C:/Project/local_model/strata/install/strata-q36-S-16k-mmap.log` 第 1、2 行：

```
[strata] ... engine started: ...\components\engine\0.1.54-windows-x86_64-cuda-cuda13\strata.exe --serve --native ...\Qwen3.6-35B-A3B-UD-Q4_K_XL.gguf --max-context 16384 --prefill auto --mmap-experts
strata-q36: ignoring --mmap-experts (not an option of this engine)
```

即：控制层把 `--mmap-experts` 老老实实放进了命令行，引擎读到、它自己的 q36 前端不认识、丢掉、继续启动。

### 2.4 为什么会这样：qwen35moe 走的是另一条引擎路径

- 控制层自己的注释（`app/control/setup.py:625-630`）：
  > "Qwen3.6-35B-A3B (GGUF architecture qwen35moe), Unsloth's GGUFs with the MTP block: a family with an engine path of its own (**src/qwen35**; `strata` switches to it from the file's architecture). **No pack, no expert profile, no separate MTP draft layer**: the engine reads the GGUF as it is, keeps every expert it can in VRAM and computes the rest on the CPU (the hybrid mode), and drafts with the file's own MTP block."
  同一文件 `setup.py:637-649`：qwen36 被放在 `OWN_PATH_FAMILIES`，不在 `FAMILIES`（后者是"带 pack 的 Flash-Next 文件"）。
- 官方文档同样表述：
  - <https://github.com/Niko1221/Strata/blob/main/docs/QWEN36.md>（第 8-10 行）：`on its own engine path (src/qwen35; strata switches to it from the file's architecture)`；第 24 行：`--prefill 512 | Engine flag in the config's args, not a strata launch option`。
  - <https://github.com/Niko1221/Strata/blob/main/docs/MODELS.md>（第 267-268 行）：`on its own engine path, chosen by the file`；（第 277 行）`The engine keeps every expert it can on the graphics card and computes the rest on the CPU.`
  - <https://github.com/Niko1221/Strata/blob/main/docs/DETAILS.md>（第 230-232 行）：Low-RAM modes 表（`--mmap-experts` / `--resident-experts` / `--resident-budget-gib N` "implies --mmap-experts"）—— 这张表是 **pack/native（Flash-Next）** 路径的说明；同文件第 1389/1395/1423/1438 行的历史测量全部用 pack 模型（IQ3_XXS / IQ2_XS 等）。
- 引擎自带帮助 `logs/engine-help.txt`（272 行）本身就是**通用/pack 路径**的帮助（首行 `strata generate --pack DIR --tokens "1,2,3" [options]`），其中：
  - 第 253 行 `--mmap-experts  R2.1: opt OUT of the resident expert arena, back to MapViewOfFile. The A/B arm: the mmap's rate depends on the OS page cache holding 34 GB, and measured 71.97 vs 34.78 ms/token cold vs warm.`
  - 第 259 行 `--resident-cpu-experts  with mmap and a static profile, keep the experts the GPU cache does not hold resident in ordinary RAM...`
  - 第 262 行 `--resident-experts  the low-RAM PC's resident mode (setup): --mmap-experts --resident-cpu-experts with the copy page-locked when possible, 4 GiB headroom...`
  - 第 181 行 `--expert-profile P  R4.2e: pre-load the VRAM tier from a profile.bin ...`；第 183 行 `--expert-profile-save P  --serve, #477: ...`
  → 这五个开关**在源码里真实存在、文档里有测量**，但它们服务于"arena / MapViewOfFile / profile.bin"这套 pack 侧机制，q36 的 GGUF 直读路径没有对应实现。

---

## ③ 要让引擎真吃 `--mmap-experts --resident-cpu-experts --expert-profile`，config 该怎么写

### 3.1 通用/Flash-Next（config 里**没有** `"arch"`）—— 能生效

config `"args"` 是原样透传，所以直接写进去就行；要"人手项永不被 setup/app 覆盖"，就写 `"user_args"`：

```json
{
  "args": ["--pack", "pack/full", "--max-context", "32768"],
  "user_args": ["--mmap-experts", "--resident-cpu-experts",
                "--expert-profile", "expert-profile.bin"]
}
```

- 前提：这条是 **Flash-Next / pack 路径**的配置（**不写 `"arch"` 键**，写了 `qwen35moe` 就落到 3.2 的 q36 路径）。
- `"args"` 与 `"user_args"` 都行；**`user_args` 更稳**（`strata_control/user_args.py`：每次 start、每次 setup 都在生成参数之上重新应用，同 flag 用户值赢，并靠 `args_written` 识别手改）。
- `--expert-profile` 的**保存侧**不必手写：`"expert_profile_save": "expert-profile-learned.bin"`（可配 `"expert_profile_save_every": 10`，0 = 只在退出时存）→ `--expert-profile-save` [+ `-every`]；当已有的 `--expert-profile` 与它同 shape 时，控制层会自动把旧值换成新学到的 profile（server.py:3297-3303）。
- 判据：**看引擎 stdout 有没有那行 `ignoring`**。通用路径不认识的参数会以 `unknown argument: %s` 直接报错，不会静默。

### 3.2 qwen36 / arch=`qwen35moe`（当前生产配置就属于这类）—— 写了也不会生效

**结论：这三个开关在这个模型上无法被"喂"进去。**它们不在 q36 前端的选项集（12 个）里，也没有等价实现；config 写 `args` 或 `user_args` 都只会换来一行 `strata-q36: ignoring …`。同理，`"expert_profile_save"` 这条自动化钩子在 qwen36 上会**静默失效**（`--expert-profile-save` 也不认识）。

想在 q36 上拿到"少占显存 / 专家更多放 CPU / 预热专家放置"的实际效果，用 **q36 自己的旋钮**（都写 `"args"` 或 `"user_args"`）：

| 意图 | 该用的开关 | 出处 |
|---|---|---|
| 每层多少专家进 VRAM | `--expert-vram` | 二进制 8947520-8947792；`strata_control/tune_knobs.py:170`（`families=("qwen36",)`，"without a matching prompt chunk it made prompts 44% slower"） |
| 混合放置的 row 块大小 | `--hybrid-rows` | 同上；`tune_knobs.py:111` 有 `q36_hybrid_rows_256` 实验臂 |
| 并行槽位数 | `--expert-slots` / `--parallel N`（→`--batch N`） | 二进制；server.py:3219-3240 |
| CPU 帮助线程数 | `--cpu-threads` / `--pool-workers` | 二进制；`tune_knobs.py:104` |
| 提示词分块（与 expert-vram 必须配套） | `--prefill N` 或环境变量 `STRATA_Q36_CHUNK` | docs/QWEN36.md:24 与 chunk 表 |
| 多请求时的草稿 | `--batch-mtp` | docs/QWEN36.md（"unless `--batch-mtp` is in the config's args (opt-in)"） |

### 3.3 如何在不启动服务的前提下验证某个 flag 属于哪条路径

1. `grep` 一下 `logs/engine-help.txt`：**出现在里面 = 通用/pack 路径的选项**（这份帮助就是 `strata generate --pack` 的）。
2. 或者在 `strata.exe` 里找两个偏移簇：**8764800–8766560 = 通用选项表**，**8947520–8947792 = q36 选项名**。落在前者 = 只有通用路径认；落在后者 = 只有 q36 认。
3. 运行期唯一判据：引擎 stdout 的 `strata-q36: ignoring …`（q36 路径）或 `unknown argument: …`（通用路径，会失败）。

---

## 附 A：32 份日志里全部被 ignoring 过的开关（去重）

| 开关（含值） | 次数 | 归属 |
|---|---|---|
| `--resident-experts` | 6 | 通用/pack 低内存模式 |
| `--kv q4_0` | 5 | 通用 KV 压缩 |
| `--kv-resident 20480` | 4 | 通用 KV 驻留 |
| `--no-capture` | 3 | 通用 |
| `--mmap-experts` | 3 | 通用低内存模式 |
| `--kv k8v4` | 3 | 通用 KV 量化 |
| `--resident-cpu-experts` | 2 | 通用低内存模式 |
| `--expert-cache 512` | 2 | 通用专家缓存 |
| `--conversation-cache-slots 1` | 2 | 通用会话缓存 |
| `--trim-stage-weights` | 1 | 通用 |
| `--memory-limit-mib 24000` | 1 | 通用 |
| `--kv-grow` | 1 | 通用 |

**没有任何一份日志出现 `--expert-profile` 的 ignoring 行** —— 不是它能用，而是此前没人试过；它同样不在 q36 的 12 个选项里。

## 附 B：生产配置（对照样本，无 ignoring）

`C:/Project/local_model/strata/install/strata-qwen36-ud-q4_k_xl.json`：

```json
"arch": "qwen35moe",
"cwd": "app\\control", "port": 8080, "gpu": 0,
"args": ["--native", "...\\model-data\\models\\qwen36-UD-Q4_K_XL\\Qwen3.6-35B-A3B-UD-Q4_K_XL.gguf",
         "--max-context", "32768", "--prefill", "auto", "--mtp", "2", "--vision"],
"vision": {"exe": "strata-vision.exe", "mmproj": "mmproj-F16.gguf", "gpu": false, "max_tokens": 300, "threads": 8}
```

`args_written` 与 `args` 完全相同（= 无手改项）。它的日志里**一句 ignoring 都没有**，引擎自己说 `strata-q36: … 753 tensors (layout checked), 4.40 GiB on the GPU … (the routed experts are placed after the engine's buffers)`，随后因显存不足拒开 hybrid slots —— 一个"只用 q36 认识的开关"的干净配置长这样，可直接当模板。

## 附 C：版本与更新源（确认这不是"旧引擎的 bug"）

- `<install>/logs/engine-update.log` 记录的更新源：<https://github.com/Niko1221/Strata/releases/latest/download/strata-feed.json>
- 该 feed（本地副本 `strata-feed.json`）：`sequence` 117，签名 `key_id` 5d1bc23abbeffd0d；app **0.2.8**（pub 2026-10-29T20:19:19Z）、control **0.1.54**、engine **0.1.54**（各后端同版本）。
- `components/engine/0.1.54-windows-x86_64-cuda-cuda13/engine-component.json`：`version 0.1.54`、`build_id 8c1aea4bca1b+cuda13.0`、`min_driver nvidia 580.65`。
→ 本机就是当前最新引擎；**不存在"换个更新的引擎就能吃这些开关"**。

## 附 D：一手证据清单

| 结论 | 证据 | 类型 |
|---|---|---|
| 命令行来自 `[exe,"--serve",*engine_args(cfg)]` | `app/control/serve/server.py:1063`、`:9024` | 本机代码 |
| 11 条派生规则（1–11b）+ `args` 透传 | `app/control/serve/server.py:3161-3213` 及 `:2723-2736`、`:3219-3240`、`:3246-3266`、`:3284-3304` | 本机代码 |
| `user_args` 是手改项的官方通道 | `app/control/strata_control/user_args.py` | 本机代码 |
| `ignoring` 只存在于 exe | 全树 grep + exe offset 8947816 | 本机二进制 |
| q36 选项共 12 个、无三者 | exe 8947520-8947792 + `usage: strata-q36 …` | 本机二进制 |
| 通用路径选项表含三者 | exe 8764800-8766560，`unknown argument: %s` 在 8766584 | 本机二进制 |
| 参数确实进 argv、引擎丢弃 | `install/strata-q36-S-16k-mmap.log:1-2` | 本机日志 |
| qwen36 = 独立引擎路径、无 expert profile | `app/control/setup.py:625-630`、`:637-649`；<https://github.com/Niko1221/Strata/blob/main/docs/QWEN36.md>（8-10 行）、<https://github.com/Niko1221/Strata/blob/main/docs/MODELS.md>（267-268、277 行） | 代码 + 官方文档 |
| 三者属 pack/native 的低内存机制 | <https://github.com/Niko1221/Strata/blob/main/docs/DETAILS.md>（230-232 行）、`logs/engine-help.txt`（181、183、253、259、262 行） | 官方文档 + 引擎帮助 |
| 无更新的引擎可改此行为 | <https://github.com/Niko1221/Strata/releases/latest/download/strata-feed.json>（sequence 117） | 官方 feed |

> 说明：GitHub API（api.github.com）在本机代理下返回 403 限流；`raw.githubusercontent.com` 直连失败、走 `http://127.0.0.1:7897` 代理可正常取（HTTP 200）。`docs/CONFIG.md` 不存在（404）—— 官方**没有**逐键映射文档，唯一权威就是 `serve/server.py`。