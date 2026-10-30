#!/usr/bin/env python3
"""chat_gateway.py - OpenAI-compatible chat gateway that gives way BEFORE the engine does.

DSH -> :8081 (this) -> :8080 (engine, 8 GiB profile: pool 16,384 tokens, MTP on).

The engine prints "prompt exceeds the resident Device KV pool ... unverified" and can silently lose
the middle of a prompt when the prompt is bigger than the pool. This gateway therefore compresses
the REQUEST until it fits, and only refuses as a last resort:

  L0 pass-through   est <= pool_usable (default 16384 - 4096 = 12288)
  L1 trim history   drop the oldest messages (system + last user are never dropped)
  L2 compress       for an over-large user/tool message keep head 10% + tail 10% + the paragraph
                    chunks with the best character n-gram overlap against the last user message,
                    and insert a visible marker line
  L3 refuse         HTTP 200 with a normal assistant text explaining the limit

Hard rules: stream:true SSE is relayed verbatim; tools/tool_calls are never removed; the engine's
options are untouched. Standard library only.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

POOL_TOKENS = 16_384
POOL_USABLE = POOL_TOKENS - 4_096          # keep ~4K of headroom for the reply + template
ENGINE = "http://127.0.0.1:8080"
REFUSE_TEXT = ("[网关] 本轮上下文 {est} token 超过 8 GiB 档 KV 池（{pool}），"
               "已尝试压缩仍不可行，请缩短或分段。")


# ---------------------------------------------------------------- estimation

def est_tokens(text: str) -> int:
    """Conservative mixed Chinese/English estimate: ceil(bytes / 3.6)."""
    return max(1, int(math.ceil(len(text.encode("utf-8")) / 3.6)))


def _part_text(part) -> str:
    if isinstance(part, str):
        return part
    if isinstance(part, dict):
        if part.get("type") == "text":
            return str(part.get("text", ""))
        return json.dumps(part, ensure_ascii=False)
    return str(part)


def message_text(message: dict) -> str:
    content = message.get("content")
    if isinstance(content, list):
        return "\n".join(_part_text(part) for part in content)
    return "" if content is None else str(content)


def request_text(body: dict) -> str:
    parts = [message_text(m) for m in body.get("messages", [])]
    if body.get("tools"):
        parts.append(json.dumps(body["tools"], ensure_ascii=False))
    return "\n".join(parts)


def request_est(body: dict) -> int:
    return est_tokens(request_text(body))


# ---------------------------------------------------------------- L2 compression

def _chunks(text: str) -> list[str]:
    parts = [p for p in re.split(r"\n\s*\n", text) if p.strip()]
    return parts if parts else [text]


def _ngrams(text: str, n: int = 5, limit: int = 400) -> set[str]:
    clean = re.sub(r"\s+", "", text)[:4000]
    if len(clean) < n:
        return {clean} if clean else set()
    return {clean[i:i + n] for i in range(min(len(clean) - n + 1, limit))}


def _score(chunk: str, query: set[str]) -> float:
    if not query:
        return 0.0
    grams = _ngrams(chunk)
    if not grams:
        return 0.0
    return len(grams & query) / float(len(grams))


def compress_text(text: str, anchor: str, budget_tokens: int) -> tuple[str, int, int]:
    """Return (compressed_text, kept_chunks, dropped_chunks)."""
    chunks = _chunks(text)
    if len(chunks) <= 1:
        head = max(1, int(len(text) * 0.10))
        tail = max(1, int(len(text) * 0.10))
        kept = text[:head] + "\n[...]\n" + text[-tail:]
        marker = f"\n\n[网关压缩：原 {est_tokens(text)} token → 保留 {est_tokens(kept)} token]\n\n"
        return kept + marker, 1, 0
    query = _ngrams(anchor)
    scored = sorted(range(len(chunks)), key=lambda i: (-_score(chunks[i], query), i))
    keep_idx: list[int] = []
    head_n = max(1, len(chunks) // 10)
    tail_n = max(1, len(chunks) // 10)
    for idx in list(range(head_n)) + list(range(len(chunks) - tail_n, len(chunks))):
        if idx not in keep_idx:
            keep_idx.append(idx)
    for idx in scored:
        if idx in keep_idx:
            continue
        keep_idx.append(idx)
        trial = "\n\n".join(chunks[i] for i in sorted(keep_idx))
        marker = f"\n\n[网关压缩：原 {est_tokens(text)} token → 保留 {est_tokens(trial)} token]\n\n"
        if est_tokens(trial + marker) > budget_tokens:
            keep_idx.pop()
            break
    keep_idx.sort()
    kept_text = "\n\n".join(chunks[i] for i in keep_idx)
    marker = f"\n\n[网关压缩：原 {est_tokens(text)} token → 保留 {est_tokens(kept_text)} token]\n\n"
    return kept_text + marker, len(keep_idx), len(chunks) - len(keep_idx)


# ---------------------------------------------------------------- L2s segmented injection

def _split_for_map(text: str, cap_chars: int) -> list[str]:
    parts = [p for p in re.split(r"\n\s*\n", text) if p.strip()] or [text]
    chunks: list[str] = []
    cur = ""
    for part in parts:
        if cur and len(cur) + len(part) + 2 > cap_chars:
            chunks.append(cur)
            cur = part
        else:
            cur = part if not cur else cur + "\n\n" + part
    if cur:
        chunks.append(cur)
    out: list[str] = []
    for chunk in chunks:
        while len(chunk) > cap_chars:
            out.append(chunk[:cap_chars])
            chunk = chunk[cap_chars:]
        if chunk.strip():
            out.append(chunk)
    return out


def _map_call(chunk: str, question: str, engine: str, segment_label: str,
              timeout: float = 600.0) -> str:
    prompt = ("你是摘要器。以下是一份长材料的第 " + segment_label +
              " 段。只提取与下面问题相关的要点，最多 200 字，禁止编造。\n\n问题：" +
              question[:500] + "\n\n材料：" + chunk)
    payload = json.dumps({"model": "j27b", "stream": False, "temperature": 0,
                          "max_tokens": 256,
                          "messages": [{"role": "user", "content": prompt}]}).encode("utf-8")
    request = urllib.request.Request(engine + "/v1/chat/completions", data=payload,
                                     method="POST",
                                     headers={"Content-Type": "application/json"})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(request, timeout=timeout) as response:
        body = json.loads(response.read().decode("utf-8", "replace"))
    return body["choices"][0]["message"]["content"]


def segment_inject(working: list[dict], last_user: int, pool_usable: int,
                   engine: str, max_segments: int = 12):
    """L2s: summarise an over-large message in <=0.7*pool_usable segments, then inject the
    summaries back as ONE user message. Returns (messages, stats) or None when not applicable."""
    candidates = [(i, est_tokens(message_text(m))) for i, m in enumerate(working)
                  if m.get("role") in ("user", "tool", "assistant")]
    if not candidates:
        return None
    index, tokens = max(candidates, key=lambda item: item[1])
    target = max(256, int(0.7 * pool_usable))
    n = max(1, int(math.ceil(tokens / float(target))))
    if n > max_segments:
        return None
    chunks = _split_for_map(message_text(working[index]), int(target * 3.6))
    if len(chunks) < 2:
        return None
    question = message_text(working[last_user]) if last_user >= 0 else ""
    summaries: list[str] = []
    map_in = 0
    calls = 0
    for k, chunk in enumerate(chunks, start=1):
        try:
            summary = _map_call(chunk, question, engine, f"{k}/{len(chunks)}")
        except Exception:  # noqa: BLE001 - any map failure falls back to L2
            return None
        calls += 1
        map_in += est_tokens(chunk)
        summaries.append(f"[段 {k}/{len(chunks)} 摘要] {summary}")
    summary_text = "\n\n".join(summaries)
    summary_text += (f"\n\n[网关分段注入：原文 {tokens} token → {len(chunks)} 段摘要 "
                     f"{est_tokens(summary_text)} token]")
    rebuilt = [m for m in working if m.get("role") == "system"]
    rebuilt.append({"role": "user", "content": summary_text})
    if last_user >= 0 and last_user != index:
        rebuilt.append(working[last_user])
    stats = {"segments": len(chunks), "calls": calls, "map_in_tokens": map_in,
             "summary_tokens": est_tokens(summary_text)}
    return rebuilt, stats


# ---------------------------------------------------------------- ladder

def _cap_descriptions(node, cap: int):
    """Recursively truncate every 'description' string in a JSON schema tree."""
    if isinstance(node, dict):
        for key, value in list(node.items()):
            if key == "description" and isinstance(value, str) and len(value) > cap:
                node[key] = value[:cap] + "..."
            else:
                _cap_descriptions(value, cap)
    elif isinstance(node, list):
        for item in node:
            _cap_descriptions(item, cap)


def trim_tools(body: dict, budget: int) -> tuple[dict, int, int]:
    """Shorten tool descriptions (function + every nested parameter description) until the
    tool schema block fits `budget` tokens. Names/参数 structure are preserved."""
    tools = body.get("tools")
    if not tools:
        return body, 0, 0
    before = est_tokens(json.dumps(tools, ensure_ascii=False))
    if before <= budget:
        return body, before, before
    trimmed = tools
    after = before
    cap = 160
    while cap >= 8:
        out = []
        for t in tools:
            t2 = json.loads(json.dumps(t))
            _cap_descriptions(t2, cap)
            out.append(t2)
        trimmed = out
        after = est_tokens(json.dumps(trimmed, ensure_ascii=False))
        if after <= budget:
            break
        cap = cap // 2
    return {**body, "tools": trimmed}, before, after


def fit_request(body: dict, pool_usable: int) -> tuple[dict, dict]:
    """Apply L0..L3 and return (body_to_send_or_none, decision)."""
    decision = {"level": "L0", "est_before": request_est(body), "pool_usable": pool_usable}

    # Tool schemas share the same pool and cannot be "dropped" without breaking the agent,
    # so shorten their descriptions first, then fit MESSAGES ONLY against the remaining budget.
    # (Fitting with tools still attached would double-count them.)
    msg_reserve = min(3072, max(1024, pool_usable // 3))
    body, tools_before, tools_after = trim_tools(body, max(1024, pool_usable - msg_reserve))
    trimmed_tools = body.get("tools")
    if tools_before:
        decision["tools_est_before"] = tools_before
        decision["tools_est_after"] = tools_after
    if tools_after:
        decision["trimmed_tools"] = trimmed_tools
        body = {k: v for k, v in body.items() if k != "tools"}
        pool_usable = max(1024, pool_usable - tools_after)
        decision["msg_budget"] = pool_usable
        decision["est_before"] = request_est(body)
    if decision["est_before"] <= pool_usable:
        decision["est_after"] = decision["est_before"]
        return body, decision

    messages = list(body.get("messages", []))
    system_idx = [i for i, m in enumerate(messages) if m.get("role") == "system"]
    last_user = max((i for i, m in enumerate(messages) if m.get("role") == "user"), default=len(messages) - 1)

    # L1: drop the oldest non-system messages, keeping system + the last user message.
    working = list(messages)
    dropped = 0
    while request_est({**body, "messages": working}) > pool_usable:
        # Recompute the protected index every round: dropping shifts the list.
        last_user_now = max((i for i, m in enumerate(working) if m.get("role") == "user"),
                            default=-1)
        candidates = [i for i, m in enumerate(working)
                      if m.get("role") != "system" and i != last_user_now
                      and i != len(working) - 1]
        if not candidates:
            break
        working.pop(candidates[0])
        dropped += 1
    decision["dropped_msgs"] = dropped
    if dropped:
        decision["level"] = "L1"
    est = request_est({**body, "messages": working})
    if est <= pool_usable:
        decision["est_after"] = est
        return {**body, "messages": working}, decision

    # L2s: when ONE message dominates the prompt, summarise it in segments through the engine and
    # inject the summaries back. Inserted between L1 and L2 per the 2026-10-19 spec.
    biggest = max((est_tokens(message_text(m)) for m in working), default=0)
    last_user = max((i for i, m in enumerate(working) if m.get("role") == "user"), default=-1)
    if est > pool_usable and biggest > 0.4 * pool_usable:
        started = time.time()
        got = segment_inject(working, last_user, pool_usable, ENGINE)
        if got is None:
            print("[chatgw] L2s fallback=l2 (not applicable or a map call failed)")
        else:
            rebuilt, stats = got
            merged = {**body, "messages": rebuilt}
            est_s = request_est(merged)
            if est_s > pool_usable:
                idx_summary = max(range(len(rebuilt)),
                                  key=lambda i: est_tokens(message_text(rebuilt[i])))
                budget = max(256, pool_usable -
                             (est_s - est_tokens(message_text(rebuilt[idx_summary]))))
                compressed, kept_chunks, dropped_chunks = compress_text(
                    message_text(rebuilt[idx_summary]), "", budget)
                rebuilt[idx_summary] = {**rebuilt[idx_summary], "content": compressed}
                merged = {**body, "messages": rebuilt}
                est_s = request_est(merged)
                print(f"[chatgw] L2s post_compress kept={kept_chunks} "
                      f"dropped={dropped_chunks}")
            elapsed_ms = int((time.time() - started) * 1000)
            print(f"[chatgw] {time.strftime('%H:%M:%S')} L2s segments={stats['segments']} "
                  f"calls={stats['calls']} map_in_tokens={stats['map_in_tokens']} "
                  f"summary_tokens={stats['summary_tokens']} final_est={est_s} "
                  f"elapsed_ms={elapsed_ms}")
            if est_s <= pool_usable:
                decision.update({"level": "L2s", "est_after": est_s,
                                 "segments": stats["segments"], "calls": stats["calls"]})
                return merged, decision
            working = rebuilt
            est = est_s

    # L2: compress the largest user/tool message in place.
    last_user = max((i for i, m in enumerate(working) if m.get("role") == "user"),
                    default=len(working) - 1) if working else -1
    anchor = message_text(working[last_user]) if last_user >= 0 else ""
    idx_big = max(range(len(working)),
                  key=lambda i: est_tokens(message_text(working[i])) if working[i].get("role") in ("user", "tool") else -1,
                  default=-1)
    if idx_big >= 0:
        budget = max(256, pool_usable - (est - est_tokens(message_text(working[idx_big]))))
        compressed, kept_chunks, dropped_chunks = compress_text(
            message_text(working[idx_big]), anchor, budget)
        if working[idx_big].get("role") == "tool":
            working[idx_big] = {**working[idx_big], "content": compressed}
        else:
            working[idx_big] = {**working[idx_big], "content": compressed}
        decision.update({"level": "L2", "kept_chunks": kept_chunks,
                         "dropped_chunks": dropped_chunks})
    est2 = request_est({**body, "messages": working})
    # compress any remaining oversized messages one by one
    for i, message in enumerate(working):
        if est2 <= pool_usable:
            break
        if message.get("role") not in ("user", "tool"):
            continue
        if i == idx_big:
            continue
        budget = max(256, pool_usable // max(1, len(working)))
        compressed, kept, gone = compress_text(message_text(message), anchor, budget)
        working[i] = {**message, "content": compressed}
        decision["kept_chunks"] = decision.get("kept_chunks", 0) + kept
        decision["dropped_chunks"] = decision.get("dropped_chunks", 0) + gone
        decision["level"] = "L2"
        est2 = request_est({**body, "messages": working})

    # L2b: hard shrink -- repeatedly halve the largest user/tool/assistant message until it fits.
    shrinks = 0
    while est2 > pool_usable and shrinks < 40:
        cand = -1
        cand_len = 0
        for i, message in enumerate(working):
            if message.get("role") not in ("user", "tool", "assistant"):
                continue
            n = len(message_text(message))
            if n > cand_len:
                cand, cand_len = i, n
        if cand < 0 or cand_len <= 512:
            break
        raw_text = message_text(working[cand])
        keep = max(512, int(len(raw_text) * 0.5))
        head = keep * 2 // 3
        tail = keep - head
        kept_body = raw_text[:head] + "\n[...]\n" + raw_text[-tail:]
        shrunk = kept_body + (f"\n\n[网关压缩：原 {est_tokens(raw_text)} token -> 保留 "
                              f"{est_tokens(kept_body)} token（二次收缩）]\n\n")
        working[cand] = {**working[cand], "content": shrunk}
        decision["level"] = "L2"
        shrinks += 1
        est2 = request_est({**body, "messages": working})
    if shrinks:
        decision["shrinks"] = shrinks

    # L2c: if the system prompt alone is what blows the pool, shrink it too (head + marker).
    sys_shrinks = 0
    while est2 > pool_usable and sys_shrinks < 20:
        cand = -1
        cand_len = 0
        for i, message in enumerate(working):
            if message.get("role") != "system":
                continue
            n = len(message_text(message))
            if n > cand_len:
                cand, cand_len = i, n
        if cand < 0 or cand_len <= 2048:
            break
        raw_text = message_text(working[cand])
        keep = max(2048, int(len(raw_text) * 0.5))
        head = keep * 3 // 4
        tail = keep - head
        kept_body = raw_text[:head] + "\n[...]\n" + raw_text[-tail:]
        shrunk = kept_body + (f"\n\n[网关压缩：系统提示原 {est_tokens(raw_text)} token -> 保留 "
                              f"{est_tokens(kept_body)} token（系统提示二次收缩）]\n\n")
        working[cand] = {**working[cand], "content": shrunk}
        decision["level"] = "L2"
        sys_shrinks += 1
        est2 = request_est({**body, "messages": working})
    if sys_shrinks:
        decision["system_shrinks"] = sys_shrinks

    if est2 <= pool_usable:
        decision["est_after"] = est2
        return {**body, "messages": working}, decision

    # L3-pre: final shoehorn -- guarantee convergence by halving the largest payload, then
    # dropping the oldest droppable message, until the request fits or nothing is left.
    shoehorn = 0
    while est2 > pool_usable and shoehorn < 80:
        cand = -1
        cand_len = 0
        for i, message in enumerate(working):
            if message.get("role") not in ("user", "tool", "assistant"):
                continue
            n = len(message_text(message))
            if n > cand_len:
                cand, cand_len = i, n
        if cand >= 0 and cand_len > 256:
            raw_text = message_text(working[cand])
            keep = max(256, int(len(raw_text) * 0.5))
            head = keep // 2
            tail = keep - head
            kept_body = raw_text[:head] + "\n[...]\n" + raw_text[-tail:]
            working[cand] = {**working[cand], "content": kept_body}
        else:
            last_user_now = max((i for i, m in enumerate(working) if m.get("role") == "user"),
                                default=-1)
            candidates = [i for i, m in enumerate(working)
                          if m.get("role") != "system" and i != last_user_now
                          and i != len(working) - 1]
            if not candidates:
                break
            working.pop(candidates[0])
        shoehorn += 1
        est2 = request_est({**body, "messages": working})
    if shoehorn:
        decision["shoehorn"] = shoehorn
        if decision["level"] in ("L0", "L1"):
            decision["level"] = "L2"

    if est2 <= pool_usable:
        decision["est_after"] = est2
        return {**body, "messages": working}, decision

    # L2z: forced rebuild -- keep only the system prompt + the last user message and truncate
    # them until the request fits. This is the "never silently refuse a text request" floor.
    sys_msg = next((m for m in working if m.get("role") == "system"), None)
    user_msg = next((m for m in reversed(working) if m.get("role") == "user"), None)
    rebuilt = []
    if sys_msg is not None:
        rebuilt.append(dict(sys_msg))
    if user_msg is not None:
        rebuilt.append(dict(user_msg))
    if not rebuilt:
        rebuilt = [{"role": "user", "content": ""}]
    est_z = request_est({**body, "messages": rebuilt})
    trim_rounds = 0
    while est_z > pool_usable and trim_rounds < 60:
        cand = max(range(len(rebuilt)), key=lambda i: len(message_text(rebuilt[i])))
        raw_text = message_text(rebuilt[cand])
        if len(raw_text) <= 256:
            break
        keep = max(256, int(len(raw_text) * 0.5))
        head = keep // 2
        tail = keep - head
        rebuilt[cand] = {**rebuilt[cand],
                         "content": raw_text[:head] + "\n[...]\n" + raw_text[-tail:]}
        trim_rounds += 1
        est_z = request_est({**body, "messages": rebuilt})
    if est_z <= pool_usable:
        print(f"[chatgw] {time.strftime('%H:%M:%S')} L2z forced_rebuild rounds={trim_rounds} "
              f"est_after={est_z}")
        decision.update({"level": "L2", "est_after": est_z, "forced_rebuild": 1})
        return {**body, "messages": rebuilt}, decision

    # L3: refuse honestly, with a normal assistant text (HTTP 200).
    print(f"[chatgw] {time.strftime('%H:%M:%S')} L3 breakdown est={decision.get('est_before')} "
          f"tools_after={decision.get('tools_est_after')} msg_budget={decision.get('msg_budget')} "
          f"sizes={[est_tokens(message_text(m)) for m in working]}")
    decision.update({"level": "L3", "est_after": est2})
    return None, decision


# ---------------------------------------------------------------- loop guard
# 死循环 / 复读护栏（默认关闭；--loop-guard 才生效）
#
# 为什么放在网关而不是引擎：NInfer 没有 reasoning_loop_recovery 这类开关，引擎侧只有超大池与
# KV 分页，复读只能在这一层拦。分类与 Strata 的两档对齐：
#   (1) 逐字复读  同一个短单元背靠背重复（"1,2,3" 反复、整句反复、同一字符长串）
#   (2) 整段复读  最近窗口里，落在「出现过 >= K 次的固定长度段落」中的字符占比 >= coverage
# 判据常量取自 Strata 源码（LOOP_CHECK_EVERY=512 / LOOP_COVERAGE=0.25 /
# LOOP_HISTORY_WORDS=30000），但长度单位是字符而不是 token —— 网关里没有 tokenizer，
# 1 个中文字约 0.7 token、1 个英文词约 1.3 token，换算见 reports/网关护栏-死循环与复读.md。

LOOP_DEFAULTS = {
    "check_every": 480,      # 每新增多少字符判一次（对齐 Strata 的 512 token）
    "window": 2000,          # 判整段复读时看最近多少字符（对齐 2000 words）
    "coverage": 0.25,        # 窗口里重复段落占比阈值（对齐 LOOP_COVERAGE）
    "repeat_count": 3,       # 同一段落出现几次算复读
    "passage_len": 60,       # 段落长度（约 12 个英文词 / 20 个汉字）
    "history": 30000,        # 往回比对多远（对齐 LOOP_HISTORY_WORDS，成本封顶）
    "run_chars": 96,         # 同一字符连续多少次算逐字复读（覆盖 "。。。" / "-----" 之外的病态串）
    "run_unit_max": 24,      # 逐字复读的单元最长多少字符
    "repeat_times": 6,       # 逐字复读单元要背靠背重复几次
    "min_chars": 24,         # 太短的一串不判（避免把分隔线当复读）
}


def loop_cfg_from_args(args) -> dict:
    """从命令行取护栏配置并夹紧到合理区间（宁可漏判，也不要把正常长文判成复读）。"""
    return {
        "check_every": max(16, int(args.loop_check_every)),
        "window": max(200, int(args.loop_window)),
        "coverage": min(0.95, max(0.05, float(args.loop_coverage))),
        "repeat_count": max(2, int(args.loop_repeat_count)),
        "passage_len": max(16, int(args.loop_passage_len)),
        "history": max(2000, int(args.loop_history)),
        "run_chars": max(0, int(args.loop_run_chars)),
        "run_unit_max": max(4, int(args.loop_run_unit_max)),
        "repeat_times": max(3, int(args.loop_repeat_times)),
        "min_chars": max(8, int(args.loop_min_unit_chars)),
    }


def loop_cfg_line(cfg: dict) -> str:
    return "loop guard ON: " + " ".join("%s=%s" % (k, cfg[k]) for k in sorted(cfg))


def _event_boundary(buf: bytes) -> int:
    """返回「第一个完整 SSE 事件」结束处的下标（含分隔符）；还没完整事件返回 -1。

    两种分隔都认：纯 \\n\\n 与 \\r\\n\\r\\n。护栏只在这里切 —— 半个 JSON 永不发给客户端。
    """
    best = -1
    for sep in (b"\n\n", b"\r\n\r\n"):
        idx = buf.find(sep)
        if idx >= 0:
            end = idx + len(sep)
            if best < 0 or end < best:
                best = end
    return best


def _event_text(event: bytes) -> str:
    """从一个完整 SSE 事件里取「给人看的文本增量」；取不到就返回空串。"""
    try:
        raw = event.decode("utf-8", "ignore")
    except Exception:  # noqa: BLE001
        return ""
    out = []
    for line in raw.splitlines():
        line = line.strip()
        if not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if not payload or payload == "[DONE]":
            continue
        try:
            obj = json.loads(payload)
        except Exception:  # noqa: BLE001
            continue
        for choice in obj.get("choices") or []:
            delta = choice.get("delta") or {}
            for key in ("content", "reasoning_content"):
                piece = delta.get(key)
                if isinstance(piece, str) and piece:
                    out.append(piece)
    return "".join(out)


class LoopGuard:
    """判 (1) 逐字复读 + (2) 整段复读；只在字符数跨过 check_every 的整数倍时判一次。"""

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.text = ""
        self.checked = 0
        self.tripped = None
        # stride-1 的 unit 出现次数表：整段复读靠它判，段落长度与 unit 长度不必对齐
        self.units_seen = {}

    def feed(self, delta: str):
        if self.tripped or not delta:
            return self.tripped
        prev_len = len(self.text)
        self.text += delta
        self._scan_units(prev_len)
        if len(self.text) - self.checked < self.cfg["check_every"]:
            return None
        self.checked = len(self.text)
        self.tripped = self.check()
        return self.tripped

    def _scan_units(self, prev_len: int):
        """把「新出现的、长度为 passage_len 的 unit」计数进 units_seen（stride=1，逐字符）。"""
        unit = self.cfg["passage_len"]
        text = self.text
        start = max(unit, prev_len + 1)
        for p in range(start, len(text) + 1):
            key = text[p - unit:p]
            self.units_seen[key] = self.units_seen.get(key, 0) + 1
        # 表太大就按最近 history+window 重建一次，避免长回答把内存吃穿
        cap = self.cfg["history"] + self.cfg["window"] + 4 * unit
        if len(text) > 2 * cap and len(self.units_seen) > cap:
            tail = text[-cap:]
            self.units_seen = {}
            for p in range(unit, len(tail) + 1):
                key = tail[p - unit:p]
                self.units_seen[key] = self.units_seen.get(key, 0) + 1

    def check(self):
        verdict = self._check_verbatim()
        if verdict is None:
            verdict = self._check_passage()
        return verdict

    def _check_verbatim(self):
        cfg = self.cfg
        text = self.text
        times = cfg["repeat_times"]
        unit_max = cfg["run_unit_max"]
        need = cfg["min_chars"]
        tail = text[-(unit_max * times + unit_max):]
        for period in range(2, unit_max + 1):
            span = period * times
            if span < need or span > len(tail):
                continue
            unit = tail[-period:]
            if unit.strip() and unit * times == tail[-span:]:
                return {"kind": "verbatim", "unit": unit[:40], "unit_len": period,
                        "times": times, "at_chars": len(text)}
        run_chars = cfg["run_chars"]
        if run_chars and len(tail) >= run_chars:
            tail_run = tail[-run_chars:]
            if len(set(tail_run)) == 1 and not tail_run[0].isspace():
                return {"kind": "verbatim", "unit": tail_run[0], "unit_len": 1,
                        "times": run_chars, "at_chars": len(text)}
        return None

    def _check_passage(self):
        """整段复读：最近 window 字符按 passage_len 切块，块内容在整个已生成文本里出现 >= repeat_count
        次（stride-1 计数，所以段落长度不必是 unit 的整数倍），这些块占窗口的比例达到 coverage 就判复读。"""
        cfg = self.cfg
        text = self.text
        win, unit, k = cfg["window"], cfg["passage_len"], cfg["repeat_count"]
        # 输出还没到 window 长也要能判：窗口取 min(window, 已生成)，但不小于 4 个 unit
        if len(text) < 4 * unit:
            return None
        recent = text[-min(win, len(text)):]
        units = [recent[i:i + unit] for i in range(0, len(recent) - unit + 1, unit)]
        if not units:
            return None
        total = 0
        rep = 0
        for u in units:
            total += len(u)
            if self.units_seen.get(u, 0) >= k:
                rep += len(u)
        if not total:
            return None
        coverage = rep / float(total)
        if coverage >= cfg["coverage"]:
            return {"kind": "passage", "coverage": round(coverage, 3),
                    "repeat_chars": rep, "window_chars": total,
                    "unit": unit, "at_chars": len(text)}
        return None


def guard_notice(verdict: dict) -> str:
    if verdict.get("kind") == "verbatim":
        detail = "逐字复读：%r 连续重复 %d 次" % (verdict.get("unit"), verdict.get("times"))
    else:
        detail = "整段复读：最近 %d 字符里重复段落占 %.1f%%" % (
            verdict.get("window_chars", 0), 100.0 * verdict.get("coverage", 0.0))
    return ("\n\n[网关护栏] 检测到%s（位置约 %d 字符），已停止本轮生成。"
            "这是 tools/chat_gateway.py 的本地护栏（默认关闭，--loop-guard 开启），"
            "不是引擎报错；详见 reports/网关护栏-死循环与复读.md。\n") % (
                detail, verdict.get("at_chars", 0))


def guard_nonstream_payload(payload: dict, cfg: dict):
    """非流式也判一次：命中就把 finish_reason 改成 length 并追加提示文本（绝不静默 200 假装正常）。"""
    guard = LoopGuard(cfg)
    text = ""
    for choice in payload.get("choices") or []:
        content = (choice.get("message") or {}).get("content")
        if isinstance(content, str):
            text += content
    if not text:
        return payload, None
    guard.text = text
    verdict = guard.check()
    if not verdict:
        return payload, None
    notice = guard_notice(verdict)
    for choice in payload.get("choices") or []:
        msg = choice.get("message")
        if isinstance(msg, dict) and isinstance(msg.get("content"), str):
            msg["content"] = msg["content"] + notice
            choice["finish_reason"] = "length"
    payload["chatgw_loop_guard"] = verdict
    return payload, verdict


# ---------------------------------------------------------------- proxying

class Handler(BaseHTTPRequestHandler):
    server_version = "chatgw/0.1"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        return

    def _opener(self):
        return urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def _json(self, payload: dict, status: int = 200):
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _relay_stream(self, request: urllib.request.Request):
        response = self._opener().open(request, timeout=None)
        self.send_response(response.status)
        for key, value in response.headers.items():
            if key.lower() in ("transfer-encoding", "content-length", "connection"):
                continue
            self.send_header(key, value)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()
        while True:
            block = response.read(4096)
            if not block:
                break
            self.wfile.write(block)
            self.wfile.flush()
        self.close_connection = True

    def _emit_guard_stop(self, model: str, guard: "LoopGuard", verdict: dict):
        """护栏触发后的收尾：先给一段明确的提示文本，再给 finish_reason=length，最后 [DONE]。"""
        notice = guard_notice(verdict)
        now = int(time.time())
        head = {"id": "chatgw-loopguard", "object": "chat.completion.chunk", "created": now,
                "model": model,
                "choices": [{"index": 0, "delta": {"content": notice}, "finish_reason": None}],
                "chatgw_loop_guard": verdict}
        tail = {"id": "chatgw-loopguard", "object": "chat.completion.chunk", "created": now,
                "model": model,
                "choices": [{"index": 0, "delta": {}, "finish_reason": "length"}],
                "chatgw_loop_guard": verdict}
        self.wfile.write(("data: " + json.dumps(head, ensure_ascii=False) + "\n\n").encode("utf-8"))
        self.wfile.write(("data: " + json.dumps(tail, ensure_ascii=False) + "\n\n").encode("utf-8"))
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()
        print(f"[chatgw] {time.strftime('%H:%M:%S')} loop guard tripped kind={verdict.get('kind')} "
              f"at_chars={verdict.get('at_chars')} generated_chars={len(guard.text)} "
              f"-> finish_reason=length, upstream closed")

    def _relay_stream_guarded(self, request: urllib.request.Request, cfg: dict, model: str):
        """和 _relay_stream 一样逐字节转发，但按「完整 SSE 事件」切：事件先原样下发，再判护栏。"""
        response = self._opener().open(request, timeout=None)
        self.send_response(response.status)
        for key, value in response.headers.items():
            if key.lower() in ("transfer-encoding", "content-length", "connection"):
                continue
            self.send_header(key, value)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()
        guard = LoopGuard(cfg)
        buf = b""
        verdict = None
        while verdict is None:
            block = response.read(4096)
            if not block:
                break
            buf += block
            while True:
                cut = _event_boundary(buf)
                if cut < 0:
                    break
                event, buf = buf[:cut], buf[cut:]
                self.wfile.write(event)
                text = _event_text(event)
                if text:
                    verdict = guard.feed(text)
                    if verdict:
                        break
            self.wfile.flush()
        if verdict:
            try:
                response.close()   # 向引擎断连（引擎日志会记 HTTP 499 client disconnected）
            except Exception:  # noqa: BLE001
                pass
            self._emit_guard_stop(model, guard, verdict)
        self.close_connection = True

    def do_GET(self):  # noqa: N802
        # GUI clients enumerate models with GET /v1/models before they will talk
        # to a base URL; pass every GET straight to the engine so 8081 can be
        # used as a drop-in base URL.
        target = ENGINE + self.path
        request = urllib.request.Request(target, method="GET")
        try:
            response = self._opener().open(request, timeout=30)
            status = response.status
            ctype = response.headers.get("Content-Type", "application/json")
            data = response.read()
        except urllib.error.HTTPError as exc:
            status = exc.code
            ctype = exc.headers.get("Content-Type", "application/json")
            data = exc.read()
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length", "0") or 0)
        raw = self.rfile.read(length) if length else b""
        body = json.loads(raw.decode("utf-8")) if raw else {}
        pool_usable = getattr(self.server, "pool_usable", POOL_USABLE)

        if self.path.rstrip("/") not in ("/v1/chat/completions", "/chat/completions"):
            # pass everything else through untouched
            target = ENGINE + self.path
            request = urllib.request.Request(target, data=raw, method="POST",
                                             headers={"Content-Type": "application/json"})
            response = self._opener().open(request, timeout=None)
            data = response.read()
            self.send_response(response.status)
            self.send_header("Content-Type", response.headers.get("Content-Type", "application/json"))
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return

        fitted, decision = fit_request(body, pool_usable)
        est_before, est_after = decision["est_before"], decision.get("est_after", 0)
        ratio = (est_before / float(pool_usable)) if pool_usable else 0.0
        print(f"[chatgw] {__import__('time').strftime('%H:%M:%S')} est={est_before} pool_usable={pool_usable} ratio={ratio:.2f} "
              f"level={decision['level']} est_after={est_after}"
              + (f" segments={decision['segments']}" if decision.get("segments") else ""))
        if decision.get("dropped_msgs"):
            print(f"[chatgw] L1 dropped_msgs={decision['dropped_msgs']}")
        if decision["level"] == "L2":
            print(f"[chatgw] L2 kept_chunks={decision.get('kept_chunks')} "
                  f"dropped_chunks={decision.get('dropped_chunks')}")

        if fitted is None:
            print(f"[chatgw] L3 refuse est={est_before} est_after={est_after}")
            refuse_text = REFUSE_TEXT.format(
                est=est_before, pool=getattr(self.server, "pool_tokens", POOL_TOKENS))
            if body.get("stream"):
                chunk = {"id": "chatgw-refuse", "object": "chat.completion.chunk", "created": 0,
                         "model": body.get("model", "j27b"),
                         "choices": [{"index": 0, "delta": {"role": "assistant", "content": refuse_text},
                                      "finish_reason": None}]}
                done = {"id": "chatgw-refuse", "object": "chat.completion.chunk", "created": 0,
                        "model": body.get("model", "j27b"),
                        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                        "usage": {"prompt_tokens": est_before, "completion_tokens": 0,
                                  "total_tokens": est_before}}
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
            else:
                self._json({"id": "chatgw-refuse", "object": "chat.completion", "created": 0,
                            "model": body.get("model", "j27b"),
                            "choices": [{"index": 0, "finish_reason": "stop",
                                         "message": {"role": "assistant", "content": refuse_text}}],
                            "usage": {"prompt_tokens": est_before, "completion_tokens": 0,
                                      "total_tokens": est_before}})
            return

        payload_body = fitted
        if decision.get("trimmed_tools"):
            payload_body = {**fitted, "tools": decision["trimmed_tools"]}
        payload = json.dumps(payload_body, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(ENGINE + self.path, data=payload, method="POST",
                                         headers={"Content-Type": "application/json"})
        if fitted.get("stream"):
            try:
                loop_cfg = getattr(self.server, "loop_guard", None)
                if loop_cfg:
                    self._relay_stream_guarded(request, loop_cfg, payload_body.get("model", "j27b"))
                else:
                    self._relay_stream(request)
            except Exception as exc:  # noqa: BLE001
                print(f"[chatgw] stream error: {exc}")
                self._json({"error": {"message": str(exc)}}, 502)
            return
        try:
            response = self._opener().open(request, timeout=None)
            data = response.read()
            loop_cfg = getattr(self.server, "loop_guard", None)
            if loop_cfg:
                # 非流式也判一次：命中就改 finish_reason 并追加提示，不静默 200 假装正常
                try:
                    obj = json.loads(data.decode("utf-8"))
                    obj2, verdict = guard_nonstream_payload(obj, loop_cfg)
                    if verdict:
                        data = json.dumps(obj2, ensure_ascii=False).encode("utf-8")
                        print(f"[chatgw] {time.strftime('%H:%M:%S')} loop guard tripped (nonstream) "
                              f"kind={verdict.get('kind')} at_chars={verdict.get('at_chars')} "
                              f"-> finish_reason=length")
                except Exception as exc:  # noqa: BLE001
                    print(f"[chatgw] loop guard nonstream skipped: {exc}")
            self.send_response(response.status)
            self.send_header("Content-Type", response.headers.get("Content-Type", "application/json"))
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except Exception as exc:  # noqa: BLE001
            print(f"[chatgw] upstream error: {exc}")
            self._json({"error": {"message": str(exc)}}, 502)


# ---------------------------------------------------------------- selftest

def _big_message(tokens: int, seed: str) -> str:
    # ~3.6 chars per token by construction
    chars = int(tokens * 3.6)
    block = (seed + " ") * (chars // (len(seed) + 1) + 1)
    return block[:chars]


def _fake_sse(text: str, piece: int = 24) -> list:
    """把一段文本造成 SSE 事件流（每 piece 字符一个 delta 事件，末尾 data: [DONE]）。"""
    out = []
    for i in range(0, len(text), piece):
        chunk = {"id": "fake", "object": "chat.completion.chunk", "created": 0, "model": "fake",
                 "choices": [{"index": 0, "delta": {"content": text[i:i + piece]}, "finish_reason": None}]}
        out.append(("data: " + json.dumps(chunk, ensure_ascii=False) + "\n\n").encode("utf-8"))
    out.append(b"data: [DONE]\n\n")
    return out


def _simulate_guard(events: list, cfg: dict = None, read_size: int = 7):
    """照 _relay_stream_guarded 的读法跑一遍：按 read_size 字节切块（故意切碎事件），再按事件边界拼回。"""
    cfg = cfg or dict(LOOP_DEFAULTS)
    guard = LoopGuard(cfg)
    data = b"".join(events)
    buf = b""
    verdict = None
    for i in range(0, len(data), read_size):
        buf += data[i:i + read_size]
        while True:
            cut = _event_boundary(buf)
            if cut < 0:
                break
            event, buf = buf[:cut], buf[cut:]
            text = _event_text(event)
            if text and verdict is None:
                verdict = guard.feed(text)
        if verdict is not None:
            break
    if verdict is None:
        verdict = guard.check()
    return verdict, guard


def _varied_text(n: int, seed: str = "记录") -> str:
    """造一段没有复读的变长文本：每句都换编号与措辞（给 selftest 当负样本）。"""
    words = ["核对", "复核", "归档", "登记", "签收", "封存", "转运", "盘点"]
    bits = []
    total = 0
    i = 0
    while total < n:
        s = "%s%d：第%d项，%s编号%d，备注%s%d。" % (
            seed, i, i * 7 + 3, words[i % len(words)], 1000 + i * 13,
            words[(i * 3) % len(words)], i * 29)
        bits.append(s)
        total += len(s)
        i += 1
    return "".join(bits)[:n]


def selftest() -> int:
    pool_usable = POOL_USABLE
    ok = True
    # case 1: L0 pass-through
    body = {"model": "j27b", "stream": False,
            "messages": [{"role": "system", "content": "sys"},
                         {"role": "user", "content": _big_message(1000, "hello")}]}
    fitted, decision = fit_request(json.loads(json.dumps(body)), pool_usable)
    pass1 = decision["level"] == "L0" and fitted is not None and \
        request_est(fitted) == decision["est_before"]
    print(f"[chatgw] selftest 1 L0 pass: level={decision['level']} "
          f"est={decision['est_before']} -> {pass1}")

    # case 2: L1 trimming (many small messages + one big tail)
    messages = [{"role": "system", "content": "sys"}]
    for i in range(40):
        messages.append({"role": "user" if i % 2 == 0 else "assistant",
                         "content": _big_message(600, f"turn{i}")})
    messages.append({"role": "user", "content": _big_message(2000, "final question")})
    body2 = {"model": "j27b", "stream": False, "messages": messages,
             "tools": [{"type": "function", "function": {"name": "f", "parameters": {}}}]}
    fitted2, decision2 = fit_request(json.loads(json.dumps(body2)), pool_usable)
    pass2 = decision2["level"] in ("L1", "L2") and fitted2 is not None and \
        request_est(fitted2) <= pool_usable and bool(decision2.get("trimmed_tools")) and \
        len(fitted2["messages"]) < len(body2["messages"])
    print(f"[chatgw] selftest 2 L1 trim: level={decision2['level']} "
          f"dropped={decision2.get('dropped_msgs')} est_after={decision2.get('est_after')} "
          f"msgs={len(body2['messages'])}->{len(fitted2['messages']) if fitted2 else 0} -> {pass2}")

    # case 3: L2 compression (the huge message IS the last user turn, so L1 cannot drop it)
    body3 = {"model": "j27b", "stream": False,
             "messages": [{"role": "system", "content": "sys"},
                          {"role": "assistant", "content": "previous answer"},
                          {"role": "user", "content": _big_message(54_000, "paragraph text here")}]}
    fitted3, decision3 = fit_request(json.loads(json.dumps(body3)), pool_usable)
    pass3 = decision3["level"] == "L2" and fitted3 is not None and \
        request_est(fitted3) <= pool_usable and \
        decision3.get("kept_chunks", 0) > 0 and \
        "[网关压缩" in json.dumps(fitted3, ensure_ascii=False)
    print(f"[chatgw] selftest 3 L2 compress: level={decision3['level']} "
          f"kept={decision3.get('kept_chunks')} dropped={decision3.get('dropped_chunks')} "
          f"est_after={decision3.get('est_after')} -> {pass3}")

    # case 4: L2s segmented injection (map calls stubbed, no engine needed)
    global _map_call
    real_map = _map_call
    _map_call = lambda chunk, question, engine, label, timeout=600.0: ("摘要" + label)  # noqa: E731
    try:
        body4 = {"model": "j27b", "stream": False,
                 "messages": [{"role": "system", "content": "sys"},
                              {"role": "user", "content": "earlier short turn"},
                              {"role": "assistant", "content": "ok"},
                              {"role": "user", "content": _big_message(40_000, "material block")}]}
        fitted4, decision4 = fit_request(json.loads(json.dumps(body4)), pool_usable)
        pass4 = (decision4["level"] == "L2s" and decision4.get("segments", 0) >= 2
                 and fitted4 is not None and request_est(fitted4) <= pool_usable
                 and "[网关分段注入" in json.dumps(fitted4, ensure_ascii=False))
        print(f"[chatgw] selftest 4 L2s: level={decision4['level']} "
              f"segments={decision4.get('segments')} calls={decision4.get('calls')} "
              f"est_after={decision4.get('est_after')} -> {pass4}")
    finally:
        _map_call = real_map

    # ---- 护栏四条假 SSE 流（正常 / 逐字复读 / 整段复读 / 长文本无复读）----
    para = ("这一段是会被反复粘贴的段落，讲同一条流程：先核对编号，再登记数量，"
            "最后归档并复核；句子本身有变化，所以只能靠整段复读判据抓住。")
    loop_cases = [
        ("正常短文", _fake_sse(_varied_text(3000)), None),
        ("逐字复读", _fake_sse("1,2,3" * 300), "verbatim"),
        ("整段复读", _fake_sse(_varied_text(2400) + (para + "\n") * 12), "passage"),
        ("长文本无复读", _fake_sse(_varied_text(6000)), None),
    ]
    guard_ok = True
    for label, events, want in loop_cases:
        verdict, guard = _simulate_guard(events)
        kind = (verdict or {}).get("kind")
        good = (kind == want)
        extra = ""
        if verdict and verdict.get("kind") == "passage":
            extra = " coverage=%.3f" % verdict.get("coverage", 0.0)
        elif verdict and verdict.get("kind") == "verbatim":
            extra = " unit=%r x%d" % (verdict.get("unit"), verdict.get("times"))
        print("[chatgw] selftest loop %s: want=%s got=%s chars=%d%s -> %s"
              % (label, want or "None", kind or "None", len(guard.text), extra, good))
        guard_ok = guard_ok and good

    ok = pass1 and pass2 and pass3 and pass4 and guard_ok
    print("SELFTEST", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def main(argv: list[str]) -> int:
    global ENGINE
    parser = argparse.ArgumentParser(description="Chat gateway (L0-L3 gives way before the engine).")
    parser.add_argument("--port", type=int, default=8081)
    parser.add_argument("--engine", default=ENGINE)
    parser.add_argument("--pool-tokens", type=int, default=POOL_TOKENS)
    parser.add_argument("--headroom-tokens", type=int, default=4_096)
    parser.add_argument("--selftest", action="store_true")
    # ---- 死循环 / 复读护栏（默认关闭）----
    parser.add_argument("--loop-guard", action="store_true",
                        help="开启流式复读护栏（默认关闭；开启后命中会给 finish_reason=length 并断开引擎）")
    parser.add_argument("--loop-check-every", type=int, default=LOOP_DEFAULTS["check_every"],
                        help="每新增多少字符判一次（默认 %(default)s，对齐 Strata 的 512 token）")
    parser.add_argument("--loop-window", type=int, default=LOOP_DEFAULTS["window"],
                        help="判整段复读时看最近多少字符（默认 %(default)s，对齐 2000 words）")
    parser.add_argument("--loop-coverage", type=float, default=LOOP_DEFAULTS["coverage"],
                        help="窗口里重复段落占比阈值，0-1（默认 %(default)s，对齐 LOOP_COVERAGE）")
    parser.add_argument("--loop-repeat-count", type=int, default=LOOP_DEFAULTS["repeat_count"],
                        help="同一段落出现几次算复读（默认 %(default)s）")
    parser.add_argument("--loop-passage-len", type=int, default=LOOP_DEFAULTS["passage_len"],
                        help="段落长度（字符，默认 %(default)s ≈ 12 个英文词 / 20 个汉字）")
    parser.add_argument("--loop-history", type=int, default=LOOP_DEFAULTS["history"],
                        help="整段复读往回比对多少字符（默认 %(default)s，成本封顶）")
    parser.add_argument("--loop-run-chars", type=int, default=LOOP_DEFAULTS["run_chars"],
                        help="同一字符连续多少次算逐字复读（默认 %(default)s；0=不查这条）")
    parser.add_argument("--loop-run-unit-max", type=int, default=LOOP_DEFAULTS["run_unit_max"],
                        help="逐字复读单元最长多少字符（默认 %(default)s）")
    parser.add_argument("--loop-repeat-times", type=int, default=LOOP_DEFAULTS["repeat_times"],
                        help="逐字复读单元要背靠背重复几次（默认 %(default)s）")
    parser.add_argument("--loop-min-unit-chars", type=int, default=LOOP_DEFAULTS["min_chars"],
                        help="太短的一串不判，避免把分隔线当复读（默认 %(default)s）")
    args = parser.parse_args(argv)
    if args.selftest:
        return selftest()
    ENGINE = args.engine.rstrip("/")
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    server.pool_usable = args.pool_tokens - args.headroom_tokens
    server.pool_tokens = args.pool_tokens
    server.loop_guard = loop_cfg_from_args(args) if args.loop_guard else None
    print(f"[chatgw] listening on http://127.0.0.1:{args.port} -> {ENGINE} "
          f"pool={args.pool_tokens} usable={server.pool_usable}")
    if server.loop_guard:
        print("[chatgw] " + loop_cfg_line(server.loop_guard))
    else:
        print("[chatgw] loop guard OFF (默认关闭；要开加 --loop-guard)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("[chatgw] stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
