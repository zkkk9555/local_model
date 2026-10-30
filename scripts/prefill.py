import json, time, urllib.request, sys

BASE = "http://127.0.0.1:8091"
FILLER = "KV cache 是一种用显存换取推理速度的工程做法，它把历史 token 的键值向量留在显存里。"


def post(prompt, max_tokens, session="prefill-test"):
    body = json.dumps({"model": "bonsai2-27b", "messages": [{"role": "user", "content": prompt}],
                       "max_tokens": max_tokens, "temperature": 0.7}).encode()
    req = urllib.request.Request(BASE + "/v1/chat/completions", data=body,
                                headers={"Content-Type": "application/json"})
    req.add_header("x-session-affinity", session)
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=3600) as r:
        out = json.loads(r.read())
    return time.time() - t0, out


for reps in (150, 400, 800):
    prompt = "请用中文概括下面这段材料，并在最后列出三个关键词。\n\n" + FILLER * reps
    total, out = post(prompt, 24)
    t = out["timings"]
    print("reps=%-4d prompt_n=%-6d prefill=%7.1f tok/s prompt_ms=%8.1f cache_n=%-6d decode=%5.1f tok/s total=%5.2fs"
          % (reps, t["prompt_n"], t["prompt_per_second"], t["prompt_ms"], t.get("cache_n", -1),
             t["predicted_per_second"], total), flush=True)
