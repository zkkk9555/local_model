# Strata 中文社区「8G 显存」实操侦察

采集时间：2026-10-30 09:24–09:55（Asia/Shanghai）
采集渠道：B站（已登录，字幕+评论+简介 API）、知乎（jina reader 绕过 403）、CSDN、什么值得买、itbanana、小众软件
网络：全部经 HTTP(S)_PROXY=http://127.0.0.1:7897
约束：只读。未启动/停止任何引擎或服务（8091/8088/8080 未触碰），未改 C:/Project/local_model 下任何文件。
可信度标记：**【一手/实测】** = 作者贴出机器配置与数字；**【官方口径】** = 引官方 README/文档；**【二手转述】** = 经他人转述未见原文；**【未核源】** = 无数字、无 URL 支撑。

---

## 0. 结论（先看这 8 条）

1. **中文社区里「8G 显存跑 125B」的一手实测确实存在，但只有 3 个可验证样本**：20–37 t/s（4060 8G + 32G 内存，IQ3_S）与 11–18 t/s（P104-100 8G + 64G 内存，32K 上下文）。
2. **官方 README 的单卡门槛是 12GB**；「8G」在官方文本里的位置是**多卡时每张卡 8GB 以上**，以及「RAM+VRAM 合计 ≥32GB（公式 RAM+VRAM−5G）」的合计口径 —— 单卡 8G 属于社区自担风险的越界区。
3. **标题里的「8G+32G」多数不是 UP 自己的机器**。播放最高的两条「8G 教程」（BV1G6nf6kEhP / BV1HMHw6wETo）简介里自报的是 **RTX 3080 魔改 20G + 32/48G 内存**，66 t/s 是 20G 卡跑出来的，不是 8G。
4. **8G 能跑的真正原因是模型结构**：Qwen3.8-Flash-Next 每 token 只激活约 6B，专家可下沉到内存/SSD；这条只对**这个 125B MoE**成立，换成 Qwen3.6-35B-A3B 就起不来（见 §7 本机对照）。
5. **8G 能不能不读盘是一条纯算术**：常驻专家权重 **34.98 GiB**；「内存 + 显存 − 5G > 34.98」才不读盘。8G 显存 + 32G 内存 = 40 − 5 = 35 GiB，只比 34.98 多 **0.02 GiB**。所以社区那套「把 Windows 静态占用压到 2.1G」不是玄学，是唯一的余量来源。
6. 8G 上出现的不是「慢」，是**不稳定**：同一配置 11.7–65.8 t/s（5 倍波动）、单轮能跑多轮死循环、logits 变 non-finite 后引擎自弃 KV。
7. **虚拟内存／页面文件：没有任何一手证据**。翻遍 B站字幕、知乎、CSDN、smzdm、itbanana，没有一条给出具体 pagefile 大小。社区做的是「减少 Windows 常驻占用」（开机项、内存优先级、专家锁内存），不是「加大 pagefile」。把 pagefile 当解法属【未核源】。
8. **沈三殊（已知线索）证伪**：他的 15 个视频里没有任何 Strata 8G 教程，8G 适配讲的是 **ninfer** 引擎（见 §1）。

---

## 1. 线索证伪：「沈三殊说 6/8/12/16/32G 都能跑 + 有 8G 专属教程」

**结论：对不上人，也大概率对不上引擎。**

- 用 bili_search（keyword=沈三殊，order=pubdate，num=50）拉全他 15 个投稿，**无一条 Strata 视频**。他的技术线是 **ninfer / kvmem / bonsai**：
  BV16ixE6DEEr 无界画布、BV1JVJd66Esq Nemotron、**BV1h8WA6XEFQ moe 小专武**、BV15VaD6EEQQ ninfer+kvmem、BV1sQaL6vEkb、BV1mvaa6nE2Q、BV1PkhU6oE2y（本地千问三档调优）、BV1Z6h76oEuw、BV1Kzhq6cEy4、BV1hjhh6DEbn、BV1dPeB6XE6d（token 自由 = bonsai27b+ninfer，8G 显卡，29.1 万播放）、BV1mDY268EkY、BV1tpbj6YEAd、BV14sbj6wEgx、BV1E8tB65Efr。
- **BV1h8WA6XEFQ《moe 小专武：小显存部署新方案！》**（2.26 万播放）字幕原文，8G 讲的是 ninfer：
  > 「在 8G 显卡的适配上，我们还做了进一步的优化……之前的时候有的人 8G 卡能部署，有的人的 8G 卡就部署不了，这个就是太极限的原因导致的，我们现在又把它给放宽了一下」

  6G 讲的也是 ninfer + 微调「小专武」（专家流式加载 + KV 进内存，代价是吃内存），不是 Strata。
- 他对 Strata 的实际贡献：提的优化被作者采纳，另外做了一份**调参清单**（不是 8G 教程）：
  - https://modelscope.cn/models/shensanshu/strata-hardware-adapt-guide
  - 网盘 https://pan.quark.cn/s/1603d00c92f2

  性质是「按 CPU/GPU 逐项扫描、逐项给建议」的目录，标称不同机器能提 **10%** 左右。
- 「8G 能跑」的标题党主力其实是：**九物AI生产力、T8star-Aix、零度解说、wangyi_AI_Studio**（见 §3 表）。
- 附带一点：他说的「有的人 8G 卡能部署、有的人部署不了」正是整个小显存生态的通病，和 §5 的不稳定现象是同一件事。

> 给父 agent：这条线索**不要再追**，沈三殊不是 Strata 8G 教程的出处。

---

## 2. 「8G」在官方文本里到底是什么口径（所有矛盾的根）

| 出处 | 原文口径 | 8G 的位置 |
| --- | --- | --- |
| 知乎《Strata 让普通游戏电脑跑 1250 亿参数大模型》 https://zhuanlan.zhihu.com/p/2089282096925878242 | NVIDIA RTX 20/30/40/50 系「**显存 12GB 及以上**」 | 单卡 8G **不在**推荐内；「双卡或三卡可分担，**此时每张卡需要 8GB 以上**」← 这才是官方 8G |
| B站 BV1yRn16REy8（只引官方文档，自标「本片没有本机实测」） | 「官方最低 32G 是 RAM + VRAM **合计**，不是单独内存；公式是 **RAM + VRAM − 5G**」；「全量模型还要满足专家 + 约 10G」 | 8G 靠「合计」勉强进；32G 内存 + 12–16G 显存官方**只预选 Coder** |
| itbanana 桌面版教程 https://itbanana.com/blog/strata-app-guide/ | 「新版每张卡可设主卡/辅助/不用；**8GB 及以下的卡默认不用**」 | 桌面版对 8G 卡的默认处理是**不参与** |
| 小众软件 https://www.appinn.com/strata/ | 「只要有 8GB 显存、16GB 内存……就有机会运行 1250 亿参数」+「对显卡要求不高，但**对内存要求极高**」 | 唯一给出「8G+16G」的正规媒体口径，但与官方 README 冲突 |
| smzdm 打假文 https://post.smzdm.com/p/a5rx8kml/ | 「当前 README 把显存门槛写得明明白白：**12GB 起**。B站九物的标题却写『8G 显存跑 125B』——在官方口径之外。证据只有个例、没有可复现条件，8G 卡用户先按『不支持』处理」 | 直接判定 8G 标题为「官方口径之外」 |

**决定 8G 上限的机制**
- 24,576 个专家 = 每层 512 × 48 层，每 token 激活 10 个；**每 1 GB 显存约多装 700 个专家**（CSDN https://blog.csdn.net/liuyunak/article/details/169070583 ，BV1yRn16REy8 同口径）。
- 常驻专家（全部 512 个专家权重）= **34.98 GiB**（BV1G6nf6kEhP 简介原文）。
- 于是：8G 显存 + 32G 内存 = 40 GiB − 5G 系统预留 = **35 GiB**，仅比 34.98 多 0.02 GiB → **8G 卡踩在门槛线上**，任何 Windows 常驻都会把它推下去。这就是所有「压 Windows 到 2.1G」操作的由来。

---

## 3. 8G／低显存 一手样本总表（按可信度排序）

| # | 机器 | 模型/量化 | 上下文与参数 | 数字 | 可复现性 | 来源 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | **RTX 4060 8G + 32G 内存** | IQ3_S | 未公布全部参数 | **20–37 t/s，均值 27**，「少量硬盘读写」 | 单人多次，给了区间 **【一手/实测】** | BV1HMHw6wETo 评论区 |
| 2 | **P104-100 8G + 64G 内存** | 未注明 | 32K 上下文 | 显存占用 **6.9G**；**11–18 t/s**（14/13/11/17/18）；思考段飙到 30+ 但属**死循环无效输出** | 单轮可、**多轮极大概率死循环**；作者自评「64G 内存是门槛，低于 64G 基本别试」**【一手/实测，个人主观门槛】** | BV1uBnn68Ety（2205 播放，一刀不剪） |
| 3 | **笔记本 4060 8G + 32G** | IQ2_XXS | **96K 上下文** | 「能跑，大概 20–30 多」 | 单点自述 **【一手/实测】** | BV1G6nf6kEhP 评论 |
| 4 | 3070 8GB（对照实验） | Qwen3.6-35B-A3B UD-Q4_K_M | llama.cpp（n-cpu-moe 41）vs Strata 0.1.45 | llama.cpp **31.5** tok/s；Strata **34.3**（6 次采样均值）→ 只差 9%，**远不到官方宣称的 1.5–1.8 倍** | 6 次采样，重复性最好 **【一手/实测】** | https://blog.csdn.net/liuyunak/article/details/169070583 |
| 5 | 魔改卡 8G（PolyStrata fork） | 自研九模型 | — | README 原文：九个模型「run on one PC with a 32 GB card, and **the seven smaller ones on a laptop with an 8 GB card** as well」 | 作者声明，**无 t/s** 【**官方口径**】 | 同上（PolyStrata README 转引） |
| 6 | RTX 3050 Laptop **4G** | fork | — | 「4GB 显存也能跑」的 fork 存在 | **【未核源】**，无数字 | 同上转引 |
| 7 | 3060 12G + 32G（九物 AI 生产力） | 最低档 Coder | 推荐上下文 33K | 标题写「8G 显存跑 125B」，**本人机器是 12G**，视频里没跑过 8G | 标题≠实测 **【一手/实测，但非 8G】** | BV1a9aZ6PEpf（5103 播放） |
| 8 | 16G + 128G（T8star-Aix） | Q3/Q4 | 端口 8080，接 harness 时 base 加 /v1、上下文填 32768、勾 images | 「开一堆程序时 30 t/s，正常 50–100」；对 8G 的建议是「只能用 Q2，Q3 也可试」 | 非 8G 实测 **【一手/实测，非 8G】** | BV15bpy6rEJ7（3.12 万播放） |

**必须写进结论的一条否证**
- 播放最高的两条「8G 教程」——BV1G6nf6kEhP（4124 播放）与 BV1HMHw6wETo（12167 播放）——**简介自报机器是 RTX 3080 魔改 20G**，内存 48G / 32G，CPU 都是 AMD 5700X。标题里的「显卡 8G+32G 内存」是**给观众的配置举例**（简介原话：「32G 内存 + 8G 显存为例（6G 显存太极限得用 linux）」）。
- 因此「**均速 66 t/s**」是 **20G 显存**跑出来的，8G 卡上见不到这个数。这是本轮最重要的一条纠偏。

---

## 4. 可直接抄的参数配方（三套）

### 4.1 20G 显存 / 32G 内存的不读盘配方（BV1HMHw6wETo 简介原文，逐字）

    --expert-cache auto
    --prefill auto
    --spec 4
    --spec-min-p 0.5
    --mtp C:\soft\Strata-023\mtp\rt
    --max-context 262144
    --kv k8v4
    --vram-reserve-mib 608
    --kv-grow
    --mmap-experts
    --resident-budget-gib 27
    --vision

- 引擎 **Strata-023**；模型 Qwen3.8-Flash-Next-Gyro-M-abliterated-TQ2_0.gguf，**85.65 GiB**（比 IQ3_S 的 77.9G 还大）。
- 判据原文：「32G 内存 + 20G 显存 = 52G > 39 G 即可不读硬盘」。
- 实测：128K **66 t/s**；256K **55 t/s**（掉 10）；写 h3 提示词 10 集均速 66；写前端 3D 建模项目均速 52。
- 同机跑分（中等思考）：deepseek-flash-1017 云端 94 ／ Gyro-M **74** ／ IQ3_S **62** ／ 27B **59** ／ IQ3_XXS **47**。

### 4.2 8G 卡「极限跑法」四步（BV1G6nf6kEhP 简介原文）

针对「32G 内存 + 8G 显存」这一档，原文给的全是**减法**：
1. **系统侧**：「让 AI 帮调，开机后占用内存为 **2.1G**（或者换 Linux）」；
2. **模型侧**：「去掉视觉，省 **1G**」；
3. **上下文**：「减少到 **100K**」；
4. **KV**：「kv 设为 **q4**」；
5. **投机解码**：「MTP 设为 **2**」（注意 4.1 的 20G 配方里是 spec 4）。
- UP 自己的劝退句（原文）：「**8G 显卡的要是嫌跑 gyro-m 太麻烦，就换低一级的 gyro-s 吧，不用这么折腾**」。
- 6G 注脚：「6G 显存太极限，得用 linux」。

### 4.3 社区零散冒出来的启动参数（未经完整复现，**【未核源】**）

- BV1G6nf6kEhP 评论区碎片：--vram-reserve-mib 608、--spec 2 或 3、上下文 110000、kv 设 q4。
- itbanana 教程给的官方命令：strata launch --plan ／ --yes --no-tui ／ --status ／ --stop；strata doctor --live；--tune thorough；--gpu-roles 1=main,0=helper；--set STRATA_DEFAULTS=026；--show-key；START-HERE.bat --setup --source modelscope --family qwen --model IQ2_XS --gguf-dir D:\models\IQ2_XS。

---

## 5. 低显存实操最真实的两件事：不稳定、静默降级

### 5.1 「32G 内存 + 16G 显存」的降级真相（最值得引用）

BV1ESHC65EVA 大瑞设计AI《Strata 实测：32G 内存跑 125B，16G 显存里只有 7G 在装专家》
机器：i7-14700KF / 32G 内存 / 4070Ti Super **16G** / SSD 2900MB/s。
- 32G 内存装不下 **36G** 专家 → 引擎进**低内存模式**，显卡只缓存 **28%** 专家，「剩下七成多，每生成一个 token 都要绕处理器和固态走一遍」。
- 同一份输入跑 **6 次**：**11.7 … 65.8 t/s**（5 倍多波动）；官方参考机（64G 内存）三次 **179 / 181 / 184**（3% 波动）。
- 内存占用 88% 只剩 3.7G，显存剩 797MB，专家缓存命中率掉到七成，**首字最长近 10 秒**。
- 结论原话：「**显存决定你能不能跑起来，内存决定你跑的多快多稳**」。
- 同系列：BV1dopb6KE1m（同一问题问 20 遍出 7 个不同答案）、BV1BxH966EkP（同一句话两遍差 3.8 倍）、BV1dHpg67EWJ（最慢一次等 6 分 49 秒）。
→ **对 8G 的含义**：16G 尚且如此，8G 落入「每 token 都读盘」的概率更高，必须按「能跑起来」而不是「跑得好」来预期。

### 5.2 静默错误与死循环（8G 上尤其常见）

- BV1HMHw6wETo 评论区贴出的引擎日志（可复现的报错样本）：

      【strata】 the engine's logits became non-finite after 22174 tokens (#879): the reply ends here as "length"; the engine dropped its cached state

- BV1uBnn68Ety 8G 实测：思考段速度飙到 30+ 但内容是**死循环**，「单轮可以、多轮极大概率进死循环」。
- itbanana / smzdm 共同点出的静默行为：**上下文打满时 Strata 不报错、悄悄丢弃最早内容**（99.5% 时输出只剩 431 token；64K/128K 满了会静默遗忘）。

### 5.3 其它 8G 相关数字

- 「8G 显卡的跑 gyro-m 太麻烦，就换低一级的 gyro-s 吧」（BV1G6nf6kEhP 简介，官方支持的降档路径）。**Gyro-S = TQ1_0 档，58.49 GB，VRAM+RAM 合计 27.6 GB** —— 8G 卡唯一有官方「装得下」背书的档位。
- 「关于 8G 显卡 + 32G 内存，系统优化到 2G 占用，**40−2 = 38 > 37** 可以跑了」（BV1HMHw6wETo 评论，与 §2 算术一致）。
- 「39g 怎么可能不读硬盘，我 32+16，读硬盘 200mb/s，峰值 30+ 平均不到 15」（同上，反例）。
- 「IQ3 12G 显存 + 80G 内存，每次简单对话思考都要超过 10 分钟」（同上，低配的代价不只在 t/s）。
- 0.1.52 提速：「昨天只能跑 70+，今天能跑 100+（5070+ddr4，IQ3_S）」（同上评论）—— **未在 8G 卡上验证**，不能直接套用。
- 官方读 SSD 档速度（itbanana，非 8G）：RTX 5070 12G+64G 约 **4–6 t/s**；RTX 3060 12G+46G 约 **9–11 t/s**。8G 若落入 file-tier，速度应在此量级或更低。

---

## 6. 各渠道覆盖与取证失败说明（别重复踩）

| 渠道 | 状态 | 说明 |
| --- | --- | --- |
| B站 搜索/字幕/评论/简介 API | 全通 | 已登录 uid 1140609405；本轮最强证据全部来自这里 |
| 知乎 | 通（经 jina reader） | 直连 403；https://r.jina.ai/<url> 可读。第二篇 https://zhuanlan.zhihu.com/p/2090202087120553566 （3060 12G+64G+i5-12500，AVX2 无 AVX-512）jina 返回 **401**，未取到正文 |
| CSDN | 半通 | 搜索 API so.csdn.net/api/v3/search 可用，但结果**绝大多数是 AI 生成的 SEO 水文**（账号 weixin_2903xxxx，标题模板「12GB 显存跑 1250 亿参数…」），只有 12G 口径、无 8G 一手数字 → **低可信，不作证据**。唯一有价值的是 liuyunak 那篇（§3 #4） |
| 什么值得买 | 通 | https://post.smzdm.com/p/a5rx8kml/ 9 组实测汇编 + 对「8G」标题的明确打假 |
| itbanana / 小众软件 | 通 | 配置表最细 / 唯一「8G+16G」媒体口径 |
| **贴吧** | **失败** | tieba.baidu.com/f/search **403**；Bing 搜 site:tieba.baidu.com strata **零贴吧结果** → 本轮拿不到贴吧一手 URL |
| **微信公众号** | **失败** | weixin.sogou.com 返回 10KB 空壳（无结果块）→ 拿不到 |
| **小红书** | **失败** | 站内不可检索 → 只能引 smzdm 的**二手转述**（「9527｜AI工具实测」核验：门槛为 RTX 30/40/50 + ≥12GB 显存 + 64GB 内存 + ~80GB 磁盘；「8G 就能跑」是标题党）【二手转述】 |
| 搜索引擎 | 半通 | web_search 工具**不可用**（DeepSeek search has no API key for "DEEPSEEK_API_KEY"）；cn.bing.com 的 HTML 与 RSS **所有查询返回同一组 10 条结果**（无长尾，等于废）；百度可用但只出新闻聚合 |

→ **结论**：贴吧／公众号／小红书在本环境**结构性拿不到**，凡涉及它们的内容一律标【二手转述】或【未核源】，不可当一手证据。

---

## 7. 与本机（8G / 4060 Ti）的对照 —— 为什么「别人 8G 能跑」而我们未必

本仓库已有实测（C:/Project/local_model/reports/Strata-8G实测-Qwen36起不来.md，2026-10-30 09:00–09:20）：
- 机器：RTX 4060 Ti **8 GB**（8,188 MiB）、Ryzen 7 7800X3D、**31.1 GB** DDR5、Win11、驱动 616.92；引擎 0.1.54。
- 模型：**Qwen3.6-35B-A3B** UD-Q4_K_XL（22.85 GB）+ mmproj。
- 结果：**起不来**。上下文 32K 压到 2K、kv q4_0、去视觉、去 MTP、expert-slots 1，28 臂全部 EngineDied，报
  「not enough VRAM left for the hybrid experts' buffers and slots (1159 MiB needed, 917 MiB free …)」，**天生差 242–418 MiB**。

**两者不矛盾，因为模型不同**：
- Qwen3.6-35B-A3B 是**激活 3B 的 35B**，稠密部分 4.40 GiB 必须全上卡，专家缓冲 1159 MiB 是 arch 固定开销 → 8G 装不下。
- Qwen3.8-Flash-Next 是 **125B / 激活约 6B**，专家可分片下沉到内存或 SSD，显卡只放「常驻专家 + 缓冲」→ 8G 才有机会。

→ 情报结论必须写成：「**8G 能跑的是 Qwen3.8-Flash-Next 这条 MoE 路线，不是任意模型**」。把「8G 能跑」推广成「Strata 在 8G 上通用」是错的。

---

## 8. 「单次首发成功」vs「反复问都正确」区分表

| 现象 | 单次/首次成功 | 反复稳定 | 证据 |
| --- | --- | --- | --- |
| 4060 8G + 32G 跑 IQ3_S | — | 是，20–37 t/s，均值 27 | BV1HMHw6wETo 评论 |
| P104 8G 跑 strata | 是（单轮） | **否**，多轮极大概率死循环 | BV1uBnn68Ety |
| 笔记本 4060 8G 跑 IQ2_XXS 96K | 是（「能跑」） | 未标次数 | BV1G6nf6kEhP 评论 |
| 32G 内存 + 16G 显存 跑 125B | 是（能起来） | **否**，6 次 11.7–65.8 t/s | BV1ESHC65EVA |
| 官方参考机 64G 内存 | — | 是，179/181/184（3%） | BV1ESHC65EVA 引用 |
| 3070 8GB 上 Strata vs llama.cpp | — | 是，6 次采样 34.3 vs 31.5 | CSDN liuyunak |
| 「8G 均速 66 t/s」 | **否，不是 8G 跑出来的**（20G 卡） | — | BV1G6nf6kEhP / BV1HMHw6wETo 简介 |

---

## 9. 证据清单（全部带 URL）

**B站（一手：视频/简介/评论）**

1. https://www.bilibili.com/video/BV1G6nf6kEhP — 国际米兰肠胃，4124 播放，8G 四步极限配方 + 34.98 GiB 常驻专家 + 跑分对照
2. https://www.bilibili.com/video/BV1HMHw6wETo — 同 UP，12167 播放，完整启动参数 + 128K 66 / 256K 55 t/s + 8G 实跑评论
3. https://www.bilibili.com/video/BV1uBnn68Ety — SC3-K所长，P104-100 8G 真机，11–18 t/s，6.9G 显存
4. https://www.bilibili.com/video/BV1ESHC65EVA — 大瑞设计AI，16G 显存降级真相，6 次 5 倍波动
5. https://www.bilibili.com/video/BV1PwHs6vEiY — AI观模者，33850 播放，6G 能启动 / 8G 最低 / 内存分档 / 5070 各档 t/s
6. https://www.bilibili.com/video/BV1f3pM6jEoi — Smthem，「8+36G 跑 125B」的硬件门槛讲法
7. https://www.bilibili.com/video/BV15bpy6rEJ7 — T8star-Aix，31170 播放，8G 建议 Q2
8. https://www.bilibili.com/video/BV1a9aZ6PEpf — 九物AI生产力，标题写 8G、实机 3060 12G（标题党样本）
9. https://www.bilibili.com/video/BV1yRn16REy8 — 降档表，纯引官方文档：RAM+VRAM−5G、每 1G 显存 700 专家、128K KV≈1.7G、262K 首 token 约 4 分半
10. https://www.bilibili.com/video/BV1h8WA6XEFQ — 沈三殊，8G 讲的是 ninfer（证伪用）

**网页（一手/官方口径）**

11. https://zhuanlan.zhihu.com/p/2089282096925878242 — 官方口径：单卡 12GB 起、多卡每卡 8GB、IQ3_S 需 54.8GB、Coder 首分片 29.6GB
12. https://blog.csdn.net/liuyunak/article/details/169070583 — 3070 8GB 对照实验（34.3 vs 31.5）、PolyStrata 8G 声明、内存不足时慢 4–7 倍的反例
13. https://post.smzdm.com/p/a5rx8kml/ — 9 组实测汇编 + 对「8G」标题的明确打假
14. https://itbanana.com/blog/strata-app-guide/ — 「8GB 及以下的卡默认不用」、内存分档表、strata 命令全集
15. https://www.appinn.com/strata/ — 「8GB 显存 + 16GB 内存」的媒体口径
16. https://modelscope.cn/models/shensanshu/strata-hardware-adapt-guide — 沈三殊的硬件适配调参清单（非 8G 教程）

**二手/未核源（不可单独作证）**

17. smzdm 对小红书「9527｜AI工具实测」的转述【二手转述】
18. 贴吧 / 微信公众号 / 小红书原帖：**本轮未取到任何一手 URL**（403 / 空壳 / 不可检索）

---

## 10. 给父 agent 的三条行动建议

1. **放弃「8G 专属教程」这个假设**，改为「8G 处于官方口径之外，社区有 3 个一手样本，20–37 t/s（4060 8G）或 11–18 t/s（P104 8G），稳定性差」。
2. 若要在 8G 上继续推进，**唯一有官方背书的路是 Gyro-S（TQ1_0，58.49 GB，VRAM+RAM 27.6 GB，low-RAM 模式让 GPU 只放约 8% 专家）**，预期落在 itbanana 的 SSD 档 4–11 t/s 量级，不要期待 60+。
3. 「**把 Windows 静态占用压到 2–2.1G**」是本轮唯一可执行的 8G 优化项（三条独立来源都指向它）；**加大页面文件不是**——没有任何一手证据支持 pagefile 能救 8G。
