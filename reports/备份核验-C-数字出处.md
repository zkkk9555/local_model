# 备份核验-C：文档数字出处核验（只读）

核验对象：repo/README.md、repo/RESTORE.md、repo/docs/评论区回复-文稿-20261031.md
检索范围：reports/、logs/、docs/（工作区根，C:/Project/local_model）
方法：grep -rn 逐一比对原文读数

| 数字 | 出处 | 状态 |
| --- | --- | --- |
| 110.5 / 110 tok/s（计数） | 无（全仓 110.5 零命中；最接近的实测中位为 107.3，reports/极限优化-实测.md:119） | 无出处 |
| 75.0 / 75 tok/s（代码） | 无（75.0 仅见 reports/Qwen36-35B-A3B-社区体检.md:96 的 SWE-bench 分与 logs 的 host 75.0%，均非 tok/s） | 无出处 |
| 38.6 tok/s | logs/lim-N0.log:844（decode 38.6 tok/s (193 tok)） | ok |
| 24.5 步/秒 | 无（仅 docs/评论区回复-文稿-20261031.md:20,48,77 自指；由 logs/lim-N0.log:596 反推约 23 步/秒） | 无出处 |
| 4.5 token/步 | 无（仅可由 logs/lim-N0.log:596 的 mtp accepted 310/356、400 出 ÷ 89 步 ≈ 4.49 反推） | 无出处 |
| 3.1 token/步 | 无（reports/logs/docs 全无代码题面的步数记录） | 无出处 |
| 1.6 token/步 | 无（仅可由 logs/lim-N0.log:893 的 accepted 96/552、233 出 ÷ 138 步 ≈ 1.69 反推） | 无出处 |
| 40,000（池） | reports/极限优化-实测.md:24（capacity | KV 40,000 tokens） | ok |
| 72,000（池） | reports/上下文上限-实测-20261030.md:42 | ok |
| 88,618（单遍上限） | reports/上下文上限-实测-20261030.md:35；logs/exp-p88.err:1734（prompt 88,618） | ok |
| 150,000 | reports/上下文-150K-200K-实测-20261030.md:11（134.9 s / 159.5 s / 173.2 s） | ok |
| 200,000 | reports/上下文-150K-200K-实测-20261030.md:12（211.4 s / 211.7 s / 211.4 s / 231.2 s） | ok |
| 262,144（窗口） | reports/上下文-150K-200K-实测-20261030.md:92（能真开 262,144 窗口） | ok |
| 135 s（150K 分片） | reports/上下文-150K-200K-实测-20261030.md:11（最小 134.9 s） | ok |
| 211 s（200K 分片） | reports/上下文-150K-200K-实测-20261030.md:12（211.4 s） | ok |
| 268 s（llama 150K 首读） | reports/上下文-150K-200K-实测-20261030.md:106（wall 268.3 s） | ok |
| 12.6 tok/s（llama decode） | reports/上下文-150K-200K-实测-20261030.md:108 | ok |
| 7,301 MiB | logs/verify-20261031-042910.log:7（long72 在跑时 7301 MiB / 8188 MiB） | ok |
| 7,533 MiB（40K 档） | 无（仅 docs/本地模型清单-给DSH用.md:314 自指；实测档位峰值为 7,459，reports/极限优化-实测.md:119） | 无出处 |
| 7,798 MiB（llama 路线） | reports/上下文上限-实测-20261030.md:71（对照表「显存」列）；注意 reports/llama8g-200K-实测.md:16 的 7,798 是 free 而非占用 | ok |
| 7,570 MiB（README 40K 档） | 无（仅 repo/README.md:15、docs/RESTORE-从零重建.md:113 自指） | 无出处 |
| 39 tok/s（散文） | reports/极限优化-实测.md:121（中位 39.9）；logs/lim-N0.log:844（38.6） | ok |
| 31 tok/s（72K 档） | docs/部署完成-实测报告.md:9（旧 64K long 档 31 tok/s）；72K 档现值 35.7–37.0 见 reports/上下文-150K-200K-实测-20261030.md:72，口径偏旧 | ok |
| 0.84 MiB/页 | reports/上下文-150K-200K-实测-20261030.md:5 | ok |
| 9.4 GB（150K 单遍算术） | 无（报告原文为 9.0 GiB，reports/上下文-150K-200K-实测-20261030.md:20） | 无出处 |

无出处共 9 条
