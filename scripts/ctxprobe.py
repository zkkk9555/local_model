import json, sys, time, os, urllib.request, random

BASE = os.environ.get("BASE", "http://127.0.0.1:8091")
FILLER = ("分布式系统中缓存一致性依赖版本号与失效广播两类机制协同；"
          "设备侧常驻窗口负责近邻语义，主机侧分页缓存负责长程证据；"
          "检索器按内容相关度把证据页回取到注意力窗口中。")
MARK = {int(k): v for k, v in (a.split("=") for a in sys.argv[1:])} if len(sys.argv) > 1 else {8000: "ZQ8K-4417", 20000: "QW20K-8823", 40000: "ER40K-6619"}


def build(target_tokens, mark):
    """Roughly target_tokens of Chinese filler, needle buried at ~60% depth."""
    per = len(FILLER) / 1.55  # tokens per filler line, rough
    n = max(4, int(target_tokens / per))
    lines = [FILLER for _ in range(n)]
    pos = int(n * 0.6)
    lines[pos] = "重要记录：本段编号 %d，口令是 %s。" % (pos, mark)
    q = "\n\n请回答：文档里那条「重要记录」的口令是什么？只输出口令本身。"
    return "\n".join(lines) + q


def ask(prompt, max_tokens=32):
    body = json.dumps({"model": "bonsai2-27b", "messages": [{"role": "user", "content": prompt}],
                       "temperature": 0.0, "max_tokens": max_tokens}).encode()
    req = urllib.request.Request(BASE + "/v1/chat/completions", data=body,
                                 headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=3600) as r:
        out = json.loads(r.read())
    wall = time.time() - t0
    t = out.get("timings") or {}
    msg = out["choices"][0]["message"]["content"].strip()
    return t, msg, wall


for size, mark in sorted(MARK.items()):
    t, msg, wall = ask(build(size, mark))
    hit = mark in msg
    print("%6d tok: prompt_n=%6d prefill=%7.1f tok/s (%.1fs) decode=%5.1f wall=%5.1fs  needle=%s  reply=%s" % (
        size, t.get("prompt_n", 0), t.get("prompt_per_second", 0), t.get("prompt_ms", 0) / 1000.0,
        t.get("predicted_per_second", 0), wall, "HIT" if hit else "MISS", msg[:40].replace("\n", " ")), flush=True)