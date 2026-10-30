# HF 与魔搭情报：Bonsai 27B 量化档全景 + 8G 能跑什么

> 侦察员：community-scout ｜ 任务：task-13 ｜ 采样时间：2026-10-30 ｜ 数据来源：HuggingFace REST API、ModelScope API（PUT /api/v1/dolphin/models）、本机引擎二进制只读扫描
> 口径：**体积全部是 API 给的字节数**（不是网页四舍五入）；速度只写有出处的读数，没出处一律标 `未验`。
> 铁律遵守：repos/ 只读；未启动任何 GPU 引擎（只读 exe 字节）；只写本报告。

---

## 一、结论先说（八条）

1. **PTQ1 之外没有"更高精度的 27B 三元档"**。Bonsai-2-27B 只有两种打包：`PTQ1_0`（1.75 bit/w，5.54 GiB）和 `PQ2_0`（2.13 bit/w，6.71 GiB）。PQ2 **不是质量更高**，是把同一个三值码塞进 2-bit 槽（体积 +17%、个别 kernel 更快）。**不存在 PTQ2 档**。
2. **同尺寸还有一条质量线**：ProCreations 的 `GSQ+RCO` 重分配版（PTQ1_0，**6.05 GiB**）——WikiText-2 PPL **8.6690 → 8.1627（−5.84%）**，四个零样本任务平均 +0.13 pp（区间全部含 0）。同体积、同格式、**唯一的无损升级候选**。
3. **KV 量化到顶了**：我们引擎的 `--kv-dtype` 共九档，**`rk2v4-e8` 已是最省**（0.84 MiB/64-token 页，比 bf16 省 79%），再往下没有档位。代价是 PPL +2.14%。
4. **.ninfer 有两种互不兼容的方言**，我们只吃其中一种：本机引擎认 `ptq1_g128_fp16` / `t2_g128_fp16`；沈三殊的 PQ2 引擎认 `PTQ1_0_G128` / `PQ2_0_G128`（二进制逐字符串证据，见 §三）。**换档必须换引擎，而换引擎会丢掉 rk2v4（KV 池从 40K 塌到 8K 级）**。
5. **我们现役的模型出处找到了**：魔搭 `q409640976/ninfer-kvmem-heretic-bonsai2-27b` 里的 `bonsai2_27b_ternary_ptq1_native_mtp.ninfer` 与本机文件**同名同字节（6,394,697,216 B）**，且那个包自带一张 RTX 4060 8GB 的实测卡（73 tok/s / 25,408 常驻窗）。
6. **Strata 侧 8G 的真相**：Qwen3.8-Flash-Next 最小可用档 Q2_0 是 **66.4 GB（37.6 常驻 + 28.8 可 mmap 留盘）**；Coder 版 IQ1_M 55.24 GB。我们 32 GB 内存 + 8 GB 显存能"跑起来"的下限是 Coder IQ1_M 常驻部分 27.58 GB，**内存刚好卡死**。
7. **Qwen3.6-35B-A3B 才是 8G 的现实对象**：IQ3_S 12.74 GiB 起，但要靠 Strata 的专家流式（8 GB 卡要 32 GB 内存 + 6 GB 系统余量，我们是**刚好不够/勉强**）。
8. **魔搭上没有 4060Ti 8G 的部署记录**（搜 "4060Ti" 全站只有 4 条，无一相关）。4060 8G 有两条，都是 PTQ1 线的。

---

## 二、Bonsai 27B ternary 量化档全表

### 2.1 先分清底座（搞错就全错）

| 系列 | 底座 | 说明 |
|---|---|---|
| **Ternary-Bonsai-2-27B** | **Qwen3.8-27B** | 我们现在用的这条（`bonsai2_27b_*`） |
| Ternary-Bonsai-27B / Bonsai-27B | Qwen3.6-27B | 上一代，体积/格式不同 |

### 2.2 GGUF 线（体积 = HF API 实测字节）

| 仓库 | 档位 | 字节 | GiB | 备注 |
|---|---|---|---|---|
| `prism-ml/Ternary-Bonsai-2-27B-gguf` ★2863 / dl 1,997,242 | **PTQ1_0** | 5,946,648,928 | **5.54** | 官方档，1.75 bit/w |
| 同上 | **PQ2_0** | 7,206,168,928 | **6.71** | 2.13 bit/w，不是"更高精度" |
| 同上 | F16 | 53,819,000,000 级 | 50.11 | 只做参考 |
| 同上 | mmproj BF16 / Q8_0 | — | 0.87 / 0.59 | 多模态才要 |
| `ProCreations/bonsai-2-27b-gsq-rco-gguf` | **PTQ1_0（GSQ+RCO 重分配）** | **6,496,332,448** | **6.05** | 质量线，见 §2.4 |
| `CaryPalmer/Ternary-Bonsai-2-27B-262k-GGUF` | PTQ1_0 + MTP | 6,397,970,272 | 5.96 | 带 MTP 草稿头 |
| `ayshinko/Swift-Bonsai-2-27B-Katana-MTP-GGUF` | PTQ1_0 + MTP | 6,397,969,728 | 5.96 | 微调版 |
| `jakeatx/Qwen3.8-27B-Ternary-PQ2_0-MTP` | PQ2_0 + MTP | 7,502,169,376 | 6.99 | |
| `groxaxo/…PQ2_0-MTP`、`BoldingBuilds/…Abliterated-v2-PQ2_0-MTP` | PQ2_0 + MTP | 7,657,489,696 | 7.13 | |
| `dealignai/Bonsai-2-27B-Ternary-CRACK-GGUF` | PQ2_0 (CRACK) | — | 6.71 | 第三种打包 |

**prism 官方原话**：
> "PTQ1_0 packs trits densely (1.75 bits/weight, 5.95 GB), PQ2_0 stores each trit in a 2-bit slot (2.13 bits/weight, 7.21 GB)" …
> "Neither is uniformly faster"

### 2.3 .ninfer 容器线（引擎直接吃，跳过 GGUF 转换）

| 仓库（平台） | 文件 | 字节 | GiB | 格式 | 8G 可行性 |
|---|---|---|---|---|---|
| `q409640976/ninfer-kvmem-heretic-bonsai2-27b`（魔搭） | `bonsai2_27b_ternary_ptq1_native_mtp.ninfer` | **6,394,697,216** | 5.96 | `ptq1_g128_fp16` | ✅ **= 本机现役件** |
| 同上 | `heretic-27b-ptq1-mtponly.ninfer` | 6,395,660,288 | 5.96 | 同上 | ✅ |
| `fyb423/Swift-Bonsai-2-27B-NInfer`（魔搭） | `PTQ1_0_G128` | 7,045,000,000 级 | **6.563** | `PTQ1_0_G128` | ⚠️ 方言不同（需 ada 引擎） |
| 同上 | `PQ2_0_G128` | 8,310,000,000 级 | **7.736** | `PQ2_0_G128` | ❌ 太满 |
| `KVMem/Bonsai2-27B-T5-MTP-Q4-NInfer`（魔搭，官方） | `Bonsai2-T5-MTP-r3-Q4.ninfer` | **6,182,359,808** | **5.758** | `t5_g128_fp16` | ⚠️ 需 KVMem v0.19.0-rc1 |
| `Lxt1992/ninfer-ternary-bonsai2`（魔搭） | `ternary-bonsai-2-27b.ninfer` | 8,306,927,628 | 7.74 | 未验 | ❌ |
| `WaveCut/Ternary-Bonsai-2-27B-NInfer-v3`（HF） | — | 9,520,051,456 | **8.87** | `t2_g128_fp16` | ❌ >8 GiB |
| `emiltsoi/…-Heretic-NInfer`（HF） | — | 8.87 GiB 级 | 8.87 | 同上 | ❌ |
| `sanbanfu/…-ninfer-v3-spliced`（HF） | 主件 + aux | 8.866 + 7.737 | — | 同上 | ❌ |

> **fyb423 的关键一句**（证明了"换壳不损质量"）：
> "三元码从源 GGUF 逐字节搬进 NInfer 容器 —— 没有解量化再重量化，所以没有二次量化损失"

### 2.4 唯一"同体积更好质量"的硬证据：GSQ+RCO

来源 `ProCreations/bonsai-2-27b-gsq-rco-gguf` README（原文数字，非我推算）：

| 模型 | WikiText-2 PPL | ARC-C | ARC-E | HellaSwag | Winogrande |
|---|---:|---:|---:|---:|---:|
| 原始 Bonsai PTQ1_0 | 8.6690 | 61.01 | 79.76 | 77.65 | 73.80 |
| **Bonsai GSQ + RCO** | **8.1627** | 60.67 | 80.13 | 77.80 | 74.11 |
| 原始 Qwen3.8 BF16（天花板） | 6.5137 | 59.30 | 74.92 | 82.15 | 75.14 |

- PPL 差 **−0.5063（−5.84%）**；四任务平均 **+0.13 pp**；**四个配对 bootstrap 95% 区间全部含 0**。
- 作者自己写："this experiment does not establish a statistically clear accuracy improvement"，"An independent experiment, not an official Prism, Qwen, or ISTA-DASLab release"。
- 手法：全模型 402/402 矩阵做三元 GSQ，任务损失做 RCO，最后离散分配 polish；**RCO 可以把个别整矩阵换成 Q4_0 而仍压住 6,500,000,000 B 红线**。
- 完整评测在包内 `reports/benchmark-results.json`（1,934,745 B）+ `gsq_rco-mc.jsonl`（1,952,842 B）+ `before-polish-*` 对照件。

**对我们的意义**：同 6 GB 级体积，PPL 低 0.5 —— 但它是 **GGUF**，我们引擎吃 `.ninfer`，要落地必须自己打包（见 §七.3，未验）。

---

## 三、.ninfer 方言：我们引擎能吃哪一种（二进制证据）

### 3.1 扫描结果（只读 exe 字节，未运行）

| 格式串 | 本机 `engine/ninfer-serve-89.exe`（801,324,544 B） | 沈三殊 sm_89 引擎（264,173,568 B，sha256 `566f0d0e…`） |
|---|---|---|
| `ptq1_g128_fp16` | ✅ ×1 | ❌ 0 |
| `t2_g128_fp16` | ✅ ×1 | ❌ 0 |
| `PTQ1_0_G128` | ❌ | ✅ ×1（汇编里逐字符比较） |
| `PQ2_0_G128` | ❌ | ✅ ×1 |
| `t5_g128_fp16` | ❌ | ❌ |
| `nvfp4_g16` | ❌ | ❌ |
| `rk2v4`（KV） | ✅ ×46 | ❌ 0 |
| `k8v4`（KV） | ✅ ×396 | ✅ ×9 |
| `dflash2` | ✅（`--spec` 可选 mtp / dflash / dflash2） | ✅ ×21 |

### 3.2 本机模型的真实格式（读前 1 MiB 的 JSON 头）

```json
{"id":"weight/000000","shape":[4096,5120],"format":"ptq1_g128_fp16","layout":"row_split_k128_v1", ...}
```

⇒ 本机 = **`ptq1_g128_fp16` + `row_split_k128_v1`**，即 P 家（Prism/Ambolio 之外的）那条 NInfer 主线方言。

### 3.3 方言血统表（fyb423 README 原话）

| 容器格式 | 血统仓库 | 我们能否直接用 |
|---|---|---|
| `ptq1_g128_fp16` / `t2_g128_fp16` | 我们这条线（801 MB 构建） | ✅ |
| `PTQ1_0_G128` / `PQ2_0_G128` | Ambolio/ninfer-4090-windows v1.0.6 / v1.0.8 | ❌ 需换引擎 |
| `t2_g128_fp16`（WaveCut v3） | iamwavecut/ninfer-all | ⚠️ 格式名同但我们构建未见该容器版本，且体积 8.87 GiB |
| `NVFP4`/groupwise-int | Neroued/ninfer（原始上游） | ❌ |

**判断任何一份 .ninfer 的方言：读它前 1 MiB 里的 `format` 字段。**

### 3.4 按架构的 KV 支持口径（不同构建互相打架，记下来）

| 架构 | fyb423 给的表（Ambolio 血统） | 我们的实测 |
|---|---|---|
| sm_86（30 系） | bf16 / int8 | 未验 |
| **sm_89（40 系）** | bf16 / int8 / fp8 / rk4v4 / rk4v4-e8 | **实测 rk2v4-e8 可跑**（现役） |
| sm_120（50 系） | bf16 / int8 / fp8 / nvfp4 / k8v4 | 未验 |

⇒ **KV 档位清单随构建而异，任何"某架构不支持某档"的说法都必须以本机 `--help` 为准**。

---

## 四、KV 量化：九档清单与代价（我们构建的权威口径）

本机 `engine/help-full.txt:82-83` 原文：

```
--kv-dtype T   KV storage: bf16 (default), int8, fp8, rk8v4, rk4v4, rk4v4-e8, rk2v4-e8, nvfp4 or k8v4
```

| 档 | 每 64-token 页 | 相对 bf16 | 困惑度代价 |
|---|---|---|---|
| bf16 | 4.00 MiB | 1.00× | 0 |
| rk4v4-e8 | 1.10 MiB | 0.275× | **+0.30%** |
| **rk2v4-e8**（现役） | **0.84 MiB** | **0.21×（省 79%）** | **+2.14%（PPL 9.23967）** |
| int8 / fp8 / rk8v4 | 行粒度缩放 | — | **已知禁忌**：行粒度（fp8 行 256、rk8v4、int8）在 32 GiB 卡上实测异常，别用 |
| nvfp4 / k8v4 | 组 16 / K-FP8+V-NVFP4 | — | k8v4 是交付口径，非省显存档 |

出处：`repos/ninfer-fusion-kvmem` 的 配方-8GB档-实测支撑-20261008.md:22,31、8G档-配置提醒-20261008.md:69、实测回执与反馈.md:392,426、复现白皮书-NInfer-KVMem环-20261002.md:204-206,444。

**结论：没有比 rk2v4-e8 更省的 KV 档。** 想再省只有压池子（`--kv-capacity`）或把 KV 挪到宿主（`--host-kv-mib`，只影响容量不影响页大小）。

---

## 五、Strata 推荐模型：真实体积与"能跑"的门槛

### 5.1 Qwen3.8-Flash-Next（GSQ-RCO，ISTA-DASLab，★1089 / dl 7,604,113）

**关键结构**：每个档都是两个 shard，**shard2 在所有档完全相同 26.82 GiB（28,800,138,432 B）** —— 那是 `per_layer_token_embd`（51.2B 参数的逐层 n-gram 表，IQ4_NL），**可以 mmap 留在磁盘上，每 token 只读一行**。真正要常驻的是 shard1。

| 档 | bpw | shard1 | shard2 | 合计 | 官方一句话 |
|---|---|---:|---:|---:|---|
| **Q2_0** | 2.40 | 37.6 GB | 28.8 GB | **66.4 GB** | 最快；避开查表格式；比 IQ2_XS **3.4× prompt 吞吐、1.9× 更低端到端延迟**；task avg 89.07 |
| IQ2_XS | 2.50 | 39.2 GB | 28.8 GB | 68.0 GB | 同质量最小（89.16） |
| IQ3_XXS | 3.00 | 47.0 GB | 28.8 GB | 75.8 GB | AIME25 追平基座；比 IQ3_S 省 7.8 GB，让 1.52 GPQA / 0.57 LCB |
| IQ3_S | 3.50 | 54.8 GB | 28.8 GB | 83.6 GB | **推荐**；AIME25 100.00 = 基座、GPQA 92.93 > 基座 91.92 |
| mmproj BF16 | — | 0.91 GB | — | — | 多模态才要 |

原文：**"只有 shard1 必须常驻，shard2 可 mmap 留盘"**（`-lm mmap --lazy-mode on`）。

### 5.2 其它 Strata 侧的档

| 模型 | 档 | 体积 | 备注 |
|---|---|---:|---|
| `ISTA-DASLab/…-GSQ-RCO-Coder-GGUF` ★540 | **IQ1_M** | **55.24 GB**（27.58 + 26.82） | Coder 只留 512 routed expert 中 256 个，有效 1.89 bpw |
| `agentionai/…-Gyro-GGUF` ★146 | Gyro-S TQ1_0 | 54.47 GiB | 省内存但更慢 |
| 同上 | Gyro-M TQ2_0 | 85.65 GiB | |
| 同上 | Gyro-L TQ3_0 | 100.88 GiB | |
| `alesha-pro/…-abliterated-…-Strata-GGUF` ★203 | 同 ISTA 四档 | 66.4–83.6 GB | 去拒答版 |
| `wszhoho/qwen3.8-flash-next-strata-bpw392`（魔搭，10-28） | 3.92 bpw | 未测（HF 匿名 401） | 中文社区自制 Strata 专用档 |

### 5.3 Qwen3.6-35B-A3B（8G 卡更现实的对象）

`unsloth/Qwen3.6-35B-A3B-GGUF` ★1741 全档（GiB）：**IQ3_S 12.74** / Q3_K_S 14.30 / Q3_K_M 15.46 / Q3_K_XL 15.69 / IQ4_XS 16.51 / IQ4_NL 16.80 / IQ4_NL_XL 18.16 / Q4_K_S 19.46 / MXFP4_MOE 20.22 / Q4_K_M 20.61 / UD-Q4_K_XL 20.82 / UD-Q5_K_S 23.23 / Q5_K_M 24.64 / Q5_K_XL 24.77 / Q6_K 27.30 / Q6_K_XL 29.66 / Q8_0 34.37 / UD-Q8_K_XL 35.81。

**8G 卡的最低可行档 = IQ3_S 12.74 GiB**：权重放不下显存，专家必须流式（Strata 的 `--expert-cache`），**内存需求 32 GB 起（引擎 21 GiB + 系统 6 GiB）**——我们正好 32 GB，**没有任何余量，不推荐**。

### 5.4 落到"我们这台机器"的判定

| 方案 | 常驻需求 | 结论 |
|---|---|---|
| Qwen3.8-Flash-Next Q2_0 @ Strata | 37.6 GB 常驻 + 28.8 GB 磁盘 | ❌ 我们 32 GB 内存，不可能 |
| Coder IQ1_M @ Strata | 27.58 GB 常驻 | ⚠️ 内存刚好卡死（27.58 + 6 系统 > 32），且 decode 会掉到 20 tok/s 量级 |
| Qwen3.6-35B-A3B IQ3_S @ Strata | 12.74 GiB 权重，专家流式 | ⚠️ 能起、约 57–63 tok/s（4080S 8G 档实测），但我们内存无余量 |
| **Bonsai-2-27B PTQ1（现役）** | 5.96 GiB 权重 + 1 GiB 运行时 | ✅ **97–98 tok/s，本期没有更好的替代品** |

---

## 六、魔搭中文社区：清单与 8G 实测读数

### 6.1 有数的两条 8G 记录（都值得抄参数）

**① `q409640976/ninfer-kvmem-heretic-bonsai2-27b`（★4，2026-10-08）—— 我们的模型就出自这里**

| 指标 | RTX 4060 8 GB 实测（MTP 开） |
|---|---|
| decode | **约 73 tok/s** |
| prefill | 80–550（长提示词旧引擎 547.8） |
| 常驻 KV 窗口 | **25,408 token（rk4v4-e8），逻辑上下文 131,072** |
| 显存 | 权重 5.94 GiB + 运行时 668 MiB，余约 255 MiB |
| 首启 | 约 90 秒自适应测量 |

- 新旧引擎 A/B："decode 79.7 → 72.7 tok/s，常驻窗口 4,032 → 25,408 token"。
- **MTP 草稿头占约 0.42 GiB**，这是窗口从 33,536 被压到 25,408 的原因；**关 MTP 可换回 33,536 但 decode 跌到约 20 tok/s**。
- 环境：驱动 616.56 / CUDA UMD 13.4，默认端口 8095，模型名 `qwen3.8-27b`。

**② `KVMem/Bonsai2-27B-T5-MTP-Q4-NInfer`（魔搭 KVMem 官方仓，10-28）—— 官方推荐的 8G 档**

文件 `Bonsai2-T5-MTP-r3-Q4.ninfer` = **6,182,359,808 B（5.758 GiB）**，sha256 `568ede3843f94d0e9a6bae3b022fcf859230bb602ef937f2ade9283a8c195c92`。
"T5 是三值权重格式，并非 5-bit；Q4 指 MTP 矩阵的量化精度"。`provenance.json`：`tensor_formats {t5_g128_fp16:322, bf16:363, fp32:96, gguf_q4_0:9}`，text 源 = prism-ml PTQ1_0（5,946,648,928），MTP 源 = ProCreations/Ternary-Bonsai-2-27B-MTP r3-mtp（849,400,392，BF16→Q4_0）。

**官方推荐 8GB 配置**：驻留预算 **36K = 36,864 token** + 输出预留 4K、**KV = NVFP4**、MTP 固定 3 草稿、GDN 状态 FP16、prefill 批量 256、并发 1、CUDA Graph 开（留 256 MiB）。
**实测**：RTX 5050 Laptop 8GB / 35 W，36,669 token 输入后完整生成 4,096 token，**约 22 tok/s**，显存峰值 **约 6.78 GiB（6,944 MiB）**。需 **KVMem v0.19.0-rc1** 引擎。

**③ `shensanshu/ninfer-ada-ternary`（魔搭，★86，2026-09-27）—— PQ2 极速档**

- 模型："Bonsai-2-27B 三元 PQ2 约 6.7 GiB + DFlash2 投机件约 9.8 GiB"；包内 sm_89 + sm_120 两支预编译引擎。
- **RTX 4080 SUPER**：ctx 262144 / fp8 KV / MTP K=3 → **decode 226 t/s、prefill 2,230 t/s**，4,070 token 冷缓存 TTFT 1.9 s；**DFlash2 K=7 → decode 353.8 t/s**；不投机对照 63.7 t/s；RTX 5090 D 志愿者 512.9 t/s。
- 显存："权重 6.70 GiB + 运行时 = **8.54 GiB** ⇒ 16 GB 舒服，12 GB 有专门 4-bit KV 启动件" ⇒ **8 GB 卡放不下**。
- 下载包「①极速档（PQ2三元）.zip」约 18.4 GiB，**解压路径必须纯 ASCII（不能有中文）**；内含 00–11 页中文白皮书 + 完整源码树 + patches（`src/targets/qwen3_6_27b/`、`ternary_rowsplit_mma_small_t.cuh`、`tools/pack.py`）。

**④ `shensanshu/strata-hardware-adapt-guide`（魔搭，★10）** —— 就是本机 `C:/Users/Administrator/Downloads/Strata-本地硬件适配指南-20261013/` 的来源件（README 38,207 B + `方向手册-本地显卡适配-20261008.md` 17,929 B），开头写"**依据的引擎版本：0.1.43.1**"。**证实：这两份中文手册的作者是沈三殊（shensanshu），不是 Strata 作者。**

### 6.2 魔搭 ninfer / Strata 生态仓清单（搜索实测）

| 仓 | 星 | 说明 |
|---|---:|---|
| `shensanshu/ninfer-ada-ternary` | 86 | PQ2 极速档完整包（见上） |
| `shensanshu/ninfer-master-shensanshu-kvmem` | 36 | KVMem 主线 |
| `shensanshu/strata-hardware-adapt-guide` | 10 | Strata 中文调优手册（0.1.43.1） |
| `working87/ninfer-bonsai2-pq2-engine` | — | 沈三殊编译件的转发镜像，README 明写"所有文件都由沈三殊编译和发布，这里只是转发镜像" |
| `KVMem/Bonsai2-27B-T5-MTP-Q4-NInfer` | — | 官方 8G 档（T5） |
| `KVMem/Bucoid-Qwen3.8-27B-IQ4_XS-MTP-DFlash2-Q3-NInfer` | — | 10-29 新 |
| `KVMem/Qwen3.8-27B-Coder390-Q3LynnStyle16G-MTP-DFlash2-Q3-NInfer` | — | 10-29 新，16G 档 |
| `fyb423/Swift-Bonsai-2-27B-NInfer` | — | PTQ1_0_G128 / PQ2_0_G128 |
| `ustcliusaisai/DeepSeek-V4.1-Flash-1017-GSQ-RCO-IQ2_XXS-Strata` | 5 | Strata 线，dl 517 |
| `windecay/Strata_Windows` | 14 | Windows 整合 |
| `wszhoho/qwen3.8-flash-next-strata-bpw392` | 5 | 3.92 bpw Strata 专用 |
| 其它 | — | `ml-resources/ninfer-ada-ternary`、`yudssd/ninfer-ampere-ternary`、`hf/neroued-*` 镜像、`Lxt1992`、`sanbanfu`、`seer2333`、`xiuming/ninfer-bonsai-4070ti`、`jiaheng0815`、`mymodel3861`、`mrwan0410`、`LittleStar888`、`wandou123456/Qwen38-Strata-Runtime`、`mymodel3861/Strata-oldhw-engine` |

### 6.3 8G 显卡专项搜索的负面结论（重要）

- 魔搭搜 "**4060**"：全站 **11 条**，相关只有 `q409640976`（RTX 4060 8GB 实测）、`Lxt1992`、`snowen/index-translate-9b-ninfer`。
- 魔搭搜 "**4060Ti**"：全站 **4 条**，**无一相关**。
- ⇒ **魔搭上没有 4060Ti 8G 的部署记录**。我们这台（4060 Ti 8G，池 40000 / rk2v4-e8 / 97 tok/s）在公开材料里**是独一份**。

---

## 七、落到本机的可行动作（按性价比排序）

### 7.1 立刻可做：试 `--spec dflash2`

我们引擎 `help-full.txt:176` 明确支持 **`--spec mtp|dflash|dflash2`**，而沈三殊在 4080S 上给出 MTP K=3 → 226 t/s、**DFlash2 K=7 → 353.8 t/s（+56%）**。这条我们**尚未试过**（现役是 mtp/draft4）。
建议（需 lead 批时间窗，重启引擎）：`--spec dflash2 --draft-tokens 7`，其余不动，看显存余量与 tok/s；若 OOM 回退 `--draft-tokens 4`。

### 7.2 不建议：换 PQ2 引擎

- 收益：PQ2 权重 + DFlash2 的组合在 12–16 GB 卡上很猛；
- 代价：**ada 引擎二进制里没有 `rk2v4`**（只有 k8v4），KV 池最省只能到 k8v4/nvfp4 级 ⇒ 我们的 40,000 池要塌到 8,000–12,000 级，**上下文直接退到 8K–16K**；
- 且 PQ2 权重 6.71–7.74 GiB + 运行时 ≈ 8.5 GiB，**8 GB 卡物理放不下**（官方原话"16GB 舒服，12GB 有专门件"）。
⇒ **8 GB 机器上，PQ2 是负收益。**

### 7.3 值得评估（未验）：GSQ-RCO 6.05 GiB 权重换进 .ninfer

- 目标：同 6 GB 体积，WikiText-2 PPL −5.84%（8.6690 → 8.1627）。
- 障碍：那是 GGUF（`PTQ1_0`），我们引擎只吃 `.ninfer` 的 `ptq1_g128_fp16` + `row_split_k128_v1`；需要打包工具（`shensanshu/ninfer-ada-ternary` 包内 `tools/pack.py` 有参考实现，但那是 PTQ1_0_G128 方言的打包器）。
- 风险：`row_split_k128_v1` 布局是量化的行切分 + K 维 128 对齐，**重新打包若不做逐字节搬运就会二次损失**（fyb423 强调的点）。
- 结论：**属"可研究但不在本期"**，需一次专门的实验（约 1 人日）。

### 7.4 已确认无需再查的事

- KV 侧无更省档（rk2v4-e8 已是九档之末）。
- 魔搭/HF 上没有比 5.54–5.96 GiB 更小的可用 27B 三值件（`t2_g128`/WaveCut 8.87 GiB 更大，`t5` 5.758 GiB 但方言不同且需 v0.19 引擎）。
- 没有 4060Ti 8G 的公开部署记录可以对照。

---

## 八、下载命令（拿到就能跑）

### 8.1 HuggingFace（hf CLI）

```bash
export HTTP_PROXY=http://127.0.0.1:7897 HTTPS_PROXY=http://127.0.0.1:7897
pip install -U "huggingface_hub[cli]"

# 官方 PTQ1_0（5.54 GiB）
hf download prism-ml/Ternary-Bonsai-2-27B-gguf --include "*PTQ1_0*" --local-dir D:/models/ternary-bonsai2

# 质量线 PTQ1_0 GSQ+RCO（6.05 GiB）
hf download ProCreations/bonsai-2-27b-gsq-rco-gguf --include "*.gguf" --local-dir D:/models/bonsai2-gsq-rco

# Strata 侧最小可用档（只需常驻 shard1，shard2 可留盘）
hf download ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-GGUF --include "*Q2_0*" --local-dir D:/models/qwen38fn-q2
```

### 8.2 魔搭（modelscope CLI）

```bash
pip install -U modelscope
# 我们现役模型的来源包（含 sm_89 引擎 + 双模型）
modelscope download --model q409640976/ninfer-kvmem-heretic-bonsai2-27b --local_dir D:/models/q409640976
# 沈三殊 PQ2 极速档（18.4 GiB，解压路径必须纯 ASCII）
modelscope download --model shensanshu/ninfer-ada-ternary --local_dir D:/models/shensanshu-pq2
# KVMem 官方 8G 档（T5，需 KVMem v0.19.0-rc1 引擎）
modelscope download --model KVMem/Bonsai2-27B-T5-MTP-Q4-NInfer --local_dir D:/models/kvmem-t5
```

---

## 九、不确定项（写清边界，别当结论用）

| 项 | 状态 |
|---|---|
| GSQ-RCO 的 6.05 GiB GGUF 能否无损失包成我们的 `ptq1_g128_fp16 / row_split_k128_v1` | **未验**（需 pack 工具 + 一次实验） |
| `t2_g128_fp16` 的 WaveCut v3（8.87 GiB）我们构建能否加载 | **未验**（格式名匹配，但体积超 8 GB，实机不可行） |
| `--spec dflash2` 在 4060 Ti 8G 上的实际 tok/s 与显存 | **未验**（引擎支持，未试） |
| fyb423 的 sm_89 KV 表不含 rk2v4-e8，与我们实测冲突 | **口径差异**，需按 `--help` 判断，勿引用该表否定 rk2v4 |
| `Lxt1992/ninfer-ternary-bonsai2`（8.307 GB）的容器格式 | **未验**（体积已超 8 GB，判定不可用） |
| 魔搭 `wszhoho/…strata-bpw392` 的实际体积 | **未测**（HF 匿名 401） |

---

*本报告所有体积为 API 返回字节数；所有速度均标注出处或标"未验"；未运行任何 GPU 引擎，未改动 repos/。*
