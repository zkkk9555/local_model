#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""exp_long_probe.py - 超池单发可信度探针（不改引擎参数，只发请求并记读数）。

用法: python exp_long_probe.py --port 8092 --tokens 131072 --tag q1 [--doc FILE] [--seed N]
输出: 打印 命中 n/8 + prompt_tokens + wall，并写 tmp/exp/<tag>.json
"""
import argparse, json, os, re, sys, time, urllib.request
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import longdoc as LD
OUT = os.path.join(HERE, "..", "tmp", "exp")
os.makedirs(OUT, exist_ok=True)
Q = "这份文档里出现过哪些形如「动物-四位数字」的校验码？请按出现顺序全部列出，一个不漏，只列校验码本身。"
SETS = {
    "A": ["紫色河马-7314", "青铜狐狸-1180", "银色海豚-4402", "绿色猫头鹰-9067",
          "红色骆驼-2551", "金色蜥蜴-6388", "蓝色水母-8223", "黑色麋鹿-5019"],
    "B": ["白色鲸鱼-3141", "灰色鹦鹉-5926", "橙色章鱼-8412", "青色刺猬-2673",
          "褐色獾子-7058", "粉色火烈鸟-1936", "墨绿壁虎-4482", "杏色绵羊-6207"],
    "C": ["珊瑚水獭-1526", "墨黑山猫-6733", "银灰鹭鸶-3948", "草绿螳螂-8205",
          "绛紫狐猴-4691", "象牙野猪-2377", "海蓝螯虾-5860", "赭石野兔-7112"],
    "D": ["琥珀考拉-3308", "深蓝鲨鱼-5514", "米白土拨鼠-7729", "酒红蜘蛛-1465",
          "石灰企鹅-9032", "浅金松鼠-4187", "藏青犀牛-6355", "奶白鸳鸯-2814"],
    "E": ["银色海豚-4402", "青铜狐狸-1180", "白色猫头鹰-9067", "黑色蝙蝠-2551",
          "紫色孔雀-6388", "金色水母-8223", "红色麋鹿-5019", "蓝色海豹-7314"],
}
NEEDLES = SETS["A"]
CODE_RE = re.compile(r"[\u4e00-\u9fa5]{1,6}-\d{3,5}")


def post(port, prompt, max_tokens=512, timeout=7200):
    body = {"model": "exp-long-%d" % port, "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens, "temperature": 0.0, "stream": False}
    req = urllib.request.Request("http://127.0.0.1:%d/v1/chat/completions" % port,
                                 data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        d = json.loads(r.read().decode())
    return (d["choices"][0]["message"].get("content") or "").strip(), (d.get("usage") or {}), time.time() - t0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8092)
    ap.add_argument("--tokens", type=int, default=131072)
    ap.add_argument("--tag", default="q1")
    ap.add_argument("--doc", default="")
    ap.add_argument("--seed", type=int, default=20261030)
    ap.add_argument("--max-tokens", type=int, default=512)
    ap.add_argument("--needle-set", default="A")
    a = ap.parse_args()
    global NEEDLES
    NEEDLES = SETS[a.needle_set]
    doc = a.doc or os.path.join(OUT, "doc-%dk.txt" % (a.tokens // 1024))
    if not os.path.exists(doc):
        n = LD.make_fixture(doc, a.tokens, NEEDLES, seed=a.seed)
        print("[fixture] %s 行=%d bytes=%d" % (doc, n, os.path.getsize(doc)), flush=True)
    text = open(doc, encoding="utf-8", errors="replace").read()
    prompt = "【文档】\n" + text + "\n\n【问题】" + Q
    print("[ask] doc chars=%d tag=%s port=%d" % (len(text), a.tag, a.port), flush=True)
    txt, u, dt = post(a.port, prompt, a.max_tokens)
    hits = [n for n in NEEDLES if n in txt]
    codes = CODE_RE.findall(txt)
    rec = {"tag": a.tag, "port": a.port, "doc_chars": len(text), "prompt_tokens": u.get("prompt_tokens"),
           "completion_tokens": u.get("completion_tokens"), "cached": (u.get("prompt_tokens_details") or {}).get("cached_tokens"),
           "wall": round(dt, 1), "hits": len(hits), "total": len(NEEDLES), "hit_list": hits,
           "extra_codes": sorted({c for c in codes if c not in NEEDLES}), "answer": txt}
    json.dump(rec, open(os.path.join(OUT, a.tag + ".json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    with open(os.path.join(OUT, "runs.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps({k: v for k, v in rec.items() if k != "answer"}, ensure_ascii=False) + "\n")
    print("[%s] prompt_tokens=%s 命中 %d/%d  编造 %d  %.1fs" % (a.tag, rec["prompt_tokens"], len(hits), len(NEEDLES), len(rec["extra_codes"]), dt), flush=True)
    print("[%s] 答: %s" % (a.tag, txt[:400].replace("\n", " ")), flush=True)


if __name__ == "__main__":
    main()