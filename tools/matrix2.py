#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""matrix2.py - 用 verifier 的已知 fixture 复测：首发 209K / 池内 30K / longdoc 分片召回。"""
import json, os, re, sys, time, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import longdoc as LD

OV = r"C:/Users/Administrator/Documents/deepseek-harness/default-workspace/tmp/overpool"
OUT = os.path.join(HERE, "..", "tmp", "matrix2")
os.makedirs(OUT, exist_ok=True)
ENGINE = "http://127.0.0.1:8091/v1"
MODEL = "local"

S1 = ["紫色河马-7314", "青铜狐狸-1180", "银色海豚-4402", "绿色猫头鹰-9067",
      "红色骆驼-2551", "金色蜥蜴-6388", "蓝色水母-8223", "黑色麋鹿-5019"]

Q_EASY = ("下面是一份很长的分条记录，共约 7244 条。请只做一件事：把文档中所有标注为「关键记录」的暗号，"
          "按它们在文档中出现的先后顺序列出来，用中文逗号分隔，不要解释、不要总结。")
CODE_RE = re.compile(r"[\u4e00-\u9fa5]{1,6}-\d{3,5}")


def post(messages, max_tokens=512, timeout=3600):
    body = {"model": MODEL, "messages": messages, "max_tokens": max_tokens,
            "temperature": 0.0, "stream": False}
    req = urllib.request.Request(ENGINE + "/chat/completions", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json",
                                          "Authorization": "Bearer local-any-key"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        d = json.loads(r.read().decode())
    return (d["choices"][0]["message"].get("content") or "").strip(), (d.get("usage") or {}), time.time() - t0


def rec(tag, txt, u, dt, needles, shards=None):
    hits = [n for n in needles if n in txt]
    codes = CODE_RE.findall(txt)
    extra = sorted({c for c in codes if c not in needles})
    r = {"tag": tag, "prompt_tokens": u.get("prompt_tokens"), "completion_tokens": u.get("completion_tokens"),
         "wall": round(dt, 1), "hits": len(hits), "total": len(needles), "hit_list": hits,
         "extra_codes": extra, "n_extra": len(extra), "shards": shards, "answer": txt}
    json.dump(r, open(os.path.join(OUT, tag + ".json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    with open(os.path.join(OUT, "m.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps({k: v for k, v in r.items() if k != "answer"}, ensure_ascii=False) + "\n")
    print("[%s] prompt=%s 命中=%d/%d 编造=%d %.1fs %s" % (
        tag, r["prompt_tokens"], r["hits"], r["total"], r["n_extra"], r["wall"],
        txt[:120].replace("\n", " ")), flush=True)
    return r


def ask_file(path, tag, needles, q=Q_EASY, max_tokens=512):
    text = open(path, encoding="utf-8", errors="replace").read()
    txt, u, dt = post([{"role": "user", "content": text + "\n\n" + q}], max_tokens)
    return rec(tag, txt, u, dt, needles)


if __name__ == "__main__":
    only = sys.argv[1] if len(sys.argv) > 1 else "ACD"
    d209 = os.path.join(OV, "d209k-s20261030.txt")
    d30 = os.path.join(OV, "d30000.txt")
    if "A" in only:
        print("[A] 干净进程第一个 209K 请求", flush=True)
        ask_file(d209, "A_209k_first_clean", S1)
    if "C" in only:
        print("[C] 池内 30K（污染后回归）", flush=True)
        ask_file(d30, "C1_30k_inpool", S1)
        ask_file(d30, "C2_30k_inpool_again", S1)
    if "D" in only:
        print("[D] longdoc 分片地图-化简 209K（池内，可重复）", flush=True)
        out = os.path.join(OUT, "D_longdoc.md")
        r = LD.run(d209, Q_EASY, ENGINE, MODEL, 26000, 1024, out)
        rec("D_longdoc_209k", r["answer"], {}, r["wall"], S1, shards=r["shards"])
    print("[matrix2] done", flush=True)
