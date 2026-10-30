# 解锁研究：nv-uefi-unlocker（UEFI 预驱动解锁）对本机 RTX 4060 Ti 8G 本地大模型的作用与风险

> 目标机器：Windows 11 Pro 26100 · AMD Ryzen 7 7800X3D（核显 Radeon 2CU 带屏）· 32GB DDR5-6000 · **RTX 4060 Ti 8GB（AD106，10DE:2803，sm_89，34SM，288 GB/s，驱动 616.92）**
> 模型/引擎：NInfer `ninfer-serve-89` + Bonsai-2-27B ternary PTQ1（5.96 GB 权重，rk2v4-e8 KV，MTP）
> 本文证据分级：**【文档】**= 项目 README/issue/社区报告原文 【实测·本机】= 我们在本机跑出来的数 【推断】**= 由代码/算术推出、未在解锁态实测 【未验】= 没有任何证据、必须实测才能定
> 采集时间：2026-10-30。外部访问均走 HTTP(S)_PROXY=127.0.0.1:7897。显示器拓扑、nvidia-smi、CIM 读数均为当日在本机实测（§8）。

---

## 0. 一页结论（**NO-GO：不刷**；8 行）

1. **三个数字先看：decode +0、显存/上下文 +0、prefill 上限 +16.3%（乐观）／+8.8%（保守）。** 这是**实测反推**出来的上限，不是估算区间（§7.2）。
2. **为什么只有 +16%**：`--no-prefill-a8`（强制全 A16）在 8k 提示上把 prefill 从 **1.10k → 396.7 tok/s（慢 2.77×）**、24k 从 **1.03k → 386.2（慢 2.66×）**（`logs/lim-FK.log:114` / `logs/lim-NOA8.log:117`；`logs/lim-FK.log:298` / `logs/lim-NOA8.log:309`）⇒ 默认 prefill 有 **63.6% 的时间已经在不加锁的 int8(A8) 通路上**，只有 **36.4%** 是可能被钳的 A16 段。解锁只买得到这 36.4%。
3. **换算**：`1/(0.636 + 0.364/1.624) = 1.163×`。8k 1.10k → **~1.28k**；37k 969 → **~1,127**；37k TTFT **38.9 → ~33.5 s（省 5.4 s）**；扣掉不可加速的 attention/KV（u≈0.15）保守只有 **+8.8%**，TTFT 省 ~3 s。
4. **所以 NO-GO**：为 37k 题面省 5.4 s 首字，去换「每次冷启动 5 s 倒数 + 易失 + 驱动更新要重刷 + 重启中断 8091/8081 + 只能『重启』进不能关机 + 本机型无先例」，性价比不成立。§13 的 GO 线要求 A16 段 ≥60%，实测只有 36.4% ⇒ **该线已不可能达成**。
5. **能不能用：能，但能跑 ≠ 值得跑。** UEFI 应用、Windows 11 原生，不用双系统/WSL2；`BiosFirmwareType=Uefi`、`Confirm-SecureBootUEFI=False`、系统盘 GPT；2803 在矩阵里是 ✅ 实测级（PR #5：FP16 46.78→75.28 TFLOPS）。
6. **三个零的物理原因**：decode 是 288 GB/s 带宽墙（22.2 ms/次权重遍历 ⇒ 45.1 tok/s 下限）+ host 51.4 ms/round；显存/上下文是**容量**问题，解锁只动 tensor issue rate（算力），不动容量也不动带宽。
7. **已有红利别丢**：面板在 AMD 核显、`display_active=Disabled`（§8 实测）⇒「推理卡不驱动显示器」那 18~20% 首字红利**已经在手**；别把显示器插到独显上。
8. **回滚一句话**：断电冷启即回出厂；判据 = `ssdiag` 判定 → GEMM 微基准回 ~46.8 TFLOPS → 37k prefill 回 969 → `nvidia-smi` throttle_reasons。

---

## 1. 三句话结论（**不刷**，理由三条）

1. **解锁不增加一字节显存。** 卡还是 8 GB，我们最大的瓶颈（KV 池 32,000 / 64,000 token、超池要用分段注入）**完全不变**。指望解锁「能开更大上下文」是错的：解锁动的是 tensor issue rate（算力），不是容量、不是带宽（288 GB/s 不变）。
2. **decode 注定零收益。** 权重 6.3947 GB ÷ 288 GB/s = **22.2 ms/次全量权重遍历 = 45.1 tok/s 的物理下限**；本机实测自由散文 42–50 tok/s 正贴这条线，MTP 投机时 98–107 tok/s 由 host 侧 51.4 ms/round 决定。两条墙（带宽、host）都不在解锁的作用面上。详见 §7。
3. **prefill 有真收益，但量级只有 +8.8~16.3%（实测推导，§7.2），不是 +25~55%。** 原因是我们的 prefill **不是**全跑在已满速的通路上：工程里三元 SwiGLU（占比最大的一类 GEMM）**在代码层面就是 A16 = BF16 输入 / FP32 累加**，正好是被钳的那条路（`src/ops/linear_swiglu/../wrapper/linear_swiglu.cpp:59-67`：「the ternary SwiGLU route is A16 by construction」）。A16 段确实吃解锁，但**它只占 prefill 时间的 36.4%**（8k/24k 两臂实测反推），所以解锁只买得到 1/(0.636+0.364/1.624)=**+16.3% 上限**；A8 那 63.6% 本来就没被钳。

**一句话判据**：解锁值不值，等于问「我们 prefill 的时间里有多大比例花在 FP32 累加的 BF16 MMA 上」。这个比例**已经测出来了：36.4%**（§7.2），上限随之封顶在 +16.3%。

---

## 2. 先修正四条既有判断（含我自己上一轮的两处错）

| # | 流行说法 | 逐条核对后的事实 | 依据 |
| --- | --- | --- | --- |
| 1 | 「NInfer prefill 走 int8/三元整数通路，所以解锁没意义」 | **只对了一半**。PTQ1_0 的**线性层**在宽 T（≥33/64 token）确实走 int8 IMMA（`src/ops/linear/linear.cpp:111-125`），但**三元 SwiGLU 这条最大头是 A16 by construction**（`src/ops/wrapper/linear_swiglu.cpp:59-67`，另有 `:178-188` 同注释），单亲 attention 投影的整数策略也被降级为 A16Only（`src/ops/wrapper/attn_input_proj.cpp:113-116`：「No single-parent qtype registers an integer-activation route … the integer policies read as A16Only there」）。⇒ prefill 是**混合通路**，A16 那一块吃得下解锁。 | 【文档·代码】 |
| 2 | 「963 tok/s ≈ 52 TFLOPS，已经超过解锁后的 FP16-FP32acc 峰值，所以肯定在整数通路」 | 算术对不上后半句：52 TFLOPS **超过**的是**解锁前**的 46.78–47.24（PR #5、本卡同款 2803），但**低于**解锁后的 75.28–76.71。它只证明「今天不全走 A16」，**不能**证明「走 A16 也没收益」。真正的上界算法是 §7 的 f 模型。 | 【推断】 |
| 3 | 「用 `--prefill-cublas` 切到 FP16 GEMM 就能吃到 +25~55%」 | **本引擎没有这条路**。全树 cuBLAS 只有两处：`src/ops/linear_swiglu/q4cublas/w4_cublas_prefill.cu:398` 用 **CUBLAS_COMPUTE_32I**（int8×int8→int32，即整数通路），`src/ops/linear/gguf/ggml_bridge.cu:501` 用 **CUBLAS_COMPUTE_32F**（gguf 反量化，FP32 速率档，更慢）。**全树没有 CUBLAS_COMPUTE_16F**，且 `--prefill-cublas` 只对 Q4 家族权重注册（`wrapper/linear_swiglu.cpp:75-88` 要求 `gate_up_rows==34816 && input_rows==5120`），三元 PTQ1 权重根本递不进 cuBLAS。想骑解锁只能新写 kernel 或换引擎。 | 【文档·代码】 |
| 4 | 「用 A/B 反解 f，就能算出解锁收益」（**我自己上一轮的框架**） | **该框架已被实测废掉**。反解式 `q=(T_B/T_A−1)/0.87` 假定 int8 只比 A16 快 1.87×，此时 T_B/T_A 最大 1.87；实测 **2.66–2.77 超出模型域**（`logs/lim-FK.log:114` vs `logs/lim-NOA8.log:117`）⇒ f 不可辨识。改用「A8 时间占比 = 1−1/R」直接算上界：解锁 ≤ **1.163×**。 | 【实测】§7.2 |

> 附带修正：我在上一轮（task-2，Zagitta/gpu-unlock 的 Linux kmod 路线）给过「量化 GGUF 上约 0%」。那条结论**对 llama.cpp 仍然成立**（它用 `CUBLAS_COMPUTE_16F`，即 fp16 累加＝满速档，`ggml-cuda.cu:1451`），但**不能平移到 NInfer**——NInfer 的是 FP32 累加。两者前提不同，勿混。

## 3. 本机基线（全部实测，未启动任何 GPU 引擎，引自项目 README §0 / 既有报告 / 日志）

| 指标 | 数值 | 出处 |
| --- | --- | --- |
| 权重文件 | `bonsai2_27b_ternary_ptq1_native_mtp.ninfer` 6,394,697,216 B（5.96 GB）/ 27,320,726,528 参数 | models/ 实测 |
| prefill 1k / 26–37k / 56k / 113k / 200k | **1,000 / 963（README §0）、969–970.8（`logs/serve_long3.log:343`，prompt 37,641，TTFT 38.8 s）/ 899 / 704 / 552 tok/s** | README §0、超池实测、日志 |
| TTFT @37,468 token | **38.9 s**（37,468 ÷ 963） | 算术复核 |
| decode（MTP，可预测文本） | 98–107 tok/s | 日志 `req#1 done … decode 76.7 tok/s, mtp 263/270 (97.4%)` 一类 |
| decode（自由散文，无投机收益） | 42–50 tok/s | README §0 |
| host / GPU 时间（decode） | host 51.4 ms/round vs GPU 0.62 ms | docs/部署方案-4060Ti-8G.md:141 |
| 显存 | 7,074 / 8,188 MiB；KV 池 32,000（快）/ 64,000（长） | README §0 |
| 驱动 / 固件 | 616.92（CUDA UMD 13.4）；`BiosFirmwareType=Uefi`；`Confirm-SecureBootUEFI=False`；系统盘 GPT | 本机 powershell 实测 |
| 显示拓扑 | **面板在 AMD 核显上**（Radeon 2560×1440），4060 Ti 无分辨率＝无显示器；另有 GameViewer 虚拟显示适配器 | `Win32_VideoController` 实测 |

> 显示拓扑这一条**推翻了任务书的前提**（「这张卡同时是显示卡」）。本机是**混合输出**（核显带屏、独显算力），对应 nv-uefi README 的「混合模式」行，风险比「独显直连」低：事务期间控制台在核显上，**黑屏风险显著下降**。

## 4. 解锁到底解锁什么（机制，逐条带出处）

**【文档】** `nvuefi.md:308-325` 原理：PLM（Protected Lock Mask）出厂默认 `0xffffff8f`＝只有重量级安全固件能写，宿主/驱动写选择器会被静默丢弃。工具在 UEFI DXE 窗口（NVIDIA 驱动绑定之前）跑完整固件事务：claim（断 GOP/驱动、独占）→ SEC2 scrubber（BSI handoff 1→3）→ FWSEC-FRTS（WPR2）→ 签名 Booter 启动 GSP-RM → V67 四写 payload（FEAT/WPR/WPRCFG/FBPA + marker `0x67b00001`）→ 写选择器 SS0/SS1 → 签名还原 → FLR → 链回 `bootmgfw`。**不刷 BIOS、不烧熔丝、不改驱动、不改 VBIOS**。
**【文档】** `nvuefi.md:269-300` 单变量对照（RTX 4060 Laptop）：stock 2.52 GHz / 95–105 W / 30.5 TFLOPS → 只开 issue-rate 2.37 GHz / 130–140 W / **47.50** → 只开功耗墙（+nvoc，3.00 GHz）/ **35.9** → 两者都开 2.89 GHz / 190–208 W / **64.30**。结论原文：「解锁的本质：被禁用的晶体管恢复工作，而非超频」「解锁是易失的，但烧坏的硅片不会恢复」。
**【文档】** 数值无害：`README.md:79`「Outputs are bit-identical before and after; only the speed changes」；issue #51 用 FP64 参考复验前后逐位一致。这一点比「换 fp16 累加内核」强——后者同样能拿 2×，但要吃精度（引擎里那个 fp16 累加变体正是因此没上线，见 docs/ninfer-analysis.md:239-250 注释「twice the FP32-accumulator rate on GeForce parts」）。
**【文档】** 被解锁的通路＝**FP16 / BF16 / TF32 且 FP32 累加**的 MMA；SS1=0x8 是 IMLA4 选择位。**INT8/INT4 是否也被钳？** 规格口径上不是：NVIDIA 给 4060 Ti 的 INT8 = 176.4 TOPS（稀疏）/ 88.2 dense，恰好是 FP32 累加 FP16（44.3）的 2 倍；README `README.md:66-77` 也自述「INT8/FP8/INT4 models: No change」。**【未验】** 没有任何社区报告在解锁前后跑过 INT8 微基准；若哪天发现 IMLA 也被钳，我们这条 int8 prefill 会跟着受益——这是唯一一条「解锁对我方 int8 通路可能有用」的尾巴，当前无证据支持。

## 5. RTX 4060 Ti 8GB（10DE:2803）到底在不在支持矩阵里

**【文档】✅ 在，而且是「实测」级，包含 8 GB 台式卡。** 依据链：

- `nvuefi.md:350`（兼容矩阵行）：**AD106 4060Ti 2803 ✅ 实测（PR #5，AD106 桌面：回放＋解锁＋四写读回，FP16 46.78→75.28 TFLOPS）**；同族的 2805（16G）✅ 实测（`docs/evidence/ad106-2805-nuc13/report.md`，FP16 45.78→75.24，ComfyUI 稠密 bf16 ×1.57）。
- `nvuefi.md:440-443`：**2803 单机单变量**——修复前 booter status 0x89、修复后 `MAILBOX0=0`＋marker＋四写全读回，**FP16 46.78 → 75.28 TFLOPS**，证据目录 `docs/evidence/ad106-4060ti-desktop/`，机理见 `docs/bridge-bme-root-cause.md`。**这就是 8 GB 台式 4060 Ti。**
- `nvuefi.md:465`：AMI 固件无路径 GOP bug 的**首次发现现场就是「ASUS ROG MAXIMUS Z790 APEX + RTX 4060 Ti 8 GB」**，修复（PR #13）已进 loader — 说明 8 GB 台式机被真机跑过多次。
- 社区复现：issue **#51**（AMD APU 桌面、2803、v0.2.0）FP16 45.96→**75.40**（+64.1%）、BF16 44.61→**78.72**（+76.5%）、TF32 20.81→36.44；issue **#33**（MSI B550、无内显、2803、165 W）FP16 45.72→**67.30**（+47%，被功耗墙压住）；issue **#56**（双卡，主卡 5060 Ti 负控被安全跳过）副卡 2803 FP16 44.94→**71.81**，24 h+ 稳定。

**「Experimental」在两条路线上含义不同，别混：**

- **Zagitta/gpu-unlock（Linux .ko）**：`README.md:26-29` 把 Ada 40 系标 Experimental —— 那是对 `.ko` 路线而言，LHR/驱动版本/`nvidia` 模块绑定顺序都可能翻车。
- **nv-uefi-unlocker（UEFI 预驱动）**：`nvuefi.md:15-42`、`:335-343` 把 Ada **全段 0x2600..=0x28ff 放行**并给「✅ 全系兼容 实测支持」，另有 2803/2805/28e0/28a0/28a1/2783/2709/2705/2704/2689 的实机读回。它对 Ada **没有** Turing 那条 GSP 模式前置（`nvuefi.md:366-370` 明说 40 系无此要求）。
**【未验】** 与我们**逐位同构**的机器仍是空白：AM5/B650 级主板 + 驱动 **616.92** + Win11 **26100** + **核显带屏的混合输出** + GameViewer 虚拟显示适配器。社区样本是 Z790/B760/B550 + 610.62/610.88/617.42，**没有一台是核显带屏的 AM5 桌面**（#51 是 AMD APU 平台但显示接独显）。B 站目前**没有任何 4060 Ti 8G 的解锁实测**（评论区在求）——我们若做，是**中文社区首例**（不是全球首例，repo 侧 PR #5 已跑过 8 GB 台式）。

## 6. 能不能在这台 Windows 上跑（这是本路线最大的优点）

**【文档 + 实测】可以，不需要双系统、不需要 WSL2、不需要装 Linux。** 这一条正是它与 Zagitta/gpu-unlock 的分水岭：后者是 Linux 内核模块（要 BAR0、要 FLR、要 `nvidia` 绑定时序），Windows 上**结构上不可能**；前者是 UEFI 应用，**在任何 OS 之前**跑，跑完把控制权交回 `bootmgfw`（`nvuefi.md:9-13`：「全平台操作系统通用」）。

| 前置条件 | 本机状态 | 判定 |
| --- | --- | --- |
| UEFI 固件（非 Legacy） | `BiosFirmwareType=Uefi` | ✅ 已满足 |
| **Secure Boot 关闭** | `Confirm-SecureBootUEFI=False` | ✅ **已经是关的**，无需改 |
| 系统盘 GPT | 磁盘 0 = GPT（WDC 1TB） | ✅（另一块 1TB 是 MBR，与启动链无关） |
| 启动介质 | FAT32 U 盘或数据盘 300 MB FAT32 分区，产物由 `make-usbroot.ps1 -Family ad102` 生成 | 需制作（一次性） |
| 每次冷启动重放 | **必须**（易失，`nvuefi.md:74-117`） | ⚠️ 日常代价 |
| 休眠/睡眠 | S3/S4 失电＝解锁被擦；`nvuefi.md:148-198`（Linux 侧 issue #9 的 RTD3 静默擦除） | ⚠️ 需 `ssdiag` 复验 |

**U 盘目录长什么样**（`nvuefi.md:45-73`）：根目录放 `\EFI\BOOT\BOOTX64.EFI`（先备份原文件）+ `booter_load_ad102.bin`、`gsp_boot_ad102.bin`、`gsp_boot_desc_ad102.bin`、`fwimage_ad102.bin`（GSP-RM ~80 MiB）、`fwsignature_ad102.bin`、`scrubber_ad10x.bin`、**`v67-ad102-four-plm.bin`（在＝解锁模式，删＝只回放不解锁）**，可选 `tx-require-d0.txt`、`tx-select-bdf.txt`、`i_know_what_i_am_doing.txt`（5 秒倒数自动跑）、`chain-target.txt`、`no-reconnect.txt`；输出 `\loader.log`。资产由 SHA-256 钉死的 610.43.03 公共输入本地再生，release 不含 NVIDIA 二进制。

**每次开机都要过一遍吗？** 是，但可以「免 U 盘」：issue #33 给的方案（`github.com/chungtair/rtx4060ti-auto-unlock`）＝把同一批文件放到数据盘一个 **300 MB FAT32 分区**，`bcdedit /copy {bootmgr}` 建固件启动项并在 `{fwbootmgr}` 里排第一，开机 5 秒倒数自动解锁再链回 bootmgfw。两个坑：【文档】MSI B550 会无视 Windows 写的 `{fwbootmgr}` 顺序，必须在 BIOS 里手动设 Boot Option #1（我们是技嘉 AM5 板，**【未验】** 同款坑是否存在）。

**推荐入口**：从 Windows 里点「重启」进 U 盘（此时独显仍在 D0）；**不要**走「纯核显关机→冷启动」那条路（`nvuefi.md:118-146` 混合模式那行是直接 `claim` 前置报 `dGPU powered off (D3cold)`、零写入中止）。台式机上冷启动是否也是 D3cold 状态 **【未验】**，但放 `\tx-require-d0.txt` 可以让非 D0 入口**零写入中止**（安全失败，不黑屏）。

## 7. 硬数字：解锁前 / 后，模型、上下文、tok/s、TTFT

### 7.1 先把算式摊开（可复算）

- 每 token 前向 FLOPs ≈ **2N = 54.6 GFLOP**（N=27.32e9；项目惯用 48.7 GFLOP/token＝0.89×2N，两个口径都列）。
- 实测 prefill 963 tok/s ⇒ **52.6 TFLOPS 等效**（按 48.7 口径则 46.9）。1,011 tok/s ⇒ 55.2。
- 本卡 **FP32 累加** 峰值：34 SM × 512 FLOP/clk × 2.535 GHz = **44.1 TFLOPS**（实测 46.78/47.24 ⇒ 等效 ~2.69 GHz）。**解锁后实测 75.28 / 76.71**（PR #5，2803 桌面，8192³ GEMM）⇒ 倍数 **1.61–1.62×**。
- decode 上限：6.3947 GB ÷ 288 GB/s = **22.2 ms ⇒ 45.1 tok/s**（无投机时的物理墙）。
- **模型**：设 A16（被钳）通路占 prefill 时间的比例 f，int8 通路速率是 A16 的 88.6/47.24 ≈ **1.87×**，则
  - 解锁后加速比 **S(f) = 1 / (1 − 0.3842·f)**（0.3842 = 1 − 1/1.624）
  - f=0.30 → S=1.13（963→1,088，TTFT 38.9→34.4 s）；f=0.50 → **S=1.24**（→1,192，31.4 s）；f=0.65 → S=1.33（→1,284，29.2 s）；f=0.80 → S=1.44（→1,390，26.9 s）；f=1.00 → S=1.62（→1,564，24.0 s）
- f 的点估计（交叉验证）：若项目早期 **801.6 tok/s（39.0 TFLOPS，= 全 A16 口径的 83% 天花板）** 是「尚未有 PTQ1 int8 路由」时的数，则 801.6→963 的 +20% 可由 f≈**0.64** 解释 ⇒ S≈1.33。另一条独立证据：B 站 2080Ti 22G 案例（BV1XnnZ6iELj）**GEMM +81% 而端到端 prefill 只 +20%**（收益比 ≈0.25），按此比例我们 +62% GEMM ⇒ **+15% 左右**。两者夹出 **+15~33%，取中值 +20~25%**。

> ⚠️ **本节这几条 f 模型已被 §7.2 的实测取代**：实测 `T_B/T_A = 2.66–2.77` 超出模型定义域（最大 1.87），`f` 不可辨识。算式保留只为记录推理链与可复算；**结论一律以 §7.2 为准**。

### 7.2 实测定价：`--no-prefill-a8` 的 A/B（ninfer-limit 执行，2026-10-30）

| 提示 token | 默认 A（实测） | 全 A16 B（实测） | 比值 R | 出处 |
| --- | --- | --- | --- | --- |
| 7,926 | prefill **1.10k tok/s**、TTFT **7.2 s**、decode 81.3 | — | — | `logs/lim-FK.log:114` |
| 7,928 | — | prefill **396.7 tok/s**、TTFT **20.0 s** | **2.77×** | `logs/lim-NOA8.log:117` |
| 23,833 | prefill **1.03k tok/s**、TTFT **23.2 s**、decode 52.0 | — | — | `logs/lim-FK.log:298` |
| 23,835 | — | prefill **386.2 tok/s**、TTFT **61.8 s** | **2.66×** | `logs/lim-NOA8.log:309` |

三条结论：

1. **默认 prefill 里 63.6% 的时间已经在不加锁的 int8(A8) 通路上。** 取 `A16 占比 = 1 − 1/R`：R=2.77 → 36.1%、R=2.66 → 37.6% ⇒ A16 段 **36.4~37.6%**。
2. **解锁上限 = 1/(0.636 + 0.364/1.624) = 1.163×（+16.3%）**；两臂各算：R=2.778 → 1.160×（+16.0%）、R=2.664 → 1.168×（+16.8%）⇒ 工作值 **+16.3%**。
3. **A8 占比与上下文长度基本无关**（8k 2.77× vs 24k 2.66×）⇒ 它是**投影 GEMM 的结构性混合**，不是长上下文效应。别指望「上下文越长解锁越划算」——attention 份额上升只会稀释 GEMM 份额。

**保守打折**：A16 段里还含 attention/KV/调度这类不碰 tensor 峰值的时间（三点拟合 u≈0.15，§7.1），扣掉后 `f_eff = 0.364 − 0.15 = 0.214` ⇒ `S_cons = 1/(1 − 0.3842×0.214) = 1.088×（+8.8%）`。**现实区间 +8.8~16.3%，工作值 ≈ +9~16%。**

**顺带一个反证（说明 A16 通路本身也不快）**：全 A16 臂 396.7 tok/s × 48.7 GFLOP/token ≈ **19.3 TFLOPS**，只有本卡被钳峰值 46.78 的 **41%**。即 A16 通路今天既不快也吃不满；解锁即使把 MMA 速率提 1.62×，若利用率不变，A16 段也只值 +62%，乘上 36.4% 的份额正好回到 +16%。

### 7.3 场景表（收益栏凡无本机解锁实测者一律标【实测推导】或【推断】）

| 场景 | 解锁前（实测） | 解锁后（预测） | TTFT / 时延 | 收益 | 依据 |
| --- | --- | --- | --- | --- | --- |
| **上下文容量 / KV 池** | 池 32,000（快）/ 64,000（长）；7,074/8,188 MiB | **完全不变** | 不变 | **0** | 【实测】显存与带宽都不动 |
| decode（MTP 投机，可预测文本） | 98–107 tok/s | 98–107 tok/s | — | **0** | 【实测+文档】带宽 45 tok/s 墙 + host 51.4 ms/round 墙 |
| decode（自由散文，MTP 失效） | 42–50 tok/s | 42–50 tok/s | — | **0** | 【实测】6.39 GB/288 GB/s=22.2 ms ⇒ 45.1 tok/s 物理下限 |
| prefill 短提示 1k | 1,000 tok/s | 1,080–1,163 | TTFT 1.0 → 0.86–0.93 s | **+8.8~16.3%** | 【实测推导】§7.2 |
| prefill 8k（A/B 同题面） | **1.10k**（`lim-FK.log:114`） | **1,196–1,278** | 7.2 → 6.2–6.6 s | **+8.8~16.3%** | 【实测+推导】§7.2 |
| prefill 24k（A/B 同题面） | **1.03k**（`lim-FK.log:298`） | **1,117–1,193** | 23.2 → 19.9–21.3 s | **+8.7~16.8%** | 【实测+推导】§7.2 |
| prefill 37k（我们的主战场） | 969 tok/s | **1,054–1,127** | **38.9 → 33.5–35.7 s（省 3.2–5.4 s）** | **+8.8~16.3%** | 【实测推导】§7.2 |
| prefill 56k / 113k | 899 / 704 tok/s | 978–1,046 / 766–819 | — | +8.8~16.3%（越长越偏低） | 【推断】attention 份额上升 |
| prefill 200k（超池） | 552 tok/s | 596–635 | 362 → 315–335 s | **+8~15%** | 【推断】200k 时 attention/KV 已占约 45% 时间 |
| 图像生成（若将来跑 ComfyUI 稠密 bf16） | — | — | 12.1→8.0 s/张（同款 2803 实测 ×1.51） | **+51%** | 【文档】issue #33 / 2805 ×1.57 |
| LoRA / 全参微调 | — | — | — | **+25~50%** | 【文档】README 表 |
| **我们真正的瓶颈：8 GB 显存** | 7,074/8,188 MiB | 同左 | — | **0（一点都没变）** | 【实测】 |

> 「解锁后」一列的依据是 **§7.2 的实测 A8/A16 时间占比**（+16.3% 乐观上界、+8.8% 保守），**不是** GEMM 倍数外推；本机解锁态一次都没跑过，故仍标【实测推导】。任何「解锁后 1,500+ tok/s」的说法都不成立——那要求 prefill 时间 100% 落在被钳通路上。

## 8. 显示器拓扑与已有红利（「显示器是不是已经不在 4060 Ti 上」）

**结论：是。推理卡今天不驱动任何显示器 —— 所以「卡不驱动显示器」那份红利我们已经吃到了，它属于「不解锁就有的 18~20%」，不是解锁的功劳。**

实测证据（2026-10-30 本机只读查询，未启动任何 GPU 引擎）：

| 证据 | 读数 | 说明 |
| --- | --- | --- |
| `nvidia-smi --query-gpu=…display_active,…` | **`display_active = Disabled`**（`display_mode` 已被驱动标 deprecated） | 4060 Ti **没有驱动任何显示头** |
| 同上 | `00000000:01:00.0`、616.92、7,305 / 8,188 MiB、util 100% | 卡正在满载推理（ninfer-limit 的扫描），占 7.3 GB |
| `Win32_VideoController` | **AMD Radeon(TM) Graphics：2560×1440 @144 Hz** | 面板 owner 是 7800X3D 的核显 |
| 同上 | NVIDIA RTX 4060 Ti：`CurrentHorizontalResolution` 为空 | 独显不驱动任何分辨率 |
| 同上 | `PCI\VEN_10DE&DEV_2803&SUBSYS_17517377&REV_A1` | 确认是我们讨论的 2803（AD106 / 8 GB） |
| 同上 | GameViewer Virtual Display Adapter（`ROOT\DISPLAY\0000`）、无分辨率 | 是 IDD（间接显示驱动），**不占 GPU 的 display head** |

**这意味着什么**

- 【文档·lead 转述】PR #1496「推理卡不驱动显示器 ⇒ prompt +18.7~20.8%、decode +38.1~48.1%」——若成立，**这份红利已经在手**，解锁不会再加一次。
- 【实测·本机】反向佐证：decode 42–50 tok/s 正贴着 45.1 tok/s 的物理墙（§7）。若桌面合成/显示路径在抢带宽，这条线会明显掉下去；贴线本身说明桌面上几乎没有额外争用。
- 【文档·repo】`nvuefi.md:118-132` 的「显示模式 × 上次离开方式」实测表：混合模式（核显带屏）**只有「混合关机→重启」这一条入口可用**；纯 iGPU 关机会让 EC 在 POST 前就断掉独显供电（D3cold、BAR0 全 `0xffffffff`），工具零写入中止。⇒ 我们的操作方式只能是**从 Windows 点「重启」进 U 盘**，不能用「关机再开」。
- **别做的事**：把显示器线插到 4060 Ti 上。那会**同时**丢掉这 18~20%（卡开始驱动显示器），并把解锁的黑屏风险从「低（混合输出，控制台在核显）」拉到「高（直连，控制台在被复位的那张卡上）」。

**【未核源】保留意见**：PR #1496 我未能核到原帖（未定位到具体仓库），因此按 lead 转述处理，其数值**不进任何算式**。本节能站得住的硬事实只有一条：本机 `display_active=Disabled` 且 2560×1440@144 由核显驱动。

## 9. 定价实验（**已于 2026-10-30 完成，结果见 §7.2**；本节保留为历史与复现步骤）

> 铁律：本机只有 ninfer-limit（ninfer-analyst）能启引擎。以下三条命令请由他执行；我这边不碰 GPU。

> **结论先行**：实验做完了 —— 8k 提示 `1.10k → 396.7 tok/s`、24k `1.03k → 386.2`（§7.2），**A16 段只占 prefill 时间 36.4%**，解锁上限 +16.3%。下面的 f 反解公式**对本数据不适用**（2.66–2.77 超出模型域，见 §2 第 4 条），脚本 `tools/unlock_pricing.py` 保留但只作历史工具，不再用于出结论。

**怎么跑：一条命令就够**：`tools/unlock_pricing.py`（python3 标准库，无第三方依赖）。它自己起引擎、自己量 TTFT、自己算 q/f/S，跑完只按 PID 停自己那个子进程；默认端口 **18080**（被占直接退出），**绝不碰 8091/8081/8092**。

```bash
# 1) 空跑自检：不连引擎，只验公式/单调性/GO 线（11 项断言，已 PASS）
python tools/unlock_pricing.py --selftest

# 2) 干跑：只打印将要执行的两条命令行，不启动任何进程
python tools/unlock_pricing.py --dry-run \
  --exe engine/ninfer-serve-89.exe --model models/<bonsai>.ninfer \
  --prompt-file prompts/37k.txt \
  --extra-args "--spec mtp --prefill-chunk 2048"

# 3) 真跑（ninfer-limit 执行）：A/B 各一次，自动反解 f 并给 GO/NO-GO
python tools/unlock_pricing.py \
  --exe engine/ninfer-serve-89.exe --model models/<bonsai>.ninfer \
  --prompt-file prompts/37k.txt --port 18080 --max-context 40960 \
  --out logs/unlock_pricing_run.json
```

输出＝上面那张表 + 一行判定（`GO` / `边缘` / `NO-GO`）+ 一行「37k TTFT 38.9 s → ?」；若 |T_B/T_A−1| < 2% 会额外警告「GO 的前提是 int8 真没用上，也可能是 `--no-prefill-a8` 没生效」。两个参数不能省：`--max-context 40960`（引擎默认 8192，`help-full.txt:7`）和 `--extra-args "--spec mtp ..."`（必须与基线同档，否则测的不是同一个系统）。

**9.1 主实验：`--no-prefill-a8`（把 A16 占比量出来）**

同一 prompt（建议就用 37,468 token 那份）、同一 `--prefill-chunk`、同一 `--spec mtp`：
```
A) 默认                          → 记录 req 完成行的 prefill tok/s（基线 963）
B) 加 --no-prefill-a8            → 全部走 A16
```
读法（T_A=963）：设 T_B 为 B 组 prefill 时间/速率对应的每 token 时间，则 int8 时间占比 q 满足 `T_B = T_A·(1 + 0.87·q)`（0.87=1.87−1）⇒ `q = (T_B/T_A − 1)/0.87`，`f = 1 − q`。

> **下表已作废（历史读表）**：实测 `T_B/T_A = 2.66–2.77` 超出该反解模型定义域（最大 1.87），`f` 不可辨识。真实结论见 **§7.2**（A16 段 36.4%、上限 +16.3%）。保留此表只为记录方法学与自证错误。

| B 组 prefill（实测） | T_B/T_A | q＝int8 时间占比 | f＝A16 时间占比 | 解锁预期 S(f) | 保守 S(f−0.15) | 37k 预估 prefill | 判定 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| ≈963（几乎没掉） | 1.00 | 0.00 | 1.00 | 1.62× | 1.49× | 1,430 | GO\*（先确认开关真生效） |
| ~900 | 1.07 | 0.08 | 0.92 | 1.55× | 1.42× | 1,367 | GO |
| ~850 | 1.13 | 0.15 | 0.85 | 1.48× | 1.37× | 1,315 | GO |
| ~800 | 1.20 | 0.23 | 0.77 | 1.42× | 1.31× | 1,261 | GO |
| ~750 | 1.28 | 0.33 | 0.67 | 1.35× | 1.25× | 1,206 | GO |
| ~700 | 1.38 | 0.43 | 0.57 | 1.28× | 1.19× | 1,147 | 边缘 |
| ~650 | 1.48 | 0.55 | 0.45 | 1.21× | 1.13× | 1,087 | NO-GO |
| ~600 | 1.61 | 0.70 | 0.31 | 1.13× | 1.06× | 1,024 | NO-GO |
| ~550 | 1.75 | 0.86 | 0.14 | 1.06× | 1.00× | 963 | NO-GO |
| ~500 | 1.93 | 1.06 | 0.00 | 1.00× | 1.00× | 963 | 模型外，查开关 |
| 崩到 ~45 tok/s | 21.4 | — | — | — | — | — | `NINFER_TERNARY_PTQ1_FAST=0` 类误设（参考 rung 44.7 tok/s，`t2_dispatch.cpp:87-105`） |

**⚠ 方向别读反**：B 组**掉得越多，说明 int8 在默认路径里帮得越是大忙**，A16 占比越小，**解锁越没用**。GO 线是 `f ≥ 0.60 ⇔ T_B/T_A ≤ 1.348 ⇔ B ≥ ~715 tok/s`（A=963）。上一版把这条写成「B 掉到 ≤700 才 GO」，方向反了，此处更正；`tools/unlock_pricing.py --selftest` 里反查过这条线（f≥0.6 ⇔ B≥714）。

**为什么还列一列「保守」**：`S(f)=1/(1−0.3842·f)` 假设所有非 int8 时间都能被解锁提速 1.624×，偏乐观——37k 上下文里 attention/KV/softmax/采样完全不碰那半个 tensor 峰值。用三点实测（1k=1,000、37k=963、200k=552 tok/s）反解：`1/963=1.0384 ms/token`、`1/552=1.8116 ms/token` ⇒ 斜率 `b=4.758e-6 ms/上下文token`、截距 `a=0.8600 ms`，37.5k 处与上下文线性相关的时间 `0.1784 ms = 17.2%`；扣掉 fast-prefill-kernel 已加速的 FP16 PV 部分，真正「不可加速」份额取 **u=0.15**，即 `S_cons = 1/(1−0.3842·(f−0.15))`。**GO/NO-GO 用 f 判，收益预估报保守列。**

**9.2 副实验（校验「我们到底在哪条 rung 上」）**
- `NINFER_TERNARY_PTQ1_FAST=0`（强制参考 rung）：预期 prefill 崩到 ~45 tok/s、decode 13.8 级 —— 证实开关有效、我们平时跑的是快 rung（默认 ON，2026-10-01 改的，`t2_dispatch.cpp:97`）。
- `NINFER_PTQ1_WIDE_T=on`（PTQ1 走 bf16 宽 T MMA 而非 int8 tile，默认 OFF，`t2_a8.cu:522-541`）：**这条最接近「解锁后我们能拿到的形态」**——若它比默认慢很多，说明 int8 帮了大忙⇒解锁收益小；若它接近默认⇒A16 可以顶上⇒解锁收益大。
- `NINFER_T2_A8_MIN=999999`：把 int8 门槛抬到不可能，等价于全 A16（与 9.1 互为对照）。

**9.3 若真的上了，解锁当天要抓的数**：`ssdiag` 判定行（PLM/SS0/SS1/READOUT_1）→ 同一 GEMM 微基准（`cli-stressor-cuda-rs`，FP16/BF16 8192³，预期 45→75 量级）→ 上面 9.1 的 A/B 两组 prefill/TTFT → decode 两组 → `nvidia-smi` 功耗/温度/`throttle_reasons`。

## 10. 日常代价与风险（照实写）

1. **易失**：断电/重启即清零（`nvuefi.md:74-117`）。等于**每次冷启动都要过一遍固件事务**（U 盘或数据盘 FAT32 分区 + 5 秒倒数）。对我们是实打实的：**重启会打断 8091/8081 两个常驻服务**，需要脚本自动拉起。
2. **睡眠/休眠擦除**：S3/S4 失电＝失解锁（`nvuefi.md:148-198`）；Windows 侧无等价文档，只能靠 `tools/ssdiag`（`nvuefi.md:524-537`，`--reapply` 可免重启写回 SS0/SS1，仅在 FEAT 门仍开时有效）。注意 ssdiag 要加载 Intel 签名的 `pmxdrv.sys`（内嵌、自建服务名、退出即删），是一个额外的内核组件。
3. **热与功耗**：只开 issue-rate 时功耗从 95–105 W 升到 130–140 W（`nvuefi.md:269-300`）；叠加 nvoc 会到 206.8 W、Hot Spot **101.8–104.4 °C**、`PerCap=Pwr`（`nvuefi.md:239-267`）。**我们不建议叠 nvoc**——那才是「防烧显卡」的那条线；单开解锁在 4060 Ti 上是 160 W TGP 内的事（#33 就是被 165 W 压住只到 67.30）。B 站作者也自警「防烧显卡」；温度 80→100 ℃ 的说法来自带 nvoc 的组合场景【文档/社区】，单解锁未达该水平【未验】。
4. **黑屏 / 驱动不认卡**：`nvuefi.md:510-522` 三个场景。我们因为**屏在核显上**，黑屏风险显著低于「独显直连」机（事务期间控制台不在被复位的那张卡上）；但 **GameViewer 虚拟显示适配器**是第三块显示设备，与 GOP 重连的交互 **【未验】**，可用 `\no-reconnect.txt` 规避（`nvuefi.md:459-476` 的 AMI 无路径 GOP bug 就发生在这类板上，且正是在 4060 Ti 8 GB 上发现的）。
5. **维护者非全职**（`nvuefi.md:478-480`）+ 无 8G/B 站先例 ⇒ 出问题时你是**在给别人探路**。工具链还依赖 `make-usbroot.ps1` 现场再生资产（哈希硬校验，构建期不允许含糊）。
6. **误操作代价**：U 盘根少一个 `v67-*.bin` 就是「只回放不解锁」——回放**仍然写固件状态并做设备复位**，不是只读检查（`nvuefi.md:45-73`）。

## 11. 回滚与「怎么确认已经恢复」

**【文档】** `nvuefi.md:508-522`：

- **A 黑屏（链式启动失败/事务中断）**：没动固件配置与 ESP 文件 ⇒ 强制重启、走原 Windows 引导项即恢复。U 盘不在启动链上时机器根本不会进它的代码。
- **B STOP/异常（事务中途失败）**：**同会话绝不重试** → **完全断电**（台式机拔电或关 PSU 开关 30 s）→ 拔 U 盘 → 正常进 Windows → 查设备管理器/事件日志 → 留证据再说。
- **C 驱动不认卡（交棒后异常）**：看错误码、查 `nvlddmkm`/Xid；解锁是易失覆盖，**一次冷启动就回出厂状态**；仍异常则再断电，最后手段 DDU 重装驱动（工具不写任何持久存储，异常只可能来自交棒时序）。

**「确认恢复」的四步（我们能执行的）**：
1. `tools/ssdiag`（v2.1.5+ release 自带 `ssdiag-x86_64-windows.exe`）：应显示 PLM 回到 `0xffffff8f` 一类出厂值、SS0/SS1 非 `0x88888888/0x8`、判定非 `UNLOCKED`（`nvuefi.md:526-537`）。
2. 同一 GEMM 微基准回到 ~46.8 TFLOPS（FP16 8192³）——**这是最强判据**，比寄存器更实在。
3. `NInfer` 跑一次 37k prompt：prefill 应回到 963 附近（若明显高于 963 反而是「还在解锁态」的信号）。
4. `nvidia-smi -q -d PERFORMANCE` 看 `throttle_reasons`、功耗、温度回到基线。

## 12. 一个比解锁更便宜的教训：Windows 上 prefill 慢，常常是配置问题

**【文档/社区】** 4090 48G 那位作者的自纠：以为解锁把 Windows prefill 从 2,000 提到 4,800，后来发现**同一负载 Ubuntu 不解锁也有 ~5,000** ⇒ 那个 2,000 是 **Windows 侧配置**（arena/环大小设小）造成的，与解锁无关。对我们直接相关的等价物：

- 本机 `--fast-prefill-kernel` A/B = 1,022 vs 965（噪声级，docs/部署完成-实测报告.md:166）⇒ 我们已经不在「配置拖后腿」的坑里，但**每次升级引擎/改参数都要重验一遍**。
- 我们自己的 prefill 掉速（37k 963 → 200k 552）**不是 GEMM 问题**：多出来的是 attention/KV 写入/换页，正好是解锁**吃不到**的部分。这条也解释了为什么不能拿 GEMM 倍数外推 TTFT。
- 还没试过的软件杠杆（都比解锁便宜）：`--prefill-chunk` 与 `--fast-prefill-kernel` 联合调参（help-full.txt:37-46 明说 `--prefill-cublas` 想要更大的 chunk）、KV dtype/池配比、`--spec` 档位、以及网关侧的 67k 前缀缓存（README §0：84.2 s → 0.54 s，**这才是我们最猛的 TTFT 杠杆**，比任何算力都强）。

## 13. 结论：**NO-GO（不刷）**

**做完了定价实验，答案出来了：不刷。** 三个数字：**decode +0、显存/上下文 +0、prefill 上限 +16.3%（保守 +8.8%）**。

- 我们的痛点在**容量**（8 GB、池 32k/64k）与**长上下文效率**（200k 时 552 tok/s），解锁对这两个点 **0 收益**；
- decode 是双墙（288 GB/s、host 51.4 ms/round），解锁 **0 收益**；
- prefill 的收益被实测封顶：A16 段只占 36.4% 时间（§7.2），乐观 +16.3%、保守 +8.8%；37k TTFT 38.9 → **33.5~35.7 s（省 3.2~5.4 s）**。
- 代价一侧没有任何一项因为实验而变小：**每次冷启动过固件事务（5 s 倒数）/ 易失 / 驱动更新重刷 / 重启中断 8091+8081 / 只能『重启』进 / 本机型（AM5 + 616.92 + Win11 26100 + 核显带屏 + GameViewer）无先例**。

**§13.1 「有条件上」的重启门槛（保留，但已封死）**：

1. ~~A/B 给出 B 组仍 ≥715 tok/s（f≥0.60）~~ → **实测 A16 段只有 36.4%，f 最大 0.376，该线结构上不可能达成**；等价地，要 GO 需要 prefill 时间 ≥60% 落在被钳通路，实测 36.4%。
2. 若未来换引擎/换模型使 A16 份额 ≥60%（例如去掉 PTQ1 的 int8 路由、或跑稠密 bf16 模型），本报告 §7.2 的算术仍可直接复用：`S = 1/(s_A8 + (1−s_A8)/1.624)`。
3. 验收口径固定：同一份 37k prompt + 同一 flags 的 prefill/TTFT/decode，不认「GEMM 倍数」和「别人 4,800 tok/s」。

**若只想要更快的首字，先去做 §12 第三条的软件调参与前缀缓存，那两条的收益确定性远高于解锁。**

## 14. 参照源

- 仓库（UEFI 路线）：https://github.com/physicsdolphin/nv-uefi-unlocker （本地副本 `tmp/ext/nvuefi.md`，598 行）
- 兼容矩阵 2803 行：`nvuefi.md:350`；2803 单变量实测：`nvuefi.md:440-443`；AMI GOP bug（4060 Ti 8 GB 现场）：`nvuefi.md:459-476`
- 锁机理：`nvuefi.md:308-325`；本质对照实验：`:269-300`；nvoc 组合：`:239-267`；显示模式矩阵：`:118-146`；RTD3：`:148-198`；回滚：`:508-522`；ssdiag：`:524-537`
- issue #33（2803、MSI B550、免 U 盘方案）：https://github.com/physicsdolphin/nv-uefi-unlocker/issues/33 ；#51（2803、AMD APU 桌面）：https://github.com/physicsdolphin/nv-uefi-unlocker/issues/51 ；#56（双卡负控）：https://github.com/physicsdolphin/nv-uefi-unlocker/issues/56
- 免 U 盘自动解锁：https://github.com/chungtair/rtx4060ti-auto-unlock
- Linux kmod 路线（对照）：https://github.com/Zagitta/gpu-unlock ；本项目上一轮分析：`docs/gpu-unlock-analysis.md`
- 视频/科普：https://www.bilibili.com/video/BV1d6xN66ECM/ 、https://www.bilibili.com/opus/1264436370549506065 、https://www.bilibili.com/opus/1264493051219279872
- 社区口径（lead 转述，未独立复核）：2080Ti 22G BV1XnnZ6iELj「GEMM +81% / prefill +20%」；4090 48G「Windows 2000 vs Ubuntu 5000＝配置问题」
- 定价脚本：`tools/unlock_pricing.py`（stdlib only，`--selftest` 通过）——A/B 反解 f、输出 GO/NO-GO
- 【未核源】PR #1496「推理卡不驱动显示器 ⇒ prompt +18.7~20.8%、decode +38.1~48.1%」：lead 转述，未定位到原仓库；本机 display_active=Disabled 已独立实测（§8），该 PR 的数值不进算式
- **定价 A/B 原始日志（本报告最关键的一手数据）**：`logs/lim-FK.log:114`（8k 默认 1.10k tok/s / TTFT 7.2 s）、`logs/lim-NOA8.log:117`（8k 全 A16 396.7 / 20.0 s）、`logs/lim-FK.log:298`（24k 默认 1.03k / 23.2 s）、`logs/lim-NOA8.log:309`（24k 全 A16 386.2 / 61.8 s）——由 ninfer-limit 执行，我未启动任何 GPU 引擎
- 引擎侧证据：`src/ops/linear/linear.cpp:111-125`、`src/ops/linear/t2/t2_a8.cu:507-510,568-580`、`src/ops/linear/t2/t2_dispatch.cpp:87-116`、`src/ops/wrapper/linear_swiglu.cpp:59-67`、`src/ops/wrapper/attn_input_proj.cpp:113-116`、`CMakeLists.txt:33-35`、`engine/help-full.txt:37-50`

> 本文不含任何在解锁态下取得的测量值；所有「解锁后」数字均标【推断】。若 §9 的 A/B 完成，请把实测结果回填到 §7.2 与 §13。