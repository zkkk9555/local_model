#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""longdoc.py - 8GB 显存上把 200K 级长文档变成「可信」的工具。

原理：设备的 KV 池只有 40,000 token。超池请求（题面 > 池）在 NInfer KVMem 引擎上
实测「同一进程里第一次超池请求 8/8 命中、之后全部静默错」。池内请求（题面 <= 池）
实测始终干净（29,818 token 8/8，且是在被超池请求污染过的进程里跑的）。

所以本工具不超池：把长文档按行切成若干「池内分片」，逐片做**逐字取证**（不是总结），
再把取证结果合并成答案。任何分片都 <= --shard-tokens，永远走在已验证干净的路径上。

用法:
  python longdoc.py --doc 长文档.md --question "文档里提到哪些动物代号？"
  python longdoc.py --doc a.txt --question "..." --shard-tokens 26000 --out result.md
  python longdoc.py --selftest          # 自检：造一份 ~200K 文档 + 8 个暗号，端到端跑一遍
"""
import argparse, json, os, sys, time, urllib.request

# 换算策略（2026-10-30 修）：不同文档的 bytes/token 差别很大——混合中英 fixture 实测 3.495，
# 纯中文下界约 1.745。所以第一片按「纯中文」保守换算（宁小勿大），跑完拿到真实
# usage.prompt_tokens 后再用实测比例切剩下的片，避免「纯中文文档把分片撑爆池」。
CONSERV_BPT = 1.75   # bytes / token 的下界（纯中文实测 1.745 => 1 token ≈ 1.75 字节）
SAFETY = 0.93        # 校正后再留 7% 余量
BYTES_PER_TOKEN = CONSERV_BPT   # 兼容旧名：make_fixture() 用它把「目标 token」换算成字节

EXTRACT_SYS = (
    "你是长文档取证器。只做一件事：把与问题相关的原文逐字摘出来，"
    "数字、代号、人名、路径、代码一律原样复制，不许改写、不许翻译、不许推断。"
    "注意：校验码这类「名称-数字」的组合必须整条原样抄（例如「白熊-1234」），"
    "只抄数字、只抄名字都算错。"
    "如果本段完全没有与问题相关的内容，只输出 NONE 四个字符，不要输出别的任何东西。"
)

FINAL_SYS = (
    "你是长文档答问器。只能用【取证】里出现的原文作答，不许补充外部知识、不许编造。"
    "取证里没有的信息，必须明确写「未找到」，不许猜。答案尽量短。"
)


def est_tokens(s):
    """保守 token 估算：取「纯中文下界」与「1.35 字符/token」两种估算的较大者。"""
    b = len(s.encode("utf-8"))
    return int(max(b / CONSERV_BPT, len(s) / 1.35)) + 1


def _take(lines, start, limit_bytes):
    """从 start 行起尽量多行，累计 utf8 字节 <= limit_bytes。返回 (end 行下标, 字节数)。"""
    total, i = 0, start
    while i < len(lines):
        b = len(lines[i].encode("utf-8"))
        if total and total + b > limit_bytes:
            break
        total += b
        i += 1
    return i, total


def post(engine, model, messages, max_tokens=1024, temperature=0.0, timeout=1800):
    body = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": False,
    }
    req = urllib.request.Request(
        engine.rstrip("/") + "/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": "Bearer local-any-key"},
    )
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        d = json.loads(r.read().decode("utf-8"))
    dt = time.time() - t0
    msg = d["choices"][0]["message"]
    txt = (msg.get("content") or "").strip()
    u = d.get("usage") or {}
    return txt, u, dt


POOL_TOKENS = 0        # >0 时：任何一片的 prompt_tokens 超过它就判定「结果不可信」
OVER_POOL = []         # 记录超池的片
# 正例：200K 长文里数字极密，模型会退化成「把所有四位数字全抄一遍」（1024 token 全是数字），
# 于是取证被垃圾塞满、合成环节直接不答。用问题里要求的形态做硬过滤，垃圾自然被丢掉。
ANSWER_RE = None       # None = 不过滤；re.Pattern = 每片只保留匹配片段


def run(doc_path, question, engine, model, shard_tokens,
        max_excerpt_tokens, out_path, quiet=False):
    text = open(doc_path, "r", encoding="utf-8", errors="replace").read()
    lines = text.splitlines(True)
    total_tok = est_tokens(text)
    def log(*a):
        if not quiet:
            print(*a, flush=True)
    log("[longdoc] 文档 %s  %d 字符 / 保守预估 %d token" % (doc_path, len(text), total_tok))
    log("[longdoc] 自适应分片启动：首片按 %.2f 字节/token（纯中文下界），拿到实测 prompt_tokens 后校正" % CONSERV_BPT)

    excerpts, stats = [], []
    t_all = time.time()
    pos, k, bpt = 0, 0, None
    while pos < len(lines):
        k += 1
        limit = shard_tokens * (bpt if bpt else CONSERV_BPT)
        end, sent_bytes = _take(lines, pos, limit)
        if end <= pos:                      # 单行就超限：硬切一行，别死循环
            end = pos + 1
            sent_bytes = len(lines[pos].encode("utf-8"))
        a, b, seg = pos + 1, end, "".join(lines[pos:end])
        pos = end
        prompt = (
            "【本段位置】全文第 %d-%d 行（第 %d 片）\n\n" % (a, b, k) +
            "【问题】" + question + "\n\n" +
            "【本段原文】\n" + seg
        )
        try:
            txt, u, dt = post(engine, model,
                              [{"role": "system", "content": EXTRACT_SYS},
                               {"role": "user", "content": prompt}],
                              max_tokens=max_excerpt_tokens)
        except Exception as e:
            txt, u, dt = "__ERROR__ %s" % e, {}, time.time() - t_all
        pt = (u or {}).get("prompt_tokens")
        # 硬闸：任一超池 ⇒ 该片答案不可信（引擎 warning 口径：prompt >= pool 就会丢中间页）
        if POOL_TOKENS and pt and pt > POOL_TOKENS:
            OVER_POOL.append({"shard": k, "prompt_tokens": pt})
            log("[longdoc] ！！！第 %d 片 prompt=%s 超过池 %d ⇒ 该片不可信，整体结果标红"
                % (k, pt, POOL_TOKENS))
        if bpt is None and pt:              # 用第一片的真实读数校正 bytes/token
            overhead = est_tokens(EXTRACT_SYS) + est_tokens(question) + 48
            body_tok = max(pt - overhead, 1)
            bpt = max(1.60, min(4.20, sent_bytes / body_tok)) * SAFETY
            log("[longdoc] 实测 %.3f 字节/token（首片 body %d token / %d 字节）-> 后续每片按 %.3f 换算"
                % (sent_bytes / body_tok, body_tok, sent_bytes, bpt))
        raw_len = len(txt)
        if ANSWER_RE is not None:
            seen, keep = set(), []
            for m in ANSWER_RE.finditer(txt):
                v = m.group(0)
                if v not in seen:
                    seen.add(v); keep.append(v)
            if keep:
                txt = "\n".join(keep)
                log("      过滤：%d 字 -> %d 条（%d 字）" % (raw_len, len(keep), len(txt)))
            elif raw_len <= 200 and any(ch.isdigit() for ch in txt):
                # 短回答（模型只抄了数字、没抄「动物-数字」整条）是有效取证，别当垃圾丢掉
                log("      过滤：%d 字 -> 短答保留（未匹配形态）" % raw_len)
            else:
                txt = "NONE"
                log("      过滤：%d 字 -> NONE（判定为数字堆砌）" % raw_len)
        isnone = txt.strip().upper().startswith("NONE")
        stats.append({"shard": k, "lines": [a, b], "prompt_tokens": pt, "sec": round(dt, 1),
                      "chars": len(seg), "reply_chars": len(txt), "none": isnone})
        log("  [%d] 行 %d-%d  prompt=%s  %.1fs  %s" % (
            k, a, b, pt, dt, "NONE" if isnone else "取证 %d 字" % len(txt)))
        if not isnone:
            excerpts.append({"shard": k, "lines": [a, b], "text": txt})

    if not excerpts:
        final = "（所有分片都报告 NONE：文档中未找到与问题相关的内容。）"
    else:
        joined = "\n\n".join("### 第 %d 片（行 %d-%d）\n%s" % (e["shard"], e["lines"][0], e["lines"][1], e["text"])
                             for e in excerpts)
        # 2026-10-30 实测：用户轮里只要出现「请只依据取证作答…才写未找到」这种尾巴，模型会直接吐「未找到」
        # （V1/V2 都是 3 字，V3 = 同样的取证 + 不加尾巴 → 8/8）。所以用户轮保持极简，拒绝词只留在 system 轮。
        final_prompt = "【问题】%s\n\n【取证】\n%s" % (question, joined)
        try:
            final, u2, dt2 = post(engine, model,
                                  [{"role": "system", "content": FINAL_SYS},
                                   {"role": "user", "content": final_prompt}],
                                  max_tokens=1024)
            stats.append({"stage": "final", "prompt_tokens": (u2 or {}).get("prompt_tokens"), "sec": round(dt2, 1)})
        except Exception as e:
            final = "__FINAL_ERROR__ %s\n\n%s" % (e, joined)
        # 兜底：取证阶段才是真相。合成环节若空/答「未找到」/报错，就按取证逐字汇总交付。
        _bad = (not final.strip()) or final.startswith("__FINAL_ERROR__") or \
               ("未找到" in final and len(final.strip()) <= 12)
        if _bad:
            log("[longdoc] 警告：合成环节未给出答案（%s），改用取证原文逐字汇总" % final.strip()[:40])
            final = ("（合成环节未给出答案，以下按取证原文逐字汇总，未做二次改写）\n" +
                     "\n".join("- 第 %d 片（行 %d-%d）：%s" % (
                         e["shard"], e["lines"][0], e["lines"][1], e["text"].replace("\n", " "))
                         for e in excerpts))

    wall = time.time() - t_all
    md = ["# longdoc 结果", "",
          "- 文档: " + os.path.abspath(doc_path) + "  (%d 字符 / 预估 %d token)" % (len(text), total_tok),
          "- 问题: " + question,
          "- 分片: %d 片 x <= %d token（自适应按实测字节/token 折算）" % (k, shard_tokens),
          "- 池: %s ｜ 超池片: %s" % (POOL_TOKENS or "未声明",
                                   ("无（每片都 <= 池）" if not OVER_POOL
                                    else "有 %d 片 ⇒ **结果不可信**" % len(OVER_POOL))),
          "- 总耗时: %.1fs（%.1f 分）" % (wall, wall / 60),
          "", "## 答案", "", final, "", "## 取证原文", ""]
    for e in excerpts:
        md += ["### 第 %d 片（行 %d-%d）" % (e["shard"], e["lines"][0], e["lines"][1]), "", e["text"], ""]
    md += ["## 分片统计", "", "| 片 | 行范围 | prompt token | 耗时 s |", "|---|---|---|---|"]
    for s in stats:
        if "shard" in s:
            md.append("| %s | %d-%d | %s | %s |" % (s["shard"], s["lines"][0], s["lines"][1], s["prompt_tokens"], s["sec"]))
    md += ["", "_引擎 %s / 模型 %s / %s_" % (engine, model, time.strftime("%Y-%m-%d %H:%M:%S")), ""]

    if out_path:
        open(out_path, "w", encoding="utf-8").write("\n".join(md))
        log("[longdoc] 报告 -> %s" % out_path)
    log("[longdoc] 完成：%.1fs，取证片 %d/%d，超池片 %d" % (wall, len(excerpts), k, len(OVER_POOL)))
    return {"answer": final, "wall": wall, "shards": k, "excerpts": len(excerpts),
            "stats": stats, "over_pool": list(OVER_POOL)}


def make_fixture(path, target_tokens, needles, seed=20261030):
    """造一份 >= target_tokens 的中文填充文档，暗号按深度等距插入。"""
    import random
    rnd = random.Random(seed)
    words = ["工序", "台账", "批次", "巡检", "阀组", "参数", "校准", "归档", "规程", "余量",
             "接口", "日志", "抽样", "复核", "阈值", "偏移", "序列", "索引", "缓存", "队列"]
    lines, nbytes = [], 0
    limit = int(target_tokens * BYTES_PER_TOKEN)
    i = 0
    while nbytes < limit:
        i += 1
        ln = "%06d 第%d条：%s%s记录，编号 %d，复核人 %s(%d)，结论 一致。\n" % (
            i, i, rnd.choice(words), rnd.choice(words), rnd.randint(1000, 9999),
            rnd.choice(["甲", "乙", "丙", "丁"]), rnd.randint(1, 99))
        lines.append(ln)
        nbytes += len(ln.encode("utf-8"))
    for j, nd in enumerate(needles):
        pos = int(len(lines) * (j + 1) / (len(needles) + 1))
        lines[pos] = "%06d 特记：本批次校验码为 %s，其余参数不变。\n" % (pos, nd)
    open(path, "w", encoding="utf-8").write("".join(lines))
    return len(lines)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--doc"); ap.add_argument("--question")
    ap.add_argument("--engine", default="http://127.0.0.1:8091/v1")
    ap.add_argument("--model", default="local")
    ap.add_argument("--shard-tokens", type=int, default=28000)
    ap.add_argument("--max-excerpt-tokens", type=int, default=1024)
    ap.add_argument("--out", default="")
    ap.add_argument("--answer-regex", default=r"[\u4e00-\u9fa5]{1,6}-\d{3,5}",
                    help="每片回复只保留匹配这个正则的片段（去重、保序）；传空串关闭")
    ap.add_argument("--pool-tokens", type=int, default=0,
                    help="引擎当前 --kv-capacity；给了就做超池硬闸，超了退出码 3")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        tmpd = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tmp")
        os.makedirs(tmpd, exist_ok=True)
        fx = os.path.join(tmpd, "longdoc-selftest.txt")
        needles = ["紫色河马-7314", "青铜狐狸-1180", "银色海豚-4402", "绿色猫头鹰-9067",
                   "红色骆驼-2551", "金色蜥蜴-6388", "蓝色水母-8223", "黑色麋鹿-5019"]
        nl = make_fixture(fx, 200000, needles)
        print("[selftest] fixture %s: %d 行" % (fx, nl))
        q = "这份文档里出现过哪些形如「动物-四位数字」的校验码？请按出现顺序全部列出，一个不漏。"
        r = run(fx, q, a.engine, a.model, a.shard_tokens, a.max_excerpt_tokens,
                os.path.join(tmpd, "longdoc-selftest.md"))
        hits = sum(1 for x in needles if x in r["answer"])
        print("[selftest] 命中 %d/8  耗时 %.1fs  分片 %d" % (hits, r["wall"], r["shards"]))
        print("[selftest] 答案:", r["answer"][:400].replace("\n", " "))
        sys.exit(0 if hits >= 7 else 1)
    if not a.doc or not a.question:
        ap.error("需要 --doc 和 --question")
    globals()["POOL_TOKENS"] = a.pool_tokens
    globals()["ANSWER_RE"] = __import__("re").compile(a.answer_regex) if a.answer_regex else None
    r = run(a.doc, a.question, a.engine, a.model, a.shard_tokens, a.max_excerpt_tokens, a.out)
    if r["over_pool"]:
        print("[longdoc] 退出码 3：有片超池，结果不可信", file=sys.stderr)
        sys.exit(3)
