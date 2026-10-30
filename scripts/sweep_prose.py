
import json, os, signal, subprocess, sys, time, urllib.request
PORT="8091"; BASE="http://127.0.0.1:"+PORT
PROSE = ("写一篇四百字左右的散文，主题是深秋清晨的江南小镇。要求：有具体的街景、气味、声音细节，"
         "句式长短交错，不要分点，不要小标题，语言自然，像人写的。")
def kill():
    subprocess.run(["taskkill","/F","/IM","ninfer-serve-89.exe"], capture_output=True); time.sleep(2)
def start(extra, pool="32000"):
    env=dict(os.environ); env.update({
        "EXTRA":extra, "POOL":pool, "PORT":PORT, "PROFILE":"fast",
        "MODEL":r"C:\Project\local_model\models\bonsai2_27b_ternary_ptq1_native_mtp.ninfer",
    })
    log=open(r"C:\Project\local_model\logs\sweep.log","wb")
    p=subprocess.Popen(["bash",r"C:\Project\local_model\scripts\serve.sh"], env=env,
                       stdout=log, stderr=subprocess.STDOUT, creationflags=0x00000008)
    for _ in range(120):
        try:
            with urllib.request.urlopen(BASE+"/v1/models", timeout=3) as r:
                if r.status==200: return p
        except Exception: pass
        time.sleep(1)
    return None
def chat(prompt, max_tokens=300, session="sweep"):
    body=json.dumps({"model":"bonsai2-27b","messages":[{"role":"user","content":prompt}],
                     "max_tokens":max_tokens,"stream":True,"temperature":0.7,"top_p":0.9,"top_k":20}).encode()
    req=urllib.request.Request(BASE+"/v1/chat/completions", data=body, headers={"Content-Type":"application/json","x-session-affinity":session})
    t0=time.time(); ttft=None; n=0
    with urllib.request.urlopen(req, timeout=1800) as resp:
        for raw in resp:
            line=raw.strip()
            if not line.startswith(b"data:"): continue
            c=line[5:].strip()
            if c==b"[DONE]": break
            try: pl=json.loads(c)
            except Exception: continue
            ch=pl.get("choices") or []
            if not ch: continue
            piece=(ch[0].get("delta") or {}).get("content")
            if piece:
                if ttft is None: ttft=time.time()-t0
                n+=1
    el=time.time()-t0
    return ttft or 0, n, el
configs=[
 ("draft4 baseline", "--spec mtp --draft-tokens 4"),
 ("draft4 adaptive", "--spec mtp --draft-tokens 4 --adaptive-mtp"),
 ("draft3", "--spec mtp --draft-tokens 3"),
 ("draft5", "--spec mtp --draft-tokens 5"),
 ("draft4 ngram31", "--spec mtp --draft-tokens 4 --ngram-draft-tokens 31"),
 ("draft4 ngram0", "--spec mtp --draft-tokens 4 --ngram-draft-tokens 0"),
]
out=[]
for label, extra in configs:
    kill()
    p=start(extra)
    if p is None:
        print("START FAIL", label, flush=True); out.append((label,"START FAIL",0,0)); continue
    try:
        ttft,n,el=chat(PROSE)
        dec=(n-1)/(el-ttft) if el>ttft and n>1 else 0
        print("%-18s decode=%6.1f tok/s  n=%d ttft=%.2fs"%(label,dec,n,ttft), flush=True)
        out.append((label,"ok",dec,n))
    except Exception as e:
        print("ERR", label, repr(e)[:120], flush=True); out.append((label,"ERR",0,0))
    # capture accept rate from log
    try:
        txt=open(r"C:\Project\local_model\logs\sweep.log","rb").read().decode("utf-8","replace")
        for ln in txt.splitlines()[-40:]:
            if "mtp" in ln.lower() and "accept" in ln.lower(): print("   ", ln.strip()[:160], flush=True)
    except Exception: pass
kill()
print("DONE", out, flush=True)
