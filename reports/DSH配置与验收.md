# DSH 里怎么摆两条本地路线：provider 配置、命名规范、验收脚本（2026-10-30）

> 口径：本文件里的「实测」都注明时间与来源；从插件源码或官方文档读来的写「源码/文档」；没跑过的一律写「未验证」。
> 本文件取代 docs/DSH接入-本地模型-20261030.md 里 provider 名字与 id 的部分（那份文档的 `local` / `Local` 命名已作废，其余实测数字仍然有效）。
>
> **当前状态（2026-10-30 09:07）：配置已落盘、YAML 校验通过、验收已实测通过（`验收通过：0 FAIL`，退出码 0）。** 8091 引擎（单实例 `ninfer-serve-89.exe` pid 7740，`profile=max`，7,459 / 8,188 MiB，`id=bonsai27b-ptq1-mtp-rk2v4-40k`）与 8081 网关都在线，§6.1 贴的是**真跑出来的原文**（`logs/verify-20261030-090645.log`）。剩下唯一没做的是 §9 第 5 条：**重启 DSH 应用与宿主后用肉眼看一眼选择器**——这一步脚本验不到。

## 0. 一句话结论

配置改完了（`local` → `ninfer`，模型 id 换成能自解释的长名），YAML 校验通过，**但有两件事必须先发生它才真的能用**：

1. **引擎必须用同一个 id 起**：`models[].id` 会原样进入请求体的 `model` 字段，引擎按启动参数 `--model-id` 逐字强校验，对不上直接 404；经 8081 网关会变成 502。而 `scripts/serve2.sh:20` 与 `scripts/asklong.sh:13` 的默认仍是 `MODELID=${MODELID:-local}`。
2. **DSH 侧要「重启应用与宿主」**（只刷新页面不够，配置在宿主启动时读入 —— 见 docs/DSH接入-本地模型-20261030.md:41）。

验收也跑通了：`tools/dsh_provider_test.py`（任意 baseURL+model 都能跑，405 行）+ `tools/verify_all.sh`（一条命令六步，215 行）。2026-10-30 09:06:45 在真实引擎上**全绿**：模型 id 命中、非流式/流式/tools/未知字段四项都 200、`-52k` 那档按预期 **SKIP**（它要单独起 long profile）、Strata 未在跑记跳过，最后 `验收通过：0 FAIL`（§6.1 有原文）。中间踩过一次坑：Strata 安装期会「闪现」，占位 id 对不上差点把 NInfer 的结论带红，处置见 §6.3。

## 1. 配置长什么样（现状，已落盘并校验）

文件：`C:/Users/Administrator/.dsh/profiles/desktop/cordis.patch.yml`（patch 层，`llm-pi-ai.config.providers` 下）

| provider key | displayName | model id（= 发给引擎的 model） | contextWindow | maxTokens | 什么时候可用 |
|---|---|---|---|---|---|
| `ninfer` | NInfer KVMem | `bonsai27b-ptq1-mtp-rk2v4-40k` | 38000 | 8192 | 现役主力：池 40K + MTP draft4/win8 |
| `ninfer` | NInfer KVMem | `bonsai27b-ptq1-nomtp-rk2v4-52k` | 50000 | 4096 | 仅当引擎以 52K 池、无 MTP 起（否则 404/502） |
| `strata`（**已启用**，块完整） | Strata | `qwen36-35b-a3b-udq4kxl` | 32768（占位） | 4096 | Strata 一起服就能选；只剩「改数字」这一步（见 §7） |
| `strata`（**已启用**，块完整） | Strata | `qwen38-flash-next-gyro-s` | 131072（占位） | 4096 | 同上 |

选中的模型名（这个名字会显示在 DSH 模型选择器里，是人眼唯一能看到的辨识依据）：

- `Bonsai 27B Ternary PTQ1 · MTP draft4/win8 · rk2v4-e8 · 池40K`
- `Bonsai 27B Ternary PTQ1 · 无MTP(~32tok/s) · rk2v4-e8 · 池52K`

落地的 YAML（`ninfer` 段原文）：

```yaml
      ninfer:
        displayName: NInfer KVMem
        api: openai-completions
        baseURL: http://127.0.0.1:8081/v1
        apiKeyEnv: LOCAL_LLM_KEY
        streamIdleTimeoutMs: 900000
        models:
          - id: bonsai27b-ptq1-mtp-rk2v4-40k
            name: Bonsai 27B Ternary PTQ1 · MTP draft4/win8 · rk2v4-e8 · 池40K
            contextWindow: 38000
            maxTokens: 8192
            input:
              - text
          - id: bonsai27b-ptq1-nomtp-rk2v4-52k
            name: Bonsai 27B Ternary PTQ1 · 无MTP(~32tok/s) · rk2v4-e8 · 池52K
            contextWindow: 50000
            maxTokens: 4096
            input:
              - text
```

`strata` 段（**启用态**，不是注释；lead 要求「可用的完整块」，验收时就只剩改数字）：

```yaml
      strata:
        displayName: Strata
        api: openai-completions
        baseURL: http://127.0.0.1:8080/v1
        apiKeyEnv: LOCAL_LLM_KEY
        # Strata 若 prefill 比 NInfer 更慢，这个值同样要放大，别用 pi-ai 默认 5 分钟。
        streamIdleTimeoutMs: 900000
        models:
          - id: qwen36-35b-a3b-udq4kxl
            name: Qwen3.6-35B-A3B MoE · UD-Q4_K_XL · 上下文占位 32K（按 strata connect 实测改）
            contextWindow: 32768
            maxTokens: 4096
            input:
              - text
          - id: qwen38-flash-next-gyro-s
            name: Qwen3.8-Flash-Next 125B级 MoE · Gyro-S · 上下文占位 128K（按 strata connect 实测改）
            contextWindow: 131072
            maxTokens: 4096
            input:
              - text
```

备份：`cordis.patch.yml.bak-2026-10-30T08-37-28-naming`（改名前）、`cordis.patch.yml.bak-2026-10-30T08-39-03-pre-rename`（第二次改之前）、`cordis.patch.yml.bak-before-local`（最初）。

YAML 校验（改了三次都跑过）：`python -c "import yaml; yaml.safe_load(open(path, encoding='utf-8'))"` → 13 个条目，providers = **opencode-go / ninfer / strata / wb**（strata 已从注释改成启用态，逐 provider 打印核对过 id 与 contextWindow）。

## 2. 字段到底什么含义（读插件源码得来的，不是猜的）

来源：`tmp/asar/pi-ai-index.js:1036-1082`（zod schema）与 `tmp/asar/pi-ai-README.zh.md:76-90`。

### 2.1 provider 级（写在 provider key 下面）

| 字段 | 默认 | 作用 / 我们怎么填 |
|---|---|---|
| `api` | — | `openai-completions`。本地引擎/Strata/网关都是这个口 |
| `baseURL` | — | 8081 网关（会裁剪）/ 8091 引擎直连（不裁剪）/ Strata 8080 |
| `displayName` | provider key | 设置页里显示的提供方名，现在是 `NInfer KVMem` |
| `apiKeyEnv` | — | 指向 `.credentials.yaml` 的 `refs` 名；引擎不校验，占位值即可 |
| `models[]` | — | 见 2.2 |
| `streamIdleTimeoutMs` | `300000`（5 分钟） | **本地必须调大**：200K 提示 prefill 要 380–400 s，默认值会让 pi-ai 中途放弃并重发，两份 prefill 叠加把引擎打崩。现填 900000 |
| `timeoutMs` | — | 整请求上限，另有 `retryPolicy`；我们没动 |
| `transport` | `auto` | `sse` / `websocket` / `websocket-cached`；本地引擎只有 SSE，别填 websocket |
| `cacheRetention` | — | `none`/`short`/`long`；本地引擎的 `cached_tokens` 由引擎自己前缀复用决定，DSH 侧不用管 |
| `compat` | — | `supportsReasoningEffort` / `thinkingFormat` 之类，非推理模型不要填 |
| `defaultContextWindow` / `defaultMaxTokens` / `defaultInput` | 262144 / 32768 / 含 text | 模型级没写时才用 |
| `headers` | — | 额外 HTTP 头 |

### 2.2 model 级（写在 `models[]` 里，`modelOverrides` 用同样字段但 id 是字典键）

| 字段 | 校验 | 作用 / 我们怎么填 |
|---|---|---|
| `id` | 必填；会原样当请求的 `model` | **必须等于引擎 `--model-id`**，否则 404（实测见 §3） |
| `name` | 可省 | 选择器里显示的人类名；模型真名+关键参数写这里 |
| `contextWindow` | 正整数（非法值插件直接报 invalid） | DSH 用它决定什么时候压缩历史；**必须 ≤ 引擎池**，写大了就是超池未验证区 |
| `maxTokens` | 正整数 | 输出上限；DSH 会从 contextWindow 里再扣掉它当提示上限 |
| `input` | 数组 | `text`（本地引擎 `modalities.vision=false`，别写 image） |
| `reasoningEfforts` | `false` 或非空字典（空字典会被拒） | 本地模型没有推理档，**整个字段省掉** |
| `compat` | — | 模型级覆盖 provider 级兼容开关 |

### 2.3 contextWindow 该填多少（这块最容易填错）

DSH 的语义是「总窗口」，然后自己扣掉 `maxTokens` 当提示上限。所以：

| 引擎池 | 我们填的 contextWindow | maxTokens | 真实提示上限 | 理由 |
|---|---|---|---|---|
| 40,000 | 38000 | 8192 | ~29,800 tok | 留 10K 余量。超池后会进「首个请求 8/8、之后 2/8→0/8」的未验证区（见 reports/超池200K-可用性实测.md） |
| 52,000 | 50000 | 4096 | ~45,900 tok | 52K 档 prefill 实测崩到 ~180 tok/s，只适合长文档批处理 |
| 16,000（fast 档） | 16000 | 4096 | ~11,900 tok | 短问答，DSH 系统提示会吃掉大半 |

## 3. 为什么 id 不能是 `local`（这也是本轮最重要的约束）

这不是命名口味问题，是引擎行为：

| 实测 | 请求 | 结果 |
|---|---|---|
| 2026-10-30 08:38（引擎 `--model-id local`） | `model="Bonsai-27B-Ternary-PTQ1"` | **HTTP 404**，`{"error":{"code":"model_not_found","message":"model 'Bonsai-27B-Ternary-PTQ1' not found","param":"model","type":"invalid_request_error"}}` |
| 同上 | `model="local"` | HTTP 200，正常返回 |
| 2026-10-30 08:39（task-17 的引擎） | `GET /v1/models` | `id="lim"` —— 印证 id 就是每次启动时 `--model-id` 那个字符串，不是模型文件里的常量 |

推论：**`id` 与引擎启动参数是同一根绳子的两头**。谁先改都行，但两边必须一致；不一致的表现是选择器里点下去就 502，日志写 `model_not_found`。

所以配套给了一份补丁 `tools/modelid-naming.patch`（把两个脚本的默认 `MODELID` 改成长名）：

```bash
        -MODELID=${MODELID:-local}
        +MODELID=${MODELID:-bonsai27b-ptq1-mtp-rk2v4-40k}
```

`scripts/` 不在我这轮的写权限里，**补丁没 apply**；不想改脚本也可以，起服时显式 `MODELID=bonsai27b-ptq1-mtp-rk2v4-40k bash scripts/serve2.sh` 等效。

## 4. 命名规范（以后加第三个 provider 也照这个来）

三条规则，按优先级：

1. **id 可机器读，且能自解释**：`<模型族><尺寸>-<量化>-<KV/推理特性>-<池>`，例 `bonsai27b-ptq1-mtp-rk2v4-40k`。全小写、无空格、只留 `a-z0-9-`（它要进请求体）。
2. **name 给人看，参数不许删**：写模型真名 + 别人一眼能分辨的运行参数，例 `Bonsai 27B Ternary PTQ1 · MTP draft4/win8 · rk2v4-e8 · 池40K`。
3. **displayName 表示「哪条路线」**：`NInfer KVMem` / `Strata`。同一路线不同档位算同一个 provider 的不同 model，不要一个档建一个 provider。

反面例子（就是旧配置）：provider `local`、displayName `Local`、model id `local`、name `local` —— 换成 52K 档、换成 Strata 都还叫 local，看名字完全无法分辨是哪一套。

## 5. 生效步骤（照做就行）

> **硬要求：下一次起服必须带 `MODELID=bonsai27b-ptq1-mtp-rk2v4-40k`。** 不起这个 id，YAML 里的两个模型点下去就是 404（直连）/ 502（网关）。脚本默认值我没改（`scripts/` 是 ninfer-limit 的写域），改动只以补丁 `tools/modelid-naming.patch` 形式留给 lead 统一 apply；在那之前，起服命令行显式传这个环境变量即可，两者等效。

1. 起引擎（或让 task-17 收尾时）带上匹配的 id：
```bash
   cd /c/Project/local_model && PROFILE=legacy FORCE=1 GW=1 PORT=8091 \
     MODELID=bonsai27b-ptq1-mtp-rk2v4-40k POOL=40000 HOSTKV=6144 bash scripts/serve2.sh
```
2. 确认两边对得上：`curl -s http://127.0.0.1:8081/v1/models` 里的 `id` 必须与 YAML 的 `models[].id` 逐字相同。
3. DSH 菜单 →「重启应用与宿主」。
4. 新开会话，选择器里应该出现 **NInfer KVMem / Bonsai 27B Ternary PTQ1 · MTP draft4/win8 · rk2v4-e8 · 池40K**。
5. 跑验收：`bash tools/verify_all.sh`（一条命令做完下面 §6.2 五步；想只跑接口六项就 `python tools/dsh_provider_test.py --config`）。

## 6. 验收脚本 `tools/dsh_provider_test.py`

设计目标是**对任意 baseURL + model 都能跑**，所以本机换档、换端口、以后上 Strata 都不用改脚本。

| 检查 | 发什么 | 判定 |
|---|---|---|
| 1 models | `GET {base}/models` | 目标 id 出现在列表里（DSH 的模型发现走这条） |
| 2 nonstream | 非流式短问 | HTTP 200 且 content 非空 |
| 3 stream | 流式 + `stream_options.include_usage` | 有 chunk、`usage.prompt_tokens` 不为空、记 TTFT 与 decode |
| 4 tools | `tools` + `tool_choice:auto` + `parallel_tool_calls` | 透传不报错即通过；**是否真吐出 tool_call 只记事实** |
| 5 unknown fields | 多塞 `foo_unknown_field` / `cache_retention` | HTTP 200 才算容错 |
| 6 oversize（可选） | `--overpool-tokens N` | 4xx 明确拒绝 = 好；200 = WARN（NInfer 超池的老毛病就是 200 + 静默丢中段） |

1/2/3/4/5 全过才 PASS，每个模型一行；`--json` 存完整请求与响应体。用法：

```bash
  python tools/dsh_provider_test.py --base http://127.0.0.1:8091/v1 --model bonsai27b-ptq1-mtp-rk2v4-40k
  python tools/dsh_provider_test.py --config                 # 读 cordis.patch.yml，只测本机 provider
  python tools/dsh_provider_test.py --config --overpool-tokens 45000 --json tmp/dsh_accept.json
  python tools/dsh_provider_test.py --base http://127.0.0.1:8080/v1 --model <strata 报的 id>
```

### 6.1 实测结果

**实测（2026-10-30 09:06:45，8091 引擎在 8091、网关在 8081，单实例 `ninfer-serve-89.exe` pid 7740，profile=max）——全绿**：

```
================= DSH 本地 provider 验收 20261030-090645 =================
--- 1/6 显卡 ---     RTX 4060 Ti, 616.92, 7459 MiB, 8188 MiB, 0 %      PASS
--- 2/6 8091 引擎直连 ---  HTTP 200  id=bonsai27b-ptq1-mtp-rk2v4-40k ctx=262144  PASS
--- 3/6 8081 网关 ---      HTTP 200  同一个 id                          PASS
--- 4/6 DSH 视角 ---       命中 1 / 声明 2（-52k 缺席，要 PROFILE=long） PASS(只读)
--- 5/6 dsh_provider_test ---  [PASS] ninfer 六项全 OK                    PASS
--- 6/6 Strata ---         8080 -> HTTP 000，跳过（不算 FAIL）            SKIP
验收通过：0 FAIL        # 退出码 0
```

第 5 步的六项原文（DSH 形状请求走 8081 网关）：

```
[PASS] ninfer  base=http://127.0.0.1:8081/v1  model=bonsai27b-ptq1-mtp-rk2v4-40k
   1 models        OK  列出=['bonsai27b-ptq1-mtp-rk2v4-40k']
   2 nonstream     OK  HTTP 200 wall=0.53s text='2'
   3 stream        OK  HTTP 200 chunks=6 ttft=0.30 usage={'p': 38, 'c': 12} decode=n/a（样本太短）
   4 tools         OK  真吐 tool_call=True
   5 unknown fields OK  HTTP 200
[SKIP/缺席] ninfer  model=bonsai27b-ptq1-nomtp-rk2v4-52k
   DSH 里声明了这个 id，但引擎当前只报：['bonsai27b-ptq1-mtp-rk2v4-40k']
   -> 预期不存在，不算 FAIL。要它可用请按 PROFILE=long（池 51,200、无投机，decode ~32 tok/s） 起服。
1/2 PASS，1 SKIP/缺席（该档现在没起、按预期 404，不算失败），0 FAIL
```

落在 `logs/verify-20261030-090645.log` / `.json`（同一天 09:05:49 与 09:06:29 也各跑过一次，形状完全一致，**可重复**）。

两处口径修正：①**「缺席」现在直接印成 `SKIP`**（表里判据列写 SKIP、汇总行写 `1 SKIP/缺席`），因为它按预期 404，不是失败——这是 lead 明确要求的措辞；②stream 的 decode 在这个量级（12 tok / 0.3 s）算不出可信值，脚本已改成在 `completion_tokens < 3 或 生成时间 < 50 ms` 时打 `n/a（样本太短）`，不再输出 `11000000.0 tok/s` 那种除法噪音。

**当前状态：验收通过（0 FAIL）**，配置、脚本、日志三样齐；剩下的只是「DSH 重启应用与宿主后在选择器里真的能看到这两个 provider」（§9 第 5 条）。

历史参照（同一轮早些时候 8091/8081 停服期间，失败路径，留作坏例子）：8091/8081 在 08:35 前后被停掉（`netstat` 只剩 8092，进程 `ninfer-serve-89.exe` pid 30240，GPU 99%，`/v1/models` 报 `id=lim`），按铁律「除 ninfer-limit 外任何人不得启引擎 / 不得插大请求」，我没有占用这段时间。

历史参照（2026-10-30 早间，同一条链路，model id 当时是 `local`，来源 docs/DSH接入-本地模型-20261030.md:47-51，我方复核过形状一致）：

| 项 | 数值 |
|---|---|
| DSH 形状请求（stream + include_usage + tools + parallel_tool_calls + penalty） | HTTP 200，4 个 SSE chunk |
| usage | prompt 289 / completion 29 |
| tool_calls | 正确吐出 `run_bash` |
| 未知字段 | `foo_unknown` / `max_completion_tokens` 不报错 |
| 前缀复用 | 第二轮 `cached_tokens=277` |
| model id 严格校验 | 错名 → 404 `model_not_found`（网关 502） |

### 6.2 一键验收 `tools/verify_all.sh`

§6 的六项只是「对某个 baseURL 发请求」；验收要的是「这台机器上现在这套东西能不能用」。所以包了一层 bash，一条命令跑完六步（第 4 步「DSH 视角」是 2026-10-30 09:0x 按 lead 要求新加的，专门回答「配置里写的 id 和引擎真实 id 对得上吗、对不上的那档什么时候才有」）：

| 步 | 做什么 | 判定 |
|---|---|---|
| 1 | `nvidia-smi --query-gpu=name,driver_version,memory.used,memory.total,utilization.gpu` | 拿不到就 FAIL（先确认卡在不在、被谁占着） |
| 2 | `GET http://127.0.0.1:8091/v1/models` | 非 200 就 FAIL，并打印原始响应体前 1200 字节 |
| 3 | `GET http://127.0.0.1:8081/v1/models` | 同上（网关也要在） |
| 4 | **DSH 视角**：拿 `cordis.patch.yml` 里声明的 `models[].id` 去比对第 2/3 步抓到的 `/v1/models` 列表 | 只打印不判分：逐行给「命中 / 缺席 + 缺席那档要起哪个 PROFILE」；一个都没命中才额外喊一句警告（真判定留给第 5 步） |
| 5 | `python tools/dsh_provider_test.py --config <cordis.patch.yml> --json logs/verify-<TS>.json` | 逐模型 PASS/FAIL/**缺席**；有 FAIL 就把原始错误体留在日志里 |
| 6 | Strata：从 YAML 读 `strata.baseURL`，`GET {base}/models` 通才跑 `--provider strata` | **不在线算「跳过」，不算 FAIL**（Strata 还没装） |

```bash
bash tools/verify_all.sh                       # 全部检查
CONFIG=/path/cordis.patch.yml bash tools/verify_all.sh
SKIP_STRATA=1 bash tools/verify_all.sh         # 不看 Strata
OVERPOOL=45000 bash tools/verify_all.sh        # 顺带判超长提示是 4xx 还是静默 200（慢 ~70 s）
```

输出：屏幕 + `tee` 到 `C:/Project/local_model/logs/verify-<时间戳>.log`（同时留一份 `verify-<时间戳>.json` 存完整请求/响应体）。退出码 0 = 全 PASS，1 = 有 FAIL。**判据就一句：全 PASS 才算验收通过**；任何 FAIL 都能在日志里直接看到原始响应体，不用复现。

为什么不用 `set -e`：验收脚本的价值在于「把六步都走完再一次告诉你坏在哪」，中途退出会掩盖后面的信息；所以用 `fails` 计数器，最后统一给结论。

**「缺席」不是 FAIL**（这一条最容易被误判）：一张 8 GB 卡同一时刻只能跑一档引擎，而配置里写着两个 ninfer 条目。所以脚本对「DSH 声明了、但引擎 `/v1/models` 里没有」的 id 只标 **缺席**，并印出「要它得按 `PROFILE=long`（池 51,200 / 无投机）起服」，**跳过后续 4 项请求、不计入失败**——因为那本来就不是故障，而是「现在跑的是另一档」。只有**某个 provider 声明的 id 一个都命中不了**时才记 FAIL（那才是起错档或引擎没起）。退出码只看 FAIL 数。

**失败路径已实测**（2026-10-30 08:43:52，两台服务都没起；下面是加第 4 步之前那版的原文，所以步骤号还是 `1/5…5/5`，现在同一位置是 `1/6…6/6`，中间多了一步只读的 `4/6`）。**通过路径在 09:06:45 也跑过了，见 §6.1**：

```
--- 1/5 显卡 ---    NVIDIA GeForce RTX 4060 Ti, 616.92, 0 MiB, 8188 MiB, 0 %
!! FAIL: 2/5 8091 引擎直连 /v1/models 不可用（HTTP 000）
!! FAIL: 3/5 8081 网关 /v1/models 不可用（HTTP 000）
    （Strata 不在线 -> 本轮从这项里排除，放到 5/5 报「跳过」）
!! FAIL: provider_test 有 FAIL（退出码 1，原始响应体见上面；完整 json: logs/verify-20261030-084352.json）
--- 5/5 Strata（在跑才测）---    Strata 未在跑（HTTP 000），跳过（不算 FAIL）
验收未通过：3 项 FAIL        # 退出码 1
```

三处细节值得记下来：

1. **失败也打印原始响应体**：`URLError(ConnectionRefusedError(10061, '由于目标计算机积极拒绝，无法连接。'))` 是这一轮的真实报错原文，不是「连接失败」这种二手描述；以后拿去搜就行。
2. **Strata 离线不拖累结论**：它是启用态 provider，若不排除会让第 5 步变 FAIL，把「NInfer 能不能用」的结论带偏。所以第 5 步会自动加 `--exclude-provider strata`，只在第 6 步报「跳过（不算 FAIL）」。
3. 同一次运行里 `nvidia-smi` 显示 **0 MiB / 0 %** —— task-17 的扫描在 08:43 前已经收尾，卡是空的，8091 随时能回位。`tools/dsh_provider_test.py` 那次实测产生的两份 FAIL 记录留在 `logs/verify-20261030-084352.log` / `.json` 里当「坏例子」存档。

**通过路径已实测**（2026-10-30 09:06:45，原文见 §6.1）：`1/6` 显存 7,459/8,188 MiB；`2/6`/`3/6` 都列出 `bonsai27b-ptq1-mtp-rk2v4-40k`；`4/6` 对照表 `-40k` 命中、`-52k` 缺席并注明要 `PROFILE=long`；`5/6` 一行 `[PASS]` + 一行 `[SKIP/缺席]`；`6/6` 跳过；末行 `验收通过：0 FAIL`，退出码 0。**离线失败路径与在线通过路径现在都覆盖到了**，脚本可重复跑（09:05:49 / 09:06:29 / 09:06:45 三次形状一致）。

### 6.3 一个真实踩到的坑：Strata 会「闪现」，不能让它给主机验收上色

09:05:10 第一次跑整脚本时，第 5 步报 FAIL：那一刻 **8080 短暂在线**，`/v1/models` 报的真实 id 是 **`qwen3.8-flash-next`**，与我配置里的 `qwen36-35b-a3b-udq4kxl` / `qwen38-flash-next-gyro-s` 两个占位 id 都不匹配，于是「provider 声明的 id 一个都没命中」被判 FAIL。随后 8080 又回到 000（`ps` 看到 `/c/Project/local_model/strata/app/control/python/python` 三个进程在 09:01–09:05 起落，是 task-15 的安装/控制面，不是常驻服务）。

三条处置（都已落进脚本）：

1. **第 5 步无条件 `--exclude-provider strata`**：Strata 的 id 还没定，它不该影响「NInfer 能不能用」这个结论。Strata 单独放第 6/6 步。
2. **第 6 步带 `--weak-absent`**：Strata 在线但 id 对不上时只打 WARN 并给出改法（把 `strata.models[].id` 改成引擎真实报告的 id），退出码仍是 0。
3. **情报留档**：Strata 的真实模型 id 很可能是 **`qwen3.8-flash-next`**。等 task-15 装完、`strata connect` 打印确认后，把配置里两个占位 id 改成它（**我没有擅自改**，因为只观测到一次闪现）。

教训一句话：**验收脚本必须和「会在后台自己起落的东西」解耦**，否则同一台机器同一份配置，验收结论会随 Strata 装没装完而随机变红。

## 7. Strata 这条路线怎么接（块已写成启用态，只剩改数字）

Strata 引擎本身还没装（task-15 pending），但按 lead 的要求，provider 段**已经写成可用的完整块**（不是注释占位）：`baseURL` 先填默认的 8080，两个 model id 先填文档里的 `qwen36-35b-a3b-udq4kxl` / `qwen38-flash-next-gyro-s`，`contextWindow` 先填 32768 / 131072 占位。这样等 `strata serve` 一起来，DSH 里直接就能选，验收时只剩「改数字」。

代价要说清楚：8080 没人听的时候，选择器里会多出一个连不上的提供方；这是有意的取舍（能选 > 干净），`tools/verify_all.sh` 里「Strata 不在线」算跳过不算 FAIL。装好之后按这四条核实：

| 要填的 | 从哪拿 | 依据 |
|---|---|---|
| `baseURL` | `strata connect` 打印的 address；没记账时默认 `http://127.0.0.1:8080/v1` | tmp/strata-docs/TERMINAL_LAUNCH.md:184、DETAILS.md:98 |
| `models[].id` | `GET /v1/models` 报的 id（`strata connect` 也会打印 model） | TERMINAL_LAUNCH.md:185「the model name the server reports」 |
| `contextWindow` | 该次 `strata serve` 实际起的上下文（`--context` / profile 里的值） | TERMINAL_LAUNCH.md:185 |
| `apiKeyEnv` | Strata 的 key；本机自用可 `none` | DETAILS.md:660 示例 `apiKey: none` |

Strata 侧的接口面（文档口径）：`/v1/models`、`/v1/chat/completions`、`/v1/messages`；流式、tools、`response_format`、logprobs 都支持（DETAILS.md:408、522、548；SAFETY.md:91 写共享端口只答这三个路径）。

额外一条可能有用的：**`strata connect` 原生列了 DeepSeek Harness**，可以 `--check` 直接让 Strata 用自己的方式发一次 prompt + 一次 tool call 验证连通（TERMINAL_LAUNCH.md:172-179）。它和我这个脚本互补：它验「Strata ↔ DSH 接口」，我验「DSH 具体模型的六项行为」。

## 8. 坑与注意

1. **同一个模型两个 provider 会让选择器变脏**。8091 直连（绕过网关裁剪）我写成注释块 `ninfer-direct`，做长文档实验时再启用，日常留 8081 网关版。
2. **网关会把 404 变 502**。看到 502 不要先怀疑引擎挂了，先看 id 对不对。
3. **网关会裁剪**：`tools/chat_gateway.py` 只对 `/v1/chat/completions` 做 L1/L2/L3 分级裁剪，其余路径直通。所以凡是要「引擎真实行为」的实验必须直连 8091，否则结论被网关污染（这条在 reports/超池200K-可用性实测.md 里踩过）。
4. **`contextWindow` 写大了等于自愿进未验证区**：40K 池上写 200K，DSH 会真的发 200K 提示，引擎 200 + 中段静默丢针。
5. **改配置只改 patch 层**（`cordis.patch.yml`），不要动 `cordis.yml`；设置页改的也是同一份 patch。
6. **`reasoningEfforts` 留空字典会被插件拒**（报 has an empty reasoningEfforts），本地模型直接不写这个字段。

## 9. 待办 / 未验证

| # | 事项 | 卡在哪 |
|---|---|---|
| 1 | ~~`bash tools/verify_all.sh` 的通过路径~~ | **已完成**（2026-10-30 09:06:45，三次形状一致，`验收通过：0 FAIL`，见 §6.1） |
| 2 | `tools/modelid-naming.patch` 是否 apply | **lead 收尾时统一 apply**（`scripts/` 是 ninfer-limit 写域）；也可以起服时显式传 `MODELID=bonsai27b-ptq1-mtp-rk2v4-40k` |
| 3 | Strata 段 5 个占位数字（端口 + 2 个 id + 2 个 contextWindow） | 等 task-15 装完 + `strata connect`；**已观测到真实 id 疑似 `qwen3.8-flash-next`**（09:05 闪现一次，见 §6.3），确认后建议把两个占位 id 收敛到它 |
| 4 | 超池 `--overpool-tokens 45000` 的 4xx/200 判定 | 引擎现在就在 8091，随时可跑（`OVERPOOL=45000 bash tools/verify_all.sh`），但要 ~70 s prefill，且结论已知是「200 + 静默丢中段」，见 reports/超池200K-可用性实测.md |
| 5 | DSH 侧「重启应用与宿主」后选择器里真的出现 `ninfer` / `strata` 两个 provider | 引擎已在 8091，现在就能做；这一步只能由人重启 GUI 后目视确认，脚本验不到 |

## 10. 附件

- 改前备份：`C:/Users/Administrator/.dsh/profiles/desktop/cordis.patch.yml.bak-2026-10-30T08-37-28-naming`
- 补丁：`tools/modelid-naming.patch`
- 验收脚本（接口六项）：`tools/dsh_provider_test.py`（405 行，`py_compile` 通过；含 ABSENT/SKIP 语义与 `--weak-absent`）
- 验收脚本（一键六步）：`tools/verify_all.sh`（215 行，`bash -n` 通过；第 4 步是 DSH 视角 id 对照）
- 验收日志：`C:/Project/local_model/logs/verify-<时间戳>.log` / `.json`；**通过路径样本 = `verify-20261030-090645.log`**，失败路径样本 = `verify-20261030-084352.log`
- 离线自测用的 mock（不占卡）：`tmp/overpool/mock_openai.py` + `tmp/overpool/mock-cfg.yml`，产物 `tmp/overpool/mock-verify-run.log`
- **面向用户的模型清单**：`docs/本地模型清单-给DSH用.md`（4 个本地条目逐行：id / 别名 / 本体 / 实测速度 / 真实窗口 / 显存 / 什么时候选 / 一条起服命令；另含换档与报错对照表、命名规范、验收三步）
- 插件 schema 读源：`tmp/asar/pi-ai-index.js`、`tmp/asar/pi-ai-README.zh.md`
