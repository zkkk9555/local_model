import hashlib, json, os, sys, time, urllib.parse, urllib.request

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
HDR = {"User-Agent": UA, "Referer": "https://www.bilibili.com/",
       "Cookie": "buvid3=0A1B2C3D-4E5F-6789-ABCD-EF012345678912345infoc; b_nut=1700000000"}
OUT = "tmp/bili"
os.makedirs(OUT, exist_ok=True)

MIXIN = [46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35, 27, 43, 5, 49, 33, 9, 42, 19,
         29, 28, 14, 39, 12, 38, 41, 13, 37, 48, 7, 16, 24, 55, 40, 61, 26, 17, 0, 1, 60, 51, 30,
         4, 22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36, 20, 34, 44, 52]


def raw(path, params=None):
    url = path + ("?" + urllib.parse.urlencode(params) if params else "")
    req = urllib.request.Request(url, headers=HDR)
    for a in range(4):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read())
        except Exception as e:
            if a == 3:
                return {"code": -1, "message": str(e)}
            time.sleep(2 + 2 * a)


nav = raw("https://api.bilibili.com/x/web-interface/nav")
wbi = nav.get("data", {}).get("wbi_img", {})
img = os.path.basename(wbi.get("img_url", "")).split(".")[0]
sub = os.path.basename(wbi.get("sub_url", "")).split(".")[0]
raw_key = img + sub
mixin_key = "".join(raw_key[i] for i in MIXIN)[:32]
print("wbi keys:", img[:12], sub[:12], "mixin:", mixin_key[:12], "nav code", nav.get("code"))


def sign(params):
    p = dict(params)
    p["wts"] = int(time.time())
    items = sorted(p.items())
    clean = {k: "".join(ch for ch in str(v) if ch not in "!'()*") for k, v in items}
    q = urllib.parse.urlencode(clean)
    p["w_rid"] = hashlib.md5((q + mixin_key).encode()).hexdigest()
    return p


def main_replies(aid, mode=3, max_pages=8):
    out, offset = [], ""
    for _ in range(max_pages):
        ps = json.dumps({"offset": offset}, separators=(",", ":"))
        params = {"oid": aid, "type": 1, "mode": mode, "pagination_str": ps, "plat": 1,
                  "web_location": 1315875}
        d = raw("https://api.bilibili.com/x/v2/reply/wbi/main", sign(params))
        if d.get("code") != 0:
            print("  reply code", d.get("code"), d.get("message"))
            break
        data = d.get("data") or {}
        reps = data.get("replies") or []
        for c in reps:
            out.append({"like": c["like"], "text": c["content"]["message"], "uname": c["member"]["uname"],
                        "mid": c["member"]["mid"], "ctime": c["ctime"],
                        "replies": [{"text": r["content"]["message"], "like": r["like"],
                                     "uname": r["member"]["uname"]} for r in (c.get("replies") or [])]})
        cur = (data.get("cursor") or {})
        if cur.get("is_end") or not reps:
            break
        offset = (cur.get("pagination_reply") or {}).get("next_offset", "")
        if not offset:
            break
        time.sleep(1.2)
    return out


if __name__ == "__main__":
    vids = json.load(open(OUT + "/videos.json", encoding="utf-8"))
    only = sys.argv[1:] or [v["bv"] for v in vids]
    for v in vids:
        if v["bv"] not in only:
            continue
        cs = main_replies(v["aid"])
        json.dump(cs, open(OUT + "/comments_%s.json" % v["bv"], "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("%s -> %d comments (mode=3 hot)" % (v["bv"], len(cs)))
