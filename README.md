# local_model — 8 GB 显存上的本地 27B 模型（RTX 4060 Ti · Windows）

**这是一份「能重建」的存档**：脚本、工具、文档、实测报告、校验值全在这里；<br>
引擎与权重太大（0.8 GB / 6.4 GB），不放仓库，下载地址与 SHA-256 全在 [RESTORE.md](RESTORE.md)。

---

## 一分钟看懂这个项目在干什么

在**一张 8 GB 显存的 4060 Ti** 上，用 [NInfer KVMem](https://github.com/1314521gjy/ninfer-fusion-kvmem)（sm_89 预编译引擎）
跑 **Bonsai-2-27B 三元 1-bit 量化（PTQ1）**，并把「上下文能有多大」当成一道算术题啃到底：

| 路线 | 可信上下文 | 生成速度 | 首字 | 代价 |
| --- | --- | --- | --- | --- |
| **40K 日常档**（池 40,000 + MTP draft4） | 40,000 token 单遍可信 | **108** tok/s（计数）/ 74（代码）/ **38**（散文） | 0.2–0.5 s | 显存 7,459 / 8,188 MiB（峰值） |
| **72K 长文档档**（关 MTP，池 72,000） | 72,000 单遍 8/8；94K 掉 1 针 | 36 tok/s | 0.3 s | 显存 7,301 MiB |
| **分片注入 150K–200K**（8086 代理） | 150K / 200K 都 8/8 可重复 | 150K ≈135 s、200K ≈211 s 整篇 | — | 每片 ≤26K，逐片取证 |
| **llama.cpp 262K 窗口** | 150K 单遍实测 8/8 | decode 12.6 tok/s、prefill 583 tok/s | 4.5 min @150K | 显存 7,798 MiB |

> 一眼结论：**8 GB 卡单遍可信上限 = 88,618 token**（池 88,000，剩 33 MiB）；再往上要么分片、要么换 llama.cpp 的 host-tail 分页。
> 150K 单遍在 NInfer 上算术不可能——权重 5.96 GiB + 150K×0.84 MiB 的 KV = 9.0 GiB > 8.19 GB。

---

## 仓库里有什么

```
RESTORE.md      从零重建：要下的件、字节数、SHA-256、起服、验收、DSH 接入、十个坑
README.md       本文件
NOTICE.md       第三方归属与许可（引擎/权重/llama.cpp）
LICENSE         MIT（本仓库自己写的代码与文档）
config/         DSH provider 样例、环境变量模板、控制台快捷方式
scripts/        起服 / 换档 / 分片 / 实验脚本（serve2.sh 是引擎入口）
tools/          控制台(8090)、护栏网关(8081)、超池分片代理(8086)、长文探针、恢复自检
docs/           22 篇中文文档（部署方案、上下文手册、DSH 接入、结论索引）
reports/        50 篇实测报告（每个数字都能追溯到某次跑）
```

## 已经验证过的事（挑几条最硬的）

- **超池就不可信，而且是静默的**：prompt ≤ 池 → 8/8 命中；1.31× 池 → 7/8；2.37× → 1/8；3.17× → 0/8，全程 HTTP 200、答案看着正常。⇒ 唯一可靠的护栏是分片（每片 ≤ 池）。
- **AUTO 检索**：`NINFER_KV_RETRIEVE` 留空时引擎自动给「池的一半」作为证据预算（500 页 @ 池 1000 页）；我们过去写死 8192 只有 128 页，白丢 3.9 倍。
- **MTP 是真的**：解码步频恒定 ≈24 步/秒，命中率高时每步吐 4.5 个 token（计数 108 tok/s），散文只吐 1.6 个（38 tok/s）。所以「同一张卡有人报 100、有人报 40」不是谁装错了。
- **GPU 解锁（UEFI / 驱动级）不值得**：被钳的 A16 通路只占 prefill 时间 36.4%，解锁上限 ×1.163；decode 与显存零收益，而代价是每次冷启动插 U 盘 + 蓝屏风险。见 `reports/UEFI解锁-Windows-对首字影响.md`。
- **llama.cpp 的 host-tail 分页可信**：故意只钉 16,384 个 KV cell（45% 上下文在内存里），30K 提示仍然 8/8。

## 快速开始

```bash
# 1) 下件（详见 RESTORE.md §3）
# 2) 自检
python tools/restore_check.py
# 3) 起服务 + 打开控制台
bash scripts/switch.sh ninfer
bash scripts/console.sh open
```

## 许可

本仓库的脚本、文档、报告：MIT（见 [LICENSE](LICENSE)）。<br>
引擎与权重的许可归原作者，见 [NOTICE.md](NOTICE.md)。**仓库不含任何二进制**。