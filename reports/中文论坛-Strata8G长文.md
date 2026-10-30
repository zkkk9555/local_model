
# 中文论坛 · Strata 8G 长文实操侦察

侦察时间：2026-10-30　范围：知乎 / CSDN / 博客园 / 贴吧 / 微信公号（搜狗微信）/ 小红书 + 上游文档核对
判定标准：只采信能给出 URL 与具体参数/数字的文本；"听说能跑"一律标【未核源】。

---

## 一、结论（先说结果）

1. **中文圈没有"8G 单卡跑 125B"的长文实测。** 按 8G 关键词检索到的标题文章（小众软件、多个公众号）全是"门槛新闻"，正文无 8G 数字；唯一自己声明没实测的是鹿哥聊AI《8GB 显存跑 125B 大模型?Strata 的分层加载思路》。
2. **8G 唯一带数字的一手证据来自小众软件的用户反馈表**：RTX 4060 Ti 8GB + 32GB 内存 + Coder IQ1_M = **19–21 tok/s**；双 Quadro RTX 4000 8GB + 96GB + Swift IQ2_XS = **18–23 tok/s**。<https://www.appinn.com/strata/>
3. **"8GB 显存就够"基本是标题党。** 官方要求 12GB 显存 + 64GB 内存 + 约 80GB 磁盘；32GB 内存只够跑 Coder 精简分片（第一分片 29.6GB）。<https://post.smzdm.com/p/a5rx8kml/>
4. **虚拟内存/页面文件：中文侧只有定性结论**（"能避免部分报错，但频繁换页仍会很慢"），**没有任何一篇给出页面文件数值**。<https://itbanana.com/blog/strata-app-guide/>　具体"固定大小、初值=最大值、例如 65536 MB、低于 4GB 会警告"只出现在上游 `docs/DETAILS.md:1257`，中文长文里查不到二次实测。
5. **`STRATA_ARENA_PIN_GIB` 不是页面文件旋钮。** 它是 Windows 上 pinned expert arena 的上限，**默认 29 GiB**；只有多卡 helper（WDDM）场景下 host arena 默认只注册 8 GiB，才需要用它覆盖。中文侧仅两篇是上游文档摘译（CSDN 152447923、公众号硅猿AI），均无 8G 实测。

---

## 二、8G 相关一手数字

| 机器 | 权重 | 速度 | 出处 |
|---|---|---|---|
| RTX 4060 Ti **8GB** + 32GB | Coder IQ1_M | **19–21 tok/s** | appinn 反馈表 |
| Quadro RTX 4000 **8GB ×2** + 96GB | Swift IQ2_XS | **18–23 tok/s** | appinn 反馈表 |
| RTX 3070 **8GB** / R9 7900 / 64G DDR5-5200 | IQ2_XS | **Strata 40 t/s**（32K），同机 llama.cpp 18.22 t/s | CSDN liuyunak |
| 同上（调 offload） | IQ2_XS | offload 加大反而 **14.05 → 7.85 → 5.73 t/s**，prefill 18 → 1.7 t/s；GPU 仅 45.9 W（上限 21%），CPU 90 W | CSDN liuyunak |
| 12GB 才是官方最低门槛 | Q2_0/IQ3 档 | 5070 Q2_0 94 / IQ3_S 53；3060 IQ3_XXS 30 | appinn、smzdm |
| 16GB 给对照：上下文吃显存 | IQ3_XXS | 16K→10.2GiB（6310 槽）；131072→5247 槽；12GB 5070 跑 IQ3_S 专家缓存只剩 **3.7GiB / 1280 专家** | CSDN 167485606 |

官方档位总需求（内存+显存合计）：Q2_0 **37.6GB** / IQ2_XS **39.2GB** / IQ3_XXS **47.0GB** / IQ3_S **54.8GB**；README 另给"每多 1GB 显存约多 700 个专家"。<https://blog.csdn.net/gitblog_00511/article/details/167485606>

---

## 三、逐源核实

### 3.1 知乎（经 r.jina.ai 绕 403）
- <https://zhuanlan.zhihu.com/p/2089282096925878242>《Strata 让普通游戏电脑跑 1250 亿参数大模型》— 官方 RTX 5070 **12GB** + 64GB 实测；各档"内存+显存"需求同上表；硬盘需约 29GB 查找表 + 约 80GB 空闲；首启装 35–55GB、卡 1–3 分钟。
- <https://zhuanlan.zhihu.com/p/2090202087120553566>《Token自由！12GB 显卡跑1250亿参数大模型》— RTX 3060 **12GB**、41 次请求：加载 33.02 GiB 专家 0.21–0.25 GiB/s（155–179 秒）；专家缓存 3488–3880 个占 4.69–5.21 GiB；MTP 5.214GB 张量→0.889GB 包→707MB 专家+116MB 稠密；草稿词表中日韩 348 MiB vs 英文 133 MiB；12GB 推荐 32K 上下文 + 8-bit KV；总下载 68GB。
- 两篇都是 12GB 机器，**没有 8GB 章节**。

### 3.2 微信公众号（搜狗微信检索，6 篇）
1. 鹿哥聊AI《8GB 显存跑 125B 大模型?Strata 的分层加载思路》2026-10-27（1522 字）：只有思路+安装步骤，原文自述"性能数字都是项目方说法，我没实测"。**无 8G 数字。**
2. 两根均线法《8GB 显存也能跑 125B》2026-10-27：Strix Halo 8060S / 128GB 统一内存划 96GB；自测 llama.cpp Vulkan IQ4_XS 全驻留 **31 tok/s**，Strata 数字"还在跑"。可用细节：MTP 草稿层约 5.2GB 独立；首载 "Packing the experts" 会长时间 0.0/0.0 GB 别中断；自打补丁量化被拒 `unsupported encoding or shape`；一个目录只放一个主模型，多分片要填 `00001-of-00003` 首分片全路径。
3. 硅猿AI《DeepSeek 1017 三引擎同机实测》2026-10-25（8187 字，本批最硬）：RTX 5090 32GB / 96GB。Strata 2.25bpw 解码 **25.35** / 1.75bpw **35.49** / Xolotl 16.57 / Maya 32.31 tok/s；prefill 227.6 / 311.1 / 86.0 / 874.8；首字 13.82 / 5.34 / 19.53 s。质量：1.75bpw KL 0.217、PPL +21%（散文 +53%）；2.25bpw KL 0.107、PPL +7.3%。同机 Qwen3.8-Flash-Next 125B 在 5090 上 160.2 tok/s。
4. AI技术小飞《Strata 隐藏加速设置》2026-10-20：M5 Pro 48G。原厂 config 的 suffix-draft 为 **0（默认关）**、args 缺 `--mtp`；开 `--suffix-draft 3`+MTP 后 Q2_0 **30–35 → 40–80**（近 90）、IQ3_S 20–30 → 30–50、UD_Q4_K_XL 10–20 → 20–40。MTP 文件约 5G 从 ModelScope 下。
5. 寂寞的熊猫《Strata 升级支持 DeepSeek V4.1-Flash:实测从 32 跑上 59 tok/s 与部署踩坑》2026-10-28：4×24GB + 256GB。冷 **32.5** → 热 **59.3** tok/s（36.6/52.2/59.2/59.2/59.3）；6682 个 CPU 专家 64.9GB **33.2 秒**预载并分双 NUMA；预载条件=可用内存装得下全部专家且留 **≥8GiB** 余量。日志原文：DSpark not loaded: the routed experts (149 GB) are far more than the GPU holds (97 GB), where its verify rounds read 3.3x a token's bytes and gain nothing。
6. ATech《2080Ti 单卡 IQ3_S vs IQ4_XS》2026-10-17：双 2080Ti 22G/192G。IQ3_S(arena+MTP) 128K 下 **63.6–67.3**；IQ4_XS(mmap) 14.9–33.7；MTP 接受率 66–77% 但 decode 不涨；预热无增益（0 major faults、每请求落盘 3–5MB）；瓶颈是 CPU 无 AVX-512。

> 6 篇里 **0 篇**给出 8G 实测；STRATA_ARENA_PIN_GIB 仅硅猿AI 一篇提及。

### 3.3 CSDN
- 搜索 API 可用：`https://so.csdn.net/api/v3/search?q=Strata%208G&t=all&p=1`（result_vos）；正文页连抓会 521，间隔 8–9 秒可过。
- <https://blog.csdn.net/liuyunak/article/details/167660758>《MoE 引擎选型实测：35B 别换引擎，125B 才值得》— **唯一的 8G 实机长文**（3070 8G / 64G / Windows / llama.cpp b11510）。同权重 IQ2_XS：llama.cpp **18.22** vs Strata **40** t/s；差约 2.5 倍，其中 MTP 草稿权重贡献 1.6–1.8 倍；结论"专家池装不进内存才值得换专用引擎"。
- <https://blog.csdn.net/gitblog_01036/article/details/152447923>《Strata 双/多 GPU 部署详解》= `docs/SECOND_GPU.md` 摘译：WDDM 下 host expert arena 只注册 8 GiB（`STRATA_ARENA_PIN_GIB` 覆盖）；`--gpu1/2/3-experts` 填槽位数；`--peer-device N` 与 `--layer-split`、`--expert-cache-device1..3` 互斥；`--peer-reserve-mib` 默认 600、`--peer-slots` 默认 0。
- <https://blog.csdn.net/gitblog_00511/article/details/167485606>《避坑实录：冷启动为什么慢如蜗牛》= README/DETAILS/TROUBLESHOOTING 摘译，含金量高：冷启动要读 **34–55GB** 进 RAM；**任务计划程序**启动 0.05 GiB/s（821–841 秒）vs 手动 1.42–1.52 GiB/s（约 35 秒），修法 Priority 改 Normal + 勾"使用最高权限"（否则丢 SeLockMemoryPrivilege 大页权限）；`--vram-reserve-mib 2048` 可与游戏共存；UD-Q4_K_XL 在 64GB RAM+12GB GPU 上 7–8.5 tok/s。
- <https://blog.csdn.net/weixin_29055699/article/details/168755710>《RTX 4060 Ti 跑千问 IQ3_S》**是 AI 幻觉垃圾**（称 Qwen3.8-Flash-Next 只有 32 层/FP16 5.2GB、把 4060 Ti 写成 GA104 16GB、大段混入 vLLM/TensorRT）。→ CSDN 上带"实测"的 Strata 帖多为内容农场，不可引用。

### 3.4 其它中文站
- <https://itbanana.com/blog/strata-app-guide/> 部署教程+QA：Q5"RTX 3070 8GB 可以吗"→"8GB 卡能尝试，但较慢，官方推荐 12GB 及以上；多卡时 8GB 及以下的卡默认不用"；Q17"总是爆内存，增加虚拟内存就行吗"→"虚拟内存可能避免部分报错，但频繁换页仍会很慢"。
- <https://post.smzdm.com/p/a5rx8kml/>（2026-10-02，标注"内容由 AI 生成"，但逐条标了 B站/小红书/知乎 出处）9 组：5070 12G 短对话 93 t/s、32K 提示 15 秒≈2170 t/s；12G+64G 168K 长上下文 峰值 48/平均 40；4060Ti 16G IQ3_XXS 30（同机 llama.cpp 15–16）；16G 调优 65→110；4070TiS 走 OCuLink 只 19–27（PCIe x4 ≈直插 28%）；2080Ti 22G+SATA 峰值 63；5060Ti 16G+96G DDR5-7200 峰值 100；RX 9070 XT Q2_0 60/IQ2_XS 52。**并直接判定"8G 显存能跑 125B"是标题党。**
- 该文转述知乎作者"青风"的调参：GPU 89W/285W 上限、在等 CPU 算冷专家；workers 13 个反而比 9 个慢；`--calibrate` 的 pcie-frac 约 0.2 最优；KV 用 int8；上下文到 99.5% 时输出空间只剩 431 token；64K 档每轮另有 6–7 秒把 KV 从 RAM 搬回 VRAM。

### 3.5 上游文档核对（github.com/Niko1221/Strata/raw/main 可直连）
- `docs/SECOND_GPU.md`：**"Under WDDM (Windows, WSL2) only 8 GiB of the host expert arena is registered with CUDA when helpers are on (`STRATA_ARENA_PIN_GIB` overrides it). On Linux the whole arena is registered."**
- `docs/DETAILS.md:1257`：**"ExpertCache: cudaMalloc(...) failed: out of memory … although VRAM is free | Windows' page file is off or tiny. Every allocation on the card is also charged to Windows' commit (RAM + page file). Set a fixed page file size, the same initial and maximum (for example 65536 MB), and restart. The engine retries with a smaller cache, and setup warns about a page file under 4 GB."**
- `docs/DETAILS.md:255-259`：**"Windows, opt-in: `STRATA_PIN_BY_NEED=1` (arena on one GPU) registers the profile's non-GPU-resident experts by rank up to `STRATA_ARENA_PIN_GIB` (29 by default on Windows) instead of the first ~30 GiB."** 配套 `STRATA_PIN_RESERVE_MIB`；日志 `[pinned-memory-exhausted]` 会提示该从哪个值起步。
- `docs/DETAILS.md:1258`：首次启动读 34–55GB 进 RAM 并 pin 一部分，"卡几分钟"是正常的；`1256`：`cudaHostRegister ... out of memory` 在 Windows 属正常（按层分片 pin）；`1259`：RAM 不足时引擎启动会警告专家剩余 < ~6GB。

---

## 四、"虚拟内存 / 页面文件 / STRATA_ARENA_PIN_GIB"的准确口径

| 民间说法 | 实际含义 | 证据 |
|---|---|---|
| "爆显存但 VRAM 明明空着" | Windows 把每张卡上的分配计入 commit（RAM+页面文件）；页面文件关闭或太小就 cudaMalloc 失败 | DETAILS.md:1257 |
| "页面文件设多大" | **固定大小、初值=最大值，官方示例 65536 MB**；< 4GB 时 setup 会警告 | DETAILS.md:1257 |
| "加虚拟内存就能跑 8G" | 只能避免部分报错，频繁换页仍慢；不能替代物理内存带宽 | itbanana Q17 |
| STRATA_ARENA_PIN_GIB | **pinned expert arena 上限，Windows 默认 29 GiB**，需配 `STRATA_PIN_BY_NEED=1`；多卡 WDDM helper 下默认只注册 8 GiB 时才要覆盖 | DETAILS.md:255-259、SECOND_GPU.md |
| 误传 | 中文长文把该变量当"页面文件/显存开关"的说法**无一手依据** | 6 篇公众号 + 2 篇知乎均未给出该变量的取值实测 |

---

## 五、检索受阻记录（避免重复踩坑）

- 贴吧：`tieba.baidu.com/f/search/res` 直接 403（先取首页 cookie 也一样）。
- 博客园：`zzk.cnblogs.com/s?w=Strata 8G` 返回 5.4KB 空壳，无结果。
- 小红书：`xiaohongshu.com/search_result?keyword=Strata 8G` 返回 200 但只有客户端渲染壳（60KB，无 noteId/displayTitle），需登录态。
- 百度 `site:` 全是空壳、360 直接反爬；**Bing 忽略查询词**（所有查询返回同一组结果），只能当发现层。
- 搜狗微信可用：`/link` 返回 822 字节中转页，需取 `var url = '...'` 再拼所有 `url += '...'` 片段；签名 URL 会过期须即抓。
- 知乎 403 → 用 `https://r.jina.ai/<url>` 可读全文。
- CSDN 正文 521 → 间隔 8–9 秒重试可过。
- 本会话 `web_search` 工具不可用（缺 DEEPSEEK_API_KEY），全程走 HTTP 代理直抓。

---

## 六、对本机（4060 Ti 8GB + 31GB 内存）的落地要点

1. **内存是硬瓶颈，不是显存。** 31GB < IQ2_XS 要求的 39.2GB，只剩 Coder IQ1_M 一档（第一分片 29.6GB）；8G 实测区间就是 19–21 tok/s。
2. **页面文件按官方固定 65536 MB**（初值=最大），否则 8G 卡最容易撞 `cudaMalloc ... out of memory`。
3. **别留 `STRATA_ARENA_PIN_GIB` 的 Windows 默认 29 GiB**——31GB 机器上它和系统抢内存；配合 `STRATA_PIN_BY_NEED=1` 时显式调小，并按 `[pinned-memory-exhausted]` 日志反推起点。
4. **不要开多卡 helper**（`--gpu1/2/3-experts`、`--peer-device`）：8GB 卡在多卡场景默认被排除，WDDM 下 arena 只注册 8 GiB。
5. 上下文与 KV：8G 卡上下文开大必然挤掉专家缓存（16G 卡 16K 就要 10.2GiB），建议小上下文 + int8 KV + `--vram-reserve-mib 2048` 保桌面。
6. MTP（`--suffix-draft 3` + mtp 目录）在 12GB+ 上带来 1.3–2 倍，**8G 上无一手实测**，属【未核源】；且多占约 5GB 内存/显存，31GB 机器慎开。
7. 预期管理：同权重同机 llama.cpp 18.22 vs Strata 40 t/s（3070 8G），Strata 的优势只在"专家池装不进内存"的场景；8G 卡功耗上不去（45.9W / 上限 21%），瓶颈是搬运不是算力。

*【未核源】标记项：8G 上 MTP 的收益、8G 单卡跑 IQ2_XS 以上的可行性、把 STRATA_ARENA_PIN_GIB 当"爆显存解药"的说法。*
