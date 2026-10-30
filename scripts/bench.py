import json, sys, time, urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8091"
SESSION = "bench-1"


def get(path):
    with urllib.request.urlopen(BASE + path, timeout=60) as resp:
        return resp.read().decode("utf-8", "replace")


def chat(prompt, max_tokens=256, session=SESSION):
    body = json.dumps({
        "model": "bonsai2-27b",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "stream": True,
        "temperature": 0.7,
        "top_p": 0.9,
        "top_k": 20,
    }).encode("utf-8")
    req = urllib.request.Request(BASE + "/v1/chat/completions", data=body,
                                 headers={"Content-Type": "application/json"})
    if session:
        req.add_header("x-session-affinity", session)
    started = time.time()
    ttft = None
    tokens = 0
    text = []
    with urllib.request.urlopen(req, timeout=3600) as resp:
        for raw in resp:
            line = raw.strip()
            if not line.startswith(b"data:"):
                continue
            chunk = line[5:].strip()
            if chunk == b"[DONE]":
                break
            try:
                payload = json.loads(chunk)
            except Exception:
                continue
            choices = payload.get("choices") or []
            if not choices:
                continue
            delta = choices[0].get("delta") or {}
            piece = delta.get("content")
            if piece:
                if ttft is None:
                    ttft = time.time() - started
                tokens += 1
                text.append(piece)
    elapsed = time.time() - started
    return ttft, tokens, elapsed, "".join(text)


def report(label, prompt, max_tokens=256):
    ttft, tokens, elapsed, text = chat(prompt, max_tokens)
    decode = 0.0
    if tokens > 1 and ttft is not None and elapsed > ttft:
        decode = (tokens - 1) / (elapsed - ttft)
    print("%-22s ttft=%6.2fs tokens=%4d total=%6.2fs decode=%5.1f tok/s" % (
        label, ttft or -1, tokens, elapsed, decode), flush=True)
    print("   text: %s" % text[:120].replace("\n", " "))
    return ttft, tokens, elapsed


print("models:", get("/v1/models")[:600])
short = "用一句话说明什么是 KV cache。"
report("warmup", short, 64)
report("round1 short", short, 128)
report("round2 short", short, 128)
long_prompt = ("请阅读下面这段文字，然后用中文写一段两百字的摘要，并在最后列出三个关键词。\n\n" + "KV cache 是自回归推理中的一种显存换时间的做法。" * 400)
report("long prompt 1", long_prompt, 256)
report("long prompt 2", long_prompt, 256)
