#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""双栈对比 bench（Strata / NInfer 通用），纯文本 prompt 直打 OpenAI 接口。

用法:
  python bench_strata.py --base http://127.0.0.1:8080 --out ../reports/data/strata-cmp.json --label strata-arena-auto
  python bench_strata.py --base http://127.0.0.1:8080 --longdoc 24000 --out ../reports/data/strata-longdoc.json
"""
import argparse, json, sys, time, statistics, urllib.request


def post_stream(base, payload, timeout):
    url = base.rstrip("/") + "/v1/chat/completions"
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json", "Authorization": "Bearer local"})
    t0 = time.time()
    ttft = None
    parts = []
    usage = {}
    timings = {}
    chunks = 0
    with urllib.request.urlopen(req, timeout=timeout) as r:
        buf = b""
        while True:
            try:
                chunk = r.read(2048)
            except Exception:
                break
            if not chunk:
                break
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                line = line.strip()
                if not line.startswith(b"data:"):
                    continue
                s = line[5:].strip()
                if s == b"[DONE]":
                    continue
                try:
                    obj = json.loads(s.decode("utf-8"))
                except Exception:
                    continue
                chunks += 1
                if obj.get("usage"):
                    usage = obj["usage"]
                if obj.get("timings"):
                    timings = obj["timings"]
                for ch in obj.get("choices") or []:
                    d = ch.get("delta") or {}
                    piece = d.get("content") or ""
                    if piece:
                        if ttft is None:
                            ttft = time.time() - t0
                        parts.append(piece)
    return {"text": "".join(parts), "ttft": ttft, "total": time.time() - t0, "usage": usage, "timings": timings, "chunks": chunks}


def norm(s):
    return "".join((s or "").split()).lower()


def grade(item, text):
    t = norm(text)
    ok = True
    miss = []
    bad = []
    for m in item.get("must_contain") or []:
        if norm(m) not in t:
            ok = False
            miss.append(m)
    for m in item.get("must_not_contain") or []:
        if norm(m) in t:
            ok = False
            bad.append(m)
    return ok, miss, bad


def make_payload(model, user, max_tokens, temp):
    return {"model": model, "messages": [{"role": "user", "content": user}], "temperature": temp, "max_tokens": max_tokens, "stream": True}


def run_item(base, model, item, timeout):
    payload = make_payload(model, item["user"], item.get("max_tokens", 128), item.get("temperature", 0))
    res = post_stream(base, payload, timeout)
    n = (res["usage"] or {}).get("completion_tokens")
    p = (res["usage"] or {}).get("prompt_tokens")
    dt = res["total"] - (res["ttft"] or 0.0)
    if n and dt > 0:
        dec = (n - 1) / dt if n > 1 else float(n) / dt
    else:
        dec = None
    t = res["timings"] or {}
    ok, miss, bad = grade(item, res["text"])
    return {"id": item["id"], "pass": ok, "miss": miss, "bad": bad, "ttft": res["ttft"], "total": res["total"], "prompt_tokens": p, "completion_tokens": n, "decode_tps": dec, "engine_predicted_tps": t.get("predicted_per_second"), "engine_prompt_tps": t.get("prompt_per_second"), "text": res["text"][:400], "chunks": res["chunks"]}


def longdoc(base, model, target_tokens, timeout):
    filler = "第{n}段：公司内部技术备忘录，记录本地推理服务的部署细节、显存占用、上下文长度的取舍，以及若干与本次提问无关的运维说明。"
    lines = []
    i = 0
    approx = 0
    while approx < target_tokens:
        i += 1
        s = filler.format(n=i)
        lines.append(s)
        approx += len(s)
    doc = "\n".join(lines)
    prompt = doc + "\n\n上面的备忘录里，最后一段的编号是多少？只输出数字。"
    expect = str(i)
    item = {"id": "longdoc%d" % target_tokens, "user": prompt, "max_tokens": 32, "temperature": 0, "must_contain": [expect]}
    res = run_item(base, model, item, timeout)
    res["expect"] = expect
    return res, prompt


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8080")
    ap.add_argument("--set", default="C:/Project/local_model/tools/cmp_set.json")
    ap.add_argument("--model", default="local")
    ap.add_argument("--out", default="")
    ap.add_argument("--label", default="")
    ap.add_argument("--timeout", type=float, default=1800.0)
    ap.add_argument("--longdoc", type=int, default=0)
    ap.add_argument("--save-prompt", default="")
    a = ap.parse_args()
    rows = []
    if a.longdoc:
        r, prompt = longdoc(a.base, a.model, a.longdoc, a.timeout)
        if a.save_prompt:
            open(a.save_prompt, "w", encoding="utf-8").write(prompt)
        print("LONGDOC target=%d prompt_tokens=%s ttft=%.2fs total=%.2fs prefill_tps=%s pass=%s" % (a.longdoc, r["prompt_tokens"], r["ttft"] or -1, r["total"], ("%.1f" % (r["prompt_tokens"] / r["ttft"])) if (r["prompt_tokens"] and r["ttft"]) else "n/a", r["pass"]))
        print("expect=%s text=%r" % (r["expect"], r["text"][:120]))
        data = {"label": a.label, "base": a.base, "kind": "longdoc", "target": a.longdoc, "row": r}
    else:
        items = json.load(open(a.set, encoding="utf-8"))["items"]
        print("%-10s %-4s %8s %8s %8s %8s %7s" % ("id", "pass", "ttft_s", "dec_tps", "prompt_t", "compl_t", "total_s"))
        for it in items:
            try:
                r = run_item(a.base, a.model, it, a.timeout)
            except Exception as e:
                print("%-10s ERROR %s" % (it["id"], e))
                rows.append({"id": it["id"], "error": str(e)})
                continue
            rows.append(r)
            print("%-10s %-4s %8s %8s %8s %8s %7.2f" % (r["id"], "PASS" if r["pass"] else "FAIL", ("%.2f" % r["ttft"]) if r["ttft"] else "n/a", ("%.1f" % r["decode_tps"]) if r["decode_tps"] else "n/a", r["prompt_tokens"], r["completion_tokens"], r["total"]))
            if not r["pass"]:
                print("           miss=%s bad=%s text=%r" % (r["miss"], r["bad"], r["text"][:160]))
        ok = [r for r in rows if r.get("pass")]
        decs = [r["decode_tps"] for r in rows if r.get("decode_tps")]
        ttfts = [r["ttft"] for r in rows if r.get("ttft")]
        print("")
        print("SUMMARY label=%s pass=%d/%d decode_median=%s ttft_median=%s" % (a.label, len(ok), len(rows), ("%.2f" % statistics.median(decs)) if decs else "n/a", ("%.2f" % statistics.median(ttfts)) if ttfts else "n/a"))
        data = {"label": a.label, "base": a.base, "kind": "cmp", "rows": rows, "summary": {"pass": len(ok), "n": len(rows), "decode_median": statistics.median(decs) if decs else None, "ttft_median": statistics.median(ttfts) if ttfts else None}}
    if a.out:
        if "/" in a.out:
            import os
            d = a.out.rsplit("/", 1)[0]
            if d and not os.path.isdir(d):
                os.makedirs(d, exist_ok=True)
        json.dump(data, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("wrote", a.out)


if __name__ == "__main__":
    main()