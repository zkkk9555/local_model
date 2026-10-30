#!/usr/bin/env python3
"""双栈对比评测：同一份题面、同一套判据，量 TTFT / decode / 正确率 / 编造。

用法：
  python tools/cmp_bench.py --label ninfer --base http://127.0.0.1:8091/v1 --model X --out reports/cmp-ninfer.json
  python tools/cmp_bench.py --label strata --base http://127.0.0.1:PORT/v1 --model Y --api-key xxx --out reports/cmp-strata.json
  python tools/cmp_bench.py --selftest

判据：must_contain 全部命中（忽略空白与大小写）且 must_not_contain 一个都不出现 => pass。
另外跑一个 doc 题：造一份带 4 个暗号的中文长文档，问「按出现顺序列出全部暗号」，考超池/检索正确率。
"""
import argparse
import json
import os
import statistics
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))


def post_stream(base, model, messages, max_tokens, temperature, api_key, timeout, reasoning_effort=""):
    url = base.rstrip("/") + "/chat/completions"
    body = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    if reasoning_effort:
        body["reasoning_effort"] = reasoning_effort
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + (api_key or "any"),
            "Accept": "text/event-stream",
        },
        method="POST",
    )
    t0 = time.time()
    ttft = None
    last_t = t0
    out = []
    usage = None
    timings = None
    finish = None
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        for raw in resp:
            line = raw.decode("utf-8", "replace").strip()
            if not line or not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            try:
                obj = json.loads(data)
            except Exception:
                continue
            if isinstance(obj.get("usage"), dict):
                usage = obj["usage"]
            if isinstance(obj.get("timings"), dict):
                timings = obj["timings"]
            for ch in obj.get("choices") or []:
                delta = ch.get("delta") or {}
                txt = delta.get("content") or ""
                if txt:
                    if ttft is None:
                        ttft = time.time() - t0
                    out.append(txt)
                    last_t = time.time()
                if ch.get("finish_reason"):
                    finish = ch["finish_reason"]
    total = time.time() - t0
    text = "".join(out)
    tm = timings if isinstance(timings, dict) else {}
    prompt_tokens = (usage or {}).get("prompt_tokens")
    if prompt_tokens is None:
        prompt_tokens = tm.get("prompt_n")
    completion_tokens = (usage or {}).get("completion_tokens")
    if completion_tokens is None:
        completion_tokens = tm.get("predicted_n")
    if completion_tokens is None:
        completion_tokens = len(out)
    cached = (usage or {}).get("prompt_tokens_details", {}).get("cached_tokens") if isinstance((usage or {}).get("prompt_tokens_details"), dict) else None
    decode_s = max(total - (ttft or total), 1e-6)
    rate = (completion_tokens - 1) / decode_s if completion_tokens and completion_tokens > 1 else None
    if rate is None and tm.get("predicted_per_second"):
        rate = float(tm["predicted_per_second"])
    return {
        "text": text,
        "ttft_s": round(ttft, 3) if ttft is not None else None,
        "total_s": round(total, 3),
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "cached_tokens": cached if cached is not None else tm.get("cache_n"),
        "finish": finish,
        "decode_tok_s": round(rate, 2) if rate else None,
        "prefill_tok_s": (round(float(tm["prompt_per_second"]), 1) if tm.get("prompt_per_second")
                          else (round(prompt_tokens / ttft, 1) if (prompt_tokens and ttft) else None)),
        "cache_n": tm.get("cache_n"),
        "timings": timings,
    }


def norm(s):
    return "".join((s or "").split()).lower()


def judge(text, must, must_not):
    t = norm(text)
    missing = [m for m in (must or []) if norm(m) not in t]
    banned = [m for m in (must_not or []) if norm(m) in t]
    return (not missing) and (not banned), missing, banned


def build_doc(lines, needles):
    """造一份分条中文记录，needles 是 [(index, 暗号)]。"""
    nmap = dict(needles)
    parts = []
    for i in range(1, lines + 1):
        if i in nmap:
            parts.append("第%d条 关键记录：暗号是 %s，请务必记住这一条。" % (i, nmap[i]))
        else:
            parts.append("第%d条 常规记录：本条目仅用于占位，不含需要记忆的内容，编号 %d。" % (i, i))
    return "\n".join(parts)


DOC_NEEDLES = [(37, "紫色河马-7314"), (211, "青铜狐狸-1180"), (488, "银色海豚-4402"), (733, "绿色猫头鹰-9067")]
DOC_QUESTION = ("下面是一份分条记录。请只做一件事：把文档中所有标注为「关键记录」的暗号，"
                "按它们在文档中出现的先后顺序列出来，用中文逗号分隔，不要解释、不要总结。")


def run(args):
    cfg = json.load(open(os.path.join(HERE, "cmp_set.json"), encoding="utf-8"))
    rows = []
    tasks = []
    for it in cfg["items"]:
        tasks.append({
            "id": it["id"],
            "messages": [{"role": "user", "content": it["user"]}],
            "max_tokens": it.get("max_tokens", 128),
            "temperature": it.get("temperature", 0),
            "must": it.get("must_contain"),
            "must_not": it.get("must_not_contain"),
        })
    doc = build_doc(args.doc_lines, DOC_NEEDLES)
    tasks.append({
        "id": "doc4needles_%d" % args.doc_lines,
        "messages": [{"role": "user", "content": DOC_QUESTION + "\n\n" + doc}],
        "max_tokens": 128,
        "temperature": 0,
        "must": [c for _, c in DOC_NEEDLES],
        "must_not": None,
    })
    for task in tasks:
        try:
            r = post_stream(args.base, args.model, task["messages"], task["max_tokens"],
                            task["temperature"], args.api_key, args.timeout,
                            args.reasoning_effort)
        except urllib.error.HTTPError as e:
            detail = ""
            try:
                detail = e.read().decode("utf-8", "replace")[:400]
            except Exception:
                pass
            rows.append({"id": task["id"], "error": "HTTP %s %s" % (e.code, detail)})
            print("%-18s ERROR HTTP %s %s" % (task["id"], e.code, detail[:160]), flush=True)
            continue
        except Exception as e:
            rows.append({"id": task["id"], "error": repr(e)[:400]})
            print("%-18s ERROR %s" % (task["id"], repr(e)[:160]), flush=True)
            continue
        ok, missing, banned = judge(r["text"], task["must"], task["must_not"])
        row = dict(r)
        row.update({"id": task["id"], "pass": ok, "missing": missing, "banned": banned,
                    "answer": r["text"][:400]})
        rows.append(row)
        print("%-18s %s ttft=%-6s prefill=%-8s decode=%-6s ctok=%-5s %s" % (
            task["id"], "PASS" if ok else "FAIL", r["ttft_s"], r["prefill_tok_s"],
            r["decode_tok_s"], r["completion_tokens"],
            ("missing=" + str(missing)) if missing else (("banned=" + str(banned)) if banned else "")), flush=True)

    good = [r for r in rows if "error" not in r]
    summary = {
        "label": args.label,
        "base": args.base,
        "model": args.model,
        "when": time.strftime("%Y-%m-%d %H:%M:%S"),
        "n": len(rows),
        "n_error": len(rows) - len(good),
        "n_pass": sum(1 for r in good if r.get("pass")),
        "ttft_median_s": round(statistics.median([r["ttft_s"] for r in good if r["ttft_s"]]), 3) if any(r["ttft_s"] for r in good) else None,
        "decode_median_tok_s": round(statistics.median([r["decode_tok_s"] for r in good if r["decode_tok_s"]]), 2) if any(r["decode_tok_s"] for r in good) else None,
    }
    out = {"summary": summary, "rows": rows}
    if args.out:
        os.makedirs(os.path.dirname(args.out), exist_ok=True)
        json.dump(out, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\n== ", json.dumps(summary, ensure_ascii=False))
    return 0


def selftest():
    doc = build_doc(20, [(5, "甲-1"), (17, "乙-2")])
    assert "甲-1" in doc and "乙-2" in doc and doc.count("关键记录") == 2
    assert judge("答案是 91 度", ["91"], None)[0]
    assert not judge("答案是 90", ["91"], None)[0]
    assert not judge("这是 2018年 的", None, ["2018年"])[0]
    assert judge("  张三 ，30", ["name", "张三"], None)[0] is False
    print("SELFTEST PASS")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", default="run")
    ap.add_argument("--base", default="http://127.0.0.1:8091/v1")
    ap.add_argument("--model", default="")
    ap.add_argument("--api-key", default="")
    ap.add_argument("--out", default="")
    ap.add_argument("--doc-lines", type=int, default=900)
    ap.add_argument("--timeout", type=int, default=3600)
    ap.add_argument("--reasoning-effort", default="",
                    help="可选；llama.cpp 传 none 可把 reasoning_n 从 38 压到 2（等价 NInfer --default-reasoning-effort none）")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        sys.exit(selftest())
    sys.exit(run(a))