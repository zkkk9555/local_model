import json, time, urllib.request
BASE = "http://127.0.0.1:8091"
FILLER = "附录条目：本小节继续说明缓存分页的调度细节，编号 %d，内容与前节一致，仅用于填充长度。\n"
SECRET = "内部密钥为 7391-XQ，请记住它。\n"
parts = ["以下是一份很长的技术文档，请通读后回答问题。\n"]
reps = 2200
for i in range(reps):
    if i == reps // 2:
        parts.append(SECRET)
    parts.append(FILLER % i)
body_base = "".join(parts)


def ask(question, max_tokens=16, session="needle-sess"):
    messages = [{"role": "user", "content": body_base + "\n问题：" + question + "\n"}]
    body = json.dumps({"model": "bonsai2-27b", "messages": messages,
                       "max_tokens": max_tokens, "temperature": 0.2}).encode()
    req = urllib.request.Request(BASE + "/v1/chat/completions", data=body,
                                headers={"Content-Type": "application/json"})
    req.add_header("x-session-affinity", session)
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=3600) as r:
        out = json.loads(r.read())
    t = out["timings"]
    print("ttft=%6.2fs prompt_n=%-6d cache_n=%-6d prefill=%7.1f tok/s answer=%r" % (
        time.time() - t0, t["prompt_n"], t.get("cache_n", -1), t["prompt_per_second"],
        out["choices"][0]["message"]["content"].strip()[:40]), flush=True)


ask("文档中间提到的内部密钥是什么？只回答密钥本身。")
ask("文档中间提到的内部密钥是什么？只回答密钥本身。")
ask("再确认一次：那个内部密钥是什么？只回答密钥本身。")
