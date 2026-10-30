#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""DSH 本地模型 provider 验收脚本（openai-completions / pi-ai 请求形状）。

对任意 baseURL + model 都能跑，只发 HTTP，不启停 GPU 引擎。
每种模型输出一行 PASS/FAIL，不通过时给出是哪一项、原始错误体。

六项检查（1/2/3/5 决定 PASS）：
  1 models      GET  {base}/models 能列出该 model id（DSH 的模型发现走这条）
  2 nonstream   POST /chat/completions 非流式短问，HTTP 200 且 content 非空
  3 stream      POST 流式 + stream_options.include_usage：有 chunk、有 usage.prompt_tokens、
                记 TTFT 与 decode（DSH 主路径就是这个）
  4 tools       带 tools/tool_choice=auto/parallel_tool_calls，看模型是否真吐出 tool_call（仅记事实）
  5 unknown     带未声明字段（foo_unknown_field / cache_retention），HTTP 200 才算容错通过
  6 oversize    可选 --overpool-tokens N：塞 N token 的提示，看是 4xx 明确拒绝还是 200 静默吞下
                （NInfer 超池的老毛病就是 200 + 静默丢中段，所以「200」要记成 WARN）

用法：
  python tools/dsh_provider_test.py --base http://127.0.0.1:8081/v1 --model bonsai27b-ptq1-mtp-rk2v4-40k
  python tools/dsh_provider_test.py --base http://127.0.0.1:8092/v1 --model lim --api-key none
  python tools/dsh_provider_test.py --config            # 读 cordis.patch.yml，只测 127.0.0.1 的 provider
  python tools/dsh_provider_test.py --config --all      # 连远程 provider（wb / opencode-go）一起测
  python tools/dsh_provider_test.py --config --overpool-tokens 45000 --json tmp/dsh_accept.json

「缺席」不是 FAIL：一个 8 GB 卡同时只能跑一档引擎，DSH 配置里却写着 2 个 ninfer 条目。
  若引擎 /v1/models 里没有该 id，脚本标 ABSENT（缺席）并跳过后续 4 项请求 —— 它只说明
  「这一档现在没起」，不参与 PASS/FAIL 判定；只有某 provider 声明的 id 一个都不在列表里，
  才记 FAIL（那才是起错档或引擎没起）。

退出码：0 = 全部 PASS（缺席不算失败），1 = 有 FAIL，2 = 参数/配置错误。
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

DEFAULT_CONFIG = r"C:/Users/Administrator/.dsh/profiles/desktop/cordis.patch.yml"
TIMEOUT = 240
TOOLS = [{
    "type": "function",
    "function": {
        "name": "run_bash",
        "description": "在本机 shell 里跑一条命令并返回输出",
        "parameters": {
            "type": "object",
            "properties": {"command": {"type": "string", "description": "要执行的命令"}},
            "required": ["command"],
        },
    },
}]


# 缺席时给用户看清楚「要起哪一档」：与 scripts/serve2.sh 的 PROFILE 对应
PROFILE_HINTS = [
    ("-52k", "PROFILE=long（池 51,200、无投机，decode ~32 tok/s）"),
    ("-40k", "PROFILE=max 或 ctx40（池 40,000，decode 107.6/97 tok/s）"),
]


def profile_hint(model):
    for suf, h in PROFILE_HINTS:
        if suf in model:
            return h
    return "对应的 PROFILE"


class Client(object):
    def __init__(self, base, api_key, timeout=TIMEOUT):
        self.base = base.rstrip("/")
        self.key = api_key or "none"
        self.timeout = timeout

    def _req(self, path, body=None, stream=False):
        url = self.base + path
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(url, data=data, headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + self.key,
        })
        t0 = time.time()
        try:
            r = urllib.request.urlopen(req, timeout=self.timeout)
        except urllib.error.HTTPError as e:
            body_txt = ""
            try:
                body_txt = e.read().decode("utf-8", "replace")
            except Exception:
                pass
            return {"ok": False, "status": e.code, "err": body_txt[:500], "wall": time.time() - t0}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "status": None, "err": repr(e)[:300], "wall": time.time() - t0}

        if not stream:
            raw = r.read().decode("utf-8", "replace")
            out = {"ok": True, "status": r.status, "ctype": r.headers.get("Content-Type"),
                   "wall": time.time() - t0, "raw": raw}
            try:
                out["json"] = json.loads(raw)
            except Exception:
                pass
            return out

        chunks, text, usage, ttft, tool_calls = 0, "", None, None, []
        for line in r:
            s = line.decode("utf-8", "replace").strip()
            if not s.startswith("data:"):
                continue
            d = s[5:].strip()
            if d == "[DONE]":
                break
            try:
                j = json.loads(d)
            except Exception:
                continue
            chunks += 1
            if j.get("usage"):
                usage = j["usage"]
            ch = (j.get("choices") or [{}])[0]
            dl = ch.get("delta") or {}
            if dl.get("content"):
                if ttft is None:
                    ttft = time.time() - t0
                text += dl["content"]
            for tc in dl.get("tool_calls") or []:
                fn = tc.get("function") or {}
                if fn.get("name"):
                    tool_calls.append(fn["name"] + "(" + (fn.get("arguments") or "")[:60] + ")")
        return {"ok": True, "status": r.status, "ctype": r.headers.get("Content-Type"),
                "wall": time.time() - t0, "chunks": chunks, "ttft": ttft, "text": text,
                "usage": usage, "tool_calls": tool_calls}


def check_model(client, model, overpool_tokens=0):
    res = {"model": model, "base": client.base, "checks": {}, "detail": {}}
    chk = res["checks"]

    # 1 模型发现
    m = client._req("/models")
    listed, ids = None, []
    if m["ok"]:
        try:
            items = m["json"].get("data") or []
        except Exception:
            items = m["json"] if isinstance(m["json"], list) else []
        ids = [it.get("id") for it in items]
        listed = model in ids
        res["detail"]["models"] = [{"id": it.get("id"),
                                   "ctx": it.get("context_window") or it.get("max_model_len")} for it in items]
    chk["1_models"] = bool(listed)

    if not listed:
        # DSH 里声明了、但引擎当前这一档没在跑：不是故障（8 GB 卡同时只能跑一档）。
        # 不发后面 4 项请求（那只会白等 404），标 ABSENT —— 不许它把验收结论带成 FAIL。
        res["verdict"] = "ABSENT"
        res["detail"]["absent"] = {"served_ids": ids, "hint": profile_hint(model)}
        for k in ("2_nonstream", "3_stream", "4_tools", "5_unknown_fields"):
            chk[k] = None
        res["pass"] = False
        return res

    # 2 非流式
    r2 = client._req("/chat/completions", {
        "model": model,
        "messages": [{"role": "user", "content": "只回答一个数字：1+1 等于几"}],
        "max_tokens": 32, "temperature": 0, "stream": False,
    })
    txt2 = ""
    if r2.get("ok"):
        try:
            txt2 = ((r2["json"].get("choices") or [{}])[0].get("message") or {}).get("content") or ""
        except Exception:
            pass
    chk["2_nonstream"] = bool(r2.get("status") == 200 and txt2.strip())
    res["detail"]["nonstream"] = {"status": r2.get("status"), "wall": round(r2.get("wall", 0), 2),
                                  "text": txt2[:120], "err": (r2.get("err") or "")[:300]}

    # 3 流式 + include_usage
    r3 = client._req("/chat/completions", {
        "model": model,
        "messages": [{"role": "system", "content": "You are a coding agent in a Windows shell."},
                     {"role": "user", "content": "用一句话回答：3 乘以 7 是多少"}],
        "stream": True, "stream_options": {"include_usage": True},
        "temperature": 0, "max_tokens": 64,
    }, stream=True)
    u = (r3.get("usage") or {})
    chk["3_stream"] = bool(r3.get("status") == 200 and r3.get("chunks", 0) > 0 and u.get("prompt_tokens"))
    dec = None
    if u.get("completion_tokens") and r3.get("wall") and r3.get("ttft"):
        gen_s = r3["wall"] - r3["ttft"]
        # 太短的生成（<3 tok 或 <50 ms）算出来的「速度」是除法噪音，宁可报 n/a
        if u["completion_tokens"] >= 3 and gen_s >= 0.05:
            dec = (u["completion_tokens"] - 1) / gen_s
    res["detail"]["stream"] = {"status": r3.get("status"), "chunks": r3.get("chunks"),
                               "ttft": round(r3["ttft"], 2) if r3.get("ttft") else None,
                               "wall": round(r3.get("wall", 0), 2),
                               "usage": u, "content": (r3.get("text") or "")[:160],
                               "decode_tok_s": round(dec, 1) if dec else "n/a（样本太短）"}

    # 4 tools 透传
    r4 = client._req("/chat/completions", {
        "model": model,
        "messages": [{"role": "user", "content": "用 run_bash 跑 echo hi，只回工具调用，不要解释。"}],
        "tools": TOOLS, "tool_choice": "auto", "parallel_tool_calls": True,
        "max_tokens": 128, "temperature": 0, "stream": False,
    })
    tc = None
    if r4.get("ok"):
        try:
            tc = ((r4["json"].get("choices") or [{}])[0].get("message") or {}).get("tool_calls")
        except Exception:
            tc = None
    chk["4_tools"] = bool(r4.get("status") == 200)   # 透传不报错即算通过；是否真调用只记事实
    res["detail"]["tools"] = {"status": r4.get("status"), "tool_calls": bool(tc),
                              "err": (r4.get("err") or "")[:300]}

    # 5 未知字段容错
    r5 = client._req("/chat/completions", {
        "model": model, "messages": [{"role": "user", "content": "hi"}],
        "max_tokens": 4, "stream": False,
        "foo_unknown_field": 1, "cache_retention": "short",
    })
    chk["5_unknown_fields"] = bool(r5.get("status") == 200)
    res["detail"]["unknown_fields"] = {"status": r5.get("status"), "err": (r5.get("err") or "")[:300]}

    # 6 超长提示：4xx 明确拒绝 vs 200 静默
    if overpool_tokens:
        filler = "第%d条 日常记录：今日事项编号 %04d，已完成核对，无异常，继续下一条。\n"
        lines, i, chars = [], 0, 0
        target_chars = int(overpool_tokens * 1.4155)
        while chars < target_chars:
            s = filler % (i, i % 10000)
            lines.append(s)
            chars += len(s)
            i += 1
        doc = "".join(lines) + "\n请只回答：这份文档总共有多少条记录？"
        r6 = client._req("/chat/completions", {
            "model": model, "messages": [{"role": "user", "content": doc}],
            "max_tokens": 8, "temperature": 0, "stream": False,
        })
        st = r6.get("status")
        res["detail"]["overpool"] = {"status": st, "target_tokens": overpool_tokens,
                                     "err": (r6.get("err") or "")[:300],
                                     "verdict": ("4xx 明确拒绝" if isinstance(st, int) and 400 <= st < 500
                                                 else ("WARN 200 静默接受，需查引擎日志有无 exceeds 警告" if st == 200 else "连接失败"))}

    res["pass"] = all(chk[k] for k in ("1_models", "2_nonstream", "3_stream", "4_tools", "5_unknown_fields"))
    return res


def load_config_models(path, include_remote):
    try:
        import yaml
    except Exception:
        print("需要 pyyaml 才能读 --config；也可以用 --base/--model 手动指定")
        sys.exit(2)
    d = yaml.safe_load(open(path, encoding="utf-8"))
    targets = []
    for e in d or []:
        if e.get("id") != "llm-pi-ai":
            continue
        for key, prov in (e.get("config") or {}).get("providers", {}).items():
            base = prov.get("baseURL")
            if not base:
                continue
            local = "127.0.0.1" in base or "localhost" in base
            if not local and not include_remote:
                continue
            for m in prov.get("models") or []:
                targets.append({"provider": key, "displayName": prov.get("displayName"),
                                "base": base, "model": m.get("id"),
                                "declared_ctx": m.get("contextWindow"), "declared_max": m.get("maxTokens")})
    return targets


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=os.environ.get("DSH_TEST_BASE"))
    ap.add_argument("--model", default=os.environ.get("DSH_TEST_MODEL"))
    ap.add_argument("--api-key", default=os.environ.get("DSH_TEST_KEY", "none"))
    ap.add_argument("--config", nargs="?", const=DEFAULT_CONFIG, default=None, help="从 cordis.patch.yml 取 provider/model 列表")
    ap.add_argument("--all", action="store_true", help="--config 时连远程 provider 也测")
    ap.add_argument("--provider", default=None, help="只测某个 provider key（如 ninfer / strata）")
    ap.add_argument("--exclude-provider", default=None, help="逗号分隔，跳过这些 provider key（未起服的路线用）")
    ap.add_argument("--overpool-tokens", type=int, default=0, help="塞多少 token 的超长提示（0=跳过）")
    ap.add_argument("--weak-absent", action="store_true",
                    help="provider 声明的 id 全部缺席时只报 WARN 不记 FAIL（占位 provider，如还没定 id 的 strata）")
    ap.add_argument("--timeout", type=int, default=TIMEOUT)
    ap.add_argument("--json", default=None)
    a = ap.parse_args()

    if a.config:
        targets = load_config_models(a.config, a.all)
        if a.provider:
            targets = [t for t in targets if t["provider"] == a.provider]
        if a.exclude_provider:
            drop = {s.strip() for s in a.exclude_provider.split(",") if s.strip()}
            targets = [t for t in targets if t["provider"] not in drop]
        if not targets:
            print("配置里没有可测的本地 provider")
            return 2
    elif a.base and a.model:
        targets = [{"provider": "-", "displayName": "-", "base": a.base, "model": a.model,
                    "declared_ctx": None, "declared_max": None}]
    else:
        print(__doc__)
        return 2

    print("=" * 108)
    print("DSH provider 验收  %s   超长提示检查：%s" % (
        time.strftime("%Y-%m-%d %H:%M:%S"),
        ("%d tok" % a.overpool_tokens) if a.overpool_tokens else "跳过"))
    print("=" * 108)
    rows, out = [], []

    def verdict_of(r):
        if r.get("verdict") == "ABSENT":
            return "缺席"
        return "PASS" if r["pass"] else "FAIL"

    for t in targets:
        c = Client(t["base"], a.api_key, a.timeout)
        r = check_model(c, t["model"], a.overpool_tokens)
        r.update({"provider": t["provider"], "displayName": t["displayName"],
                  "declared_ctx": t["declared_ctx"], "declared_max": t["declared_max"]})
        out.append(r)
        d = r["detail"]
        st, ss = d.get("nonstream", {}), d.get("stream", {})
        print()
        if r.get("verdict") == "ABSENT":
            ad = d.get("absent") or {}
            print()
            print("[SKIP/缺席] %s  base=%s  model=%s" % (t["provider"], t["base"], t["model"]))
            print("   DSH 里声明了这个 id，但引擎当前只报：%s" % (ad.get("served_ids") or []))
            print("   -> 预期不存在，不算 FAIL。要它可用请按 %s 起服。" % ad.get("hint"))
            rows.append([t["provider"], t["model"], "缺席", None, None, None])
            continue
        print("[%s] %s  base=%s  model=%s" % (verdict_of(r), t["provider"], t["base"], t["model"]))
        print("   1 models        %s  列出=%s" % ("OK " if r["checks"]["1_models"] else "FAIL",
                                                [x["id"] for x in d.get("models") or []][:6]))
        print("   2 nonstream     %s  HTTP %s wall=%ss text=%r" % ("OK " if r["checks"]["2_nonstream"] else "FAIL",
                                                                  st.get("status"), st.get("wall"), (st.get("text") or "")[:60]))
        print("   3 stream        %s  HTTP %s chunks=%s ttft=%s wall=%s usage=%s decode=%s tok/s" % (
            "OK " if r["checks"]["3_stream"] else "FAIL", ss.get("status"), ss.get("chunks"),
            ss.get("ttft"), ss.get("wall"), {
                "p": (ss.get("usage") or {}).get("prompt_tokens"),
                "c": (ss.get("usage") or {}).get("completion_tokens")}, ss.get("decode_tok_s")))
        print("   4 tools         %s  真吐 tool_call=%s" % ("OK " if r["checks"]["4_tools"] else "FAIL",
                                                          d.get("tools", {}).get("tool_calls")))
        print("   5 unknown fields %s  HTTP %s" % ("OK " if r["checks"]["5_unknown_fields"] else "FAIL",
                                                   d.get("unknown_fields", {}).get("status")))
        if "overpool" in d:
            print("   6 oversize      %s  %s" % (d["overpool"]["verdict"], d["overpool"].get("err") or ""))
        fails = [k for k, v in r["checks"].items() if not v]
        if fails:
            for k in fails:
                key = k.split("_", 1)[1]
                err = (d.get(key) or {}).get("err") or ""
                if err:
                    print("   -> %s 原始错误：%s" % (k, err.replace("\n", " ")[:220]))
        rows.append([t["provider"], t["model"], verdict_of(r),
                     st.get("status"), ss.get("ttft"), ss.get("decode_tok_s")])

    # provider 级判据：声明的 id 一个都不在引擎列表里 = 起错档或引擎没起，那是真 FAIL
    byprov = {}
    for i, r in enumerate(rows):
        byprov.setdefault(r[0], []).append(i)
    for prov, idxs in byprov.items():
        if all(rows[i][2] == "缺席" for i in idxs):
            served_ids = []
            for r in out:
                if r.get("provider") == prov:
                    served_ids = ((r.get("detail") or {}).get("absent") or {}).get("served_ids") or []
                    break
            print()
            if a.weak_absent:
                print("!! %s 声明的 id 一个都不对：引擎在跑，但它报的 id 是 %s" % (prov, served_ids or "（/v1/models 空）"))
                print("   -> 记 WARN（--weak-absent，占位 provider 不判死）。改法：把配置里 %s.models[].id 改成引擎真实报告的那个 id，或先删掉这些条目。" % prov)
            else:
                for i in idxs:
                    rows[i][2] = "FAIL"
                print("!! %s 声明的 id 一个都不在引擎 /v1/models 里 -> 记 FAIL（起错档，或引擎没起）" % prov)

    print()
    print("-" * 108)
    print("%-14s %-34s %-6s %-6s %-9s %s" % ("provider", "model", "判定", "HTTP", "TTFT(s)", "decode"))
    for r in rows:
        label = "SKIP" if r[2] == "缺席" else r[2]
        print("%-14s %-34s %-6s %-6s %-9s %s" % (r[0], r[1], label, r[3], r[4], r[5]))
    npass = sum(1 for r in rows if r[2] == "PASS")
    nabs = sum(1 for r in rows if r[2] == "缺席")
    nfail = sum(1 for r in rows if r[2] == "FAIL")
    print("-" * 108)
    print("%d/%d PASS，%d SKIP/缺席（该档现在没起、按预期 404，不算失败），%d FAIL" % (npass, len(rows), nabs, nfail))
    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
        print("完整结果 -> %s" % a.json)
    return 0 if nfail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
