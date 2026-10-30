import hashlib, json, os, subprocess, sys, urllib.request
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
REPO = "zkkk9555/local_model"
TAG = "dlls-20261031"
env = dict(os.environ, HTTPS_PROXY="http://127.0.0.1:7897", HTTP_PROXY="http://127.0.0.1:7897")
out = subprocess.run(["gh", "release", "view", TAG, "--repo", REPO, "--json", "assets,isDraft,isPrerelease"],
                     capture_output=True, text=True, encoding="utf-8", env=env)
if out.returncode != 0:
    print("gh 失败:", out.stderr[:300]); sys.exit(1)
d = json.loads(out.stdout)
print("draft=%s prerelease=%s assets=%d" % (d["isDraft"], d["isPrerelease"], len(d["assets"])))
total = 0
for a in sorted(d["assets"], key=lambda x: x["name"]):
    total += a["size"]
    print("  %-20s %12d B  %s" % (a["name"], a["size"], a["state"]))
print("小计 %d B = %.1f MiB" % (total, total / 1048576))

EXPECT = {
    "avcodec-63.dll": "1ab43ac33e92aad9f29e82e6b4f57e06ff3537097d71908786d1388a6032ea45",
    "avformat-63.dll": "1082bdcb0fd3bb62205a2be123350f2f4fa67a1478bb0162989d65c1463d29ef",
    "avutil-61.dll": "aabe139afdf6c3277d490faddaac739c8ed616739bd9287cd53a7a56ba919022",
    "swscale-10.dll": "c10c48b8003ed5730b3ece95009a2db5c5e49c40c0a0b07c3b305ddc7fcc01f4",
    "swresample-7.dll": "dc8594e1c7cc627a2f2a1510c98a6b823a8dff95455684aafcfd3514dc12eb93",
    "libcurl-x64.dll": "d8bfa3e3ed29c29dc4db02afda0355f4a67990e93a3a4ecb089bf09a6071131d",
}
opener = urllib.request.build_opener(urllib.request.ProxyHandler({
    "http": "http://127.0.0.1:7897", "https": "http://127.0.0.1:7897"}))
os.makedirs("C:/Project/local_model/tmp/reltest", exist_ok=True)
print("\n匿名下载实测（不带 token，取小的两个）")
for name in ["swscale-10.dll", "SHA256SUMS.txt"]:
    url = "https://github.com/%s/releases/download/%s/%s" % (REPO, TAG, name)
    req = urllib.request.Request(url, headers={"User-Agent": "curl/8"})
    with opener.open(req, timeout=120) as r:
        data = r.read()
    h = hashlib.sha256(data).hexdigest()
    ok = "OK" if EXPECT.get(name, h) == h else "MISMATCH"
    print("  %-18s http=%s bytes=%d sha256=%s %s" % (name, r.status, len(data), h, ok))

url = "https://github.com/%s/releases/download/%s/avcodec-63.dll" % (REPO, TAG)
req = urllib.request.Request(url, headers={"User-Agent": "curl/8", "Range": "bytes=0-32767"})
with opener.open(req, timeout=180) as r:
    chunk = r.read()
print("  avcodec-63.dll 前 32KB: http=%s 拿到 %d B（%s）" % (r.status, len(chunk), "可匿名分段下载" if r.status == 206 else "整件返回" ))