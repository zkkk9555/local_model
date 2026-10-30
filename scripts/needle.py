import json, time, urllib.request, sys

BASE = "http://127.0.0.1:8091"
FILLER = "附录条目：本小节继续说明缓存分页的调度细节，编号 %d，内容与前节一致，仅用于填充长度。\n"
SECRET = "内部密钥为 7391-XQ，请记住它。\n"


def build(target_reps):
    parts = ["以下是一份很长的技术文档，请通读后回答问题。\n"]
    for i in range(target_reps):
        if i == target_reps // 2:
            parts.append(SECRET)
        parts.append(FILLER % i)
    parts.append("\n问题：文档中间提到的内部密钥是什么？只回答密钥本身。\n")
    return "".join(parts)


def ask(prompt, max_tokens=24):
    body = json.dumps({"model": "bonsai2-27b", "messages": [{"role": "user", "content": prompt}],
                       "max_tokens": max_tokens, "temperature": 0.2}).encode()
    req = urllib.request.Request(BASE + "/v1/chat/completions", data=body,
                                headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=3600) as r:
        out = json.loads(r.read())
    elapsed = time.time() - t0
    msg = out["choices"][0]["message"]["content"]
    t = out["timings"]
    return elapsed, msg, t


for reps in (1200, 2200):
    prompt = build(reps)
    elapsed, msg, t = ask(prompt)
    print("reps=%-5d prompt_n=%-6d prefill=%7.1f tok/s ttft=%6.1fs decode=%5.1f tok/s answer=%r"
          % (reps, t["prompt_n"], t["prompt_per_second"], t["prompt_ms"] / 1000,
             t["predicted_per_second"], msg.strip()[:60]), flush=True)
