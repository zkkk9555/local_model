# -*- coding: utf-8 -*-
import json, time, urllib.request
BASE="http://127.0.0.1:8091"; KEY="sk-local"
r=urllib.request.Request(BASE+"/v1/models",headers={"Authorization":"Bearer "+KEY})
M=json.loads(urllib.request.urlopen(r,timeout=20).read().decode())["data"][0]["id"]
def run(tag,prompt,mt=340,temp=0.0):
    data={"model":M,"messages":[{"role":"user","content":prompt}],"temperature":temp,
          "max_tokens":mt,"reasoning_effort":"none","stream":True,"stream_options":{"include_usage":True}}
    req=urllib.request.Request(BASE+"/v1/chat/completions",data=json.dumps(data).encode(),
        headers={"Content-Type":"application/json","Authorization":"Bearer "+KEY})
    t0=time.time(); ttft=None; chunks=0; u=None
    for raw in urllib.request.urlopen(req,timeout=600):
        line=raw.decode("utf-8","replace").strip()
        if not line.startswith("data:"): continue
        d=line[5:].strip()
        if d=="[DONE]": break
        try: j=json.loads(d)
        except Exception: continue
        if j.get("usage"): u=j["usage"]
        c=((j.get("choices") or [{}])[0].get("delta") or {}).get("content") or ""
        if c:
            if ttft is None: ttft=time.time()-t0
            chunks+=1
    dt=time.time()-t0; ct=(u or {}).get("completion_tokens") or 0
    print("%-4s out=%d ttft=%.2fs total=%.2fs decode=%.1f tok/s steps=%.1f/s tok/step=%.1f" % (
        tag, ct, ttft or -1, dt, ct/(dt-(ttft or 0)) if dt>(ttft or 0) else 0,
        chunks/(dt-(ttft or 0)) if dt>(ttft or 0) else 0, ct/chunks if chunks else 0), flush=True)
run("计数", "从 1 数到 400，每个数字单独一行。")
run("代码", "用 Python 写一个带 argparse 的 JSONL 分组统计脚本，不要解释。")
run("散文", "用中文写一段约 300 字的随笔：深夜的机房。")
