#!/usr/bin/env python
"""单发长文探针（llama.cpp 专用）：一个请求塞进整篇文档，数命中针 + 抓 timings。

用法：
  python tools/llama_probe.py --doc tmp/exp/doc-30k8.txt --needles "A,B,..." --max-tokens 256
"""
import argparse, json, os, re, sys, time, urllib.request

CODE_RE = re.compile(r"[\u4e00-\u9fa5]{1,6}-\d{3,5}")


def post(base, key, model, prompt, max_tokens, timeout, reasoning_effort="none"):
    body = {"model": model, "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens, "temperature": 0.0, "stream": False}
    if reasoning_effort:
        body["reasoning_effort"] = reasoning_effort
    req = urllib.request.Request(base.rstrip("/") + "/chat/completions",
                                 data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json",
                                          "Authorization": "Bearer " + key})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        d = json.loads(r.read().decode("utf-8"))
    return d, time.time() - t0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8089/v1")
    ap.add_argument("--api-key", default="")
    ap.add_argument("--model", default="bonsai-2-27b")
    ap.add_argument("--doc", required=True)
    ap.add_argument("--needles", default="", help="逗号分隔的标准答案（用于数命中）")
    ap.add_argument("--question", default="这份文档里出现过哪些形如「动物-四位数字」的校验码？请按出现顺序全部列出，一个不漏，只列校验码本身。")
    ap.add_argument("--max-tokens", type=int, default=512)
    ap.add_argument("--timeout", type=float, default=21600.0)
    ap.add_argument("--tag", default="")
    ap.add_argument("--out", default="")
    a = ap.parse_args()
    key = a.api_key or "x"
    text = open(a.doc, "r", encoding="utf-8", errors="replace").read()
    prompt = "【文档】\n" + text + "\n\n【问题】" + a.question
    needle_list = [x.strip() for x in a.needles.split(",") if x.strip()]
    print("[llama-probe] doc %s  %d chars  needles %d  tag=%s" % (a.doc, len(text), len(needle_list), a.tag), flush=True)
    try:
        d, dt = post(a.base, key, a.model, prompt, a.max_tokens, a.timeout)
        err = ""
    except Exception as e:
        d, dt, err = {}, time.time() - time.time(), "%s: %s" % (type(e).__name__, e)
    u = (d.get("usage") or {})
    t = (d.get("timings") or {})
    msg = ((d.get("choices") or [{}])[0].get("message") or {})
    txt = (msg.get("content") or "").strip()
    hits = [n for n in needle_list if n in txt]
    codes = []
    seen = set()
    for m in CODE_RE.finditer(txt):
        v = m.group(0)
        if v not in seen:
            seen.add(v); codes.append(v)
    rec = {"tag": a.tag, "doc": os.path.abspath(a.doc), "chars": len(text), "wall": round(dt, 1),
           "prompt_tokens": u.get("prompt_tokens"), "completion_tokens": u.get("completion_tokens"),
           "prompt_ms": t.get("prompt_ms"), "predicted_ms": t.get("predicted_ms"),
           "prompt_per_second": t.get("prompt_per_second"), "predicted_per_second": t.get("predicted_per_second"),
           "hits": len(hits), "needles": len(needle_list), "codes_found": codes, "error": err,
           "answer_head": txt[:300].replace("\n", " ")}
    print("[llama-probe] %s" % json.dumps(rec, ensure_ascii=False), flush=True)
    if a.out:
        os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
        with open(a.out, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return 0 if (not err and (not needle_list or len(hits) == len(needle_list))) else 1


if __name__ == "__main__":
    sys.exit(main())