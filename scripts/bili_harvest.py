import json, os, sys, time, urllib.parse, urllib.request

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
HDR = {"User-Agent": UA, "Referer": "https://www.bilibili.com/"}
OUT = "tmp/bili"
os.makedirs(OUT, exist_ok=True)


def get(url):
    req = urllib.request.Request(url, headers=HDR)
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read())
        except Exception as e:
            if attempt == 3:
                return {"code": -1, "message": str(e)}
            time.sleep(2 + attempt * 2)


BVS = ["BV1dPeB6XE6d", "BV1hjhh6DEbn", "BV1Kzhq6cEy4", "BV1Z6h76oEuw", "BV1PkhU6oE2y",
       "BV1mvaa6nE2Q", "BV15VaD6EEQQ", "BV1h8WA6XEFQ", "BV1JVJd66Esq"]

videos = []
for bv in BVS:
    d = get("https://api.bilibili.com/x/web-interface/view?bvid=" + bv)
    if d.get("code") != 0:
        print("FAIL", bv, d.get("message"))
        continue
    v = d["data"]
    videos.append({"bv": bv, "aid": v["aid"], "cid": v["cid"], "title": v["title"],
                   "dur": v["duration"], "pub": v.get("pubdate"), "desc": v.get("desc", "")[:400],
                   "stat": {k: v["stat"].get(k) for k in ("view", "reply", "danmaku", "like")}})
    print("%s | %5ds | %6d views | %4d comments | %s" % (bv, v["duration"], v["stat"]["view"], v["stat"]["reply"], v["title"]))
    time.sleep(1.0)

json.dump(videos, open(OUT + "/videos.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)

for v in videos:
    allc = []
    for pn in range(1, 6):
        u = ("https://api.bilibili.com/x/v2/reply?type=1&oid=%d&sort=2&ps=20&pn=%d" % (v["aid"], pn))
        d = get(u)
        if d.get("code") != 0:
            break
        page = (d.get("data") or {}).get("replies") or []
        if not page:
            break
        for c in page:
            item = {"like": c["like"], "text": c["content"]["message"], "uname": c["member"]["uname"],
                    "mid": c["member"]["mid"], "ctime": c["ctime"],
                    "replies": [{"text": r["content"]["message"], "like": r["like"], "uname": r["member"]["uname"]}
                                for r in (c.get("replies") or [])]}
            allc.append(item)
        time.sleep(1.1)
    json.dump(allc, open(OUT + "/comments_%s.json" % v["bv"], "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("comments", v["bv"], len(allc))
    time.sleep(1.0)
