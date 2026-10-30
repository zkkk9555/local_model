# sm_120a 8GB 工具集侦察报告（AAANDYYY-A/ninfer-sm120a-8gb-toolkit）

- 侦察员：sm120a-scout（共享任务 task-7）｜日期：2026-10-30（Asia/Shanghai）
- 对象：<https://github.com/AAANDYYY-A/ninfer-sm120a-8gb-toolkit>
- 落地副本：`tmp/scout/ninfer-sm120a-8gb-toolkit`（HEAD `7625917`，main，37 个受控文件，619 KB）
- 本机基线：RTX 4060 Ti 8G（sm_89）+ `repos/` 只读 + **未启动任何引擎实例**（8091/8081 正在服务用户；全程只做读文件/git/二进制字节扫描，未执行 exe）
- 引用格式：仓库内相对路径 + 行号，均指本报告落地副本；我方文件用绝对路径

---

## 0. 存在性核验（不是 404，先给证据）

全部经代理 `http://127.0.0.1:7897`：

```
$ curl -sI https://github.com/AAANDYYY-A/ninfer-sm120a-8gb-toolkit
HTTP/1.1 200 Connection established
HTTP/1.1 200 OK
Date: Thu, 29 Oct 2026 23:21:55 GMT
Content-Type: text/html; charset=utf-8
Strict-Transport-Security: max-age=31536000; includeSubdomains; preload
```

```
$ git ls-remote origin
76259178042c7a5a695d2b506f29e01e21b14507	HEAD
76259178042c7a5a695d2b506f29e01e21b14507	refs/heads/main
00de6aa7b8d7100b6e532a6449930c14d8f52086	refs/tags/engine-sm120a-20261002

$ git log --format="%h %ad %s" --date=short
7625917 2026-10-03 Sync the six launcher tiers (two redundant flags removed), speed test tooling, and the audited README
66216e9 2026-10-03 Add the API usage dashboard (engine request log + stats port)
cf4b072 2026-10-03 LAN serving: firewall rule verified via registry, add agent-lan.bat and the LAN verification record
b124763 2026-10-03 NInfer sm_120a deployment toolkit for an 8 GB RTX 5060 (redacted, public)
```

`api.github.com` 在本机 403 限流（未用 REST，故无 star/issue 数）；网页 HEAD 与 git 协议均正常。

---

## 1. ①这仓库是什么

**一句话：一份「RTX 5060 8GB 上把 NInfer sm_120a 引擎跑起来」的部署工具集 + 逐轮实验回执，不含引擎与模型。**

原文（`README.md:3-4`）：

> 本仓库**只包含我们自己写的脚本、文档与实验记录**，用于把一台 8 GB 显存的机器（NVIDIA GeForce RTX 5060，compute capability 12.0）跑通 **NInfer `sm_120a` 引擎包**（PTQ1_0 档）。

不含什么（`README.md:8-16`）：`engine\ninfer-serve-120a.exe` + 9 个 DLL（1,901 MiB）、`models\bonsai2_27b_ternary_ptq1_native_mtp.ninfer`（6,098 MiB，6,394,697,216 B，sha256 `5C4486C8…E21B8`）。Release `engine-sm120a-20261002` 另存 engine/ 的 11 个文件（1.86 GiB）作备份。`.gitignore` 逐项排除 `engine/`、`models/`、`*.ninfer`、`*.exe`、`*.dll`、`api-key.txt`、`logs/`、`kvdisk/`。

内容分四类（`git ls-files`，37 项）：

| 类 | 文件 | 作用 |
|---|---|---|
| 启动器 6 档 | `start-ptq1-mtp-8gb.bat` / `-lan.bat` / `-fast.bat` / `-lan-bigctx.bat` / `-lan-1m.bat` / `-diskkv.bat` | 每档只差几个旋钮（`README.md:25-34`） |
| 客户端 | `ninfer-chat.py` + `chat-web.bat`（本地聊天页 + 同源代理 + 交付护栏 + max_tokens 钳制）、`ninfer-cli.py` + `chat-cli.bat`、`agent/agent-min.py` + `agent.bat` / `agent-lan.bat`、`usage-dashboard.py` + `usage.bat`（8098 看板） | 引擎只有 OpenAI API、无网页、无 CORS（`README-聊天怎么用.md:3-4`） |
| 测速 | `test-speed.bat` + `tools/speedtest.py` | 发「数数字」语料，打印引擎自报 timings |
| 记录/文档 | `records/*`（部署回执、严格 argv 运行 #01、隔离实验、手册落地、LAN 验证、探针 bat、模型下载脚本）、`docs/*`（换设备部署指南、手册落地记录）、`demos/` | 每条读数都附引擎控制台原文 |

**质量信号（值得学的地方）**：`README.md:46-58` 是「参数审计」——默认值全部取自引擎 `--help`，删掉了与默认逐字相同的 `--prefill-chunk 1024`、`--max-concurrency 1`；`records/receipt-ptq1-8gb-deployed.md:42-52` 是单旋钮隔离实验表（每行只改一个旋钮，给出 engine 要求字节 / 可用字节 / 结果）；各 `receipt-*.md` 末尾都有「未做（显式声明，不用推断顶替）」清单。

**两处内部不一致（如实登记）**：
1. `README-聊天怎么用.md:111` 仍写「回答上限…最大 32768」，与 `README-聊天怎么用.md:63-69` 的「钳到 4096」冲突（文档漂移，代码是 4096）。
2. `records/receipt-ptq1-8gb-deployed.md:143` 写 “host KV **pinned** 16.0 GiB”，而启动器同时设 `NINFER_HOST_PAGEABLE=1`（pageable，见 `start-ptq1-mtp-8gb.bat:73`）——措辞互相矛盾，原文照登，未深究。

---

## 2. ②对 8GB 卡宣称的上下文窗口 + 靠什么拿到

### 2.1 六档表（`README.md:27-34`，逐字转写）

| 启动器 | 主机池 | 逻辑上下文 | 解码 | 监听 | 统计口/请求日志 |
|---|---|---|---|---|---|
| `start-ptq1-mtp-8gb.bat` | 16 GiB | 256K | draft 4 | 127.0.0.1 | 无 |
| `start-ptq1-mtp-lan.bat` | 16 GiB | 256K | draft 4 | 0.0.0.0 + API key | 有（基线） |
| `start-ptq1-mtp-fast.bat` | 16 GiB | 256K | **draft 12 + fast-prefill** | 同上 | 有 |
| `start-ptq1-mtp-lan-bigctx.bat` | 24 GiB | **768K** | draft 4 | 同上 | 有 |
| `start-ptq1-mtp-lan-1m.bat` | 28 GiB | **1M** | draft 12 + fast-prefill | 同上 | 有（「推荐日常」） |
| `start-ptq1-mtp-diskkv.bat` | 28 GiB | 1M | draft 12 + fast-prefill | 同上 | 有 + 磁盘 KV 层（64 GiB，跨重启存活） |

即：**8GB 卡上宣称 256K 起步，最大 1M 逻辑上下文**（主机内存够的前提下）。

### 2.2 凭什么（三条机制 + 一条算术规则）

1. **逻辑上下文与设备池解耦**。`--max-context` 只是单序列逻辑上限；`--kv-capacity` 是设备（VRAM）池。规则原文（`README.md:36-37`）：

> **容量规则**（引擎启动时强制，教程 §2）：`主机池页数 + 设备池页数 ≥ 逻辑上下文页数`，页 = 64 token；
> 本 artifact 的主机开销实测 **25.12 KiB/token**（`host_kv_page_group_bytes = 1,646,592 B / 64 token`）：

   `README.md:39-42` 的换算：`262144 → 6.28 GiB`、`524288 → 12.56 GiB`、`786432 → 18.84 GiB`、`1048576 → 25.12 GiB`、`2097152 → 50.25 GiB（本机不可行）`。
2. **主机池是「预算」不是「物理钉住」**。`start-ptq1-mtp-lan-1m.bat:30`：`NINFER_HOST_PAGEABLE=1` ⇒ host KV 属 pageable 记账（只记在 commit 上）；实测 24 GiB 预算只占 **2.49 GiB** 物理（`start-ptq1-mtp-lan-bigctx.bat:32-35`），被拒就退 24576。
3. **放不进设备池的 KV 留主机、按需经 PCIe 搬回**——这既是他们要的长上下文，也是他们自己写明的**减速**来源（`start-ptq1-mtp-lan-bigctx.bat:25-30`）：

> **它不会让解码更快**；放不进 8192 设备池的 KV 留在主机 RAM、按需经 PCIe 搬回，上下文越长每步搬得越多。

**具体参数（可直接抄的那一组）**——`start-ptq1-mtp-8gb.bat:100-106` 全文 argv：

```
"%ENGINE%" "%MODEL%" ^
  --host 127.0.0.1 --port 8095 --model-id qwen3.8-27b ^
  --max-context 262144 --kv-capacity 8192 --kv-dtype k8v4 --host-kv-mib 16384 ^
  --spec mtp --draft-tokens 4 --no-cuda-graph ^
  --default-max-tokens 4096 --default-reasoning-effort none ^
  --max-shared-prefixes 0 ^
  --presence-penalty 0 --temperature 0.7 --top-p 0.9 --top-k 20
```

环境变量六件套（`start-ptq1-mtp-8gb.bat:70-75`）：`NINFER_KV_WINDOW=16384`、`NINFER_KV_RETRIEVE=8192`、`NINFER_KV_RING=1`、`NINFER_HOST_PAGEABLE=1`、`NINFER_KV_REUSE_HOSTBACKED=1`、`NINFER_TERNARY_PTQ1_FAST=1`。

### 2.3 三条「不能删」的参数（`README.md:49-55`）

| 参数 | 引擎默认 | 为什么保留（原文数字） |
|---|---|---|
| `--kv-capacity 8192` | 默认 = `--max-context`（1M！） | 删了池变 1M token，8GB 装不下 |
| `--no-cuda-graph` | CUDA Graph **默认开** | 关掉把运行时预留从 `1,863,978,752` 降到 `1,010,437,888` 字节；否则启动即被拒 |
| `--default-max-tokens 4096` | 8192 | 池只有 8192；手册 §1-11 要求 `max_tokens ≤ 池`，客户端要 32,000 会触发 worker 崩溃 |

启动成功时引擎原文（`records/receipt-ptq1-8gb-deployed.md:142`）：
`capacity | KV 8,192 tokens, k8v4, explicit | pages 128/4,096 | runtime 710.0 MiB | free 218.5 MiB`。

### 2.4 一个很硬的实测结论（对我们最有用的一条）

`records/receipt-ptq1-run01-strict-argv.md:79-85`（每行只改一个旋钮）：

> 1. `--host-kv-mib` 16384 → 1024：预留**完全不变** ⇒ 主机池页表不占这 1.31 GiB。
> 2. `--max-context` 262144 → 32768（1/8）：预留只降 28,672 B ⇒ 逻辑上下文不是驱动项。
> 3. `--kv-capacity` 17920 → 7168（-60%）：预留只降 293,916,672 B ⇒ 斜率 **27,336 B/token**
> ⇒ **回归式：预留 ≈ `1,374,117,632` B（1.31 GiB 固定项）+ 27,336 B × 池。**

即：**在这套引擎里，把 `--max-context` 抬到 200K/1M 几乎不花显存；花显存的只有设备池 + 1.31 GiB 的 CUDA Graph 固定项。**

### 2.5 它没有做什么

- **没有任何分片注入/网关**：仓库里没有 agg/shard 组件，长上下文全靠「主机池 + 按需搬回」。边界写在 `README-聊天怎么用.md:162-163`：

> 引擎声明 `n_ctx = 262144`，但**设备池只有 8,192 token**，其余靠 KVMem 放在 16 GiB 主机池里按需搬回。所以长题面/多轮对话**理论可用但本机未测**。

- **没有用共享显存**：`start-ptq1-mtp-diskkv.bat:7-18` 结论是 NO——`--wddm-evictable-budget` 报 `needs a Windows build with NINFER_D3D12_RESIDENCY=ON`，该 exe 里该符号只出现 1 次（就在错误消息里），且该开关语义相反（对 dedicated 记账、保持 arena 常驻）。

---

## 3. ③有没有实测 tok/s / prefill —— 有，但只在 1,133 token 题面上

全部是引擎自报 `timings`（不是估算），条件：**1,133 prompt token / 1,000 输出 / temperature 0 / 数数字语料**：

| 读数 | 值 | 出处 |
|---|---|---|
| prefill | 481.2 / **570.1** tok/s（两次独立运行） | `records/receipt-ptq1-8gb-deployed.md:79` |
| prefill（脚本基线） | 482.8 tok/s | `tools/speedtest.py:14` |
| prefill（区间） | 482–670 tok/s | `README.md:65` |
| decode | 59.0 / **60.3** tok/s | `records/receipt-ptq1-8gb-deployed.md:80` |
| decode（脚本基线／区间） | 54.5 ／ 54–99 tok/s | `tools/speedtest.py:14`；`README.md:65` |
| MTP 接受 | 780/875 = **89.1%**（两次相同） | `records/receipt-ptq1-8gb-deployed.md:82` |
| TTFT | 2.0 / 2.4 s | `records/receipt-ptq1-8gb-deployed.md:78` |
| 总时间 | 18.6 / 19.3 s | `records/receipt-ptq1-8gb-deployed.md:81` |
| 构建机（RTX 4080 SUPER / sm_89 / 池 17920 / CUDA Graph 开） | decode **196.8** tok/s、prefill 2.01k tok/s | `records/receipt-ptq1-8gb-deployed.md:74-81` |
| 复现性 | 同配置两次测出 **54.7** 与 **80.0** tok/s（差 46%）⇒ 单次读数不可作准 | `README.md:68` |
| 长题面的代价 | 一次 19.5k 题面 / 3.1k 输出的请求把后续请求**堵了 81 秒**（`--max-concurrency 1`） | `README.md:69` |

**没有的东西（关键）**：
- **没有任何 >10k token 题面的 tok/s/prefill 读数**。作者两处显式声明未测：`records/receipt-ptq1-8gb-deployed.md:120` 与 `:166`（「未跑长题面（>10k token）、未跑多轮、未跑超池检索」），`README-聊天怎么用.md:163` 同义。
- 因此「256K/768K/1M 上下文」在**速度**上没有任何实测支撑，只有容量算术。

---

## 4. ④与我们现役引擎是否同源；sm120a 件能不能在 sm_89 上跑

### 4.1 结论

1. **同源（同一条 NInfer 0.11.0 KVMem 血统），但不是同一支二进制**——它是 sm_120a 那次编译的产物，我们跑的是 sm_89 的另一次编译。
2. **sm120a 件在 sm_89 上跑不了，且不会回退**。仓库自己写了这条（`docs/README-在别的设备上部署.md:3-5`）：

> 结论先说：**能不能搬，取决于那台设备的显卡**。这套引擎是按架构分别编译的，**不会回退** —— 包内说明原话："One binary per architecture … the wrong one does not fall back — it dies with no usable kernel image"。所以先看架构，再选下面四条路之一。

   同文档 `:17` 的判据表把 `compute_cap = 8.9（RTX 40 系）` 归到「路径 A：.ninfer + **对应架构的引擎包**」，并注明「我们手里只有 sm_120a」；`:32` 更直白：

> 我们的私有仓库里**只有 sm_120a** 的引擎（Release `engine-sm120a-20261002`），**在那台设备上不能用**。

   上游融合项目同样写明（`repos/ninfer-fusion-kvmem/编译指南-怎么编.md:12`）：

> 一支 exe 只含一个架构（sm_86 / sm_89 / sm_120a），没有 PTX 回退 ⇒ 每个架构单独编一次。

### 4.2 证据链（三条独立证据）

| # | 事实 | 出处 |
|---|---|---|
| 1 | 本机 sm89 引擎：`801,324,544 B`，sha256 `3B6F9AF936A1E205…`，构建标签 `engine-v0.11.0-kvmem-20261003-98-g43c39c6-dirty` | `pack/ninfer-27b-kv-stream-3arch-20261019/engines/sm89/README.md:14-15`；同包 `MANIFEST.md` §2 |
| 2 | 120a 包的引擎：`1,329,240,576 B`，sha256 `E3E0486A5B78DFC9…`，启动只打印 `INFO build unknown`（无版本戳） | `records/receipt-ptq1-8gb-deployed.md:29`；`records/receipt-ptq1-run01-strict-argv.md:14` |
| 3 | 我们三 arch 包里那份 **sm120a** 引擎：`710,338,048 B`，sha256 `B07D9FCFD2BAD41F…`，与上表第 2 行那份**不是同一支** | `pack/ninfer-27b-kv-stream-3arch-20261019/MANIFEST.md` §2 |

⇒ 三份二进制互不相同；连「同为 sm120a」的两份都差近一倍体积（677 MiB vs 1.24 GiB），说明 120a 包是另一路编译（无版本戳、体积更大），**不是我们这条 2026-10-19 三 arch 构建线的产物**。

### 4.3 同源的正面证据（同一血统）

| 证据 | 说明 |
|---|---|
| 模型 sha256 逐字节相同 | 仓库要求 `5C4486C8A52687E3F62072C7DD2A320546D0E00D1C019BF137EB02CC944E21B8`（`README.md:15`）；本机 `models/bonsai2_27b_ternary_ptq1_native_mtp.ninfer` 本次实算 `5c4486c8a52687e3f62072c7dd2a320546d0e00d1c019bf137eb02cc944e21b8`，一致 |
| 同一套日志签名 | 双方都有 `[ring] content scoring ON by default` 与 `kvmem_score: SELECT …`（120a：`records/receipt-ptq1-8gb-deployed.md:100-108`；我们：`repos/ninfer-fusion-kvmem/README.md:204-205`） |
| 同一套开关词汇 | 120a 启动器用的 `--kv-capacity`／`--kv-dtype`／`--host-kv-mib`／`--no-cuda-graph`／`--fast-prefill-kernel`／`--disk-kv-*` 与 `NINFER_KV_*`，我方引擎 `--help` 与二进制里**同名存在**（逐条见 §5） |

**结论**：可以把它当「同一引擎在另一张卡上的配置样本」来读，**不能**把它的二进制或 tok/s 直接搬成 4060 Ti 的结论。

---

## 5. ⑤能直接搬到 4060 Ti 8G 的参数/脚本（文件名 + 行号 + 是否可搬）

我方现役：`ninfer-serve-89.exe`（`engine-v0.11.0-kvmem-20261003-98-g43c39c6`）+ `--kv-capacity 40000 --kv-dtype rk2v4-e8 --host-kv-mib 6144 --max-context 262144` + MTP draft4/win8 + `--no-cuda-graph` + `--device-state-slots 0`（峰值 7,469 MiB / 97–98 tok/s / 37K prefill 963 tok/s）。

「我方支持」一栏依据：`C:/Project/local_model/engine/help-full.txt`（我方引擎 `--help` 存档）与对 `C:/Project/local_model/engine/ninfer-serve-89.exe` 的 `NINFER_*` 字节扫描（只读，未执行 exe）。

| # | 可搬的东西 | 出处（文件:行） | 我方对应 | 判定 |
|---|---|---|---|---|
| 1 | `--no-cuda-graph`（省 1.31 GiB 固定项） | `start-ptq1-mtp-8gb.bat:104`；`README.md:54` | 已用 | **已在用**，无需动 |
| 2 | `--max-context` 抬高几乎不花显存 | `start-ptq1-mtp-lan-bigctx.bat:99`（786432）、`start-ptq1-mtp-lan-1m.bat:104`（1048576）；依据 `records/receipt-ptq1-run01-strict-argv.md:82` | 已 262144 | **可照搬思路**：200K 逻辑上下文本身免费，卡的是主机池与速度 |
| 3 | `--host-kv-mib` 作「预算」、按 25.12 KiB/token 算 | `start-ptq1-mtp-lan-bigctx.bat:99`（24576）、`start-ptq1-mtp-lan-1m.bat:104`（28672）；规则 `README.md:36-42` | 6144 | **可搬公式，不可搬数字**：25.12 KiB/token 是 **k8v4** 口径；我方 `rk2v4-e8` 按 `pack/ninfer-27b-kv-stream-3arch-20261019/engines/sm89/README.md:45` 的锚点 0.8357 MiB/页 ≈ **13.4 KiB/token** ⇒ 200K ≈ 2.6 GiB，6144 MiB 预算本就够 |
| 4 | `--kv-capacity` 必须显式给（默认=最大上下文） | `start-ptq1-mtp-8gb.bat:103`；`README.md:53` | 已 40000 | 已在用；**别把 k8v4 的 8192 照搬**（那会让池只剩 8192 token） |
| 5 | `--default-max-tokens` ≤ 池 | `start-ptq1-mtp-8gb.bat:105`；`README.md:55` | 引擎默认 8192，池 40000 | 合规；**若把池降到 <8192 必须同步下调** |
| 6 | `--max-shared-prefixes 0`（六档全带） | `start-ptq1-mtp-8gb.bat:106`、`start-ptq1-mtp-lan.bat:108`、`start-ptq1-mtp-fast.bat:95`、`start-ptq1-mtp-lan-bigctx.bat:102`、`start-ptq1-mtp-lan-1m.bat:107`、`start-ptq1-mtp-diskkv.bat:102` | 我方包启动器也注入 | **必须保留**：`pack/ninfer-27b-kv-stream-3arch-20261019/engines/sm89/README.md:37` 记 ring（池<逻辑页）下共享前缀快照会抛 `active KV snapshot page ownership is not ordered` |
| 7 | `NINFER_KV_WINDOW=16384`（KVMem ring 的唯一门） | `start-ptq1-mtp-8gb.bat:70`；`README.md:57` | 二进制有（10 处命中） | **可搬**，值得在我方做一次 A/B |
| 8 | `NINFER_KV_RETRIEVE=8192` | `start-ptq1-mtp-8gb.bat:71` | 二进制有（3 处命中） | **可搬**（与 window 一起调） |
| 9 | `NINFER_KV_RING=1` | `start-ptq1-mtp-8gb.bat:72` | **我方二进制 0 命中** | **死开关，别抄**：`repos/ninfer-fusion-kvmem/README.md:193` 明写「新件**不再读取** `NINFER_KV_RING`；环的门是 `NINFER_KV_WINDOW`」，`repos/ninfer-fusion-kvmem/8G档-配置提醒-20261008.md:62` 还记「只设 RING 不给 WINDOW ⇒ 命令行直接拒绝启动」 |
| 10 | `NINFER_HOST_PAGEABLE=1` | `start-ptq1-mtp-8gb.bat:73`；`README.md:58` | 二进制有（2 处命中） | **可搬**（Windows 上钉住的主机会映射进 GPU 地址空间） |
| 11 | `NINFER_KV_REUSE_HOSTBACKED=1` | `start-ptq1-mtp-8gb.bat:74` | 二进制有（1 处命中） | **可搬**，未验效果 |
| 12 | `NINFER_TERNARY_PTQ1_FAST=1` | `start-ptq1-mtp-8gb.bat:75` | 二进制有（1 处命中） | **可搬**，未验效果（需 A/B） |
| 13 | `--fast-prefill-kernel` | `start-ptq1-mtp-fast.bat:93`；`start-ptq1-mtp-lan-1m.bat:105` | `help-full.txt:37-40` 支持（int8/rk* KV 的快速 prefill 核） | **可搬且建议试**：200K 的瓶颈就在 prefill |
| 14 | `--draft-tokens 12` | `start-ptq1-mtp-fast.bat:93`；`start-ptq1-mtp-lan-1m.bat:105` | 我方 draft 4 / win8 | **谨慎**：作者自己写「draft 更深在不可预测文本更慢」（`start-ptq1-mtp-fast.bat:18-20`），且 draft 4 时接受率已 89.1% |
| 15 | `--disk-kv-path` / `--disk-kv-gib` / `--disk-kv-restore` | `start-ptq1-mtp-diskkv.bat:99` | `help-full.txt:147-153` 支持 | **可搬**（跨重启复用长文档前缀），代价：写 SSD、**从不提速**（`start-ptq1-mtp-diskkv.bat:20-30`） |
| 16 | 端口守卫（防第二实例） | `start-ptq1-mtp-8gb.bat:79-87`（`netstat` + `findstr ":8095 "`，命中即 `exit /b 4`） | 我方无 | **建议搬**：8GB 卡第二实例必崩（对方 10-01 实测） |
| 17 | 一键测速 `test-speed.bat` + `tools/speedtest.py` | `test-speed.bat:39`；`tools/speedtest.py:13-23,71-101` | 无等价物 | **可搬**（改 `--engine host:port` 指向我方）；但它会占用唯一解码通道，**需择时**，本次未跑 |

**不能搬的**：`engine/`、`models/`（本仓库没有）；以及它整套 `--kv-dtype k8v4` 的池数字——k8v4 比我方 `rk2v4-e8` 大约 1.86×（`pack/ninfer-27b-kv-stream-3arch-20261019/engines/sm89/README.md:82` 容量倍率表：`k8v4 / rk4v4 / rk2v4-e8 = 1.00 / 1.436 / 1.861`）。

---

## 6. 对「8GB 上要 200K 上下文」这条诉求的意义（判断，非仓库原文）

1. **逻辑上下文 200K 几乎不花显存——这条已被本仓库的隔离实验证实可复用**（`--max-context` 1M→32768 只差 28,672 B，`records/receipt-ptq1-run01-strict-argv.md:82`）。我方现役已把 `--max-context` 报到 262144，这条路不需要再证明。
2. **真正的成本是主机 KV 与搬页带宽**：本仓库 25.12 KiB/token 是 k8v4 口径（200K ≈ 4.8 GiB 主机）；我方 `rk2v4-e8` 约 13.4 KiB/token（200K ≈ 2.6 GiB），6144 MiB 的 `--host-kv-mib` 装得下。
3. **速度上该仓库给不出任何 200K 证据**：>10k 题面明确未测（§3），且作者反复写「更长上下文不会更快」。⇒ 200K「可接受速度」只能我们自己在 4060 Ti 上量，不能从这份仓库抄结论。
4. 若要补这组数据，最小实验是（**未执行，交 lead 决定**）：在 8091 空闲时段发 20K/50K/100K/200K 定长题面，读引擎自报 `timings.prompt_per_second` 与 `predicted_per_second`，得「速度 vs 长度」曲线。

---

## 7. 未核实 / 存疑（不许当结论用）

1. 我**没有启动任何引擎**（铁律③），所以「我方支持某参数」只来自 `--help` 文本与二进制字符串，**不等于实跑通过**。
2. 25.12 KiB/token 是 **k8v4** 口径；13.4 KiB/token（rk2v4-e8）是**算术外推**（0.8357 MiB/页），非本机实测。
3. 收据里「host KV pinned 16.0 GiB」与 `NINFER_HOST_PAGEABLE=1`（pageable）措辞冲突，未深究。
4. GitHub REST 403，未取 star/fork/issue；仓库无 PR/issue 讨论可读。
5. 120a 包的引擎是「最后一版」还是中间版无从判断（`build unknown`，无版本戳）。

---

## 附 A 关键行号索引

- 六档表 `README.md:27-34`｜容量规则与算术 `README.md:36-42`｜参数审计 `README.md:46-58`｜实测读数 `README.md:60-70`
- 8GB 档 argv `start-ptq1-mtp-8gb.bat:100-106`｜环境变量 `start-ptq1-mtp-8gb.bat:70-75`｜端口守卫 `start-ptq1-mtp-8gb.bat:79-87`｜隔离实验数字 `start-ptq1-mtp-8gb.bat:33-52`
- 1M 档算术 `start-ptq1-mtp-lan-1m.bat:20-39`｜bigctx 档负面结论 `start-ptq1-mtp-lan-bigctx.bat:25-30`｜fast 档取舍 `start-ptq1-mtp-fast.bat:12-29`｜diskkv 档 WDDM 结论 `start-ptq1-mtp-diskkv.bat:7-18`
- 实测回执 `records/receipt-ptq1-8gb-deployed.md:70-96`｜被拒原文 `records/receipt-ptq1-run01-strict-argv.md:9-28`｜单旋钮隔离实验 `records/receipt-ptq1-run01-strict-argv.md:68-90`
- 换设备部署（架构不回退）`docs/README-在别的设备上部署.md:3-5,17,32-35`｜长题面未测 `README-聊天怎么用.md:162-163`｜测速工具 `tools/speedtest.py:13-23`

## 附 B 复现命令（代理下）

```bash
export HTTP_PROXY=http://127.0.0.1:7897 HTTPS_PROXY=http://127.0.0.1:7897
curl -sI https://github.com/AAANDYYY-A/ninfer-sm120a-8gb-toolkit | head -3
git clone --depth 200 https://github.com/AAANDYYY-A/ninfer-sm120a-8gb-toolkit tmp/scout/ninfer-sm120a-8gb-toolkit
cd tmp/scout/ninfer-sm120a-8gb-toolkit && git ls-remote --tags origin && git log --oneline
```

---
*本报告只读侦察：未改 `repos/`、未启动引擎、未起第二实例；每条结论后附出处行号，「未做」的一律显式标注。*
