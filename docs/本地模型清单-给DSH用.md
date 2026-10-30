# 本地模型清单 · 给 DSH 用（RTX 4060 Ti 8G · 2026-10-30）

> **一句话**：DSH 的模型选择器里能看到 **3 个本地条目** + 2 个云端 provider（共 5 个云端模型），但**这台机器的 8 GB 卡同一时刻只装得下一支本地引擎**——3 个本地条目里，永远只有「当前正在跑的那一档」能用，其余三个点下去必然连不上。判断方式见 §2。
>
> 数据来源：`docs/200K上下文-最终处方-20261030.md`、`docs/DSH接入-本地模型-20261030.md`、`docs/全家桶-地图与最终方案-20261030.md`、`docs/Strata对照-8G能跑多大-20261030.md`、`reports/超池200K-可用性实测.md`、`reports/DSH配置与验收.md`。**标「未验」的格子是真没测过**；标「推算」的是从实测数字算出来的，不是直接读到的。

---

## 1. 模型目录表（DSH 里会出现的条目）

| DSH 里的 model id | 中文别名 | 它到底是什么 | 真实窗口（设备 KV 池） | 实测速度 | 显存 / 内存 | 什么时候选它 |
|---|---|---|---|---|---|---|
| `bonsai27b-ptq1-mtp-rk2v4-40k` | **现役主力**（日常/写代码） | Bonsai2 27B **稠密** ternary，PTQ1 三值量化，权重 5.94 GiB；64 层里只有 16 层带 KV（25,728 B/token）；KV dtype `rk2v4-e8`；投机解码 MTP draft4 / win8 | **40,000**（625 页 × 64 tok） | decode **107.6 tok/s**（计数题，`max` 档 = CUDA Graph 开 + MTP；旧档 97–98）、散文 45.7；prefill **1,091 tok/s @8K**、**969 @37K**（旧档 963）；TTFT ≈19.3 s @19.7K、**≈38 s @37K**（推算） | 峰值 **≈7,291 / 8,188 MiB**（`max` 档，余 ~900；旧档 7,469）；引擎私有内存 14.8 GiB | 默认选它。单请求提示 ≤ ~29.8K（DSH 声明 ctx 38000 − max 8192） |
| ~~`bonsai27b-ptq1-nomtp-rk2v4-52k`~~（**已从选择器移除**：2026-10-30 实测档没起时 0.014 s 即 502，见 §8） | **长文档档**（慢 3 倍） | 同一个 Bonsai2 27B PTQ1，但**关掉投机**（8G 上 MTP 与 CUDA Graph 互斥，关掉 MTP 才腾得出显存），池拉到 51,200 | **51,200**（`PROFILE=long` 口径；id 里 52k 是取整） | decode **32.1 tok/s**（散文 32.2）；prefill 未单测（同池带 MTP 时崩到 ~180 tok/s，属换页） | 峰值 **7,353 MiB** | 要一次贴整本说明书/长代码，能忍 3 倍慢。DSH 声明 ctx 50000 / max 4096 ⇒ 提示 ≤ ~45.9K |
| `Qwen3.6-35B-A3B-UD-Q4_K_XL` | Qwen3.6 小 MoE（**Strata 路线，已装**） | Qwen3.6-**35B-A3B** MoE，`UD-Q4_K_XL` 量化，跑在 **Strata** 引擎上（专家摊主机内存：trunk 4.40 GiB 上卡 + 18.75 GiB 专家在内存） | **1,024**（实测 `READY 1024`；再抬一格就 EngineDied） | prefill **120.9 tok/s**、decode **42.1 tok/s**（`strata/logs/g-BENCH.log` 原文 `bench 2: pp32 120.9 tok/s, tg8 42.1 tok/s`） | 起服后只剩 **1.13 GiB** 显存余量给 KV；引擎私有内存 15+ GiB | 只想验证 Strata 能跑 / 想看它的硬件监控面板。**日常别用**：上下文比现役少 39 倍、prefill 慢 8 倍（§8 表） |
| `Ternary-Bonsai-2-27B-PTQ1_0-mtp-262k` | **第三条路**（llama.cpp 262K） | 同一份 Bonsai2 27B PTQ1_0（1.75 bpw）跑在 **llama.cpp 分叉**（build 10807）上：KV 前 93,696 位置在显存、其后在 pinned RAM 走 PCIe，窗口真到 262,144 | **262,144**（`n_ctx`；`kv tiered` 分档） | 短上下文 decode **56.7 tok/s**（中位）/ 热缓存追问 **96 tok/s**；首读 O(n²)：30K=236 s、60K≈28 min、209K≈3–6 h | 权重 6.39 GB + 峰值 ≈7,798 MiB 自由顯存线自动重算 | 同一份 200K 文档**要反复追问**时：建一次 3–6 h，之后每次 0.9–1.1 s |

**现役档的启用条件（重要）**：现役这一档**开 CUDA Graph**，起服就是 `PROFILE=max`，实际参数是 **`--cuda-graph-allowance-mib 16 --ngram-draft-tokens 0 --prefill-chunk 1536`**。这里有个坑：**allowance 16 + chunk 1536 才是唯一能同时开 CUDA Graph 与 MTP 的组合**；allowance 128 与 chunk 1536 **互斥**（两者差 142 MiB，一起给起不来），所以别照抄「128」。不给 allowance 就退回 `--no-cuda-graph` 旧档，decode 掉到 97–98 tok/s；给了才拿到 107.6。`scripts/serve2.sh:34` 现在写的就是 16 + `--ngram-draft-tokens 0`、CHUNK 1536，与实测一致。**起服后以引擎 banner 与 `nvidia-smi` 峰值（≈7,291–7,459 MiB）为准。**

另外两个 provider 是**云端**、不占这张卡：`opencode-go`（deepseek-v4.1-flash、longcat-2.5-preview-free）与 `wb`（hy4-preview、hy3、deepseek-v4.1-flash）。它们和本地档不冲突。

### 1.1 每个条目怎么起来（一条命令）

| model id | 起服命令（在 `C:/Project/local_model` 下执行） |
|---|---|
| `bonsai27b-ptq1-mtp-rk2v4-40k`（现役，`max` 档） | `PROFILE=max FORCE=1 GW=1 PORT=8091 MODELID=bonsai27b-ptq1-mtp-rk2v4-40k bash scripts/serve2.sh` |
| 同上（旧档，回退用） | `PROFILE=ctx40 FORCE=1 GW=1 PORT=8091 MODELID=bonsai27b-ptq1-mtp-rk2v4-40k bash scripts/serve2.sh` |
| `bonsai27b-ptq1-nomtp-rk2v4-52k` | `PROFILE=long FORCE=1 GW=1 PORT=8091 MODELID=bonsai27b-ptq1-nomtp-rk2v4-52k bash scripts/serve2.sh` |
| `Qwen3.6-35B-A3B-UD-Q4_K_XL`（Strata） | `bash scripts/switch.sh ninfer` 先停 NInfer → `strata/data/terminal/current/bin/strata.cmd serve`（或 `bash scripts/strata-gui.sh` 开桌面版，在界面里选模型）。档文件 `strata/install/strata-q36-*.json`；端口 8080 |
| `Ternary-Bonsai-2-27B-PTQ1_0-mtp-262k`（llama.cpp） | `bash scripts/switch.sh llama`（会自动停 8091；环境 `BONSAI_8GB=1 BONSAI_CTX=262144 BONSAI_PORT=8089 BONSAI_SPARSE=1`） |

`PROFILE` 的含义（`scripts/serve2.sh:30-60`）：`max` = 池 40,000 / 6,144 / **CUDA Graph 开 + MTP draft4/win8 + chunk 1536**（2026-10-30 task-17 极限档）；`ctx40` = 池 40,000 / host-kv 6,144 / draft4+win8 / `--no-cuda-graph`；`fast` = 16,000 / 4,096；`ctx20` = 20,032 / 5,120；`long` = 51,200 / 2,816 / **无投机**；`legacy` = 32,000 / 8,192（已越红线，只做 A/B）。

**`MODELID` 建议始终显式传**：`scripts/serve2.sh:24` 的默认值已从 `local` 改成 `bonsai27b-ptq1-mtp-rk2v4-40k`（2026-10-30 已 apply，`tools/modelid-naming.patch` 是它的存档）。但引擎对 `--model-id` 是**逐字强校验**——起服传什么，DSH 里就必须配什么，否则 404。默认值只覆盖现役档：敲 `PROFILE=long` 又不传 `MODELID` 时，引擎会用 `-40k` 这个名字挂一个 52K 池，DSH 里点 52k 那条照样 404，所以 §1.1 的命令表每条都写了 `MODELID`。

### 1.2 这些数字的出处与空缺

| 数字 | 出处 |
|---|---|
| **107.6 tok/s**、**1,091 tok/s @8K**、**969 tok/s @37K**、峰值 **≈7,291 MiB** | task-17（ninfer-limit）的极限档实测，lead 口头转述；`reports/极限优化-实测.md` **尚未落盘**，出来后以该报告为准 |
| 旧档 97–98 / 45.7 tok/s、963 tok/s @37K、7,469 MiB | `docs/DSH接入-本地模型-20261030.md` 一、三节（`--no-cuda-graph` 档本机实测） |
| 32.1 tok/s、7,353 MiB、`long` 档参数 | `docs/全家桶-地图与最终方案-20261030.md` §3 档位表 + `scripts/serve2.sh:39-41` |
| 194 ms / 19.3 s TTFT、1,022 tok/s @19.7K | 同上 §4 实测性能表 |
| 200K 超池的边界与静默错误 | `reports/超池200K-可用性实测.md`（本文不重复，只给结论：超池区每个引擎进程**只可信一次**） |
| Strata 外部机器速度 | `docs/Strata对照-8G能跑多大-20261030.md`（来源是 B 站视频 + 评论，**外来数据，不当本机结论**） |

**空缺（诚实留着）**：① 52K 无投机档的 prefill 与 TTFT 没单独实测；② Strata 两个制品在本机是**零实测**；③ `reports/极限优化-实测.md`（task-17 的数值扫描）**还没落盘**，现役档的 107.6 / 1,091 / 7,291 三个数字目前只有 lead 的转述，等报告出来以它为准（旧档 97–98 / 963 / 7,469 是已有实测，两条都列在表里，掉速时能对照）。

---

## 2. 换模型 = 停旧引擎 → 起新引擎（没有第二条路）

硬规则来自引擎自己：**同一张卡只允许一个实例**。首次启动会校准并把 device profile 写进 `%LOCALAPPDATA%\ninfer\device-profiles.json`，两个实例互相踩这份文件；更要紧的是显存算不过来——7,291 + 7,353 > 8,188，第二个必 OOM。所以「在 DSH 里换个模型」在物理上等于「换一支引擎」。

### 2.1 三步换档

```bash
# ① 停旧的（引擎 + 8081 网关）
taskkill //F //IM ninfer-serve-89.exe
for pid in $(netstat -ano | grep "127.0.0.1:8081 " | awk '{print $5}' | sort -u); do taskkill //F //PID $pid; done

# ② 起新的（以长文档档为例）
cd /c/Project/local_model
PROFILE=long FORCE=1 GW=1 PORT=8091 MODELID=bonsai27b-ptq1-nomtp-rk2v4-52k bash scripts/serve2.sh

# ③ 等就绪（约 4–8 s；慢是因为在校准 device profile）
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8091/v1/models   # 要 200
```

> 上面两条 `taskkill` 是**给你手动换档用的**，不要放进自动化脚本：压测/实验期间杀引擎会把别人的读数作废。

### 2.2 选择器会显示 3 个本地条目，只有 1 个能用

provider 是配置里写死的，选择器不会自动灰掉连不上的条目。所以点之前先确认「现在跑的是哪一档」：

| 现象 | 说明 |
|---|---|
| `curl 127.0.0.1:8091/v1/models` 返 200，`id` = X | 能用的只有 id = X 那一条 |
| `nvidia-smi` 里没有 `ninfer-serve-89.exe` 占显存 | 本地档全都没起（云端 provider 不受影响） |
| 8092 被别的进程占着 | 有人在 8092 跑实验（如压测），**卡已被吃掉**，8091 起不来 |

### 2.3 选错模型会报什么错（照这个表认）

| 你怎么点的 | 实际发生 | 你会看到 | 怎么确认 |
|---|---|---|---|
| 选了**没在跑**的本地档（最常见） | 请求打到没人监听的端口，连接被拒 | 连接失败 / 请求出错；`tools/verify_all.sh` 里是 `HTTP 000` + `URLError(ConnectionRefusedError(10061, ...))` | `curl 127.0.0.1:8091/v1/models` → 000 |
| 引擎在跑，但 **id 与引擎 `--model-id` 不一致** | 引擎拒答 | 直连 8091：**HTTP 404**，体 `{"error":{"code":"model_not_found","message":"model 'X' not found","param":"model","type":"invalid_request_error"}}`；走 8081 网关则变 **502** | `curl /v1/models` 拿真实 id，与 YAML 的 `models[].id` 逐字比 |
| 提示**超过设备 KV 池** | 引擎照答，但中段静默丢失 | **HTTP 200 + 看似合理的错答案**；日志 `prompt exceeds the resident Device KV pool ... Treat every answer to this request as unverified` | `grep -c "prompt exceeds the resident Device KV pool" logs/*.log` > 0 就别信这次答案 |
| 池调太大起不来 | 起服即拒 | 引擎直接退出；日志 `runtime reservation requires ... bytes, but only ... available` | 别超 40,000（52,000 能起但 prefill 崩到 180） |

> 网关为什么把 404 变 502：`tools/chat_gateway.py` 把上游非 2xx 当网关错误转出去。**看到 502 先查 id，不要先怀疑引擎挂了**。

### 2.4 为什么「把 host-kv 开大」换不来可复问的超池（Windows 专有坑）

`--host-kv-mib` 在 Windows 上**确实是真 pinned 内存**（`src/core/arena.cu:657-679`：`cudaHostAlloc(&ptr, size_bytes, cudaHostAllocPortable)`），但 WDDM 把这块 pinned 分配**映射进 GPU 地址空间、记账到显卡头上**，所以运行时在第一次分配前就把请求**钳到 `(free VRAM − 1 GiB) / 2`**——它不能「先试再退」，因为一次失败会毒化进程内之后所有分配（`docs/maintainer/launcher-profiles.md:410-419`）：

```
profile                              free after startup   pinned host KV
-----------------------------------------------------------------------------
qwen38-27b tuned (MTP profile)              1.59 GiB           302 MiB
qwen36-35b-a3b tuned                     184-344 MiB           0 -- none at all
```

本机实测吻合：我们传 `--host-kv-mib 6144`，引擎日志里 `[ring] budgets: ... backend_pages=4 ... backend_capped=1` 长期只有 **4–7 页**（每页 64 token，即 256–448 token）——真正钉住的只有几百 MiB，不是 6 GiB。

**结论：靠加 host-kv 换「超池可复问」在 Windows 上走不通。** 这就是 `reports/超池200K-可用性实测.md` 里「每个引擎进程只可信一次」的物理层解释：能分页到 host 的部分本来就极少（连 8,192 token 的证据预算都装不满），超池请求只能靠淘汰设备页让位，淘汰掉的 KV 不可恢复，于是同一进程里的第二个超池请求必然在「旧打分表 + 幽灵块」上做选择。Linux 上这个 flag 是真的（8 GiB 全钉），所以这个坑只在 Windows 出现。

---

## 3. 为什么叫 `bonsai27b-ptq1-mtp-rk2v4-40k`

这个 id 把「这一档到底跑的是什么」按五段编码，扫一眼就能和截图里的档位对上：

| 段 | 含义 | 取值说明 |
|---|---|---|
| `bonsai27b` | **模型族 + 尺寸** | Bonsai2 **27B** ternary（三值）蒸馏版；稠密结构，27B 权重每 token 全部参与 |
| `ptq1` | **量化档** | Post-Training Quantization **PTQ1**（三值）。权重落到 **5.94 GiB** —— 8 GB 卡唯一装得下的制品 |
| `mtp` / `nomtp` | **投机解码** | `mtp` = 开 MTP 投机（draft 4 / 窗口 8，接受率 ~80%，换来 **107.6** tok/s（CUDA Graph 开）/ 97–98（关））；`nomtp` = 关掉（8G 上 MTP 与 CUDA Graph 互斥，关掉才能把池拉到 51,200，代价是 decode 掉到 32） |
| `rk2v4` | **KV 缓存 dtype** | Key 2 bit / Value 4 bit，`e8` = 8 bit 指数。每页 64 token，边际约 **0.836 MiB/页**（这套数字决定池能开多大） |
| `40k` / `52k` | **设备 KV 池大小** | 这才是**真实窗口**。引擎 `/v1/models` 报的 `262144` 是 `--max-context` 的逻辑上限，**不是能装多少**；装不下的部分要么分页到 host（超池，不可信），要么干脆没有 |

所以 `bonsai27b-ptq1-mtp-rk2v4-40k` 读作「Bonsai 27B · PTQ1 三值 · 开 MTP 投机 · KV=rk2v4-e8 · 40K 池」。改任何一段都是**另一套引擎启动参数**，也就必须是**另一个 model id**——引擎按 `--model-id` 逐字校验，名字对不上就 404。

反面教材就是旧配置：provider `local`、displayName `Local`、model id `local`。换成 52K 档、换成 Strata 都还叫 `local`，看截图分不出是哪一套，也分不出这次开没开 MTP。

---

## 4. Strata 这一条：已装、实测能起，但只能当备选（2026-10-30 更新）

引擎与模型都已落到 `C:/Project/local_model/strata/`（共 112 GB），本机实测能起：`READY 1024`、`bench 2: pp32 120.9 tok/s, tg8 42.1 tok/s`。所以选择器里那条**不再是占位**，而是实测口径：id `Qwen3.6-35B-A3B-UD-Q4_K_XL`、ctx 1,024、maxTokens 512。

| 项 | 现在（实测/已定） | 什么时候还要改 |
|---|---|---|
| `strata.baseURL` | `http://127.0.0.1:8080/v1` | 只要 `strata serve --port` 不改就不用动 |
| model id | `Qwen3.6-35B-A3B-UD-Q4_K_XL` | 换了档文件（Gyro-S 等）就以 `curl 127.0.0.1:8080/v1/models` 报的为准 |
| `contextWindow` | **1,024**（实测上限：再抬一格 EngineDied，28 次尝试全灭） | 若换更省显存的档且实测能开更大，按实测改 |
| `maxTokens` | 512（ctx 1024 已被 KV 吃满，留一半给输出） | 同上 |

旧的两条占位（`qwen36-35b-a3b-udq4kxl` ctx 32768 / `qwen38-flash-next-gyro-s` ctx 131072）**已从配置删除**：那是没实测时写的空想数字，留着只会让人以为本机能开 32K–128K。

为什么它当不了主力：见 `docs/两条路终极对照-20261030.md`（上下文 1,024 vs 40,000；prefill 120.9 vs 1,001 tok/s；decode 42.1 vs 107）。它真正的价值是**桌面版里的硬件监控面板**（GPU 利用率 / 显存拆分 / 功耗 / 温度 / CPU）——那块面板不占显存。

**另一档（Gyro-S）已实测**：125B 级 MoE（TQ1_0，58.5 GB）**上下文 32,768 能起**（8K/16K/32K 三档全 READY），但 decode 只有 **19.0–24.4 tok/s**、`strata.exe` 工作集 **21.3 GB**、7.4k 汉字提示一轮**读盘 368 GB**、显存只剩 719 MiB。想切到这档就按配置里那段注释改 id/ctx（读数见 `reports/Strata-GyroS-极限实测.md`）。定位：**长上下文备胎**，不顶替 NInfer。

改完 `C:/Users/Administrator/.dsh/profiles/desktop/cordis.patch.yml` 后必须 **DSH 菜单 →「重启应用与宿主」**（只刷页面不够，配置在宿主启动时读入）。

---

## 5. 验收三步（每次起完服 / 改完配置之后）

> 脚本内部跑 **6** 步（显存 → 8091 → 8081 → DSH 视角 → 六项行为 → Strata），但**你要做的只有 3 件事**：跑脚本、在 DSH 里发一句话、看日志。

```bash
cd /c/Project/local_model
bash tools/verify_all.sh          # ① 一条命令：显存 → 8091 → 8081 → 六项行为 → Strata（在线才测）
```

② **在 DSH 里选模型、发一句话**（例如「你是谁，本地跑的吗」）。能正常吐字 = 端到端通了；这一步脚本替不了，因为验的是 DSH 自己的 SSE / tools / 凭据链路。

③ **看日志**：`logs/verify-<时间戳>.log`（同时有一份 `.json` 存完整请求与响应体）。

| 结果 | 含义 |
|---|---|
| 退出码 0、`验收通过：0 FAIL` | 六步全过，能用 |
| FAIL 在 `2/6` 或 `3/6` | 引擎/网关没起或端口不对（`HTTP 000` = 连接被拒） |
| FAIL 在 `4/6` | DSH 视角对不上：`4/6` 只比「YAML 声明的 id vs 引擎真实 id」，缺席档按 SKIP 处理，不算 FAIL |
| FAIL 在 `5/6` 且日志是 `model_not_found` | id 与引擎 `--model-id` 不一致 |
| FAIL 在 `5/6` 且日志是 401 / `unauthorized` | `.credentials.yaml` 里的 `LOCAL_LLM_KEY` 丢了 |
| `6/6` 写「跳过（不算 FAIL）」 | Strata 没起，正常；装了之后应自动变实测 |

`tools/verify_all.sh` 的判据只有一句：**全 PASS 才算验收通过**；任何 FAIL 都会把原始响应体打出来，不用自己复现。

---

## 6. 一句话备忘（贴在选择器旁边）

1. 卡是 8,188 MiB，一支引擎就吃掉 7,400+；**换模型 = 换引擎 = 停旧起新**。
2. DSH 里能选 3 个本地条目，**只有 `curl 127.0.0.1:8091/v1/models` 报的那个 id 能用**（llama 例外：它不校验名字）。
3. 名字里的 `mtp`/`nomtp` 与 `40k`/`52k` 就是速度与窗口的旋钮：`40k+mtp` 快，`52k+nomtp` 长。
   现役快档靠 **CUDA Graph**：起服要 `PROFILE=max`，即 `--cuda-graph-allowance-mib 16 --ngram-draft-tokens 0 --prefill-chunk 1536`（allowance 128 与 chunk 1536 互斥，别混搭），否则掉回 97–98 tok/s。
4. 提示别超池：现役档 ≤ ~29.8K，长文档档 ≤ ~45.9K；超了引擎不报错，只打一条 `unverified` 警告。
5. 200K 不是这一档的事：`reports/超池200K-可用性实测.md` 的结论是「每个引擎进程只可信一次」，要反复问 200K 得换卡或换 Strata。**加 `--host-kv-mib` 也没用**：Windows/WDDM 会把 pinned 分配记到显卡账上、并把它钳到 `(空闲显存 − 1 GiB)/2`，实测只钉住 4–7 页（§2.4）。

---

*本文只描述「怎么选、怎么起、怎么验」；各档的边界实测与引擎 bug 证据见 `reports/超池200K-可用性实测.md` 与 `reports/DSH配置与验收.md`。*
---

## 7. 新增第三条路：llama.cpp 262K（8089，与 NInfer 互斥）

DSH 选择器里叫 **Bonsai · llama.cpp 262K**，模型 id **`Ternary-Bonsai-2-27B-PTQ1_0-mtp-262k`**（`n_ctx 262144`、PTQ1_0 1.75 bpw、MTF/lookup 32；llama-server 不校验 model 名，名字只为自解释）。起服/停服一律走：

```bash
bash C:/Project/local_model/scripts/switch.sh llama    # 起 8089（自动停 8091）
bash C:/Project/local_model/scripts/switch.sh ninfer   # 起 8091+8081（自动停 8089）
bash C:/Project/local_model/scripts/switch.sh status   # 看谁在跑
```

- **要 Bearer key**（与 NInfer 不同）：key 在 `llama8g/bundle/artifacts/api_key.txt`，已写进凭据 `LLAMA_API_KEY`。
- **关思考要显式带** `"reasoning_effort": "none"`，否则默认 `effort=medium`。
- **代价**：首读 O(n²)（干净进程 30K=236 s、60K≈28 min、100K≈1 h、209K≈3–6 h）；**收益**：建好之后每次追问 0.9–1.1 s（前缀全命中、decode 96 tok/s），窗口真到 262,144。
- 操作口径与排错：`docs/llama262k-使用说明-20261030.md`；实测报告：`reports/llama8g-200K-实测.md`。
- `tools/verify_all.sh` 已适配：8089 没在跑时自动 `--exclude-provider llama`（不再误判 FAIL）。

---

## 8. 2026-10-30 这次改了什么（命名三规则 + 端到端验收）

### 8.1 命名三规则（用户定的，改配置必须遵守）

1. **原名优先**：名字里要看得见它是什么模型（`Bonsai 27B Ternary PTQ1`、`Qwen3.6-35B-A3B`），不起代号。
2. **可以简化，但不许简化成 `local`**：5 个 provider 摆在一起时 `local` 等于没名字。
3. **指标参数不能删**：量化（`PTQ1_0` / `rk2v4-e8` / `UD-Q4_K_XL`）、投机（`mtp draft4/win8`）、窗口（`40K` / `262K` / `1K`）要留在名字里。

### 8.2 落盘的三处改动（文件 `C:/Users/Administrator/.dsh/profiles/desktop/cordis.patch.yml`，备份 `.bak-20261030031405`）

| provider | 改前 | 改后 | 为什么 |
|---|---|---|---|
| ninfer | 两条 model（40k + 52k） | **只留 40k 一条** | 52k 那条实测 0.014 s 就 502（上游 `404 model_not_found`）：现役引擎是 `--kv-capacity 40000 --model-id …-40k`，**换档不是换 id**。换档命令写进注释 |
| llama | id `bonsai-2-27b` | id **`Ternary-Bonsai-2-27B-PTQ1_0-mtp-262k`** | llama-server 单模型模式**不校验** `model` 字段（拿 `foo-bar` 试也 200、回答一字不差），所以名字可以按规则自解释 |
| strata | 两条占位（ctx 32768 / 131072） | **一条实测** `Qwen3.6-35B-A3B-UD-Q4_K_XL`，ctx **1,024** / max 512 | 引擎已装且实测上限就是 1,024 cell；摆 32K/128K 是假数据 |

> 配置是**宿主启动时读入**的：改完必须 **DSH 菜单 →「重启应用与宿主」**，只刷页面不生效。

### 8.3 端到端验收（`tools/e2e_model_probe.py`，报告 `reports/DSH-本地模型端到端实测.md`）

| provider / model id | HTTP | 首字 | 判定 |
|---|---|---|---|
| ninfer · `bonsai27b-ptq1-mtp-rk2v4-40k` | **200** | 0.383 / 0.327 / 0.456 s（三次） | **可用**（生产档） |
| ninfer · `bonsai27b-ptq1-nomtp-rk2v4-52k` | **502**（0.014 s 立即失败） | — | 档没起；**已从选择器删除** |
| llama · `bonsai-2-27b`（旧名） | **200** | 0.376 s | 可用（须先 `switch.sh llama`） |
| llama · `foo-bar`（故意错名） | **200**，同答案 | 0.121 s | 证明 llama 不校验名字 |
| strata · 两条占位 id | 8080 无监听 | — | 当时未测；现已改实测口径 |

**502 的指纹**：0.014 s 立即失败 + 同一时刻 40k 仍 200 ⇒ 是「model id 与引擎 `--model-id` 不一致」。网关 `tools/chat_gateway.py:929/:954` 把上游 404 统一包成 502，别看到 502 就以为服务挂了。
**另一条相反**：llama 的 `/v1/models` 不带 key 返回 **401**，所以 `LLAMA_API_KEY` 必须在，key 在 `llama8g/bundle/artifacts/api_key.txt`。

### 8.4 现在选择器该选谁

| 想干什么 | 选哪条 | 起服 |
|---|---|---|
| 日常问答 / 写代码（提示 ≤ 29.8K） | **`bonsai27b-ptq1-mtp-rk2v4-40k`** | `bash scripts/switch.sh ninfer` |
| 一次贴很长的文档（≤ 45.9K），能忍 3 倍慢 | 换档：52K + 无投机 | `PROFILE=long MODELID=bonsai27b-ptq1-nomtp-rk2v4-52k FORCE=1 GW=1 PORT=8091 bash scripts/serve2.sh`（改完 DSH 里仍没有这条 model，属预期） |
| 同一份 200K 文档反复追问 | **`Ternary-Bonsai-2-27B-PTQ1_0-mtp-262k`** | `bash scripts/switch.sh llama`（首读 3–6 h，之后 0.9–1.1 s） |
| 想看硬件占用 / 试 Strata | **`Qwen3.6-35B-A3B-UD-Q4_K_XL`** | 先 `switch.sh ninfer` 停 NInfer → `bash scripts/strata-gui.sh` 或终端 `strata serve` |

三条本地路**互斥**（一张 8 GB 卡），所以任何时刻只有当前跑的那条能通。


---

## 9. 新增 provider `ninfer-long`（8086 超池分片注入，2026-10-30 13:30）

给「想问 150K–200K 的长文」用。它不是新引擎，是 `tools/longctx_proxy.py` 起的一个 OpenAI 兼容门面：

- 估 token ≤ 池 85%（现在 61,200）→ **原样直通** 8091，和 `ninfer` provider 完全等价；
- 超过 → 按行切 ≤26,000 token 的片，逐片「只摘相关原文」，再用摘录合成一次作答；每片 ≤ 池 ⇒ 每片都可信。
- 回答第一行会写「（超池分片注入：原文约 N token > 引擎池 72000，已切成 M 片…）」——**不会假装是单次推理**。

| model id | ctx | 实测（8 针 fixture） |
| --- | --- | --- |
| `bonsai27b-ptq1-nomtp-rk2v4-shard200k` | 200,000（覆盖 150K） | 150K：173.2 s / 8/8 · 200K：231.2 s / 8/8 |

> 2026-10-31 整理：原来 150K 与 200K 是两条 model，其实同一个代理、同一条路径，150K 条目删掉，只留 200K（DSH 只会拒绝超过 ctx 的提示）。

起服两步（顺序不能反）：

```bash
bash scripts/switch.sh long72    # 引擎：池 72,000 / 无 MTP / rk2v4-e8
bash scripts/longctx.sh start    # 代理：127.0.0.1:8086；停用 bash scripts/longctx.sh stop
```

`tools/verify_all.sh` 已适配：8086 没在听时自动把 `ninfer-long` 从验收里排除（不会误报 FAIL）。
代理启动时带 `--advertise ...shard150k,...shard200k`，所以 `/v1/models` 会同时列出引擎 id 和这两个声明 id —— 否则 `tools/dsh_provider_test.py` 按「声明 id 不在 /v1/models 里」判缺档。实测 `--provider ninfer-long` ⇒ **2/2 PASS**（非流式 0.16 s / 流式 ttft 0.51 s / tools OK）。
重启代理后复跑 150K 端到端：**169.8 s，8/8**，`x_longctx={shards:8, est_tokens:210141}`。

单遍真读那档（llama，2026-10-30 13:37）：CTX 155,648 + cells 自动 ⇒ **151,873 token / 268.3 s / 8/8**，decode 12.6 tok/s。

---

## 10. 本机控制台（网页，替代 Strata 那个面板）

```bash
bash scripts/console.sh start      # 起服务，然后浏览器开 http://127.0.0.1:8090
bash scripts/console.sh status     # 看有没有在跑
bash scripts/console.sh stop       # 关掉
bash scripts/console.sh open       # 起服务并直接开浏览器（等价双击仓库根目录的 控制台.cmd）
```

面板能干什么：

- **看**：显存占用条 / GPU 利用率 / 温度 / 功耗 / 引擎与 llama 各自的 model id / 8081 网关与 8086 代理在不在 / 进程与 RSS（含代理的 python）/ 当前档位。
- **一键换档**：`起 40K 日常档`、`起 72K 长文档档`、`起 llama.cpp 262K`、`停掉引擎`；以及 `起/停分片代理`。
- **看 DSH 那 4 个本地条目现在哪条能用**（表里直接写「需要哪个引擎」+ 绿/红）。
- **看日志尾巴**：serve-switch-*.log / llama8g-launch.log / longctx-8086.log 下拉切换。

实现：`tools/console.py`（纯标准库，只监听 127.0.0.1:8090）；动作就是去跑 `scripts/switch.sh` 与 `scripts/longctx.sh`，输出落 `logs/console-<动作>.log`，**不另造一套启停逻辑**。

两个注意：① 8 GB 卡一次只能一个引擎，换档时面板会先变红再变绿，约 15 s；② 起 40K 档时分片代理仍在跑，但它会自动把 model 名改写成「引擎此刻真实的 id」，所以不会 404（代理已按 5 s 缓存探测引擎 id）。

**为什么不能干脆让引擎自己读 150K**：prompt > 池时引擎会丢提示词的**中间段**，只打一行 warning（30 s 节流），HTTP 200 给一个看起来正常的错答案。实测 1.31× 就掉 1/8 针，3.17× 全丢。单遍上限池 88,000（8/8），再往上显存算术不成立。
### 10.1 20261031 界面重做（亮色 · 四卡说明书 · 待起态）

改成了亮色纸感（`--bg:#F5F4F1`、白卡片、近黑主按钮），一屏读得完。三处结构变化：

1. **顶部「当前正在跑」**：只有一档在跑，所以这里只显示那一档 —— 大档名 + 真实 model id + 三块指标（窗口/生成速度/首字延迟），右边直接给换档按钮。
2. **中间「四条路」= 四张卡片，每张都是一页小说明书**：一句话卖点 → 上下文刻度条（满刻度 262,144，一眼看出 38K/80K/200K/262K 的相对大小）→ 五行硬指标（上下文·生成·首字·显存·怎么起）→ **代价**一行 → ✓ 适合 / × 别用 → 按钮 + DSH 该选哪个 id。
3. **底部** 日志尾巴（折叠，出问题才看）+ 读数出处脚注（每条数字都指回 reports/ 里的实测文件）。

四张卡的读数（都是这台机器实测，不是估的）：

| # | 档 | 窗口 | 生成 | 首字 | 显存 | 一句话 |
|---|---|---|---|---|---|---|
| 01 | 40K 日常档（池 40,000 · MTP draft4） | 38,000 | 41.5–107 tok/s | 0.2–0.5 s（24K 提示 23 s） | ≈7,533 MiB | 问答/写代码/读几页，最快 |
| 02 | 72K 长文档档（池 72,000 · 关 MTP） | 80,000 | ≈31 tok/s | 0.3 s（prefill ≈1,000 tok/s） | ≈7,301 MiB | 几万字一次读完再答 |
| 03 | llama.cpp 262K | 262,144 | 12.6 tok/s（长文） | 150K 首读 268 s | ≈7,798 MiB | 一份 15 万字通读后全局归纳 |
| 04 | 超池分片 150–200K（72K 档 + 8086） | 200,000 | 整篇 170–211 s | 首段 ≈26 s | ≈7,301 MiB | 超长文只要「里面写了什么」 |

交互细节：点按钮后按钮立刻变 `◌ 正在起…` 并禁用，顶部横条显示「正在执行：切到 40K · 已等 N 秒」，等状态真的翻绿才恢复（状态每 2 s 拉一次 `/api/status`）。

改 UI 只动 `tools/console_page.py`（前端模板 `PAGE`），后端在 `tools/console.py`；每档的文案（`name/sub/headline/ctx/speed/ttft/vram/need/cost/yes/avoid/dsh`）都在后端 `PROFILES` 里改，不用碰 HTML。
