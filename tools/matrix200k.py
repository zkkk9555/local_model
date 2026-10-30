#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""matrix200k.py - 超池静默错的边界矩阵 + 池内分片方案验证（一次跑完，不重启引擎）。

batch 1（要求引擎是**刚启动**的干净进程）:
  A  209K 长文档，8 针            -> 首发是否 8/8
  B  209K **另一份、不同开头**，8 针 -> 第二个超池请求是否还成立（分辨「前缀相关」还是「状态污染」）
  C  30K 池内 x2（不同暗号）        -> 被污染之后池内是否仍干净
  D  longdoc 分片地图-化简 200K     -> 池内方案能否可靠召回全部暗号

batch 2（重启后再跑）:
  E  先 30K 池内、再 209K          -> 池内请求是否会「占用」掉那一次超池机会
"""
import argparse, json, os, re, subprocess, sys, time, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import longdoc as LD

OUT = os.path.join(HERE, "..", "tmp", "matrix")
os.makedirs(OUT, exist_ok=True)
ENGINE = "http://127.0.0.1:8091/v1"
MODEL = "local"

S1 = ["紫色河马-7314", "青铜狐狸-1180", "银色海豚-4402", "绿色猫头鹰-9067",
      "红色骆驼-2551", "金色蜥蜴-6388", "蓝色水母-8223", "黑色麋鹿-5019"]
S2 = ["白色鲸鱼-3141", "灰色鹦鹉-5926", "橙色章鱼-8412", "青色刺猬-2673",
      "褐色獾子-7058", "粉色火烈鸟-1936", "墨绿壁虎-4482", "杏色绵羊-6207"]
S3a = ["琥珀考拉-3308", "深蓝鲨鱼-5514", "米白土拨鼠-7729", "酒红蜘蛛-1465"]
S3b = ["石灰企鹅-9032", "浅金松鼠-4187", "藏青犀牛-6355", "奶白鸳鸯-2814"]
S4 = ["珊瑚水獭-1526", "墨黑山猫-6733", "银灰鹭鸶-3948", "草绿螳螂-8205",
      "绛紫狐猴-4691", "象牙野猪-2377", "海蓝螯虾-5860", "赭石野兔-7112"]

Q_LIST = "这份文档里出现过哪些形如「动物-四位数字」的校验码？请按出现顺序全部列出，一个不漏，只列校验码本身。"

CODE_RE = re.compile(r"[\u4e00-\u9fa5]{1,6}-\d{3,5}")


def http_post(messages, max_tokens=512, timeout=1800):
    body = {"model": MODEL, "messages": messages, "max_tokens": max_tokens,
            "temperature": 0.0, "stream": False}
    req = urllib.request.Request(ENGINE.rstrip("/") + "/chat/completions",
                                 data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json",
                                          "Authorization": "Bearer local-any-key"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        d = json.loads(r.read().decode("utf-8"))
    dt = time.time() - t0
    txt = (d["choices"][0]["message"].get("content") or "").strip()
    return txt, (d.get("usage") or {}), dt


def ask_doc(doc_path, q, needles, tag, max_tokens=512):
    text = open(doc_path, encoding="utf-8", errors="replace").read()
    prompt = "【文档】\n" + text + "\n\n【问题】" + q
    txt, u, dt = http_post([{"role": "user", "content": prompt}], max_tokens=max_tokens)
    hits = [n for n in needles if n in txt]
    codes = CODE_RE.findall(txt)
    extra = sorted({c for c in codes if c not in needles})
    rec = {"tag": tag, "doc": os.path.basename(doc_path), "chars": len(text),
           "prompt_tokens": u.get("prompt_tokens"), "completion_tokens": u.get("completion_tokens"),
           "cached_tokens": (u.get("prompt_tokens_details") or {}).get("cached_tokens"),
           "wall": round(dt, 1), "hits": len(hits), "total": len(needles),
           "hit_list": hits, "extra_codes": extra, "n_extra": len(extra), "answer": txt}
    json.dump(rec, open(os.path.join(OUT, tag + ".json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    # 追加总表
    with open(os.path.join(OUT, "matrix.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps({k: v for k, v in rec.items() if k != "answer"}, ensure_ascii=False) + "\n")
    print("[%s] prompt=%s 命中 %d/%d  编造 %d  %.1fs  答: %s" % (
        tag, rec["prompt_tokens"], rec["hits"], rec["total"], rec["n_extra"], rec["wall"],
        txt[:160].replace("\n", " ")), flush=True)
    return rec


def batch1():
    t0 = time.time()
    dA = os.path.join(OUT, "docA-209k.txt")
    if not os.path.exists(dA):
        LD.make_fixture(dA, 200000, S1, seed=20261030)
    print("[batch1] A: 209K 首发", flush=True)
    ask_doc(dA, Q_LIST, S1, "A_209k_first")

    dB = os.path.join(OUT, "docB-209k.txt")
    if not os.path.exists(dB):
        n = LD.make_fixture(dB, 200000, S2, seed=777)
        # 换开头：把第一段换成完全不同的内容，确保与前一份无共同前缀
        body = open(dB, encoding="utf-8").read().splitlines(True)
        head = ["序言：本卷为独立编号的一册，与任何其他卷册的内容、编号、措辞均无重叠。\n",
                "本册专记北岭工段的第三类校验流程，代号体系与小动物无关，仅沿用形制。\n",
                "\n"]
        open(dB, "w", encoding="utf-8").write("".join(head + body))
        print("[batch1] docB 行数 %d（已换开头）" % (n + 3), flush=True)
    print("[batch1] B: 209K 第二发（不同文档、不同开头）", flush=True)
    ask_doc(dB, Q_LIST, S2, "B_209k_second_otherdoc")

    print("[batch1] C: 池内 30K x2", flush=True)
    dC1 = os.path.join(OUT, "docC1-30k.txt")
    if not os.path.exists(dC1):
        LD.make_fixture(dC1, 29000, S3a, seed=11)
    ask_doc(dC1, Q_LIST, S3a, "C1_30k_inpool")
    dC2 = os.path.join(OUT, "docC2-30k.txt")
    if not os.path.exists(dC2):
        LD.make_fixture(dC2, 29000, S3b, seed=12)
    ask_doc(dC2, Q_LIST, S3b, "C2_30k_inpool")

    print("[batch1] D: longdoc 分片（200K，8 针）", flush=True)
    dD = os.path.join(OUT, "docD-200k.txt")
    if not os.path.exists(dD):
        LD.make_fixture(dD, 200000, S4, seed=424242)
    r = LD.run(dD, Q_LIST, ENGINE, MODEL, 26000, 1024, os.path.join(OUT, "D_longdoc.md"))
    hits = [n for n in S4 if n in r["answer"]]
    codes = CODE_RE.findall(r["answer"])
    rec = {"tag": "D_longdoc_200k", "wall": round(r["wall"], 1), "shards": r["shards"],
           "excerpts": r["excerpts"], "hits": len(hits), "total": len(S4), "hit_list": hits,
           "extra_codes": sorted({c for c in codes if c not in S4}), "answer": r["answer"]}
    json.dump(rec, open(os.path.join(OUT, "D_longdoc_200k.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    with open(os.path.join(OUT, "matrix.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps({k: v for k, v in rec.items() if k != "answer"}, ensure_ascii=False) + "\n")
    print("[D] 命中 %d/%d  分片 %d  编造 %s  %.1fs" % (len(hits), len(S4), r["shards"],
          rec["extra_codes"], r["wall"]), flush=True)
    print("[batch1] 全部完成，总耗时 %.1f 分" % ((time.time() - t0) / 60), flush=True)


def batch2():
    dC = os.path.join(OUT, "docE-30k.txt")
    if not os.path.exists(dC):
        LD.make_fixture(dC, 29000, S3a, seed=21)
    print("[batch2] E1: 池内 30K 先行", flush=True)
    ask_doc(dC, Q_LIST, S3a, "E1_30k_before_big")
    dA = os.path.join(OUT, "docA-209k.txt")
    print("[batch2] E2: 紧接着 209K", flush=True)
    ask_doc(dA, Q_LIST, S1, "E2_209k_after_inpool")
    print("[batch2] 完成", flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", type=int, default=1)
    a = ap.parse_args()
    (batch1 if a.batch == 1 else batch2)()
