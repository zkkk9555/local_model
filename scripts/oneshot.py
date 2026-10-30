import json, sys, time, urllib.request
BASE = "http://127.0.0.1:8091"
body = json.dumps({"model": "bonsai2-27b", "messages": [{"role": "user", "content": "用一句话说明什么是 KV cache。"}], "max_tokens": 96, "temperature": 0.7}).encode()
req = urllib.request.Request(BASE + "/v1/chat/completions", data=body, headers={"Content-Type": "application/json"})
t0 = time.time()
with urllib.request.urlopen(req, timeout=600) as r:
    out = json.loads(r.read())
print("elapsed %.2fs" % (time.time() - t0))
print(json.dumps(out, ensure_ascii=False)[:900])
