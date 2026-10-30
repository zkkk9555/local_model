#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""llama.cpp 路线长上下文验证器（优先自测，不碰 GPU）。

背景：现役 NInfer KVMem 在 8G 上实测「同一个引擎进程只可信一次」——第一个超池请求 8/8，
     之后同长度请求掉到 2/8、0/8（见 reports/超池200K-可用性实测.md）。
     llama.cpp 分叉 professorpalmer/bonsai-ada-surgery 的设计是「前 N 个 KV 位置放显存
     (--kv-vram-cells)、其余全量放 pinned RAM 走 PCIe」，理论上不该复现这个毛病。
     本脚本就是用来证实/证伪它的：同一个服务进程内连发 209k -> 30k -> 209k -> 100k -> 209k，
     看第 2、第 3 次 209K 是否仍然 8/8。

用法：
  python tools/llama_longctx_test.py --base http://127.0.0.1:8089/v1 --model <id> \
         --fixtures C:/Users/Administrator/Documents/deepseek-harness/default-workspace/tmp/overpool \
         --out logs/llama-longctx.json --seq 209k,30k,209k,100k,209k --timeout 3600
  python tools/llama_longctx_test.py --selftest        # 本地 mock，不联网、不碰卡

只依赖标准库（Python 3.12），全部输出 UTF-8。
"""

import argparse
import json
import os
import re
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DEFAULT_BASE = "http://127.0.0.1:8089/v1"
DEFAULT_SEQ = "209k,30k,209k,100k,209k"
DEFAULT_FIXTURES = ("C:/Users/Administrator/Documents/deepseek-harness/"
                   "default-workspace/tmp/overpool")
CHARS_PER_TOKEN = 1.4155   # 与 tmp/overpool/needles.py 同口径（295,944 chars -> 209,037 tokens）

ANIMALS = [("紫色河马", 7314), ("青铜狐狸", 1180), ("银色海豚", 4402), ("绿色猫头鹰", 9067),
           ("红色骆驼", 2551), ("金色蜥蜴", 6388), ("蓝色水母", 8223), ("黑色麋鹿", 5019)]
LEGIT = {"%s-%04d" % (c, k) for c, k in ANIMALS}
CODE_LIST = ["%s-%04d" % (c, k) for c, k in ANIMALS]

# matrix2.py 里的 Q_EASY（提问原文，逐字一致）
Q_EASY = ("下面是一份很长的分条记录，共约 7244 条。请只做一件事：把文档中所有标注为「关键记录」的暗号，"
          "按它们在文档中出现的先后顺序列出来，用中文逗号分隔，不要解释、不要总结。")

FIXTURES = {
    "209k": ["d209k-s20261030.txt"],
    "150k": ["d150k-s20261030.txt"],
    "100k": ["d100k-s20261030.txt"],
    "100k-s777": ["d100k-s777.txt"],
    "30k": ["d30000.txt"],
    "60k": ["d60000-s20261030.txt"],
}

CODE_RE = re.compile(r"[\u4e00-\u9fa5]{2,6}-\d{2,5}")
WS_RE = re.compile(r"\s+")


def fixture_path(fixdir, label):
    """把 209k / 100k-s777 这类标签解析成 fixture 文件路径。"""
    cands = list(FIXTURES.get(label, []))
    cands += ["d%s.txt" % label, "d%s-s20261030.txt" % label]
    for name in cands:
        p = os.path.join(fixdir, name)
        if os.path.isfile(p):
            return p
    have = []
    if os.path.isdir(fixdir):
        have = sorted(f for f in os.listdir(fixdir) if f.endswith(".txt"))
    raise SystemExit("找不到 fixture %r（目录 %s 里只有：%s）" % (label, fixdir, ", ".join(have) or "无"))


def build_prompt(text, question_mode="append", question=Q_EASY):
    """append 与 tools/matrix2.py 的 ask_file 逐字一致（doc + 两个换行 + Q）；asis 直接用文件内容。

    注意：tmp/overpool 里的 fixture 开头已经带了同一句提问（needles.py --dump-doc 写的），
    append 会让提问在首尾各出现一次 —— 这是 matrix2 实测沿用的口径，保持可比性。
    """
    if question_mode == "asis":
        return text
    return text + "\n\n" + question


def ask(base, model, prompt, max_tokens=512, timeout=3600.0, api_key="x", reasoning_effort=""):
    """发一次流式请求，返回原文 + 计时 + usage。HTTP 非 200 不抛异常，记在 status/error 里。"""
    url = base.rstrip("/") + "/chat/completions"
    body = {"model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens, "temperature": 0, "stream": True,
            "stream_options": {"include_usage": True}}
    if reasoning_effort:
        body["reasoning_effort"] = reasoning_effort
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
        "Authorization": "Bearer " + api_key})
    t0 = time.time()
    t_byte = None
    t_first = None
    chunks = 0
    parts = []
    usage = None
    timings = None
    status = None
    err = None
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = resp.status
            for raw in resp:
                if t_byte is None:
                    t_byte = time.time() - t0
                line = raw.decode("utf-8", "replace").strip()
                if not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if payload == "[DONE]":
                    break
                try:
                    obj = json.loads(payload)
                except Exception:
                    continue
                chunks += 1
                if obj.get("usage"):
                    usage = obj["usage"]
                if isinstance(obj.get("timings"), dict):
                    timings = obj["timings"]
                for ch in obj.get("choices") or []:
                    piece = (ch.get("delta") or {}).get("content")
                    if piece:
                        if t_first is None:
                            t_first = time.time() - t0
                        parts.append(piece)
    except urllib.error.HTTPError as e:
        status = e.code
        try:
            err = e.read().decode("utf-8", "replace")[:800]
        except Exception:
            err = "<no body>"
    except Exception as e:
        err = "%s: %s" % (type(e).__name__, str(e)[:400])
    wall = time.time() - t0
    text = "".join(parts)
    u = usage or {}
    tm = timings if isinstance(timings, dict) else {}
    ptok = u.get("prompt_tokens")
    if ptok is None:
        ptok = tm.get("prompt_n")
    ctok = u.get("completion_tokens")
    if ctok is None:
        ctok = tm.get("predicted_n")
    cached = None
    det = u.get("prompt_tokens_details") or {}
    if isinstance(det, dict) and det.get("cached_tokens") is not None:
        cached = det.get("cached_tokens")
    elif u.get("cached_tokens") is not None:
        cached = u.get("cached_tokens")
    cache_n = tm.get("cache_n")
    if cached is None and cache_n is not None:
        cached = cache_n
    prefill = tm.get("prompt_per_second")
    if prefill is None and ptok and wall > 0:
        prefill = round(ptok / wall, 1)
    decode = tm.get("predicted_per_second")
    if decode is None and ctok and t_first is not None and ctok >= 3:
        decode = round(ctok / max(0.05, wall - t_first), 1)
    if decode is not None:
        decode = round(float(decode), 1)
    return {"text": text, "status": status, "error": err, "chunks": chunks,
            "wall_sec": round(wall, 1),
            "first_byte_sec": round(t_byte, 2) if t_byte is not None else None,
            "ttft_sec": round(t_first, 2) if t_first is not None else None,
            "usage": usage, "timings": timings, "prompt_tokens": ptok,
            "completion_tokens": ctok, "cached_tokens": cached, "cache_n": cache_n,
            "prefill_tok_s": prefill, "decode_tok_s": decode}


def evaluate(text):
    """8 针命中 / 顺序 / 编造编号。空白（含换行）不影响命中，因为先拍平。"""
    flat = WS_RE.sub("", text or "")
    detail = []
    hits = 0
    for code in CODE_LIST:
        pos = flat.find(code)
        ok = pos >= 0
        hits += 1 if ok else 0
        detail.append({"needle": code, "hit": ok, "pos": pos})
    found = CODE_RE.findall(flat)
    extra = sorted(set(found) - LEGIT)
    present = [d["pos"] for d in detail if d["pos"] >= 0]
    order_ok = None
    if len(present) == len(detail):
        order_ok = present == sorted(present)
    return {"hits": hits, "total": len(CODE_LIST), "detail": detail,
            "hit_list": [d["needle"] for d in detail if d["hit"]],
            "n_extra": len(extra), "extra": extra[:20], "order_ok": order_ok}


def _fmt(v, spec="%s"):
    return "n/a" if v is None else (spec % v)


def run_seq(cfg):
    """同一进程内按序列连发；返回逐题记录 rows 与复现性判定 verdict。"""
    rows = [];
    total = len(cfg.seq_labels)
    for i, label in enumerate(cfg.seq_labels):
        path = fixture_path(cfg.fixtures, label)
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
        prompt = build_prompt(text, cfg.question_mode)
        print("[%d/%d] %s  fixture=%s chars=%d prompt_chars=%d"
              % (i + 1, total, label, os.path.basename(path), len(text), len(prompt)), flush=True)
        r = ask(cfg.base, cfg.model, prompt, max_tokens=cfg.max_tokens,
                timeout=cfg.timeout, api_key=cfg.api_key,
                reasoning_effort=getattr(cfg, "reasoning_effort", ""))
        ev = evaluate(r["text"]);
        print("       -> HTTP %s  hits=%d/%d  extra=%d  wall=%ss  ttft=%ss  prompt_tok=%s  cached=%s  prefill=%s  decode=%s"
              % (r["status"], ev["hits"], ev["total"], ev["n_extra"], r["wall_sec"], r["ttft_sec"],
                 r["prompt_tokens"], r["cached_tokens"], r.get("prefill_tok_s"), r["decode_tok_s"]), flush=True)
        if r["error"]:
            print("       !! error: " + str(r["error"])[:300], flush=True)
        row = {"seq": i + 1, "label": label, "fixture": os.path.basename(path),
               "fixture_chars": len(text), "prompt_chars": len(prompt),
               "status": r["status"], "error": r["error"],
               "hits": ev["hits"], "total": ev["total"], "hit_list": ev["hit_list"],
               "n_extra": ev["n_extra"], "extra_codes": ev["extra"], "order_ok": ev["order_ok"],
               "wall_sec": r["wall_sec"], "ttft_sec": r["ttft_sec"],
               "first_byte_sec": r["first_byte_sec"], "chunks": r["chunks"],
               "prompt_tokens": r["prompt_tokens"], "completion_tokens": r["completion_tokens"],
               "cached_tokens": r["cached_tokens"], "cache_n": r.get("cache_n"),
                "prefill_tok_s": r.get("prefill_tok_s"), "timings": r.get("timings"),
                "decode_tok_s": r["decode_tok_s"],
               "answer": (r["text"] or "")[:4000]}
        rows.append(row);
        if i < total - 1 and cfg.sleep > 0:
            print("       .. sleep %ss" % _fmt(cfg.sleep, "%g"), flush=True)
            time.sleep(cfg.sleep)
    return rows, compute_verdict(rows)


def compute_verdict(rows):
    """核心判据：同一个 209K 长度，第 2 次起命中若掉下来，就是「只可信一次」。"""
    idx = [i for i, r in enumerate(rows) if "209k" in r["label"]]
    first_hits = rows[idx[0]]["hits"] if idx else None
    later = [rows[i]["hits"] for i in idx[1:]]
    only_once = None
    if later:
        only_once = any(h < rows[idx[0]]["total"] for h in later)
    base30 = [r["hits"] for r in rows if r["label"] == "30k"]
    if only_once is True:
        concl = ("只可信一次：同一进程内第 2 次起的 209K 命中降到 %s（首次 %s/%d），"
                 "与现役 NInfer KVMem 的毛病一致" % (later, first_hits, rows[idx[0]]["total"]))
    elif only_once is False:
        concl = ("可重复：同一进程内 %d 次 209K 全部 %s/%d，pinned-RAM KV 没有 NInfer 那个坑"
                 % (len(idx), later, rows[idx[0]]["total"]))
    elif only_once is None:
        concl = "序列里只有 1 次 209K，无法判断可重复性（把 --seq 写成 209k,30k,209k 再看）"
    return {"n_209k_in_seq": len(idx), "first_209k_hits": first_hits,
            "later_209k_hits": later, "only_trust_once": only_once,
            "baseline_30k_hits": base30, "conclusion": concl}


def md_table(rows, verdict=None):
    out = ["| # | 题面 | hits/8 | 编造数 | wall s | prompt_tokens | prefill tok/s | ttft s | decode tok/s | 顺序 |",
           "|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        out.append("| %d | %s | %d/%d | %d | %s | %s | %s | %s | %s | %s |"
                   % (r["seq"], r["label"], r["hits"], r["total"], r["n_extra"],
                      _fmt(r["wall_sec"], "%.1f"), _fmt(r["prompt_tokens"]),
                      _fmt(r.get("prefill_tok_s"), "%.1f"),
                      _fmt(r["ttft_sec"], "%.2f"), _fmt(r["decode_tok_s"], "%.1f"),
                      "n/a" if r["order_ok"] is None else ("是" if r["order_ok"] else "否")))
    if verdict is not None:
        out.append("")
        out.append("**判定**：" + verdict["conclusion"])
    return "\n".join(out)


def save_output(cfg, rows, verdict):
    out = cfg.out
    d = os.path.dirname(os.path.abspath(out))
    if d:
        os.makedirs(d, exist_ok=True)
    payload = {"tool": "tools/llama_longctx_test.py",
               "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
               "base": cfg.base, "model": cfg.model, "seq": cfg.seq_labels,
               "question_mode": cfg.question_mode, "fixtures": cfg.fixtures,
               "rows": rows, "verdict": verdict}
    with open(out, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
    md = os.path.splitext(out)[0] + ".md"
    lines = ["# llama.cpp 长上下文可重复性实测（%s）" % payload["generated_at"], "",
             "- base: " + cfg.base, "- model: " + str(cfg.model),
             "- seq: " + ",".join(cfg.seq_labels),
             "- question_mode: " + cfg.question_mode, "- fixtures: " + cfg.fixtures, "",
             "## 结果", "", md_table(rows, verdict), "", "## 说明", "",
             "1. hits = 8 个暗号逐字命中数；编造数 = 答案里出现但不属于这 8 个的「动物名-数字」token 数。",
             "2. 每题之间 sleep " + _fmt(cfg.sleep, "%g") + " 秒，尽量避开前缀缓存。",
             "3. 判据：同一进程内 209K 的第 2 次起 hits < 8 即「只可信一次」。",
             "4. cached_tokens 若服务端不报则为 null（llama.cpp 默认不报）。", ""]
    with open(md, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return out, md


# ---------------------------------------------------------------- selftest

class _MockState:
    def __init__(self):
        self.lock = threading.Lock()
        self.counts = {}
        self.requests = []


def _mock_answer(state, prompt):
    """按 prompt 长度分档，按档内的第几次给不同答案（全对 / 部分对 / 编造）。"""
    n = len(prompt)
    if n > 200000:
        cls = "209k"
    elif n > 120000:
        cls = "100k"
    else:
        cls = "30k"
    with state.lock:
        k = state.counts.get(cls, 0) + 1
        state.counts[cls] = k
        state.requests.append((cls, n, k))
    if cls == "209k" and k == 1:
        ans = "关键记录的暗号依次是：" + "，".join(CODE_LIST) + "。以上共 8 条。"
    elif cls == "209k":
        ans = "关键记录的暗号依次是：" + "，".join(CODE_LIST[:3]) + "，粉色犀牛-1234，灰色企鹅-5678。"
    elif cls == "100k":
        ans = "关键记录的暗号依次是：" + "，".join(CODE_LIST[:5]) + "，橙色袋鼠-9012。"
    else:
        ans = "关键记录的暗号依次是：" + "，".join(CODE_LIST) + "。"
    return cls, k, ans


class _MockHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path.rstrip("/").endswith("/models"):
            body = json.dumps({"object": "list", "data": [{"id": "mock-llama", "object": "model"}]},
                              ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(404)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_POST(self):
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except Exception:
            n = 0
        raw = self.rfile.read(n) if n else b"{}"
        try:
            body = json.loads(raw.decode("utf-8"))
        except Exception:
            body = {}
        msgs = body.get("messages") or []
        prompt = (msgs[0] or {}).get("content") if msgs else ""
        if isinstance(prompt, list):       # 兼容 content 为分片列表的写法
            prompt = "".join(str(x.get("text", "")) for x in prompt if isinstance(x, dict))
        prompt = prompt or ""
        cls, k, ans = _mock_answer(self.server.state, prompt)
        ptok = int(round(len(prompt) / CHARS_PER_TOKEN))
        ctok = max(1, len(ans) // 2)
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()
        step = 24
        for i in range(0, len(ans), step):
            ev = {"id": "mock-1", "object": "chat.completion.chunk",
                  "choices": [{"index": 0, "delta": {"content": ans[i:i + step]}, "finish_reason": None}]}
            self.wfile.write(("data: " + json.dumps(ev, ensure_ascii=False) + "\n\n").encode("utf-8"))
            self.wfile.flush()
        last = {"id": "mock-1", "object": "chat.completion.chunk",
                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": ptok, "completion_tokens": ctok,
                          "total_tokens": ptok + ctok,
                          "prompt_tokens_details": {"cached_tokens": 0 if k == 1 else 4096}}}
        self.wfile.write(("data: " + json.dumps(last, ensure_ascii=False) + "\n\n").encode("utf-8"))
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()
        self.close_connection = True


def _make_fixture(dirpath, name, nchars):
    filler = "第0000条 日常记录：今日事项编号 0000，已完成核对，无异常，继续下一条。\n"
    reps = max(1, nchars // len(filler) + 1)
    text = (filler * reps)[:nchars]
    p = os.path.join(dirpath, name)
    with open(p, "w", encoding="utf-8") as f:
        f.write(text)
    return p


def selftest():
    """不联网、不碰卡：本地 mock 跑完整序列，断言统计与落盘都对。"""
    ok = [True]

    def check(name, cond, extra=""):
        print("[selftest] %-44s %s %s" % (name, "PASS" if cond else "FAIL", extra), flush=True)
        if not cond:
            ok[0] = False

    # --- 1. 纯函数层 ---
    good = "关键记录：" + "，".join(CODE_LIST)
    e = evaluate(good)
    check("evaluate 全对 -> 8/8 无编造 顺序对",
          e["hits"] == 8 and e["n_extra"] == 0 and e["order_ok"] is True, str(e["hits"]))
    e2 = evaluate("暗号：" + "，".join(CODE_LIST[:3]) + "，粉色犀牛-1234，灰色企鹅-5678")
    check("evaluate 部分对 -> 3/8 + 编造 2",
          e2["hits"] == 3 and e2["n_extra"] == 2, "%d/%d extra=%d" % (e2["hits"], e2["total"], e2["n_extra"]))
    e3 = evaluate("\n".join(CODE_LIST))     # 换行分隔也必须命中
    check("evaluate 换行分隔 -> 仍 8/8", e3["hits"] == 8, str(e3["hits"]))
    e4 = evaluate("，".join(reversed(CODE_LIST)))
    check("evaluate 逆序 -> 8/8 但顺序判否", e4["hits"] == 8 and e4["order_ok"] is False, str(e4["order_ok"]))

    # --- 2. mock 服务 + 完整序列 ---
    tmpdir = tempfile.mkdtemp(prefix="llama-longctx-selftest-")
    fixdir = os.path.join(tmpdir, "fixtures")
    os.makedirs(fixdir, exist_ok=True)
    _make_fixture(fixdir, "d209k-s20261030.txt", 250000)
    _make_fixture(fixdir, "d100k-s20261030.txt", 150000)
    _make_fixture(fixdir, "d30000.txt", 40000)
    state = _MockState()
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _MockHandler)
    httpd.state = state
    port = httpd.server_address[1]
    th = threading.Thread(target=httpd.serve_forever, daemon=True)
    th.start()
    out = os.path.join(tmpdir, "selftest.json")
    cfg = argparse.Namespace(base="http://127.0.0.1:%d/v1" % port, model="mock-llama",
                             fixtures=fixdir, out=out, max_tokens=64, timeout=30.0,
                             api_key="x", question_mode="append", sleep=0.0,
                             seq_labels=["209k", "30k", "209k", "100k", "209k"])
    try:
        rows, verdict = run_seq(cfg)
        jp, mp = save_output(cfg, rows, verdict)
    finally:
        httpd.shutdown()
        httpd.server_close()
    hits = [r["hits"] for r in rows]
    extras = [r["n_extra"] for r in rows]
    check("序列跑完 5 题且 HTTP 全 200", len(rows) == 5 and all(r["status"] == 200 for r in rows), str(len(rows)))
    check("hits 序列 = [8,8,3,5,3]", hits == [8, 8, 3, 5, 3], str(hits))
    check("编造数序列 = [0,0,2,1,2]", extras == [0, 0, 2, 1, 2], str(extras))
    check("首次 209K 顺序判对", rows[0]["order_ok"] is True, str(rows[0]["order_ok"]))
    check("30K 基线 8/8", rows[1]["hits"] == 8, str(rows[1]["hits"]))
    check("判定 only_trust_once = True", verdict["only_trust_once"] is True, str(verdict["only_trust_once"]))
    check("cached_tokens 解析（第 2 次 209K = 4096）", rows[2]["cached_tokens"] == 4096, str(rows[2]["cached_tokens"]))
    check("prompt_tokens 有值", all(r["prompt_tokens"] for r in rows), str(rows[0]["prompt_tokens"]))
    check("json 落盘可解析", os.path.isfile(jp) and len(json.load(open(jp, encoding="utf-8"))["rows"]) == 5, jp)
    md_text = open(mp, encoding="utf-8").read()
    nrows = sum(1 for ln in md_text.splitlines()
                if ln.startswith("| ") and not ln.startswith("| #") and not ln.startswith("|---"))
    check("markdown 表格 5 行数据", nrows == 5, str(nrows))
    check("mock 收到 5 个请求", len(state.requests) == 5, str(len(state.requests)))

    # --- 3. 真 fixture 目录映射（存在才检查） ---
    if os.path.isdir(DEFAULT_FIXTURES):
        miss = []
        for lab in ("209k", "100k", "100k-s777", "150k", "30k"):
            try:
                fixture_path(DEFAULT_FIXTURES, lab)
            except SystemExit:
                miss.append(lab)
        check("真 fixture 目录 5 个标签都能解析", not miss, ",".join(miss) or "ok")
    else:
        print("[selftest] 跳过真 fixture 目录检查（%s 不存在）" % DEFAULT_FIXTURES, flush=True)

    print("[selftest] SELFTEST %s" % ("PASS" if ok[0] else "FAIL"), flush=True)
    return ok[0]


def parse_args(argv=None):
    ap = argparse.ArgumentParser(
        description="llama.cpp 长上下文可重复性验证器（8 针 + 同进程序列）",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    ap.add_argument("--base", default=DEFAULT_BASE, help="OpenAI 兼容口，例如 http://127.0.0.1:8089/v1")
    ap.add_argument("--model", default=None, help="服务端 /v1/models 报的 id（llama.cpp 常是文件名/别名）")
    ap.add_argument("--fixtures", default=DEFAULT_FIXTURES, help="fixture 目录（d209k-s20261030.txt 等）")
    ap.add_argument("--out", default=None, help="结果 json（同名 .md 同时写）")
    ap.add_argument("--seq", default=DEFAULT_SEQ, help="同进程连发序列，逗号分隔")
    ap.add_argument("--timeout", type=float, default=3600.0, help="单请求超时秒（209K prefill 本机可能 10-20 分钟，默认 3600）")
    ap.add_argument("--max-tokens", type=int, default=512, help="每题 max_tokens")
    ap.add_argument("--sleep", type=float, default=20.0, help="两题之间 sleep 秒（避前缀缓存）")
    ap.add_argument("--api-key", default="x", help="Bearer token；llama 分叉 8089 要 401 校验，key 在 llama8g/bundle/artifacts/api_key.txt")
    ap.add_argument("--reasoning-effort", default="none",
                    help="请求体 reasoning_effort；llama.cpp 传 none 可把 reasoning_n 从 38 压到 2（默认 none）")
    ap.add_argument("--question-mode", default="append", choices=["append", "asis"],
                    help="append = doc + 提问（与 tools/matrix2.py 同口径）；asis = 只用文件内容")
    ap.add_argument("--selftest", action="store_true", help="本地 mock 自测，不联网不碰卡")
    return ap.parse_args(argv)


def main(argv=None):
    a = parse_args(argv)
    if a.selftest:
        return 0 if selftest() else 1
    if not a.model:
        print("真跑必须给 --model：先 curl " + a.base + "/models 看服务端报的 id", flush=True)
        return 2
    a.seq_labels = [s.strip() for s in a.seq.split(",") if s.strip()]
    if not a.out:
        a.out = os.path.join("logs", "llama-longctx-" + time.strftime("%Y%m%d-%H%M%S") + ".json")
    print("[llama-longctx] base=%s model=%s seq=%s sleep=%ss max_tokens=%d"
          % (a.base, a.model, ",".join(a.seq_labels), _fmt(a.sleep, "%g"), a.max_tokens), flush=True)
    t0 = time.time()
    rows, verdict = run_seq(a)
    jp, mp = save_output(a, rows, verdict)
    print("")
    print(md_table(rows, verdict))
    print("")
    print("[llama-longctx] json=%s" % jp)
    print("[llama-longctx] md=%s" % mp)
    print("[llama-longctx] 总耗时 %.1fs" % (time.time() - t0))
    return 0


if __name__ == "__main__":
    sys.exit(main())
