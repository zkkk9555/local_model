# 备份核验-B：从零可重建性

> 核验对象：`repo/`（= GitHub zkkk9555/local_model 的推送源）＋本地实物＋网盘/Release/HF。
> 只读核验：未改动、未删除、未移动任何文件；未触碰 8091/8081/8086/8090 上正在跑的引擎（没有重跑 `--help`，直接用现成的 `engine/help-full.txt`）。唯一副作用：`python -m py_compile` 在 `repo/tools/` 下生成了 `__pycache__/`，已删除，清理后 `git -C repo status --porcelain` 为空。

## 结论

**照 `RESTORE.md` 现在写的做，删掉本地模型后重建不出来** —— 它指定的唯一模型来源（r3 总包，`RESTORE.md:90`「解开后 `model/bonsai2_27b_ternary_ptq1_native_mtp.ninfer` 就是它」、`RESTORE.md:262`「这一个包就含 模型 + sm89 引擎 + 运行期 DLL」）里 `model\` 是个空目录，全包 0 个 `.ninfer`/`.gguf`；第二条夸克链接（`RESTORE.md:91`）要提取码而文档没给。真正能凑齐「6,394,697,216 B 模型 + sm89 引擎 + 运行期 DLL」的是 ModelScope 的 `q409640976/ninfer-kvmem-heretic-bonsai2-27b`，而 `RESTORE.md` 全文 0 次提到它（只有 `repo/reports/HF与魔搭-情报.md:15,54` 记过「同名同字节」）。**把这一条补进 §3.2，其余照抄就能全量重建。**

## 1. 六项要求：逐项判定

| # | 要求 | 判定 | 硬证据 |
| --- | --- | --- | --- |
| 1 | 本地实物 sha256 vs RESTORE 表 | ✅ **全部逐位一致**，0 处不符 | 5 个件实算值 = 文档值（见 §1.1） |
| 2 | 九个运行期 DLL | ✅ **9/9 字节数与 SHA-256 全对** | 见 §1.1 |
| 3 | r3 总包 SHA-256 + 内容 | ⚠️ SHA **对**；内容 **缺模型**（致命） | 见 §2 P0-1 |
| 4 | 下载链接活性 | ✅ HF 3/3、GH Release 4/4、夸克 2/3；❌ 夸克 1 条要提取码 | 见 §2 P0-2 / §1.2 |
| 5 | 脚本可执行性 | ✅ `bash -n` 20/20、`py_compile` 39/39；真树 `--deep` 18/18 OK；子树跑准确报缺失不崩 | 见 §1.3 |
| 6 | §3.4 命令行参数 vs 引擎 | ✅ **20/20 全部被引擎接受，0 个"文档写了引擎不认"** | 见 §1.4 |

### 1.1 本地实物（实算 sha256sum）

| 文件 | 字节 | 实测 SHA-256 | vs 文档 |
| --- | --- | --- | --- |
| `engine/ninfer-serve-89.exe` | 801,324,544 | `3b6f9af936a1e20520c3de3a4185f627ba59481139659cf3104bdead815ef6e4` | = §3.1选B |
| `models/bonsai2_27b_ternary_ptq1_native_mtp.ninfer` | 6,394,697,216 | `5c4486c8a52687e3f62072c7dd2a320546d0e00d1c019bf137eb02cc944e21b8` | = §3.2 |
| `llama8g/bundle/models/Ternary-Bonsai-2-27B-PTQ1_0-mtp-procreations.gguf` | 6,397,970,272 | `5f212d02ff57cb8eaad260fd7ff57bfaff87ae2bc9183a21dd2f127c27252505` | = §4 |
| `llama8g/bonsai-bundle-win-x64.zip` | 616,671,821 | `6285cd5d6ef72e9e13ffadefb20b1ef91dd90afe80e53f3375bae268454e79ce` | = §4 |
| `Downloads/infer-27b-kv-stream-3arch-20261019-r3.zip` | 2,092,648,837 | `25436366f1f0e9caa284b64c1e97e6a241cf3e50785c5775569eb9788e4a788c` | = §10.2 |

九个 DLL（`cudart64_13` 551,024 / `cublas64_13` 51,870,320 / `cublasLt64_13` 460,301,424 / `avcodec-63` 91,810,816 / `avformat-63` 23,003,136 / `avutil-61` 3,025,408 / `swscale-10` 2,343,936 / `swresample-7` 747,008 / `libcurl-x64` 3,722,344）**字节与 SHA-256 全部等于 §3.3 表**，逐条比对无一项不符。

### 1.2 链接活性（逐条 curl）

| 链接 | 结果 |
| --- | --- |
| 夸克 `pan.quark.cn/s/5af2f61bc482`（§3.1选A） | ✅ 有效：title「NInfer 引擎包 · 三架构 sm86/sm89/sm120a（2026-10-13）」，`expired_at=4102416000000`，只有目录 `ninfer-engine-packs-3arch-20261013` |
| 夸克 `pan.quark.cn/s/d4a29bfcb547`（§3.2路1） | ✅ 有效：title「NInfer 27B KV流式 三arch分发包 r3」，**分享内只有 1 个文件** = r3 zip（无独立模型件） |
| 夸克 `pan.quark.cn/s/4c7d9e017d98`（§3.2路2） | ❌ token 返回 `code=41008「需要提取码」`，title「本地部署」→ 按文档拿不到 |
| GH Release `engine-v0.11.0-kvmem-20261008`（§3.1选B） | ✅ 4 资产全 200：`ninfer-serve-89.exe` 801,324,544（dl 1587）、`-86` 820,153,856、`-120a` 710,338,048、`SHA256SUMS.txt` 6,273 |
| HF `CaryPalmer/Ternary-Bonsai-2-27B-262k-GGUF`（§4） | ✅ API 200，`private=false gated=false`，三件套字节 = gguf 6,397,970,272 / bundle zip 616,671,821 / start-server.ps1 26,955，`resolve/main` HEAD 全 200 |

Release 自带 `SHA256SUMS.txt`（68 条，大写十六进制）里 `engines\sm89\infer-serve.exe` = `3B6F9AF936A1E20520C3DE3A4185F627BA59481139659CF3104BDEAD815EF6E4`，与本地 `engine/ninfer-serve-89.exe` 完全一致 —— §3.1选B 是可信的。

### 1.3 脚本可执行性

- `repo/scripts/*.sh`：20 个，`bash -n` **0 失败**。
- `repo/tools/*.py` 18 个 + `repo/scripts/*.py` 21 个：`python -m py_compile` **0 失败**。
- 真树（`C:/Project/local_model`，`ROOT` 推导正确）跑 `python tools/restore_check.py --deep`：**18 项全部 OK**（2 必需 + 9 DLL + 7 可选件），0 BAD / 0 MISSING，退出码 0。（要求里写"期望 13 项 OK"是记错了项数，仓库本身没错：`restore_check.py` 就是 18 项。）
- 把 `repo/` 整树复制到 `tmp/verify-b/repo` 再跑同一脚本：**11 项 MISSING，不崩、路径打得对**（因为 `ROOT` = 脚本上一级 = `tmp/verify-b`）。→ 这条同时说明了脚本行为正确、以及 §2 P1-7 的踩坑点。

### 1.4 §3.4 命令行 20 个参数

`--host --port --model-id --max-context --kv-capacity --kv-dtype --host-kv-mib --max-concurrency --max-shared-prefixes --derive-session-keys --prefill-chunk --cuda-graph-allowance-mib --ngram-draft-tokens --device-state-slots --gdn-state-fp16 --spec --draft-tokens --mtp-attention-window --default-reasoning-effort --default-max-tokens` —— **20/20 在 `engine/help-full.txt` 中都存在**，文档没写错参数。附带印证 §7 坑5：`--kv-lease-growth` 存在、`--no-kv-lease-growth` 不存在。

## 2. 问题清单（文件:行号 → 怎么修）

### P0-1 `repo/RESTORE.md:262`（连带 `:90`）总包不含模型 —— 「离线一个包全须全尾重建」是假的

原文：`:262` 「↑ 这一个包就含 模型 + sm89 引擎 + 运行期 DLL：断网机器上也能把它全须全尾重建起来」；`:90` 「解开后 `model/bonsai2_27b_ternary_ptq1_native_mtp.ninfer` 就是它，另外还带 sm89 引擎与 runtime DLL」。

实测（`unzip -l`，73 条目、解压后共 3,019,971,806 B）：

- 顶层 `ninfer-27b-kv-stream-3arch-20261019\` 下：`engines\{sm86,sm89,sm120a}\`、`runtime\`（含 `runtime\python\` 便携 CPython 3.12）、`model\`（**空目录**）、`logs\`、`run\`、`ui\`、`gateway\`、`docs\`。
- `.ninfer` 条目 **0 个**，`.gguf` **0 个**；`model\` 下 **0 个文件**。
- Release 侧同源清单 `SHA256SUMS.txt`（68 条）里同样 **0 条** 模型/gguf 路径。
- 体积自证：2.09 GB 的包解压 3.02 GB，装不下 6.39 GB 的模型。

**怎么修**：`:262` 改成「这一个包含 sm86/sm89/sm120a 三支引擎 + 运行期 DLL + 便携 CPython 3.12（不含模型）」；`:90` 删掉「`model/…` 就是它」与「模型 + 引擎一次拿全」，改成「引擎一次拿全；模型见 §3.2」。同时改 §10.2 标题下那句"最小集"的说明——现最小集其实是「r3 zip（引擎+运行时）+ 模型单件」。

### P0-2 `repo/RESTORE.md:91` 第二条夸克链接要提取码

原文：「2. 网盘 <https://pan.quark.cn/s/4c7d9e017d98>（aivault 的引擎/模型分目录）也收着同族模型件。」

实测：token 接口 `code=41008`、`message="需要提取码"`，title「本地部署」，未登录/无码拿不到任何条目。（`repo/docs/20261030-结论与索引.md:77` 里的提取码 `s9mG` 属于另一个链接 `a23f244661b4`，不是这条。）

**怎么修**：删掉该条，或补上提取码并注明"需登录 + 提取码"；若留作备份路径，明确写"未验证"。

### P0-3 `repo/RESTORE.md:87` 「公共 HF 上没有…只存在于作者分发包里」——有公开可用的第三来源，文档漏了

实测 ModelScope 仓 `q409640976/ninfer-kvmem-heretic-bonsai2-27b`：

| 文件 | 字节 | 验证 |
| --- | --- | --- |
| `models/bonsai2_27b_ternary_ptq1_native_mtp.ninfer` | **6,394,697,216** | HEAD 200，`content-length` 一致，`etag E7E708883C1016BEDDB0A27D9CAA142D-610`；**首 1 MiB / 尾 1 MiB 与本地件逐字节相同**（sha 前缀 `82d98d18f47ce599a8c7d3abd620d315` / `1a481016bba2612b76e285e4ddd000c9`） |
| `engine/ninfer-serve-89.exe` | 795,030,528 | HEAD 200（= §3.1选A 那支） |
| `engine/*.dll`（12 个）+ `models/heretic-27b-ptq1-mtponly.ninfer` | — / 6,395,660,288 | 与 A 包同一套 DLL 尺寸 |

**怎么修**：§3.2 增加「路 0（推荐）：ModelScope `q409640976/ninfer-kvmem-heretic-bonsai2-27b` → `models/bonsai2_27b_ternary_ptq1_native_mtp.ninfer`，6,394,697,216 B，同一个仓还带 sm89 引擎与全套 DLL（断网重建时一次拿全）」；`:87` 的断言改成「公共 **HuggingFace** 上没有（ModelScope 上有同名同字节镜像仓）」，并顺手把 `repo/reports/HF与魔搭-情报.md:15,54` 交叉引用上。

### P1-4 `repo/RESTORE.md:273` 「`runtime/*.dll` 放进 `engine/`」会把 6 个 DLL 换成另一套构建

实测：包内 `runtime\` 与 §3.3 / 本地 `engine/` 是**两套不同构建**——

| DLL | 包内字节 | 包内 SHA-256（Release 清单） | §3.3 / 本地 |
| --- | --- | --- | --- |
| `avcodec-63.dll` | 118,445,056 | `6C1261FCE61F9E45EF75336E471D717CA90E651ECD9AE4F275D00009E0ABBCCF` | 91,810,816 / `1AB43AC3…` |
| `avformat-63.dll` | 23,643,648 | `F4FF30EEC58AE74A0B24961FEEB692A1910EF5C342C45A00D1AC45E2FACBCA00` | 23,003,136 / `1082BDCB…` |
| `avutil-61.dll` | 3,030,528 | `362AFC7047F618E10A2BF436844517DAF29E3E473FFDEBF4A23C30FF2E6AB2AB` | 3,025,408 / `AABE139A…` |
| `libcurl-x64.dll` | 3,648,104 | `10C8871B2188095C26B28767B4F99DC97D0F6FAB58A70BE47F6679CD9126B13F` | 3,722,344 / `D8BFA3E3…` |
| `swresample-7.dll` | 738,816 | `A81BE671FE3FDEBB6BC12ABC1268C6E065D68DE61DDF1EFCA721E52752F10F8F` | 747,008 / `DC8594E1…` |
| `swscale-10.dll` | 2,370,048 | `DC0CBDA7376786E63E4B427F1340CFDEE809700EC5F81C3016274CDAA8C3EB10` | 2,343,936 / `C10C48B8…` |

三个 CUDA DLL 则**完全一致**（`B00CA6F5…` / `F1D500D0…` / `B592CD01…`）。照 `:273` 抄完再跑 `restore_check.py` → 九项里 **6 项 BAD**。

**怎么修**：`:273` 改成「`engines/sm89/*` 进 `engine/`；`runtime\` 只留 3 个 CUDA DLL 和 4 个 MSVC 运行库，6 个 FFmpeg/curl DLL 按 §3.3 用 `scripts/fetch_runtime.sh` 取（或接受包内这套，但要同步改 `tools/restore_check.py` 的 `DLLS` 白名单）」。

### P1-5 `repo/RESTORE.md:70` `sha256sum -c SHA256SUMS.txt` 直接跑必失败（CRLF）

实测：`C:/Users/Administrator/Downloads/engine-pack-sm89/SHA256SUMS.txt`（1,458 B，16 条，CRLF）→ 16 行全 `FAILED open or read`，退出码 1（行尾 `\r` 被当成文件名一部分）。`tr -d '\r' < SHA256SUMS.txt | sha256sum -c -` → **16/16 OK**，exe sha = `9fa7490bcbc4825a77673c5f8c6ffdbf25aab5b3e768a54d8bcebd7161ca41eb`（与 §3.1 一致）。

**怎么修**：`:70` 改成 `tr -d '\r' < SHA256SUMS.txt | sha256sum -c -`（或先 `dos2unix`）；顺手在 §3.1 提醒"这个网盘包是 Windows 换行"。

### P1-6 `repo/RESTORE.md:123` `export unset NINFER_KV_RETRIEVE` 不会 unset

实测：先 `export NINFER_KV_RETRIEVE=8192`，再执行这一行，`echo` 仍是 `8192`（bash 把 `unset` 当成变量名导出了）。

**怎么修**：改成 `unset NINFER_KV_RETRIEVE` —— `scripts/serve2.sh:94` 自己用的就是正确写法，照抄它。

### P1-7 `repo/RESTORE.md:271-274` clone 到 `repo/` 后立刻跑 `restore_check.py` → 必然全误报

实测：`restore_check.py` 的 `ROOT` = 脚本所在目录的上一级；在 `C:/Project/local_model/repo/` 里跑，它检查的是 `repo/engine/ninfer-serve-89.exe`、`repo/models/*.ninfer` —— 实测把整树放到 `tmp/verify-b/repo` 跑出 **11 项 MISSING**（不崩，但这 11 项全是假的缺失）。

**怎么修**：`:271` 后加一步「把 `repo/*` 摊到 `C:/Project/local_model/` 根（`engine/ models/ scripts/ tools/ docs/ config/` 同级），或 `cd repo && python tools/restore_check.py` 时知道自己在检查 `repo/`」；更好的做法是让 `restore_check.py` 支持 `--root` 或读环境变量，别靠相对位置推 ROOT。

### P2-8 `repo/RESTORE.md:159` `mv <下载的 start-server.ps1> .` 会覆盖 bundle 自带的启动器

实测：`llama8g/bundle/start-server.ps1` = **62,380 B**（内含 113 处 `BONSAI_*` 变量，含 `BONSAI_CTX`、`BONSAI_CTK`、`BONSAI_KV_VRAM_CELLS` 等），HF 仓根那份 = **26,955 B**（下载后现躺在 `llama8g/start-server.ps1`）。而 `scripts/llama8g_launch.sh:11` 是 `exec powershell -File ./start-server.ps1`（`cd llama8g/bundle`）→ 覆盖后起的是另一个 launcher。

**怎么修**：删掉 `:159`（bundle 自带就够），或改成 `mv <下载的 start-server.ps1> start-server.hf.ps1` 并说明"仅供对照，不替换 bundle 内版本"。

### P2-9 `repo/RESTORE.md:57` 「全局搜 `local_model` 即可」不成立

这些硬编码路径里没有 `local_model`，照 §2 的说法搜不到：

| 位置 | 内容 |
| --- | --- |
| `repo/scripts/ab.sh:4` | `ROOT=/c/Users/Administrator/Documents/deepseek-harness/default-workspace` |
| `repo/scripts/fetch_model.sh:5` | `cd /c/Users/Administrator/Documents/deepseek-harness/default-workspace/models` |
| `repo/scripts/fetch_runtime.sh:6` | `cd /c/Users/Administrator/Documents/deepseek-harness/default-workspace` |
| `repo/tools/dsh_provider_test.py:40` | `DEFAULT_CONFIG = C:/Users/Administrator/.dsh/profiles/desktop/cordis.patch.yml` |
| `repo/tools/llama_longctx_test.py:14,35-36` | 同一批 DeepSeek Harness 路径 |
| `repo/tools/matrix2.py:10` | 同上 |
| `repo/tools/verify_all.sh:21` | `CONFIG` 默认值指向 `.dsh/profiles/desktop` |

**怎么修**：§2 把这 7 处列成表（或统一改成 `ROOT=${LOCAL_MODEL_ROOT:-/c/Project/local_model}` 并在 `:57` 写"搜 `deepseek-harness/default-workspace` 与 `.dsh/profiles` 两串"）。

### P2-10 `repo/RESTORE.md:63-73` 选A 与 `restore_check.py` 的 DLL 白名单不兼容

实测：`engine-pack-sm89/engine` 12 个 DLL 的尺寸 = Release `runtime\` 那套 = ModelScope 那套，与 §3.3 表不同；而 `restore_check.py` 的 `DLLS` 只认 §3.3 一套字节数（只把 exe 放宽到两尺寸）→ 走"选A"建树必判 6 项 BAD。

**怎么修**：`repo/tools/restore_check.py` 的 `DLLS` 每项改成"允许的尺寸集合"（两套），或只对 3 个 CUDA DLL 校验字节数、其余只校验存在。

### P3 其余（不影响重建，但会误导人）

- `repo/scripts/fetch_model.sh:5` 下的是 `Ternary-Bonsai-2-27B-ninfer-v3.ninfer`（9,520,051,456 B，HF `WaveCut/…`），**不是** §3.2 那个 6.39 GB PTQ1 件；`RESTORE.md` 全文没提这个脚本。要么删脚本，要么在 §3.2 注明「另一条路：v3 件，更大、8 GB 卡未验证」。
- `RESTORE.md:262` 说"断网机器上也能重建"——即便模型补齐，这条也不成立：r3 包里的 `runtime\` 只有 DLL 与 CPython，**没有 CUDA 驱动/显卡驱动**，§1 的机器要求仍需预装驱动。
- 本报告没有重跑 `--help`（避免碰正在跑的进程），用的是 `engine/help-full.txt`（20,543 B / 318 行，与 `tmp/engine-help.txt` 字节相同）。§9 若要求"重建后自己跑 `--help` 对齐参数"，建议在文档里写明这一点。

## 3. 可以直接照抄的最小修复单

1. §3.2 加"路 0：ModelScope `q409640976/ninfer-kvmem-heretic-bonsai2-27b`"（模型 + 引擎 + DLL 一次拿全，`:87` 的"只存在于作者分发包"改掉）。
2. §10.2 / §10.3 与 `:90` 的"包内含模型"改掉，说明 r3 包只含引擎三支 + 运行时。
3. `:273` 拆开写：引擎进 `engine/`，`runtime\` 只取 CUDA + MSVC，6 个 FFmpeg/curl DLL 说明两套构建的取舍。
4. `:70` 加 `tr -d '\r'`；`:123` 改成 `unset`；`:159` 删掉或改名不覆盖。
5. `:271` 补"摊平到根目录"一步；`restore_check.py` 支持 `--root` 并接受两套 DLL 尺寸。
6. `:57` 补 7 处不含 `local_model` 的硬编码路径；删掉或标注 `fetch_model.sh`。

## 4. 实际跑过的命令（节选，按执行顺序）

```bash
# 0 环境
export HTTP_PROXY=http://127.0.0.1:7897 HTTPS_PROXY=http://127.0.0.1:7897
python -V; nvidia-smi --query-gpu=name,memory.total --format=csv

# 1/2 本地实物哈希（5 个大件 + 9 个 DLL，逐个 sha256sum，与 RESTORE 表逐位比对）
cd /c/Project/local_model
sha256sum engine/ninfer-serve-89.exe
sha256sum models/bonsai2_27b_ternary_ptq1_native_mtp.ninfer
sha256sum llama8g/bundle/models/*.gguf llama8g/bonsai-bundle-win-x64.zip
sha256sum /c/Users/Administrator/Downloads/infer-27b-kv-stream-3arch-20261019-r3.zip
sha256sum engine/{cudart64_13,cublas64_13,cublasLt64_13,avcodec-63,avformat-63,avutil-61,swscale-10,swresample-7,libcurl-x64}.dll
stat -c '%s %n' engine/*.dll

# 3 r3 总包内容（只列清单，不解压）
unzip -l /c/Users/Administrator/Downloads/infer-27b-kv-stream-3arch-20261019-r3.zip
unzip -l ... | grep -ciE '\.(ninfer|gguf)$'          # → 0
unzip -l ... | grep -E 'model/'                       # → 只有空的 model\ 目录

# 4 链接活性
curl -sI https://huggingface.co/api/models/CaryPalmer/Ternary-Bonsai-2-27B-262k-GGUF   # 200
curl -s  https://huggingface.co/api/models/CaryPalmer/Ternary-Bonsai-2-27B-262k-GGUF | python -c 'import json,sys;d=json.load(sys.stdin);print([(f["rfilename"],f["size"]) for f in d["siblings"]])'
curl -sIL https://huggingface.co/CaryPalmer/Ternary-Bonsai-2-27B-262k-GGUF/resolve/main/<file>   # HEAD 200 ×3
# 夸克：分享 token + 详情接口（detail / token）
curl -s 'https://pan.quark.cn/s/5af2f61bc482'          # title「NInfer 引擎包 · 三架构…」
curl -s 'https://pan.quark.cn/s/d4a29bfcb547'          # 仅 1 个文件 = r3 zip
curl -s 'https://pan.quark.cn/s/4c7d9e017d98'          # code=41008 需要提取码
# GitHub Release
curl -s https://api.github.com/repos/1314521gjy/ninfer-fusion-kvmem/releases/tags/engine-v0.11.0-kvmem-20261008
curl -sIL https://github.com/1314521gjy/ninfer-fusion-kvmem/releases/download/engine-v0.11.0-kvmem-20261008/ninfer-serve-89.exe
curl -sL .../SHA256SUMS.txt -o tmp/verify-b/gh-SHA256SUMS.txt   # 68 条，engines\sm89\infer-serve.exe = 3B6F9AF9…

# 5 脚本
for f in repo/scripts/*.sh; do bash -n "$f" || echo "FAIL $f"; done        # 20 个，0 失败
python -m py_compile repo/scripts/*.py repo/tools/*.py                    # 39 个，0 失败
cp -r repo tmp/verify-b/repo && (cd tmp/verify-b/repo && python tools/restore_check.py)   # 11 MISSING，不崩
python tools/restore_check.py --deep                                      # 18 项 OK，exit 0
tr -d '\r' < /c/Users/Administrator/Downloads/engine-pack-sm89/SHA256SUMS.txt | sha256sum -c -   # 16/16 OK
sha256sum -c SHA256SUMS.txt                                               # exit 1，16 行 FAILED（CRLF 复现）

# 6 参数核对（没有重跑 --help，避免碰运行中的引擎）
diff -q tmp/engine-help.txt engine/help-full.txt                          # 字节相同
for p in --host --port --model-id --max-context --kv-capacity --kv-dtype --host-kv-mib \
         --max-concurrency --max-shared-prefixes --derive-session-keys --prefill-chunk \
         --cuda-graph-allowance-mib --ngram-draft-tokens --device-state-slots --gdn-state-fp16 \
         --spec --draft-tokens --mtp-attention-window --default-reasoning-effort --default-max-tokens; do
  grep -q -- "$p" engine/help-full.txt && echo "OK $p" || echo "MISSING $p"
done                                                                      # 20/20 OK
grep -c -- '--kv-lease-growth' engine/help-full.txt                       # 存在；--no-kv-lease-growth 不存在

# 额外：export unset 复现
export NINFER_KV_RETRIEVE=8192; export unset NINFER_KV_RETRIEVE; echo "$NINFER_KV_RETRIEVE"   # → 8192

# 额外：ModelScope 替代来源（HEAD + 首尾 1 MiB 对拍）
curl -s 'https://modelscope.cn/api/v1/models/q409640976/ninfer-kvmem-heretic-bonsai2-27b/repo/files?Revision=master&Recursive=true'
curl -sI 'https://modelscope.cn/api/v1/models/q409640976/ninfer-kvmem-heretic-bonsai2-27b/repo?Revision=master&FilePath=models%2Fbonsai2_27b_ternary_ptq1_native_mtp.ninfer'   # content-length 6394697216
curl -s -r 0-1048575 <same-url> | sha256sum        # 82d98d18… = 本地首 1 MiB
curl -s -r 6393648639-6394697215 <same-url> | sha256sum   # 1a481016… = 本地尾 1 MiB

# git 侧核对
git -C repo log --oneline -n 3; git -C repo status --porcelain; git -C repo rev-parse HEAD; git -C repo remote -v
```
