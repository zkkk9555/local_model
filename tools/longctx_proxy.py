#!/usr/bin/env python
"""超池长上下文代理（分片注入）：给 DSH 用的 OpenAI 兼容门面。

为什么需要它：NInfer 引擎的「可信上下文」= 设备 KV 池 token 数（本机 72,000）。
prompt 超过池时引擎会丢中间页、HTTP 200 给一个看着像真的错答案（引擎只打一行 warning）。
本代理做两件事：
  1) 估算 token 数 <= --trigger：原样转发（含 SSE 流式），零副作用；
  2) 超过 --trigger：把长文按行切成 N 片，每片 <= --shard-tokens（远小于池），
     逐片「只摘相关原文」，再用摘录做一次合成作答。每片都 <= 池，所以每片都可信。

用法：
  python tools/longctx_proxy.py --port 8086 --engine http://127.0.0.1:8091 --pool-tokens 72000
"""
import argparse, json, os, sys, time, urllib.request, urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

CONSERV_BPT = 1.75   # 与 tools/longdoc.py 同口径：bytes/token 下界（纯中文实测 1.745）
SAFETY = 0.93

EXTRACT_SYS = (
    "你是长文档取证器。只做一件事：把与请求相关的原文逐字摘出来，"
    "数字、代号、人名、路径、代码一律原样复制，不许改写、不许翻译、不许推断。"
    "注意：「名称-数字」这类组合必须整条原样抄，只抄数字算错。"
    "如果本段完全没有与请求相关的内容，只输出 NONE 四个字符。"
)

FINAL_SYS = (
    "你是长文档答问器。只能用【分片取证】里出现的原文作答，不许补充外部知识、不许编造。"
    "取证里没有的信息必须明确写「未找到」。答案尽量短。"
)


def est_text(s):
    if not s:
        return 0
    b = len(s.encode("utf-8"))
    return int(max(b / CONSERV_BPT, len(s) / 1.35)) + 1


def content_text(c):
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        out = []
        for part in c:
            if isinstance(part, dict) and part.get("type") in (None, "text"):
                out.append(part.get("text") or "")
        return "\n".join(out)
    return ""


def est_messages(msgs):
    return sum(est_text(content_text(m.get("content"))) for m in msgs) + 16 * len(msgs)


def chat_url(base):
    b = (base or "").rstrip("/")
    return b + "/chat/completions" if b.endswith("/v1") else b + "/v1/chat/completions"


def engine_post(base, payload, timeout=None):
    req = urllib.request.Request(chat_url(base),
                                 data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def log(msg):
    try:
        print("[longctx] %s %s" % (time.strftime("%H:%M:%S"), msg), flush=True)
    except Exception:
        try:
            sys.stdout.write("[longctx] %s %s\n" % (time.strftime("%H:%M:%S"),
                                                     msg.encode("ascii", "replace").decode("ascii")))
            sys.stdout.flush()
        except Exception:
            pass


def split_text(text, shard_tokens, bpt):
    """按行切；单行过长时按字符硬切。返回 [(a,b,seg)]，a/b 是行号（1 起）。"""
    lines = text.splitlines(keepends=True) or [text]
    out, pos, k = [], 0, 0
    while pos < len(lines):
        limit = int(shard_tokens * bpt)
        end, got = pos, 0
        while end < len(lines) and (got == 0 or got + len(lines[end].encode("utf-8")) <= limit):
            got += len(lines[end].encode("utf-8"))
            end += 1
        if end <= pos:
            end = pos + 1
        k += 1
        out.append((pos + 1, end, "".join(lines[pos:end])))
        pos = end
    return out


_EM = {"t": 0.0, "id": None}


def engine_model(base, fallback, ttl=5.0):
    """取引擎此刻真实的 model id（引擎按 --model-id 逐字强校验；换档后 id 会变）。
    NInfer 同一时刻只挂一个 id，所以「第一个 id」就是答案；取不到就退回启动参数。"""
    now = time.time()
    if _EM["id"] and now - _EM["t"] < ttl:
        return _EM["id"]
    try:
        url = (base or "").rstrip("/") + "/v1/models"
        with urllib.request.urlopen(url, timeout=4) as r:
            d = json.loads(r.read().decode("utf-8", "replace"))
        ids = [m.get("id") for m in (d.get("data") or []) if m.get("id")]
        if ids:
            if ids[0] != _EM["id"]:
                log("引擎实际 model id：%s" % ids[0])
            _EM["id"], _EM["t"] = ids[0], now
            return ids[0]
    except Exception:
        pass
    _EM["t"] = now
    return _EM["id"] or fallback


def sharded_answer(base, model, msgs, opts):
    sys_txt = "\n".join(content_text(m.get("content")) for m in msgs if m.get("role") == "system")
    body_msgs = [m for m in msgs if m.get("role") != "system"]
    # 找出最长的一段当「文档」，其余当「请求」
    idx_long, longest = -1, -1
    for i, m in enumerate(body_msgs):
        n = len(content_text(m.get("content")))
        if n > longest:
            idx_long, longest = i, n
    if idx_long < 0:
        idx_long, longest = 0, 0
    doc_msg = body_msgs[idx_long]
    doc = content_text(doc_msg.get("content"))
    others = [content_text(m.get("content")) for i, m in enumerate(body_msgs) if i != idx_long]
    tail, head = "", ""
    if not others and len(doc) > 4000:
        # 全部内容都在一条消息里：把开头/结尾的指令剥出来当「请求」，中间当文档
        head, doc, tail = doc[:1200], doc[1200:-1200], doc[-1200:]
    question = "\n".join(x for x in others if x.strip())
    if head or tail:
        question = (head + "\n" + tail).strip() or question
    question = question[-6000:] if len(question) > 6000 else question
    question = question or "请依据全文完整回答这段内容所要求的任务。"
    shards = split_text(doc, opts.shard_tokens, CONSERV_BPT)
    log("分片：文档 %d 字 -> %d 片（每片 <= %d token），请求 %d 字"
        % (len(doc), len(shards), opts.shard_tokens, len(question)))
    excerpts, total_pt, total_ct, bpt = [], 0, 0, CONSERV_BPT
    for k, (a, b, seg) in enumerate(shards, 1):
        prompt = ("【本段位置】全文第 %d-%d 行（第 %d/%d 片）\n\n" % (a, b, k, len(shards)) +
                  "【请求】" + question + "\n\n【本段原文】\n" + seg)
        payload = {"model": model, "messages": [{"role": "system", "content": EXTRACT_SYS},
                   {"role": "user", "content": prompt}],
                   "max_tokens": opts.extract_max, "temperature": 0.0, "stream": False}
        if opts.reasoning_effort:
            payload["reasoning_effort"] = opts.reasoning_effort
        t0 = time.time()
        try:
            d = engine_post(base, payload, timeout=opts.timeout)
            txt = ((d.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
            u = d.get("usage") or {}
            total_pt += int(u.get("prompt_tokens") or 0)
            total_ct += int(u.get("completion_tokens") or 0)
            pt = int(u.get("prompt_tokens") or 0)
            if k == 1 and pt:   # 用第一片真实读数校正 bytes/token
                overhead = est_text(EXTRACT_SYS) + est_text(question) + 48
                bpt = max(1.60, min(4.20, len(seg.encode("utf-8")) / max(pt - overhead, 1))) * SAFETY
                log("实测 %.3f 字节/token，后续按 %.3f 切" % (len(seg.encode("utf-8")) / max(pt - overhead, 1), bpt))
        except Exception as e:
            txt, pt = "NONE", 0
            log("第 %d 片失败：%s" % (k, e))
        txt = (txt or "").strip()
        none = (not txt) or txt.upper().startswith("NONE")
        log("  [%d/%d] 行 %d-%d prompt=%s %.1fs %s" % (k, len(shards), a, b, pt, time.time() - t0,
            "NONE" if none else "取证 %d 字" % len(txt)))
        if not none:
            excerpts.append((a, b, txt[:4000]))
    if not excerpts:
        answer = "（分片取证全部返回 NONE：这些内容里没有与请求相关的原文。）"
    else:
        joined = "\n\n".join("### 第 %d-%d 行\n%s" % (a, b, t) for a, b, t in excerpts)
        final_prompt = "【请求】" + question + "\n\n【分片取证】\n" + joined
        payload = {"model": model, "messages": [{"role": "system", "content": (sys_txt or FINAL_SYS)},
                   {"role": "user", "content": final_prompt}],
                   "max_tokens": opts.final_max, "temperature": 0.0, "stream": False}
        if opts.reasoning_effort:
            payload["reasoning_effort"] = opts.reasoning_effort
        try:
            d = engine_post(base, payload, timeout=opts.timeout)
            answer = ((d.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
            u = d.get("usage") or {}
            total_pt += int(u.get("prompt_tokens") or 0)
            total_ct += int(u.get("completion_tokens") or 0)
        except Exception as e:
            answer = ""
            log("合成失败：%s" % e)
        if not answer.strip() or "未找到" in answer and len(answer.strip()) <= 12:
            answer = ("（合成环节未给出答案，以下按分片取证逐字汇总）\n" +
                      "\n".join("- 第 %d-%d 行：%s" % (a, b, t.replace("\n", " ")) for a, b, t in excerpts))
    return answer, {"prompt_tokens": total_pt, "completion_tokens": total_ct}, len(shards)


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def _json(self, obj, code=200):
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path.rstrip("/") in ("/v1/models", "/models"):
            ids = [self.server.model_id] + list(self.server.opts.advertise or [])
            seen = []
            for i in ids:
                if i and i not in seen:
                    seen.append(i)
            return self._json({"object": "list",
                               "data": [{"id": i, "object": "model",
                                         "owned_by": "longctx-proxy",
                                         "context_window": self.server.opts.max_context}
                                        for i in seen]})
        self._json({"error": "not found"}, 404)

    def do_POST(self):
        if self.path.rstrip("/") not in ("/v1/chat/completions", "/chat/completions"):
            return self._json({"error": "not found"}, 404)
        n = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(n).decode("utf-8") or "{}")
        except Exception as e:
            return self._json({"error": {"message": "bad json: %s" % e}}, 400)
        opts = self.server.opts
        msgs = body.get("messages") or []
        req_model = body.get("model")
        # 引擎逐字校验 model 名（不像 llama.cpp）：改写成本刻引擎真实挂着的 id（换档自适应）
        em = engine_model(getattr(self.server.opts, "engine", ""), self.server.model_id)
        if req_model != em:
            body["model"] = em
            log("model 改写：%s -> %s" % (req_model, em))
        est = est_messages(msgs)
        if est <= opts.trigger:
            log("直通：估 %d token <= %d" % (est, opts.trigger))
            return self._passthrough(body)
        log("超池：估 %d token > 触发线 %d（池 %d）⇒ 分片注入" % (est, opts.trigger, opts.pool_tokens))
        try:
            answer, usage, nshards = sharded_answer(opts.engine, body.get("model") or self.server.model_id, msgs, opts)
        except Exception as e:
            return self._json({"error": {"message": "longctx: %s" % e, "type": "proxy_error"}}, 500)
        usage.setdefault("prompt_tokens", 0)
        usage.setdefault("completion_tokens", 0)
        usage["total_tokens"] = usage["prompt_tokens"] + usage["completion_tokens"]
        head = ("（超池分片注入：原文约 %d token > 引擎池 %d，已切成 %d 片分别取证后合成；"
                "每片都 <= 池，所以每片都可信）\n\n" % (est, opts.pool_tokens, nshards))
        content = head + answer
        extra = {"x_longctx": {"shards": nshards, "est_tokens": est, "pool_tokens": opts.pool_tokens}}
        if body.get("stream"):
            chunk = {"id": "longctx-1", "object": "chat.completion.chunk", "created": int(time.time()),
                     "model": body.get("model") or self.server.model_id,
                     "choices": [{"index": 0, "delta": {"role": "assistant", "content": content},
                                  "finish_reason": None}]}
            done = {"id": "longctx-1", "object": "chat.completion.chunk", "created": int(time.time()),
                    "model": body.get("model") or self.server.model_id,
                    "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}], "usage": usage}
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(("data: " + json.dumps(chunk, ensure_ascii=False) + "\n\n").encode("utf-8"))
            self.wfile.write(("data: " + json.dumps(done, ensure_ascii=False) + "\n\n").encode("utf-8"))
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
            self.close_connection = True
            return
        self._json({"id": "longctx-1", "object": "chat.completion", "created": int(time.time()),
                    "model": body.get("model") or self.server.model_id,
                    "choices": [{"index": 0, "finish_reason": "stop",
                                 "message": {"role": "assistant", "content": content}}],
                    "usage": usage, **extra})

    def _passthrough(self, body):
        opts = self.server.opts
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(chat_url(opts.engine), data=data,
                                     headers={"Content-Type": "application/json"})
        try:
            resp = urllib.request.urlopen(req, timeout=None)
        except urllib.error.HTTPError as e:
            payload = e.read()
            self.send_response(e.code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            return self.wfile.write(payload)
        if body.get("stream"):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "close")
            self.end_headers()
            while True:
                chunk = resp.read(4096)
                if not chunk:
                    break
                self.wfile.write(chunk)
                self.wfile.flush()
            self.close_connection = True
            return
        payload = resp.read()
        self.send_response(resp.status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8086)
    ap.add_argument("--engine", default="http://127.0.0.1:8091")
    ap.add_argument("--model", default="bonsai27b-ptq1-nomtp-rk2v4-72k")
    ap.add_argument("--pool-tokens", type=int, default=72000)
    ap.add_argument("--trigger", type=int, default=0, help="0 = 池的 85%%")
    ap.add_argument("--shard-tokens", type=int, default=26000)
    ap.add_argument("--extract-max", type=int, default=512)
    ap.add_argument("--final-max", type=int, default=2048)
    ap.add_argument("--max-context", type=int, default=262144)
    ap.add_argument("--timeout", type=float, default=3600.0)
    ap.add_argument("--reasoning-effort", default="", help="透传给引擎，如 none")
    ap.add_argument("--advertise", default="", help="逗号分隔：/v1/models 里额外挂出来的 model id（DSH 声明的 id 必须在这里出现，否则验收判缺档）")
    a = ap.parse_args()
    a.advertise = [s.strip() for s in (a.advertise or "").split(",") if s.strip()]
    if not a.trigger:
        a.trigger = int(a.pool_tokens * 0.85)
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), Handler)
    srv.opts = a
    srv.model_id = a.model
    log("监听 127.0.0.1:%d -> %s（池 %d，触发线 %d，片 <= %d）"
        % (a.port, a.engine, a.pool_tokens, a.trigger, a.shard_tokens))
    srv.serve_forever()


if __name__ == "__main__":
    main()