import json, struct, sys, collections
p = r"models/Ternary-Bonsai-2-27B-ninfer-v3.ninfer"
with open(p,'rb') as f:
    head = f.read(32)
    assert head[:7] == b"NINFER\x00", head[:8]
    n = struct.unpack("<Q", head[8:16])[0]
    man = f.read(n)
d = json.loads(man)
objs = d["objects"]
def pref(name):
    return name.split("/")[0] + "/"
DROP = ("dflash2/", "vision/", "proposal/")
kept_bind = {k:v for k,v in d["bindings"].items() if not k.startswith(DROP)}
ids = set()
for ref in kept_bind.values():
    if isinstance(ref, dict):
        if isinstance(ref.get("object"), str): ids.add(ref["object"])
        for part in ref.get("parts") or []:
            if isinstance(part, dict) and isinstance(part.get("object"), str): ids.add(part["object"])
for o in objs:
    if o["id"].startswith("resource/text") or o["id"].startswith("auxiliary/"): ids.add(o["id"])
kept = [o for o in objs if o["id"] in ids]
def sz(o): return o.get("bytes") or o.get("size")
tot = sum(sz(o) for o in kept)
byfmt = collections.Counter()
for o in kept:
    byfmt[o.get("format","<res>")] += sz(o)
print("kept objects", len(kept), "bytes", tot, "=%.3f GiB" % (tot/1024**3))
for k,v in byfmt.most_common(): print("  ", k, v, "%.3f GiB" % (v/1024**3))
t2 = byfmt.get("t2_g128_fp16",0)
new = tot - t2 + int(t2*28/34)
print("after ptq1 recode: %d = %.3f GiB (save %.3f GiB)" % (new, new/1024**3, (tot-new)/1024**3))
# also text-only (drop mtp too)
DROP2 = DROP + ("mtp/",)
kb2 = {k:v for k,v in d["bindings"].items() if not k.startswith(DROP2)}
ids2 = set()
for ref in kb2.values():
    if isinstance(ref, dict):
        if isinstance(ref.get("object"), str): ids2.add(ref["object"])
        for part in ref.get("parts") or []:
            if isinstance(part, dict) and isinstance(part.get("object"), str): ids2.add(part["object"])
for o in objs:
    if o["id"].startswith("resource/text") or o["id"].startswith("auxiliary/"): ids2.add(o["id"])
kept2 = [o for o in objs if o["id"] in ids2]
tot2 = sum(sz(o) for o in kept2)
t2b = sum(sz(o) for o in kept2 if o.get("format")=="t2_g128_fp16")
new2 = tot2 - t2b + int(t2b*28/34)
print("text-only: %d = %.3f GiB ; after ptq1: %.3f GiB" % (tot2, tot2/1024**3, new2/1024**3))
print("components kept:", [c for c in d["components"] if c not in ("dflash2","vision")])
print("objects entry sample:", json.dumps(objs[0])[:300])
print("files:", json.dumps(d["files"])[:200])
print("top-level keys:", list(d.keys()))
print("meta:", json.dumps(d.get("metadata"))[:200])
