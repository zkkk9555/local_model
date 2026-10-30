# 备份核验-A：GitHub 仓库完整性

核验对象：<https://github.com/zkkk9555/local_model>（公开）
本地工作副本：`C:/Project/local_model/repo/`
核验时间：2026-10-31 05:17–05:40（Asia/Shanghai）
核验方式：只读。克隆到 `C:/Project/local_model/tmp/verify-a`，未删除/移动任何既有文件，未触碰 8091/8081/8086/8090 上的引擎。

---

## 结论（一句话）

**仓库本身完整、干净、可匿名访问（236 文件 / 3 commit / 931 KiB pack，无二进制、无权重、无密钥，与本地 `repo/` 的提交树逐字节一致，61 个"差异文件"100% 只是本地工作区的 CRLF）；但「照 RESTORE.md 从零重建」会在两处直接卡住——clone 目录层级与脚本硬编码 ROOT 冲突、`logs/` 未预建导致 `switch.sh` 起服前日志重定向即失败。**

判定：**仓库内容合格，文档/脚本的落地路径不合格（P1 × 2）。**

---

## 1. 仓库体量（克隆实测）

| 项 | 值 |
| --- | --- |
| 默认分支 | `main`（`git ls-remote --symref origin HEAD` → `ref: refs/heads/main`） |
| HEAD | `2c89c0dbb81596c140d0acfe54d1fbed45e3c60a`（= 本地 origin/main） |
| commit 数 | 3（`a59a23c` → `6ed0360` → `2c89c0d`，2026-10-31 05:11–05:13） |
| 受版本控制文件 | 236（`git ls-files`）；工作区文件总数也是 236，无多余未跟踪文件 |
| 目录分布 | `docs/` 56、`reports/` 112、`scripts/` 41、`tools/` 19、`config/` 3 |
| 工作区体积 | 4.1 MB（其中 `.git` 1.1 MB） |
| pack | 253 objects / 931.08 KiB；blob 238 个共 2,708,401 B |
| 最大单文件 | 138,827 B（`docs/archive/opus_1264436370549506065.json`） |
| 克隆耗时 | 2 秒（走 127.0.0.1:7897 代理） |

无 LFS、无 submodule、无 Git LFS 指针文件。

## 2. 与本地 `repo/` 的差异：**没有漏推**

`diff -r --exclude=.git repo tmp/verify-a` 共 64 行差异：61 个文件"同名但内容不同"，另 1 行是 `Only in repo/tools: __pycache__`（本地 pyc 缓存目录，`.gitignore` 已忽略，未入库）。

对这 61 个文件逐个做 `cmp <(tr -d '\r' <repo/x) <(tr -d '\r' <clone/x)`：**61/61 完全相同** ⇒ 差异只有行尾 CR。

证明仓库存 LF、本地工作区被改成 CRLF 的三组证据：

- `repo/config/控制台.cmd` 头部 4 字节 `40 65 63 68` 之后是 `0d 0a`；克隆里同一文件是 `0a`。
- `git cat-file -p HEAD:README.md | wc -c` = 3840，两边一致；`git hash-object README.md` == `git rev-parse HEAD:README.md` == `fe44de31456bf4f18842c6ae188ceb29eb32b0e2`。
- `git ls-files --eol` 在克隆里：`203 i/lf w/lf`、`31 i/none w/none`、`2 i/-text w/-text`，**没有任何 `w/crlf`**。

本地 `repo/` 的 `git status --porcelain` 为空、`HEAD == origin/main == 2c89c0d`、无 stash；本机 `core.autocrlf=input`（global 同），两边都没有 `.gitattributes`。

⇒ **GitHub 上的树 == 本地已提交的树，一行没漏推。** 本地看到的"差异"纯粹是 `autocrlf` 让 CRLF 工作区文件在 status 里显示为干净，与提交内容无关。

## 3. 仓库元数据与匿名可达性

`gh api repos/zkkk9555/local_model`：

    private=false   visibility=public   default_branch=main   license=MIT
    topics=[8gb-vram, llama-cpp, local-llm, ninfer, rtx-4060-ti, windows]
    fork=false   archived=false   has_issues=true   size_kb=0
    created_at=2026-10-30T21:12:12Z   pushed_at=2026-10-30T21:13:42Z

- **public ✅**、license **MIT ✅**、default_branch **main ✅**、topics 6 个已设 ✅、未归档、非 fork。
- `size` 报 0 KB 是 GitHub 向下取整（<1 MB），不是空仓库 —— 实际 931 KiB pack。

匿名可达性（**显式清空 Authorization 头**，不带任何 token）：

| 请求 | 结果 |
| --- | --- |
| `curl -H "Authorization:" .../main/README.md` | **200**，3840 B，`text/plain; charset=utf-8` |
| 同上 `RESTORE.md` | **200**，16925 B |
| `curl -H "Authorization:" https://api.github.com/repos/zkkk9555/local_model` | **200**（未鉴权可读） |

两份 raw 与克隆里的同名文件 `cmp` **逐字节相同**。

## 4. RESTORE.md 提到的路径逐条核对：**22/22 全部存在**

| 文档位置 | 路径 | 结果 |
| --- | --- | --- |
| RESTORE.md:56,119,140 | `scripts/serve2.sh` | ✅ 存在（7,441 B） |
| RESTORE.md:56,113-116,160,275 | `scripts/switch.sh` | ✅ |
| RESTORE.md:56 | `scripts/longctx.sh` | ✅ |
| RESTORE.md:56,141,275 | `scripts/console.sh` | ✅ |
| RESTORE.md:56 | `scripts/llama-*.sh` | ✅（llama-150k-run / llama-tier-run / llama-tier-test 三个都在） |
| RESTORE.md:140,233 | `tools/verify_all.sh` | ✅ |
| RESTORE.md:232,274 | `tools/restore_check.py` | ✅ |
| RESTORE.md:175 | `tools/chat_gateway.py` | ✅ |
| RESTORE.md:176 | `tools/longctx_proxy.py` | ✅ |
| RESTORE.md:178 | `tools/console.py` | ✅ |
| RESTORE.md:18,187 | `config/dsh-providers.example.yml` | ✅ |
| RESTORE.md:20,221 | `config/env.example.sh` | ✅ |
| RESTORE.md:221 | `docs/两条路终极对照-20261030.md` | ✅ |
| RESTORE.md:221 | `docs/上下文手册-20261030.md` | ✅ |
| RESTORE.md:225 | `docs/20261030-结论与索引.md` | ✅ |
| RESTORE.md:222 | `reports/上下文-150K-200K-实测-20261030.md` | ✅ |
| RESTORE.md:223 | `reports/极限优化-实测.md` | ✅ |
| RESTORE.md:224 | `reports/UEFI解锁-Windows-对首字影响.md` | ✅ |

**「RESTORE.md 提到但仓库里没有」的清单：空。**（RESTORE.md 之外文档里的断链见 §7 P2-3 / P2-4。）

顺带计数核对：`docs/*.md` = 22（`README.md:35` 写 22 ✅）；`reports/*.md` = 50（`README.md:36` 写 48 ❌，见 P3-1）。

## 5. 该不该公开：扫描结果

### 5.1 密钥：无

逐一跑过 `sk-[A-Za-z0-9_-]{16,}`、`ghp_[A-Za-z0-9]{20,}`、`gho_`、`AKIA[0-9A-Z]{16}`、`Bearer [A-Za-z0-9._-]{20,}`、`hf_[A-Za-z0-9]{20,}` —— **全 0 命中**。所有带 key 语义的赋值都是占位符：

- `config/env.example.sh:12-13` → `LOCAL_LLM_KEY=local` / `LLAMA_API_KEY=local`
- `config/dsh-providers.example.yml:10,29,42` → 只有 `apiKeyEnv:` 变量名，无值
- `scripts/asklong.sh:69`、`tools/bench_strata.py:15` → `Bearer local-any-key` / `Bearer local`
- 真 key 在 `llama8g/bundle/artifacts/api_key.txt`（本机 48 B），`llama8g/` 由 `.gitignore:7` 忽略，`git ls-files` 确认**仓库里没有该文件**

### 5.2 大文件：无

`git ls-files | grep -Ei "\.(exe|dll|gguf|zip|ninfer|7z|so|dylib|bin|safetensors|onnx)$"` → (none)。
`git ls-files -z | xargs -0 ls -la | awk '$5>204800` → 空。最大文件 138,827 B。

### 5.3 git 历史：也没有藏大件

    git count-objects -vH  →  in-pack 253 / size-pack 931.08 KiB / 无 loose object
    git cat-file --batch-all-objects --batch-check='%(objecttype) %(objectsize)'
      →  blob 238 个共 2,708,401 B；commit 3 个 1,003 B；tree 12 个 12,437 B

历史最大 blob 就是工作区最大那个 opus JSON（138,827 B）—— 只有 3 个 commit，不存在"提交过又删除"的大件。

### 5.4 隐私

- `C:/Users/Administrator/...` 出现在 20+ 处（`docs/DSH接入-本地模型-20261030.md:19,35,68`、`docs/本地模型清单-给DSH用.md:145,215`、`reports/DSH配置与验收.md:19,341` 等）。**属任务允许范围，不算泄漏**（想更好可换 `%USERPROFILE%`）。
- 真实内网地址 1 处：`reports/DSH-本地模型端到端实测.md:138` —— `http://192.168.0.241:8788/v1`。建议脱敏（P3-3）。
- 无邮箱、无手机号、无 cookie/session；`docs/archive/*.json` 只有公开的 HF 模型卡与 issue 元数据。

## 6. 链接与锚点

`README.md` + `RESTORE.md` 的相对链接**只有 3 条，全部有效**：`README.md:4` → `RESTORE.md` ✅、`README.md:60` → `LICENSE` ✅、`README.md:61` → `NOTICE.md` ✅。

- 两个文件里**没有任何 `#anchor` 形式的锚点链接**（全是外链或纯文本 `§x.y` 引用）⇒ 不存在"锚点失效"问题。
- 正文 `§` 引用逐条对得上：`§2` `§3` `§3.1` `§3.2` `§3.3` `§4` `§5` `§9` `§10` `§10.3` 都有对应标题（`§0`–`§10` + `10.1`–`10.4` 齐全）。
- 外链 5 条：3 个夸克网盘（`RESTORE.md` §3.1 引擎包、§3.2 2.09 GB 包等）+ `RESTORE.md:74` 的 GitHub Release tag `engine-v0.11.0-kvmem-20261008` + `RESTORE.md:152` 的 HF 仓库 `CaryPalmer/Ternary-Bonsai-2-27B-262k-GGUF`。夸克需登录，本次未做可达性判定（见 §8）。

---

## 7. 问题清单（文件:行号 + 怎么修）

### P1 —— 会让「从零重建」直接卡住

**P1-1 克隆层级与脚本硬编码 ROOT 冲突（最严重）**

证据链：

- `RESTORE.md:43`（§2 目标结构）要求 `C:/Project/local_model/` 下直接是 `scripts/ tools/ docs/ reports/`，即**仓库内容 == 项目根**。
- `RESTORE.md:271`（§10.3 第 1 步）却写 `git clone ... C:/Project/local_model/repo`，即**仓库内容在 repo/ 下一层**。
- `scripts/switch.sh:6-7`：`ROOT="C:/Project/local_model"; cd "$ROOT"`，随后 `scripts/switch.sh:36,46,54` 用 `bash scripts/serve2.sh`（相对 ROOT 解析）。
- `scripts/serve2.sh:17-18`：`ROOT=/c/Project/local_model`、`MODEL=$ROOT/models/...`。
- `tools/restore_check.py:13`：`ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))` —— ROOT 取自脚本自身位置。

实测后果（已复现，非推测）：在 `C:/Project/local_model` 下跑 `python repo/tools/restore_check.py`，ROOT 被解析成 `C:\Project\local_model\repo`，于是**连本机真实存在的文件也全报 MISSING**：

    [MISSING] engine/ninfer-serve-89.exe
    [MISSING] models/bonsai2_27b_ternary_ptq1_native_mtp.ninfer
    [MISSING] engine/cudart64_13.dll …（9 个 DLL 全 MISSING）
    [MISSING] llama8g/bundle/artifacts/api_key.txt
    [OK     ] scripts/serve2.sh / tools/*.py
    exit=1

而 `engine/`、`models/`、`llama8g/bundle/artifacts/api_key.txt` 在本机确实存在（engine/ 1.4 GB 含 9 个 DLL；models/bonsai2_27b_ternary_ptq1_native_mtp.ninfer 6,394,697,216 B；api_key.txt 48 B）。同理，按 `RESTORE.md:271` 克隆到 `repo/` 后执行 `bash scripts/switch.sh ninfer`，会在 `C:/Project/local_model/scripts/serve2.sh` 处 `No such file or directory` —— 全新机器的项目根没有 `scripts/`。

本机为何"看起来没事"：`C:/Project/local_model/` 下另有一份**独立于仓库的** `scripts/ tools/ docs/ reports/` 工作副本，`repo/` 只是它的快照，所以本地跑不暴露，换台机器立刻暴露。

怎么修（二选一，建议 A）：

- **A**：把 `RESTORE.md:271` 改成 `git clone https://github.com/zkkk9555/local_model.git C:/Project/local_model`（让仓库内容就是项目根，与 §2、`switch.sh:6`、`restore_check.py:13` 全部对齐），并在 §10.3 第 3 步明确 `models/` `engine/` 放在同一层。
- **B**：`tools/restore_check.py:13` 加 `--root` 参数并向上探测（`<脚本目录>/../engine` 不存在而 `<脚本目录>/../../engine` 存在就用后者）；`scripts/switch.sh:6` 与 `scripts/serve2.sh:17` 的 ROOT 改由 `BASH_SOURCE` 推 `dirname $0/..`，别硬编码 `C:/Project/local_model`。

**P1-2 `logs/` 未预建 → `switch.sh` 在起服前就失败**

- `scripts/switch.sh:36`：`nohup bash scripts/serve2.sh > logs/serve-switch-ninfer.log 2>&1 &`；`:46`、`:54` 同样重定向到 `logs/`。
- `logs/` 在 `.gitignore:8`，克隆后不存在；`RESTORE.md:53`（§2 结构）列了 `logs/`，但 `RESTORE.md:269-275`（§10.3 五步）**没有任何 mkdir**。
- 后果：全新机器上 `bash scripts/switch.sh ninfer` 先报 `logs/serve-switch-ninfer.log: No such file or directory`（重定向先于命令执行失败），引擎根本没被拉起，用户只看到 `ninfer NOT up`。
- 佐证：仓库里唯一建 `logs/` 的是 `tools/verify_all.sh:28`（`mkdir -p "$ROOT/logs"`），但那是验收阶段，晚于起服；另一处 `scripts/fetch_runtime.sh:7` 只建 `dl runtime`。
- 怎么修：`scripts/switch.sh:7` 的 `cd "$ROOT"` 之后加一行 `mkdir -p logs tmp`；`RESTORE.md:271` 之后补一步 `mkdir -p C:/Project/local_model/logs`。

### P2 —— 脚本/文档自洽性（不影响主链路，但照抄必失败）

**P2-1 `scripts/scan-pool.sh` 调两个不存在的 .ps1**

- `scripts/scan-pool.sh:6` 与 `:23` → `powershell ... -File scripts/kill-engines.ps1`
- `scripts/scan-pool.sh:9` → `powershell ... -File scripts/exp-start.ps1 -Port 8092 ...`
- 全仓库无任何 `*.ps1` ⇒ 该脚本必然失败。
- 修：补进 `scripts/`，或删掉 `scripts/scan-pool.sh`，或改成直接调 `taskkill` / `scripts/serve2.sh`。

**P2-2 `tools/cmp_bench.py` 的用法串指向不存在的 `tools/cmp_set.py`**

- `tools/cmp_bench.py:5,6,7`：`python tools/cmp_set.py --label ...`、`python tools/cmp_set.py --selftest`
- 文件实为 `cmp_bench.py`，`cmp_set.py` 不存在 ⇒ 照抄命令直接 `can't open file`。
- 修：把 `tools/cmp_bench.py:5,6,7` 的 `cmp_set.py` 全部改成 `cmp_bench.py`（改名后没同步 docstring）。

**P2-3 `docs/全家桶-地图与最终方案-20261030.md` 指向 4 篇不在仓库的 report**

- `:3` → `reports/部署方案-最终-4060Ti-8G.md`（仓库里其实是 `docs/部署方案-最终-20261030.md`）
- `:23`、`:147`、`:165` → `reports/评论区与竞品项目-洞察.md`
- `:163` → `reports/新开关扫描-实测.md`
- `:164` → `reports/新配方A-B-实测.md`
- 另：`reports/广度搜集-Strata与社区.md:5,117,164,178` 也引用 `reports/部署方案-最终-4060Ti-8G.md` 与 `reports/评论区与竞品项目-洞察.md`。
- 修：补这 4 篇进 `reports/`，或把这些行改成 `docs/` 里的现名，"未入库"就标注"（未入库）"。

**P2-4 两处"文件在自己 docs/ 里却写成 reports/"**

- `reports/解锁-研究-nvUEFI.md:296` → `reports/gpu-unlock-analysis.md`（实际在 `docs/gpu-unlock-analysis.md`，21,943 B）
- `docs/ninfer-analysis.md:288` → 写 `Report path: reports/ninfer-analysis.md`，而文件本身是 `docs/ninfer-analysis.md`（35,006 B）
- 修：改路径，或注明"本文件已归档到 docs/"。

### P3 —— 小瑕疵

**P3-1 README 报告计数少报 2 篇** —— `README.md:36` 写"48 篇实测报告"，实际 `reports/*.md` 有 **50** 篇（`README.md:35` 的"22 篇文档"是对的）。改 48 → 50。

**P3-2 `.gitignore` 少了 `config/env.local.sh`** —— `config/env.example.sh:3` 说"复制成 config/env.local.sh 后按需修改（env.local.sh 不入库）"，但 `.gitignore` 里只有 `.env`，没有这条规则 ⇒ 用户照文档操作后 `git status` 会冒出未跟踪文件，容易误提交。加一行 `config/env.local.sh`。

**P3-3 内网 IP 进了公开仓库** —— `reports/DSH-本地模型端到端实测.md:138`：`| wb | http://192.168.0.241:8788/v1 | ...`。改 `http://<另一台机器>:8788/v1` 或 `192.168.0.x`。

**P3-4 缺 `.gitattributes`，行尾由客户端 autocrlf 决定** —— 索引里 22 个 `.sh`、1 个 `.cmd`、39 个 `.py` 全是 `i/lf`。实测对照：把 `scripts/switch.sh` 转成 CRLF 后 `bash -n` 仍 exit 0、`bash crlf-switch.sh status` 也正常输出 —— **本机 Git Bash 容忍 CRLF，这不是硬故障**；但 Git for Windows 默认 `autocrlf=true` 的机器会全检出 CRLF，`.cmd` 与含 `tr -d` 的脚本体有风险。加 `.gitattributes`：`* text=auto eol=lf` / `*.sh text eol=lf` / `*.py text eol=lf` / `*.md text eol=lf` / `*.cmd text eol=crlf`。

**P3-5 `config/控制台.cmd` 是 LF 的批处理** —— `config/控制台.cmd:1-4`（`@echo off` / `chcp 65001 >nul` / `cd /d C:\Project\local_model` / `bash scripts/console.sh open`），索引里是 LF。只有 4 行短命令，风险低，但按 P3-4 加 `*.cmd text eol=crlf` 更稳。

**P3-6 `restore_check.py` 在中文控制台输出乱码** —— 实测输出 `[MISSING] engine/ninfer-serve-89.exe   ???`（cp936 控制台读 UTF-8 流）。在 `tools/restore_check.py` 顶部加 `sys.stdout.reconfigure(encoding="utf-8", errors="replace")`，或在 RESTORE.md 提示 `chcp 65001`。

**P3-7 `docs/archive/` 收了第三方全文** —— `docs/archive/opus_article1.txt`（96 行，B 站 cv53657756 全文）、`opus_articles.txt`、`opus_text.txt`、`docs/archive/hf/*.json`、`docs/archive/gh_assets.html`。`NOTICE.md:28` 只说"引用处标注了来源"，没点明这几份是**全文转载**。在 `NOTICE.md` 加一句"docs/archive/ 为核验留档的第三方公开内容快照，版权归原发布者"，或裁成摘录。

## 8. 修完后仍然"不可本地验证"的残余项

- `RESTORE.md:74` 的 Release tag `engine-v0.11.0-kvmem-20261008`、`RESTORE.md:152` 的 HF 仓库是否仍提供 `bonsai-bundle-win-x64.zip`：本次未做可达性验证（任务范围外），属"上游可能变"的固有风险。
- `llama8g/bundle/artifacts/api_key.txt` 是否随 `bonsai-bundle-win-x64.zip` 一起给出：仓库里没有该文件（正确），但 `RESTORE.md` §4 的解压步骤没交代它从哪来，而 `scripts/switch.sh:29,57`、`scripts/llama-150k-run.sh:4`、`scripts/llama-tier-run.sh:4` 都直接 `cat` 它 ⇒ 若包里没有，llama 路线第 4 行就失败。建议 §4 补一句："若包内无 `artifacts/api_key.txt`，写一个 48 字节随机串即可（llama-server 只校验非空）。"

---

## 9. 附：实际跑过的命令

    # 0) 定位
    pwd; ls -la /c/Project/local_model; ls -la /c/Project/local_model/repo; ls -la /c/Project/local_model/reports

    # 1) 本地仓库状态
    cd /c/Project/local_model/repo
    git remote -v; git branch -a; git log --oneline --all; git rev-list --count HEAD
    git status --porcelain | wc -l; git ls-files | wc -l; cat .gitignore
    git rev-parse HEAD origin/main; git status -sb; git stash list; git count-objects -vH

    # 2) 克隆（走代理）
    export HTTP_PROXY=http://127.0.0.1:7897 HTTPS_PROXY=http://127.0.0.1:7897
    git clone https://github.com/zkkk9555/local_model /c/Project/local_model/tmp/verify-a

    # 3) 体量
    cd /c/Project/local_model/tmp/verify-a
    git ls-files | wc -l; git rev-list --count HEAD; git branch -a; git symbolic-ref --short HEAD
    git ls-remote --symref origin HEAD; du -sh .; du -sh .git
    find . -path ./.git -prune -o -type f -print | wc -l
    git log --oneline; git count-objects -vH
    git ls-files -z | xargs -0 du -k | sort -rn | head -15

    # 4) 与本地对比（含 CRLF 判定）
    cd /c/Project/local_model
    diff -r --exclude=.git repo tmp/verify-a
    diff -r --exclude=.git --strip-trailing-cr repo tmp/verify-a
    git --no-pager diff --no-index --stat repo tmp/verify-a
    ( cd repo && find . -path ./.git -prune -o -type f -print | sort ) > /tmp/l1.txt
    ( cd tmp/verify-a && find . -path ./.git -prune -o -type f -print | sort ) > /tmp/l2.txt
    diff /tmp/l1.txt /tmp/l2.txt
    ( cd repo && git ls-files -z | xargs -0 sha256sum ) > /tmp/h1.txt
    ( cd tmp/verify-a && git ls-files -z | xargs -0 sha256sum ) > /tmp/h2.txt
    diff /tmp/h1.txt /tmp/h2.txt
    head -c 120 repo/config/控制台.cmd | xxd; head -c 120 tmp/verify-a/config/控制台.cmd | xxd
    git config --get core.autocrlf; git config --global --get core.autocrlf
    ls -la repo/.gitattributes tmp/verify-a/.gitattributes
    wc -c repo/README.md tmp/verify-a/README.md; file repo/README.md tmp/verify-a/README.md
    ( cd repo && git cat-file -p HEAD:README.md | wc -c; git hash-object README.md; git rev-parse HEAD:README.md )
    # 逐文件：cmp -s <(tr -d '\r' < "repo/$rel") <(tr -d '\r' < "tmp/verify-a/$rel")
    #   → checked=61  real_diffs=0

    # 5) 元数据 + 匿名可达
    gh --version; gh auth status
    gh api repos/zkkk9555/local_model
    gh api repos/zkkk9555/local_model --jq '{private,visibility,default_branch,license,topics,fork,archived,has_issues,size,created_at,pushed_at}'
    curl -sS -o /tmp/raw_readme.md   -w "%{http_code} %{size_download} %{content_type}\n" -H "Authorization:" https://raw.githubusercontent.com/zkkk9555/local_model/main/README.md
    curl -sS -o /tmp/raw_restore.md  -w "%{http_code} %{size_download} %{content_type}\n" -H "Authorization:" https://raw.githubusercontent.com/zkkk9555/local_model/main/RESTORE.md
    curl -sS -o /tmp/api.json        -w "%{http_code}\n" -H "Authorization:" https://api.github.com/repos/zkkk9555/local_model
    cmp /tmp/raw_readme.md  tmp/verify-a/README.md
    cmp /tmp/raw_restore.md tmp/verify-a/RESTORE.md

    # 6) RESTORE.md 路径核对
    for p in scripts/serve2.sh scripts/switch.sh scripts/longctx.sh scripts/console.sh \
             scripts/llama-150k-run.sh scripts/llama-tier-run.sh scripts/llama-tier-test.sh \
             scripts/llama8g_launch.sh scripts/restore-8091.sh \
             tools/verify_all.sh tools/restore_check.py tools/chat_gateway.py tools/longctx_proxy.py tools/console.py \
             config/dsh-providers.example.yml config/env.example.sh \
             docs/两条路终极对照-20261030.md docs/上下文手册-20261030.md docs/20261030-结论与索引.md \
             reports/上下文-150K-200K-实测-20261030.md reports/极限优化-实测.md reports/UEFI解锁-Windows-对首字影响.md \
             LICENSE NOTICE.md README.md .gitignore; do
      if [ -e "$p" ]; then echo "OK   $p"; else echo "MISS $p"; fi
    done
    ls docs/*.md | wc -l; ls reports/*.md | wc -l; ls scripts | wc -l; ls tools | wc -l; ls config | wc -l

    # 7) 敏感面扫描
    git ls-files | grep -Ei "\.(exe|dll|gguf|zip|ninfer|7z|so|dylib|bin|safetensors|onnx)$"
    git ls-files -z | xargs -0 ls -la | awk '$5>204800 {print $5, $9}' | sort -rn
    git cat-file --batch-all-objects --batch-check='%(objecttype) %(objectsize)'
    git rev-list --objects --all | git cat-file --batch-check='%(objecttype) %(objectsize) %(rest)' | sort -k2 -rn | head
    for pat in 'sk-[A-Za-z0-9_-]{16,}' 'ghp_[A-Za-z0-9]{20,}' 'gho_[A-Za-z0-9]{20,}' 'AKIA[0-9A-Z]{16}' 'Bearer [A-Za-z0-9._-]{20,}' 'hf_[A-Za-z0-9]{20,}'; do
      echo "== $pat"; grep -rInE "$pat" --exclude-dir=.git . ; done
    grep -rInE "(api[_-]?key|passwd|secret|token)[\"']?[[:space:]]*[:=][[:space:]]*[\"']?[A-Za-z0-9._-]{12,}" --exclude-dir=.git .
    grep -rInE "192\.168\.|10\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}|172\.(1[6-9]|2[0-9]|3[01])\." --exclude-dir=.git .
    grep -rIn "Users.Administrator" --exclude-dir=.git . | wc -l
    grep -rInoE "[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}" --exclude-dir=.git .
    cat config/env.example.sh; head -60 config/dsh-providers.example.yml; cat config/控制台.cmd

    # 8) 可执行性 / 引用一致性
    git ls-files --eol | awk '{print $1,$2}' | sort | uniq -c
    git ls-files --eol -- '*.sh'; git ls-files --eol -- '*.cmd'; git ls-files --eol -- '*.py'
    while read -r f; do bash -n "$f" || echo "SYNTAX FAIL $f"; done < <(git ls-files '*.sh')   # 22/22 通过
    python - <<'PY'                                                                          # 39/39 通过
    import ast, subprocess
    for f in subprocess.run(['git','ls-files','*.py'], capture_output=True, text=True).stdout.split():
        ast.parse(open(f, encoding='utf-8').read())
    print('ast ok')
    PY
    grep -rhoE '(scripts|tools|config)/[A-Za-z0-9_.-]+\.(sh|py|yml|cmd|ps1)' --include='*.sh' --include='*.py' --include='*.yml' --include='*.md' . | sort -u
    grep -rhoE '(docs|reports)/[^ )"<>]+\.md' --include='*.md' . | sort -u
    grep -n 'exp-start.ps1\|kill-engines.ps1' scripts/scan-pool.sh
    grep -n 'cmp_set.py' tools/cmp_bench.py
    grep -rn 'mkdir -p' scripts/*.sh tools/*.sh
    grep -n 'logs/\|mkdir\|^ROOT' scripts/switch.sh scripts/serve2.sh

    # 9) 功能验证（只读，不改文件）
    cd /c/Project/local_model && python repo/tools/restore_check.py; echo "exit=$?"
    python -c "import os;f=os.path.abspath('repo/tools/restore_check.py');print(os.path.dirname(os.path.dirname(f)))"
    python -c "import os;f=os.path.abspath('tools/restore_check.py');print(os.path.dirname(os.path.dirname(f)))"
    ls -la /c/Project/local_model/engine | head -8
    ls -la /c/Project/local_model/models | head -5
    ls -la /c/Project/local_model/llama8g/bundle/artifacts/

    # 10) 链接与锚点
    grep -nEo "\[[^]]*\]\([^)]*\)" README.md RESTORE.md
    grep -nEo "<https?://[^>]+>" README.md RESTORE.md
    grep -c '#[A-Za-z]' README.md RESTORE.md
    ls -la docs/gpu-unlock-analysis.md docs/ninfer-analysis.md

    # 11) CRLF 对照实验（写 /tmp，未动仓库）
    sed "s/$/\r/" /c/Project/local_model/tmp/verify-a/scripts/switch.sh > /tmp/crlf-switch.sh
    file /tmp/crlf-switch.sh; bash -n /tmp/crlf-switch.sh && echo "bash -n exit=0"
    bash /tmp/crlf-switch.sh status | head -6

---

## 10. 判定汇总

| 维度 | 结论 |
| --- | --- |
| 公开可匿名访问 | ✅ raw README/RESTORE + api 均 200，与克隆逐字节相同 |
| 默认分支 / License / topics | ✅ main / MIT / 6 个 topics / 未归档 / 非 fork |
| clone 是否完整 | ✅ 236 文件、3 commit、931 KiB pack、无 LFS/submodule |
| 与本地是否一致 | ✅ 提交树一致；61 个文件差异 100% 是 CRLF，无漏推 |
| RESTORE.md 路径是否齐全 | ✅ 22/22 存在，缺件清单为空 |
| 是否泄漏密钥/大文件 | ✅ 无 key、无二进制/权重、无 >200 KB 文件、历史无大件 |
| README/RESTORE 相对链接与锚点 | ✅ 3/3 相对链接有效，无锚点链接 |
| 脚本语法 | ✅ 22/22 .sh 过 bash -n，39/39 .py 过 ast.parse |
| **能否照文档从零重建** | ❌ **不能**：P1-1 目录层级冲突 + P1-2 logs/ 未预建 —— 两条都是"照抄命令必失败"，改文档/脚本即可 |

优先级建议：先修 P1-1（改 `RESTORE.md:271` 一行即可）、P1-2（两行 `mkdir -p`），再修 P2-3 的 4 条断链，其余按需。
