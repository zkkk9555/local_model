# DSH 本地模型条目 · 端到端实测

> 实测时间 2026-10-30 11:09–11:16（Asia/Shanghai）· 机器 RTX 4060 Ti 8 GB / Ryzen 7 7800X3D / 31.1 GB DDR5-6000 / Win11
> 被测对象：`C:/Users/Administrator/.dsh/profiles/desktop/cordis.patch.yml` 中 plugin `llm-pi-ai` 的 `providers` 段（5 个 provider、9 个 model 条目）
> 探针：`C:/Project/local_model/tools/e2e_model_probe.py`（GET /v1/models + POST /v1/chat/completions 流式，记首字）

## 0 一页结论

| # | 配置里的 provider / model id | 实测 | 判定 |
|---|---|---|---|
| a | `ninfer` / `bonsai27b-ptq1-mtp-rk2v4-40k`（8081 网关） | HTTP **200**，首字 **0.33–0.46 s** | **【可用】** |
| b | `ninfer` / `bonsai27b-ptq1-nomtp-rk2v4-52k`（8081 网关） | HTTP **502**（0.014 s 立即失败）；直连 8091 是 **404 model_not_found** | **【需改配置·换档】** |
| c | `llama` / `bonsai-2-27b`（8089 直连 + Bearer） | HTTP **200**，首字 **0.376 s**；换 `foo-bar` 也 **200** | **【可用】**（须先 `switch.sh llama`），且**名字可自由改** |
| d | `strata` / `qwen36-35b-a3b-udq4kxl`、`qwen38-flash-next-gyro-s`（8080） | 8080 无监听，**未测** | **【占位—服务未起】** |

两条行动建议（本次**未改任何配置**）：

1. **52k 那条不要删，但要给它加护栏**：它不是 id 写错，而是「档没起」。现役引擎命令行是 `--kv-capacity 40000`，所以 DSH 里选中 52k 必然 502。可用性只在引擎按 `PROFILE=long`（池 51,200、无投机、decode ~32 tok/s）起服时成立。最小改动建议（二选一）：在 DSH 里把这条改名加「（需 PROFILE=long 起服）」标注；或临时注释掉它，避免误选。
2. **llama 那条的 id 可以随便起规范名**（实测 `foo-bar` 也 200），这是它相对 NInfer 的一个好处：可以把名字写成带参数的规范名（如 `bonsai2-27b-ternary-ptq1-262k-llamacpp`）而不必改服务器启动参数。**NInfer 则相反**：`--model-id` 逐字强校验，改 id 必须同时改 `scripts/serve2.sh` 的 `MODELID`。

## 1 主表（逐条实测）

| provider | baseURL | model id（逐字） | GET /v1/models | POST /v1/chat/completions | 首字 s | 判定 | 备注 |
|---|---|---|---|---|---|---|---|
| ninfer | 8081 | `bonsai27b-ptq1-mtp-rk2v4-40k` | 200，列表 = 同 id | **200** | 0.383 / 0.327 / 0.456（三次） | 可用 | 引擎 cmdline 里 `--kv-capacity 40000 --model-id bonsai27b-ptq1-mtp-rk2v4-40k --spec mtp --draft-tokens 4` |
| ninfer | 8081 | `bonsai27b-ptq1-nomtp-rk2v4-52k` | 200（但列表里只有 40k） | **502** | 0.014（立即） | 需改配置·换档 | 网关把引擎 404 包成 502 |
| ninfer（直连对照） | 8091 | `bonsai27b-ptq1-mtp-rk2v4-40k` | 200 | **200** | 0.103 | — | 证明 40k 本身健康 |
| ninfer（直连对照） | 8091 | `bonsai27b-ptq1-nomtp-rk2v4-52k` | 200 | **404** | — | 需换档 | body 见 §3 |
| llama | 8089 | `bonsai-2-27b` | 200（带 key）/ **401**（不带 key） | **200** | 0.376 | 可用（须起 8089） | 列表 aliases=[bonsai-2-27b]、n_ctx=262144、ftype `PTQ1_0 - 1.75 bpw ternary (group 128)` |
| llama | 8089 | `foo-bar`（**故意不匹配**） | 200 | **200** | 0.121 | 名字不校验 | 与上一行同一句回答 ⇒ llama-server 忽略 model 字段 |
| strata | 8080 | `qwen36-35b-a3b-udq4kxl` | 无监听（连接失败） | 未测 | — | 占位—服务未起 | `netstat -ano | grep :8080` 空 |
| strata | 8080 | `qwen38-flash-next-gyro-s` | 无监听 | 未测 | — | 占位—服务未起 | 同上；未为它启动 35 GB 全量模型 |

> 所有请求都带 `temperature: 0`、`reasoning_effort: none`、`max_tokens: 64`、`stream: true`；首字 = 第一个非空 `delta.content` 到达时刻。
> 两个引擎对「用一句话说明你是哪个模型」的**同一句回答**：`我是通义千问（Qwen），由阿里巴巴集团通义实验室独立研发的大语言模型。` —— 这是权重自述口癖，不是配置串味（NInfer 与 llama 用的是同一份 ternary 权重）。

## 2 证据命令与原文

### 2.1 现役引擎到底是哪个档

```text
C:\Project\local_model\engine\ninfer-serve-89.exe C:/Project/local_model/models/bonsai2_27b_ternary_ptq1_native_mtp.ninfer
  --host 127.0.0.1 --port 8091 --model-id bonsai27b-ptq1-mtp-rk2v4-40k --max-context 262144
  --kv-capacity 40000 --kv-dtype rk2v4-e8 --host-kv-mib 6144 ... --spec mtp --draft-tokens 4
  --mtp-attention-window 8 --default-reasoning-effort none --default-max-tokens 8192
```

⇒ 现役 = **40K 池 + MTP**。52K 档（`PROFILE=long`：池 51,200、`--host-kv-mib 2816`、无投机、CUDA graph 可开、decode ~32 tok/s）**未起**。

### 2.2 三个 ID 的实测（窗口原文，JSON 一行一条）

```json
{"base":"http://127.0.0.1:8081/v1","model":"bonsai27b-ptq1-mtp-rk2v4-40k","models_http":200,"models_ids":["bonsai27b-ptq1-mtp-rk2v4-40k"],"http":200,"ttft_s":0.383,"wall_s":0.384}
{"base":"http://127.0.0.1:8081/v1","model":"bonsai27b-ptq1-nomtp-rk2v4-52k","models_http":200,"models_ids":["bonsai27b-ptq1-mtp-rk2v4-40k"],"http":502,"ttft_s":null,"wall_s":0.014,"err":"{\"error\": {\"message\": \"HTTP Error 404: Not Found\"}}"}
{"base":"http://127.0.0.1:8091/v1","model":"bonsai27b-ptq1-nomtp-rk2v4-52k","models_http":200,"http":404,"err":"{\"error\":{\"code\":\"model_not_found\",\"message\":\"model 'bonsai27b-ptq1-nomtp-rk2v4-52k' not found\",\"param\":\"model\",\"type\":\"invalid_request_error\"}}"}
{"base":"http://127.0.0.1:8089/v1","model":"bonsai-2-27b","models_http":200,"models_ids":["bonsai-2-27b"],"http":200,"ttft_s":0.376,"wall_s":0.736}
{"base":"http://127.0.0.1:8089/v1","model":"foo-bar","models_http":200,"models_ids":["bonsai-2-27b"],"http":200,"ttft_s":0.121,"wall_s":0.469}
```

### 2.3 DSH 配置视角的复核（用配置本身驱动，不是我手写 id）

```text
$ python tools/dsh_provider_test.py --config C:/Users/Administrator/.dsh/profiles/desktop/cordis.patch.yml --provider ninfer
[PASS] ninfer base=http://127.0.0.1:8081/v1 model=bonsai27b-ptq1-mtp-rk2v4-40k
   1 models OK  2 nonstream OK HTTP 200 text='2'  3 stream OK HTTP 200 chunks=6 ttft=0.31
   4 tools OK 真吐 tool_call=True  5 unknown fields OK HTTP 200
[SKIP/缺席] ninfer model=bonsai27b-ptq1-nomtp-rk2v4-52k
   DSH 里声明了这个 id，但引擎当前只报：['bonsai27b-ptq1-mtp-rk2v4-40k']
1/2 PASS，1 SKIP/缺席，0 FAIL
```

## 3 ninfer：40k 可用、52k 必然 502 的原因链

引擎对 `--model-id` **逐字强校验**，这条链是：

```
DSH 发 model=bonsai27b-ptq1-nomtp-rk2v4-52k
  → 引擎 8091：404 model_not_found（正文见 §2.2）
  → tools/chat_gateway.py:929 / :954 把上游任何异常统一包成 502
  → DSH 看到 {"error": {"message": "HTTP Error 404: Not Found"}}
```

所以**在 DSH 里看到 502 不等于网关坏了、也不等于引擎挂了**：0.014 秒就失败、且同一时刻 40k 那条 200，就是「id 对不上」的指纹。要分辨，直连 8091 打一次就能看到真 404。

**换档不是换 id**：52k 档要用

```bash
cd /c/Project/local_model && PROFILE=long FORCE=1 GW=1 PORT=8091 MODELID=bonsai27b-ptq1-nomtp-rk2v4-52k bash scripts/serve2.sh
```

（`scripts/serve2.sh` 的 `long` 档 = 池 51,200 / `--host-kv-mib 2816` / 无 `--spec` / `--window 10240`；decode ~32 tok/s。）
注意现役 `scripts/serve2.sh` 的 MODELID 已经用 prod id，`long` 档起服时**必须显式传 MODELID=…-52k**，否则引擎报 40k 的 id，DSH 里选 52k 照样 502。

## 4 llama：不校验 model 名（与 NInfer 相反）

`GET /v1/models`（带 key）：

```json
{"models":[{"name":"bonsai-2-27b","model":"bonsai-2-27b", ...}],"object":"list","data":[{"id":"bonsai-2-27b","aliases":["bonsai-2-27b"],"owned_by":"llamacpp","meta":{"n_ctx":262144,"n_params":27320697856,"ftype":"PTQ1_0 - 1.75 bpw ternary (group 128)"}}]}
```

不带 key → **401**（鉴权是必须的，key 在 `llama8g/bundle/artifacts/api_key.txt`）。
带 key、model 写 `foo-bar` → **200 且回答与 `bonsai-2-27b` 一字不差** ⇒ llama-server 单模型模式下**忽略 model 字段**。

| 引擎 | model 名不匹配时 | 能不能改 DSH 里的 id |
|---|---|---|
| NInfer 8091 | 404 model_not_found（经网关 502） | **不能单改**，必须同步改 `serve2.sh` 的 `MODELID` |
| llama-server 8089 | 200，照常回答 | **可以随便改**，服务器不校验 |

## 5 strata：占位未启用（未测，不臆测）

`netstat -ano | grep :8080` 在 11:09 与 11:15 两次采样都是**空**；按指示没有为它启动 35 GB 级全量模型。
因此 `qwen36-35b-a3b-udq4kxl` 与 `qwen38-flash-next-gyro-s` 两个 id 的真伪**本次未验证** —— 这两个 id 是从上游文档抄来的，**必须以 `strata serve` 起来后 `GET /v1/models` 报的 id 为准**（此前安装期曾观察到 8080 短暂报出过的真实 id 是 `qwen3.8-flash-next`，与这两个占位 id 都不相等）。

## 6 配置 diff

**本次未改动任何配置**（按要求只测不改）。`cordis.patch.yml` 的 sha256 与改动前一致；无 `.bak` 生成。

若后续要落地 §0 建议 1，最小 diff 是（**未 apply**，仅备选）：

```diff
       # 仅当引擎以 52K 池 + 无 MTP 启动时可用（否则选中它同样 404/502）。
       - id: bonsai27b-ptq1-nomtp-rk2v4-52k
-        name: Bonsai 27B Ternary PTQ1 · 无MTP(~32tok/s) · rk2v4-e8 · 池52K
+        name: Bonsai 27B Ternary PTQ1 · 无MTP(~32tok/s) · rk2v4-e8 · 池52K【需 PROFILE=long 起服，现役 40K 档选中即 502】
```

## 7 YAML 校验结果

`python -c "import yaml; yaml.safe_load(open(cfg))"` 通过；顶层是 **list（14 个 plugin 条目）**，`llm-pi-ai` 的 `providers` = 5 个，逐个打印：

```text
providers: ['opencode-go', 'ninfer', 'strata', 'llama', 'wb']
 - opencode-go | baseURL: None                | id=deepseek-v4.1-flash(ctx 1000000/max 384000), longcat-2.5-preview-free(1000000/131072)
 - ninfer      | http://127.0.0.1:8081/v1     | id=bonsai27b-ptq1-mtp-rk2v4-40k(38000/8192), bonsai27b-ptq1-nomtp-rk2v4-52k(50000/4096)
 - strata      | http://127.0.0.1:8080/v1     | id=qwen36-35b-a3b-udq4kxl(32768/4096), qwen38-flash-next-gyro-s(131072/4096)
 - llama       | http://127.0.0.1:8089/v1     | id=bonsai-2-27b(262144/8192)
 - wb          | http://<内网地址已脱敏>:8788/v1 | id=hy4-preview(960000/64000), hy3(192000/64000), deepseek-v4.1-flash(1000000/128000)
ctx/max：ninfer 38000/8192 → DSH 提示上限 29,808 tok（池 40,000 留 10K 余量），与实测一致。
```

## 8 环境还原（已确认）

| 项 | 状态 |
|---|---|
| NInfer 8091 | 已还原：`ninfer-serve-89.exe` PID 16092，`GET /v1/models` 200 |
| 8081 网关 | 已还原且有坑：`switch.sh ninfer` 起来后出现**两个 LISTENING**（旧 22920 + 新 33232，Windows SO_REUSEADDR），已 kill 旧的 22920，现只剩 **33232** |
| llama 8089 | 已停（`switch.sh ninfer` 先 taskkill llama-server.exe，PID 24176） |
| 显存 | 还原后 **7,680 / 8,188 MiB**；llama 在跑时 7,816 MiB |
| 8089 探活 | 000（符合预期，llama 已停） |

## 9 未测项（不拿「可能」当结论）

1. **strata 两个 id 的真伪**：8080 未监听，未起 35 GB 模型 ⇒ 未测。
2. **52K 档实跑速度**：本次未按 `PROFILE=long` 换档（会打断生产），52K 档的 decode ~32 tok/s 与 prefill ~180 tok/s 都是**旧实测**，本次未复测。
3. **llama 的 maxTokens 8192 与真实吞吐**：只发了 64 token 的短问，长输出未测；262K 窗的首读成本见 `reports/llama8g-200K-实测.md`（O(n²)，200K 首读 3.2–6.5 h）。
4. **llama 的 ctx 262144 是否被 DSH 接受**：只验了模型条目能连通，未在 GUI 里真跑 200K 提示（那条要数小时）。

## 10 附件

| 文件 | 说明 |
|---|---|
| `C:/Project/local_model/tools/e2e_model_probe.py` | 本次探针（100 行，纯 stdlib；`--base --model --api-key --max-tokens --timeout`，输出一行 JSON） |
| `C:/Project/local_model/reports/DSH配置与验收.md` | 配置字段含义、id 与 MODELID 耦合、验收脚本用法（前一份报告） |
| `C:/Project/local_model/docs/本地模型清单-给DSH用.md` | 起服命令速查、换档三步、报错对照表 |
| `C:/Project/local_model/tools/dsh_provider_test.py` | 用配置驱动跑六项验收（本次 §2.3 用它复核） |

