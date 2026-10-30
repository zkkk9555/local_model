import json, sys, time, os, urllib.request

BASE = os.environ.get("BASE", "http://127.0.0.1:8091")
LONG = len(sys.argv) > 1 and sys.argv[1] == "long"


def send(prompt, max_tokens, temp=0.0, label=""):
    body = json.dumps({"model": "bonsai2-27b", "messages": [{"role": "user", "content": prompt}],
                       "temperature": temp, "max_tokens": max_tokens}).encode()
    req = urllib.request.Request(BASE + "/v1/chat/completions", data=body,
                                 headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=3600) as r:
        out = json.loads(r.read())
    wall = time.time() - t0
    t = out.get("timings") or {}
    msg = out["choices"][0]["message"]["content"]
    accept = ""
    if t.get("draft_n"):
        accept = " accept=%.1f%% (%d/%d)" % (100.0 * t.get("draft_n_accepted", 0) / t["draft_n"],
                                             t.get("draft_n_accepted", 0), t["draft_n"])
    print("%-10s prefill=%7.1f tok/s (n=%d, %.2fs) decode=%6.1f tok/s (n=%d) wall=%5.2fs%s" % (
        label, t.get("prompt_per_second", 0), t.get("prompt_n", 0),
        t.get("prompt_ms", 0) / 1000.0,
        t.get("predicted_per_second", 0), t.get("predicted_n", 0), wall, accept), flush=True)
    print("   sample: %s" % msg[:60].replace("\n", " "), flush=True)
    return t


counting = " ".join(str(i) for i in range(1, 301)) + "\n\nContinue the same number sequence from the next number. Output numbers only, in the same space-separated format, and keep going until the length limit."
prose = "请用中文写一段关于缓存淘汰策略的说明，大约三百字。"

send(counting, 400, 0.0, "counting")
send(prose, 300, 0.7, "prose")

if LONG:
    # ~8k-token Chinese-ish document with a needle, then ask for it.
    unit = "第{i}段：KV 缓存分级存储把设备侧常驻窗口与主机侧分页缓存分开管理，按需回取。"
    doc = "\n".join(unit.format(i=i) for i in range(1, 220))
    prompt = doc + "\n\n文档里有一句标记：段落编号 137 后面写着什么？原样引用该段。"
    send(prompt, 120, 0.0, "doc~8k")
