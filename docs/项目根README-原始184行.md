# 本地大模型部署项目（RTX 4060 Ti 8 GB / Windows 11）

> 目录：C:/Project/local_model　｜　引擎：NInfer KVMem sm_89　｜　模型：Bonsai-2-27B 三元 PTQ1（作者官方件）
> 本文件是这套部署的唯一入口：从一台裸 Windows 到能跑起来，需要的东西、每个文件的来源与校验值、启动方法、验收标准、已知边界，全在这里。

---

## 0. 结论速览

| 项目 | 数值（本机实测） |
| --- | --- |
| 模型 | Bonsai-2-27B（Qwen3.8-27B 的三元重训版），27,320,726,528 参数 / 248,320 词表 / 5120 维 / 262,144 训练上下文 |
| 量化 | PTQ1 三元（+ MTP 投机头），文件 6,394,697,216 B = 5.96 GB |
| 常驻显存 | 权重 5.94 GiB（开 MTP）/ 5.52 GiB（不开）+ 运行期 780 MiB |
| 显存占用实测 | 7,074 / 8,188 MiB（余量 205 MiB） |
| 解码速度 | 可预测文本（计数/代码/结构化）98–107 tok/s；自由散文 42–50 tok/s |
| 预填充 | 1,000 tok/s @1k、946–1,011 @26–37k、899 @56k、704 @113k |
| 可靠上下文 | 由 KV 池决定：fast 档 32,000 token、long 档 64,000 token（不是 262k！见 §6） |
| 冷启动 | 62 s（含一次路由标定）；热启 4 s |
| 前缀缓存 | 命中 67k token 时首字从 84.2 s 降到 0.54 s |

---

## 1. 这台机器（实测）

| 部件 | 型号 / 规格 | 与本项目的关系 |
| --- | --- | --- |
| CPU | AMD Ryzen 7 7800X3D 8C/16T 4.2 GHz | 引擎解码阶段是 host-bound，CPU 单核性能直接决定 tok/s |
| 内存 | 31.1 GB DDR5-6000（2×16） | host KV 层、页回迁都吃内存；建议 32 GB 起步 |
| GPU | NVIDIA RTX 4060 Ti 8 GB（AD106, 10DE:2803, sm_89, 288 GB/s, 34 SM） | 算力够用，显存是唯一瓶颈；显示器由 AMD 核显驱动，独显不占显示开销 |
| 驱动 | NVIDIA 616.92（CUDA UMD 13.4） | 引擎自带 CUDA 运行时，**不需要装 CUDA Toolkit / cuDNN** |
| 系统 | Windows 11 Pro 26100 x64，Secure Boot 关 | 纯 ASCII 路径是硬要求（中文路径会让引擎抛 json UTF-8 异常） |
| 磁盘 | C: 185 GB 可用 | 引擎 1.4 GB + 模型 6.0 GB + 归档 15 GB |

---

## 2. 目录结构

```
C:/Project/local_model/
  engine/           引擎 + 9 个运行期 DLL（约 1.4 GB）
    ninfer-serve-89.exe   主程序（sm_89 = Ada，即本机架构）
    cublas64_13.dll / cublasLt64_13.dll / cudart64_13.dll   CUDA 运行时
    avcodec-63 / avformat-63 / avutil-61 / swscale-10 / swresample-7   FFmpeg 运行库
    libcurl-x64.dll       HTTP 客户端
    SHA256SUMS.txt        作者整套发布包的清单（含 runtime DLL 的官方哈希）
  models/
    bonsai2_27b_ternary_ptq1_native_mtp.ninfer    当前使用（作者官方件）
    _archive/                                     可删（见 §3.5）
  scripts/          启动与测试脚本（serve.sh 是入口）
  logs/             历史日志
  docs/             分析报告与部署文档
  tools/ffmpeg/     便携 ffmpeg + ffprobe（含 DLL，从本机 LosslessCut 复制而来）
  transcripts/      B 站视频转写稿（研究用，与推理无关）
```

---

## 3. 从零到跑起来：完整文件清单

> 只有 §3.2（引擎）与 §3.3（模型）是推理必需的；其它都能缺。

### 3.1 系统层：不需要安装，但必须满足

| 项 | 要求 | 本机状态 |
| --- | --- | --- |
| GPU 架构 | sm_80 / sm_86 / sm_89 / sm_120a 之一（引擎按架构分发） | sm_89 ✔ |
| 显存 | ≥ 8 GB（8 GB 是官方四档里最小的一档） | 8,188 MiB ✔ |
| 内存 | ≥ 16 GB，建议 32 GB | 31.1 GB ✔ |
| NVIDIA 驱动 | ≥ 570 系（含 CUDA UMD 13.x）。**不要**为了跑这个装 CUDA Toolkit | 616.92 ✔ |
| VC++ 运行库 | MSVCP140.dll / MSVCP140_ATOMIC_WAIT.dll / VCRUNTIME140.dll / VCRUNTIME140_1.dll（来自 VC++ 2015-2022 Redistributable） | System32 里已有 ✔ |
| 路径 | 引擎与模型所在路径必须**纯 ASCII 且不含空格**（C:/Project/local_model 满足） | ✔ |
| 文本模式 | 需要 UTF-8 终端或写日志到文件（控制台默认 GBK 会乱码，不影响运行） | — |

### 3.2 引擎（必需，1.4 GB）

来源：GitHub Release `engine-v0.11.0-kvmem-20261008`（仓库 1314521gjy/ninfer-fusion-kvmem）

| 文件 | 字节 | SHA-256 | 来源 |
| --- | --- | --- | --- |
| ninfer-serve-89.exe | 801,324,544 | 3b6f9af936a1e20520c3de3a4185f627ba59481139659cf3104bdead815ef6e4 | Release 资产 `ninfer-serve-89.exe`；与作者 quant kit 里 `engines/sm89/infer-serve.exe` 逐字节相同 |
| cudart64_13.dll | 551,024 | b00ca6f53699120da815bf3e06e2e4285fae2f201235b883dcbb50eec51e2a2a | PyPI `nvidia-cuda-runtime-cu13` 13.3.29 win-x64 |
| cublas64_13.dll | 51,870,320 | f1d500d0cd892f5b8c6b6cdbffd82d0c55d5f5427215668e7ceb55aeeccc1b63 | PyPI `nvidia-cublas-cu13` 13.5.1.27 win-x64 |
| cublasLt64_13.dll | 460,301,424 | b592cd016d7673e9cb97716a22b27c4010ee635377a3ba28f37070a9bdb76a68 | 同上 |
| avcodec-63.dll | 91,810,816 | 1ab43ac33e92aad9f29e82e6b4f57e06ff3537097d71908786d1388a6032ea45 | BtbN FFmpeg-Builds `ffmpeg-n9.0-latest-win64-lgpl-shared` |
| avformat-63.dll | 23,003,136 | 1082bdcb0fd3bb62205a2be123350f2f4fa67a1478bb0162989d65c1463d29ef | 同上 |
| avutil-61.dll | 3,025,408 | aabe139afdf6c3277d490faddaac739c8ed616739bd9287cd53a7a56ba919022 | 同上 |
| swscale-10.dll | 2,343,936 | c10c48b8003ed5730b3ece95009a2db5c5e49c40c0a0b07c3b305ddc7fcc01f4 | 同上 |
| swresample-7.dll | 747,008 | dc8594e1c7cc627a2f2a1510c98a6b823a8dff95455684aafcfd3514dc12eb93 | 同上 |
| libcurl-x64.dll | 3,722,344 | d8bfa3e3ed29c29dc4db02afda0355f4a67990e93a3a4ecb089bf09a6071131d | curl.se `curl-8.23.0_6-win64-mingw` |
| SHA256SUMS.txt | 6,273 | 9cae2eab9f4ae6c2782534da4226e5b95d2e5835440b8863b33a2061b05b2f2a | 同一 Release；是作者整套发布包的清单，可用于核对 DLL |

三个 CUDA DLL 与作者清单逐字节相同；五个 FFmpeg DLL 与 libcurl 是不同构建（大版本号相同、ABI 兼容），哈希与作者清单不同。
**注意：官方 Release 只发三个 exe，不发任何 DLL**，这 9 个 DLL 必须自备，缺一个就是启动报 0xC0000135。

### 3.3 模型（必需，6.0 GB）

| 文件 | 字节 | SHA-256 |
| --- | --- | --- |
| models/bonsai2_27b_ternary_ptq1_native_mtp.ninfer | 6,394,697,216 | 5c4486c8a52687e3f62072c7dd2a320546d0e00d1c019bf137eb02cc944e21b8 |

内部元数据（引擎 /v1/models 可查）：ftype `bf16+fp32+ptq1_g128_fp16+q8_g32_fp16`、n_params 27,320,726,528、n_embd 5,120、n_vocab 248,320、meta.size 6,381,571,072、context_window 262,144。
公共渠道（HuggingFace）**没有**这个 PTQ1 件，只有 8.87 GiB 的 PQ2 完整件；8 GB 卡装不下 PQ2。PTQ1 仅存在于作者的网盘分享里。

### 3.4 工具链 / 杂项（可选，只用于测试与研究，不参与推理）

| 项 | 版本 | 用途 |
| --- | --- | --- |
| Python | 3.12.10（C:/Users/Administrator/AppData/Local/Programs/Python/Python312） | 跑 scripts/ 下的测试与抓取脚本 |
| numpy | 3.x | 测试脚本 |
| faster-whisper + ctranslate2 + onnxruntime | 1.2.1 / 4.8.4 | 中文视频转写（B 站研究用） |
| yt-dlp | 2026.10.26 | 下载视频音频 |
| ffmpeg / ffprobe | n8.0（tools/ffmpeg，含 av*/sw* DLL） | 音频抽取、视频分析 |
| git / node | 2.56 / 24.19 | 克隆参考仓库（本机已有，非必需） |

### 3.5 可直接删除的大件（省 15 GB）

| 文件 | 大小 | 说明 |
| --- | --- | --- |
| models/_archive/Ternary-Bonsai-2-27B-ninfer-v3.ninfer | 8.9 GB | 从 HF 下载的 PQ2 完整件，我们当初裁它的原料；已不再需要 |
| models/_archive/ours-repack-ptq1.ninfer | 6.0 GB | 我早期用脚本自己重打包的 PTQ1（功能等价、但哈希与官方件不同），已被官方件取代 |

---

## 4. 启动

```bash
cd C:/Project/local_model
bash scripts/serve.sh                 # 默认 fast 档：MTP draft-4 + 32k 池，解码 98/42-50
PROFILE=long bash scripts/serve.sh    # long 档：不开投机 + 64k 池，解码 31.7，长文更稳
PORT=8092 bash scripts/serve.sh       # 换端口
```

服务地址 http://127.0.0.1:8091/v1（OpenAI 兼容）。脚本里已设好的 5 个环境变量是硬性要求：
`NINFER_KV_WINDOW=16384`（环语义的门）、`NINFER_KV_RETRIEVE=8192`（缺了会静默答错）、`NINFER_HOST_PAGEABLE=1`、`NINFER_KV_REUSE_HOSTBACKED=1`、`NINFER_TERNARY_PTQ1_FAST=1`。

验活：`curl http://127.0.0.1:8091/v1/models`（返回 context_window 262144 且 id=bonsai2-27b）。

---

## 5. 验收清单（每次改动配置都要过一遍）

1. 启动日志出现 `INFO loading weights | 5.94 GiB`（开 MTP）或 5.52 GiB（不开）。
2. 启动日志出现 `INFO capacity | KV <X> tokens, rk2v4-e8, explicit | pages a/b | runtime <R> MiB | free <F> MiB`；**X 就是可靠题面上限**，F 要 > 200 MiB。
3. 日志出现 `[ninfer] reuse host-backed: on`。
4. `GET /v1/models` 返回 200，context_window=262144。
5. 同一会话第二轮命中前缀缓存：`cache %` ≥ 90%，TTFT 掉到百毫秒级。不满足就是缓存的 host-backed 层没生效。
6. 长文针测试：把唯一针（例如 7391-XQ）埋进 30k+ token 的正文中段，提问能答对。

---

## 6. 已知边界（比速度更重要）

- **上下文不是 262k，是池**。`--kv-capacity` 才是可靠题面上限（fast 档 32,000 / long 档 64,000）。超池时引擎可能返回 HTTP 200 + 看似合理的错误答案，只在开始 30 s 内告警一次。
- **`--kv-capacity` 的单位是 token，不是页**。
- `PROFILE` 两档都必须在 `--max-concurrency 1` + `--max-shared-prefixes 0` 下跑，否则实例可能被打砖。
- 显存不够时的操作顺序：先关别的 GPU 程序（QQNT/GameViewer/OBS 各占几十到几百 MiB）→ 缩池 → 关 MTP。
- 不要开 `dflash2`（小卡规则：≤10 GB 只用 `--spec mtp`）。
- 权重层固定在 64 token/页；`--kv-dtype` 用 `rk2v4-e8`（+0.30% PPL 级别代价换 1.86 倍池容量）。`k8v4` 会让池腰斩，别用。

---

## 7. 故障排查

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| 启动 0xC0000135 | 缺 DLL | 对照 §3.2 补齐 |
| `invalid UTF-8 byte` / json type_error | 路径含中文 | 挪到纯 ASCII 路径 |
| `--kv-headroom-mib requires --kv-capacity auto` | 两参数互斥 | 显式池时去掉 headroom |
| 引擎启动即退、报 active KV snapshot page ownership is not ordered | `--max-shared-prefixes` 非 0 | 设回 0 |
| 答非所问但 HTTP 200 | 题面超池（或漏了 NINFER_KV_RETRIEVE） | 缩题面 / 加大池 / 确认 retrieve |
| 只有 2 个 token 就停 | KV dtype 用了行粒度 | 换回 rk2v4-e8 / k8v4 |

---

## 8. 相关文档

| 文件 | 内容 |
| --- | --- |
| docs/部署完成-实测报告.md | 完整实测记录：速度扫描、draft 深度对比、上下文边界实验、与竞品 toolkit 对照 |
| docs/部署方案-4060Ti-8G.md | 最初的方案设计（含解锁收益评估） |
| docs/ninfer-analysis.md | 引擎源码级分析 |
| docs/gpu-unlock-analysis.md | GPU 解锁项目分析（本阶段不采用） |
| docs/视频理解方案.md | B 站视频批读方案（插件对比 + 自建管线） |
