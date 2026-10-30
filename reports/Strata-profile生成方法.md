# Strata `profile.bin` 生成方法（Qwen3.6-35B-A3B）

> 侦察时间：2026-10-30 09:27–09:35（Asia/Shanghai）
> 结论先行：**本机没有 make_profile.py（安装包没带 tools/），已从上游仓库下载到 `C:/Project/local_model/strata/tools/make_profile.py`。但它把 N_LAYER/N_EXPERT 写死为 48×512（DeepSeek V4.1-Flash 的形状），对 Qwen3.6-35B-A3B（41×256）直接跑会产出引擎拒收的文件——必须把层数改成 41。**
> 本次未启动/未停止任何引擎（8091/8081 未触碰），未修改 `C:/Project/local_model` 下任何配置脚本；只新增两个文件（下载的工具 + 一层薄封装）。

---

## 1. 本机现状（①：工具在不在）

| 事实 | 证据 |
| --- | --- |
| **`make_profile.py` 不在本机** | `find C:/Project/local_model/strata -iname '*make_profile*'` 零命中；`tools/` 下只有 mkcfg*/ladder*/gate_chat 等既有脚本 |
| **`profile.bin` 有，而且不止一个** | `app/control/data/expert-profile.bin` 196632 B、`expert-profile-coder.bin` 98328 B、`expert-profile-sycl.bin` 196632 B、`app/control/data/dsv41/profile-2.00.bin` / `profile-2.25.bin` 各 66048 B（`data/terminal/0.1.54/data/` 下有同一套镜像） |
| **引擎 help 确实指向这个工具** | `logs/engine-help.txt:181-182`：`--expert-profile P   R4.2e: pre-load the VRAM tier from a `profile.bin` (see tools/make_profile.py) instead of admitting on first use.` |
| **`--resident-cpu-experts` 的前置条件** | `logs/engine-help.txt:259-261`：`with mmap and a static profile, keep the experts the GPU cache does not hold resident in ordinary RAM`；二进制里对应报错串：`strata generate: --resident-cpu-experts requires --mmap-experts and a static --expert-profile` |
| **安装里残留了调用方的用法** | `data/terminal/0.1.54/serve/test_server.py:2479-2486`：`sys.path.insert(0, str(ROOT / "tools")); import make_profile; make_profile.N_LAYER = nl; make_profile.write_profile(path, [(i % nl, i // nl) ...], n_expert=ne)` —— 注意测试自己也在改 `N_LAYER` |
| **serve 端会读这个格式** | `data/terminal/0.1.54/serve/server.py:3268-3283` `profile_shape()`：magic `STRP` + `struct.unpack("<5I", head[4:])` 取 `(nl, ne)`，注释写明 "tools/make_profile.py's format" |

## 2. 上游源码（②：下载落地）

- 仓库：<https://github.com/Niko1221/Strata>
- 原始文件：<https://raw.githubusercontent.com/Niko1221/Strata/main/tools/make_profile.py>（6386 B，HTTP 200；`master` 分支同哈希）
- 已落地：`C:/Project/local_model/strata/tools/make_profile.py`
- **sha256 = `54864322d25f688144ce01217aed8a829a9c3dc1dad9610f2feb033d0e601027`**
- 文档：<https://raw.githubusercontent.com/Niko1221/Strata/main/docs/DETAILS.md>（156192 B）第 85-88 行原文：
  > More VRAM matters more than a faster GPU. Every extra GB holds about 700 more experts, and every expert on the GPU is one the CPU does not have to compute. `tools/make_profile.py` builds an expert profile from your own prompts: run the engine once with `--dump-routing trace.bin`, then see the tool's help. The shipped profile ranks every expert pair, so a trace changes the order only with `--reorder` (your trace's pairs first, then the base's, then the rest).
- 版本对齐风险：仓库没有 `v0.1.54` / `0.1.54` / `v0.1.55` 标签（三次 raw 探测均 404），`api.github.com` 因 IP 限流 403（`API rate limit exceeded for 207.32.218.91`），只能取 `main`。本机引擎是 0.1.54，属**同一大版本、非同一 commit**；引擎侧有版本闸门：`read_expert_profile: %s is a version %u profile but this engine reads version 1 - it was written by a different release's tools/make_profile.py or --expert-profile-save`，即格式版本 1 是稳定的，漂移只影响这个脚本的命令行细节。

## 3. 文件格式（读源码 + 读二进制双向确认）

`tools/make_profile.py:32-34,61-70`：

```python
ROOT = Path(__file__).resolve().parent.parent
N_LAYER, N_EXPERT = 48, 512
MAGIC, VERSION = b"STRP", 1

def write_profile(path, ranked, n_expert=N_EXPERT):
    table = [[-1] * n_expert for _ in range(N_LAYER)]
    for slot, (layer, e) in enumerate(ranked):
        table[layer][e] = slot
    with open(path, "wb") as f:
        f.write(MAGIC + struct.pack("<5I", VERSION, N_LAYER, n_expert, len(ranked), len(ranked)))
        for layer, e in ranked:
            f.write(struct.pack("<HH", layer, e))
        for layer in range(N_LAYER):
            f.write(struct.pack("<%di" % n_expert, *table[layer]))
```

即：**24 B 头**（`STRP` + 5×u32 = version, n_layer, n_expert, n_slots, n_pairs）+ **n_pairs × (u16 layer, u16 expert)**（= 排行，靠前的先进 VRAM）+ **n_layer × n_expert × i32**（layer→expert 的逆表 slot 号，未入选写 -1）。

实测对齐（这与"为什么文件是 8 B/对"的疑问对上了 —— 后半段是那张逆表）：
- `expert-profile.bin`：24 + 24576×4 + 48×512×4 = **196632** ✓
- `expert-profile-coder.bin`（48×256）：24 + 12288×4 + 48×256×4 = **98328** ✓
- 我生成的 Qwen3.6 全量版：24 + 10496×4 + 41×256×4 = **83992** ✓

## 4. 关键陷阱：这个工具是给 48 层模型写的

- `N_LAYER, N_EXPERT = 48, 512` 是**硬编码**；CLI 只有 `--n-expert`，**没有 `--n-layer`**。
- `read_profile()`（`make_profile.py:41-44`）会硬校验：`if (nl, ne) != (N_LAYER, n_expert): raise SystemExit(f"{path}: {nl}x{ne}, not {N_LAYER}x{n_expert}")`。
- 上游 `data/expert-profile.bin` 是 48×512；本机安装目录里那份同款也在。所以 `--n-expert 256` 单独用**只会得到 48×256**，对 Qwen3.6 是错的。

引擎会当场拒收 —— 从 `components/engine/0.1.54-windows-x86_64-cuda-cuda13/strata.exe` 抽出的字符串（同段还有 `read_expert_profile: ... does not start with STRP`、`the ranked list is truncated`、`pair %u is (layer %d, expert %d), out of range`）：

```
read_expert_profile: %s is %ux%u but this model is %lldx%lld - it is a profile for a different artifact
read_expert_profile: the header claims more ranked pairs than slots
```

**Qwen3.6-35B-A3B 的真实几何**（读本机 GGUF 头得来，非传闻）：
`model-data/models/qwen36-UD-Q4_K_XL/Qwen3.6-35B-A3B-UD-Q4_K_XL.gguf` → `general.architecture = qwen35moe`、`qwen35moe.block_count = 41`、`qwen35moe.expert_count = 256`、`expert_used_count = 8`、`context_length = 262144`、`embedding_length = 2048`。
→ 合法 profile 必须是 **41×256，10496 对**。

## 5. 准确命令（③：不执行，只写命令）

我为这一步加了一层薄封装 `C:/Project/local_model/strata/tools/make_profile_qwen36.py`（不改上游文件，只把两个模块级常量改成 41/256 再调它自己的 `main()`，因此 `ROOT` 仍解析到 `strata/`）：

```bat
cd /d C:\Project\local_model\strata

REM --- 0) 只读确认几何（可跳过；我已确认 = 41 层 x 256 专家） ---
REM     若换模型，先重新读 GGUF 的 qwen35moe.block_count / expert_count

REM --- 1)（可选，但强烈建议）用一条典型 prompt 抓路由 trace ---
REM     在现有启动参数里加一行，跑完退出即可，产物就是 trace：
REM       --dump-routing C:\Project\local_model\strata\data\trace-qwen36.bin
REM     trace 格式（make_profile.py:47-58）：循环 [i32 layer][i32 k][k x i32 expert][k x i32 weight]
REM     Qwen3.6 的 k = expert_used_count = 8

REM --- 2a) 无 trace：全量排行（每层轮转铺满，10496 对，引擎"profile 排满所有 pair"的那条路） ---
python tools\make_profile_qwen36.py --no-base --out data\expert-profile-qwen36.bin

REM --- 2b) 有 trace：让 trace 决定前排（--no-base 本身就是 trace 优先；--reorder 在无 base 时等价） ---
python tools\make_profile_qwen36.py --no-base data\trace-qwen36.bin --out data\expert-profile-qwen36.bin

REM --- 3) 引擎侧（改配置里的 args；命令只写不执行） ---
REM       --expert-profile data\expert-profile-qwen36.bin
REM     要走 --resident-cpu-experts，还必须同时给 --mmap-experts，且 profile 必须是静态的那份：
REM       --mmap-experts --resident-cpu-experts --expert-profile data\expert-profile-qwen36.bin
REM     （二进制原文：strata generate: --resident-cpu-experts requires --mmap-experts and a static --expert-profile）
```

预期输出（我已用同一封装在临时目录实跑验证，未碰生产）：

```
wrote ...\q36-blanket.bin: 10496 ranked pairs (0 from the base, 0 from the traces, 10496 filled in)
header (ver,n_layer,n_expert,slots,n_pairs) = (1, 41, 256, 10496, 10496)   size 83992
```

带 trace 时（合成 41 层 × k=8 的 trace 测的）：`328 from the traces`（= 41×8），前 4 名 `(0,0)(0,1)(0,2)(0,3)`，与 trace 一致。

## 6. 另一条引擎原生路线（可能更省事，但我不能启动引擎所以未验证）

引擎自己会写合规 profile：`--expert-profile-save P`（0.1.36+，#477）"save what the adaptive tier learned (the experts in VRAM, then the routing counted since the start) as a profile at P, on QUIT and every --expert-profile-save-every MIN minutes (default 10; 0 = on QUIT only)"（`logs/engine-help.txt:183-186`）。二进制侧对应 `write_expert_profile: ...` 与 `strata serve: expert profile saved to %s (%s)`。它的几何由引擎按实际模型写，**天生是 41×256，绕开 N_LAYER 硬编码**。
建议路线：先用 `--expert-profile-save data\learned-qwen36.bin` 跑一轮真实流量 → 拿到 41×256 的 learned profile → 之后 `--expert-profile data\learned-qwen36.bin` 直接冷启动；`make_profile.py` 则用来在有 trace 时做"人工排序"。

## 7. 自检记录（可复现）

1. `python tools/make_profile_qwen36.py --no-base --out %TEMP%\q36-blanket.bin` → 10496 对，83992 B，头 `(1,41,256,10496,10496)`
2. 合成 trace（41 层，k=8）→ `328 from the traces`，排行头部是 trace 的 pair
3. 用安装自带的 `serve/server.py` 的 `profile_shape()` 反读（**引擎同一套解析**）：`q36-blanket.bin -> (41, 256)`、`q36-trace.bin -> (41, 256)`、`app/control/data/expert-profile.bin -> (48, 512)` ✓
4. 未做：真实引擎启动、`--expert-profile` 加载 41×256 的实跑（硬约束：不得启停引擎）

## 8. 未核源 / 待验证

- 【未核源】"41×256 能被 0.1.54 引擎直接吃下" —— 只证明了**格式与几何匹配**（引擎的几何校验串 + serve 的解析器 + 我生成的头部三方一致），**没有实跑加载**。若要一次确认：启动时看引擎日志 `strata generate: profile %s: %zu ranked pairs, built for %lld slots` 与 `pre-filled %lld of %lld slots from the profile in %.1f s`。
- 【未核源】`--dump-routing` 产出的 k 是否恒为 8（GGUF 的 `expert_used_count=8` 是模型侧数字；trace 里 k 由引擎写，脚本按读到的 k 解析，两者不冲突，但我没跑过引擎所以未见真实 trace）。
- 【未核源】若哪天引擎对 Qwen3.6 报 `%ux%u but this model is %lldx%lld`，**以后面那个 `lldx%lld` 为准**即可自我校正（我给的 41×256 来自 GGUF 头，不是引擎自报）。

## 9. 本次落地的文件

| 文件 | 说明 |
| --- | --- |
| `C:/Project/local_model/strata/tools/make_profile.py` | 上游原样下载，sha256 `54864322…e601027`，6386 B |
| `C:/Project/local_model/strata/tools/make_profile_qwen36.py` | 新增封装：`make_profile.N_LAYER, make_profile.N_EXPERT = 41, 256` 后调用其 `main()` |
| `C:/Project/local_model/strata/tools/make_profile.py.provenance.txt` | 来源 URL / 哈希 / 抓取时间 / 分支探测结果 |
