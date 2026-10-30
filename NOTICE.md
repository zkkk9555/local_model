# 第三方归属与许可

本仓库**不含任何二进制文件、模型权重、引擎**，只放脚本、文档、实测报告与校验值。
下面对运行这套东西所需的第三方件逐个说明归属。

## 引擎：NInfer（KVMem 分支）

- 上游：<https://github.com/1314521gjy/ninfer-fusion-kvmem>（Apache-2.0，497★）
- 它自己是这些项目的下游派生（见其 NOTICE）：`Neroued/ninfer`、`ashalliants/ninfer-3090`、`iamwavecut/ninfer-3090`（基线 0.11.0-rtx3090）、`tancau/ninfer-kvmem-ring`（KVMem 环）、`kvmem/kvmem-qw3`（策略层）
- 引擎产物为预编译二进制，按架构分发（sm_80 / sm_86 / sm_89 / sm_120a），本机用 sm_89
- **我们不分发引擎**，只给出下载地址与 SHA-256（见 RESTORE.md §3.1）

## 模型：Bonsai-2-27B（三元 PTQ1）

- 模型族：Bonsai-2-27B（Qwen3.8-27B 的三元重训版）
- 权重格式 `.ninfer`（PTQ1 三元 + MTP 投机头）；公共 HuggingFace 只有 PQ2 全件，PTQ1 件可从 ModelScope `q409640976/ninfer-kvmem-heretic-bonsai2-27b` 公开下载（见 RESTORE.md §3.2）
- llama.cpp 路线的 GGUF 来自公开仓库 <https://huggingface.co/CaryPalmer/Ternary-Bonsai-2-27B-262k-GGUF>
- **我们不分发权重**；权重的许可与使用条款由原作者/HF 仓库规定，使用前请自行确认

## llama.cpp

- <https://github.com/ggml-org/llama.cpp>，MIT
- 本机用的是社区打包的 `llama-server` build 10807（commit 96f6e49cdc，MSVC 19.44），随 HF 仓库的 `bonsai-bundle-win-x64.zip` 分发

## 我们自己的内容

- `scripts/`、`tools/`、`docs/`、`reports/`、`config/`：MIT（见 LICENSE）
- 文档里引用的 B 站视频内容、GitHub issue、HF 模型卡均为公开信息，引用处标注了来源
- `docs/archive/` 存有少量第三方公开内容的全文副本（B 站专栏 cv53657756、HF 模型卡、GitHub issue/PR 讨论），仅作离线引用证据，版权归原作者；作者要求可随时删除

## 免责

所有实测数字都在**本机特定硬件/版本/日期**下取得（RTX 4060 Ti 8 GB、驱动 616.92、Win11 26100、
引擎 sha256 见 RESTORE.md）。换卡、换驱动、换引擎构建都可能不同，未测的格子请当"未验证"，不要当"已验读数"。