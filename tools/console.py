# -*- coding: utf-8 -*-
"""本机本地模型控制台（替代 Strata 那个面板）：127.0.0.1:8090
三件事：看状态（GPU/端口/进程/当前档位）、起停引擎、起停分片代理；外加「四条路各自什么能力/什么速度」的档案。
所有动作都是调仓库里已有的脚本（scripts/switch.sh / scripts/longctx.sh），不另造一套。
"""
import json, os, re, socket, subprocess, sys, threading, time, urllib.request
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG = os.path.join(ROOT, "logs")
KEYFILE = os.path.join(ROOT, "llama8g", "bundle", "artifacts", "api_key.txt")
PORT = int(os.environ.get("CONSOLE_PORT", "8090"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from console_page import PAGE  # noqa: E402  前端模板单独一个文件，改 UI 只动它
LOGS = ["serve-switch-ninfer.log", "serve-switch-long72.log", "serve-switch-long64.log",
        "serve-switch-long80.log", "llama8g-launch.log", "longctx-8086.log",
        "console-engine-40k.log", "console-engine-72k.log", "console-engine-llama.log"]

_CACHE = {"t": 0.0, "v": None}
_LOCK = threading.Lock()
_LAST = {"at": None, "label": "", "action": "", "log": "", "ok": None}


def run(cmd, timeout=8):
    try:
        p = subprocess.run(cmd, shell=True, capture_output=True, timeout=timeout)
        return (p.stdout or b"").decode("utf-8", "replace") + (p.stderr or b"").decode("utf-8", "replace")
    except Exception:
        return ""


def listening(port):
    s = socket.socket()
    s.settimeout(0.25)
    try:
        return s.connect_ex(("127.0.0.1", port)) == 0
    finally:
        s.close()


def get_json(url, timeout=3, headers=None):
    try:
        req = urllib.request.Request(url, headers=headers or {})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8", "replace"))
    except Exception:
        return None


def llama_key():
    try:
        return open(KEYFILE, encoding="utf-8").read().strip()
    except Exception:
        return ""


def gpu():
    out = run("nvidia-smi --query-gpu=memory.used,memory.total,utilization.gpu,temperature.gpu,power.draw "
              "--format=csv,noheader,nounits", timeout=6)
    line = out.strip().splitlines()[0] if out.strip() else ""
    parts = [x.strip() for x in line.split(",")]
    d = {"used": None, "total": None, "util": None, "temp": None, "power": None}
    try:
        d = {"used": int(float(parts[0])), "total": int(float(parts[1])), "util": int(float(parts[2])),
             "temp": int(float(parts[3])), "power": float(parts[4])}
    except Exception:
        pass
    return d


def procs():
    """引擎进程 + 上游 python 代理，带 RSS。"""
    out = run('powershell -NoProfile -Command "Get-CimInstance Win32_Process | '
              "Where-Object { $_.Name -in ('ninfer-serve-89.exe','llama-server.exe') -or "
              "($_.Name -eq 'python.exe' -and $_.CommandLine -like '*longctx_proxy*') } | "
              'Select-Object ProcessId,Name,WorkingSetSize | ConvertTo-Json -Compress"', timeout=12)
    rows = []
    try:
        data = json.loads(out.strip() or "[]")
        if isinstance(data, dict):
            data = [data]
        for p in data:
            rows.append({"pid": p.get("ProcessId"), "name": p.get("Name"),
                         "mib": round((p.get("WorkingSetSize") or 0) / 1048576)})
    except Exception:
        pass
    return rows


# ---------------------------------------------------------------- 档案（数字都来自本机实测，出处写在 src）
PROFILES = [
    {"key": "p40", "idx": "01", "name": "40K 日常档", "sub": "池 40,000 · MTP draft4",
     "tag": "日常主力", "headline": "问答、写代码、整理短中篇——首字最快、生成最快的那一档",
     "ctx": 38000, "ctxnote": "提示 ≤ 40,000 单遍可信（池内实测 8/8）",
     "speed": "41.5–107", "speedunit": "tok/s", "speednote": "散文 41.5 · 计数类 107",
     "ttft": "0.2–0.5 s", "ttftnote": "短提示；24K 提示首字 23 s（prefill ≈1,000 tok/s）",
     "vram": "≈7,533 MiB", "need": "要先起 40K 档引擎", "action": "engine:40k",
     "dsh": "bonsai27b-ptq1-mtp-rk2v4-40k", "provider": "NInfer KVMem",
     "yes": "随手问答、改代码、读几页文档；要快就用它",
     "avoid": "别把超长文档硬塞进来：提示超过池会静默漏证据",
     "cost": '换档约 15 秒；长文档硬塞会静默漏证据',
    "src": "reports/实测-40k档-20261030.md"},
    {"key": "p72", "idx": "02", "name": "72K 长文档档", "sub": "池 72,000 · 关 MTP 换显存",
     "tag": "长文档单遍", "headline": "一次贴进整篇长文、模型自己通读——关掉 MTP 才腾得出这块显存",
     "ctx": 80000, "ctxnote": "单遍实测 70,473 token 8/8；94K 掉 1 针",
     "speed": "≈31", "speedunit": "tok/s", "speednote": "关 MTP，比 40K 档慢一半",
     "ttft": "0.3 s", "ttftnote": "prefill ≈1,000 tok/s：24K 提示约 23 s",
     "vram": "≈7,301 MiB", "need": "要先起 72K 档引擎", "action": "engine:72k",
     "dsh": "bonsai27b-ptq1-nomtp-rk2v4-72k", "provider": "NInfer KVMem",
     "yes": "几万字的报告/论文/日志，要它一次读完再答",
     "avoid": "要极快首字请回 01；超过 ≈70K 单遍就开始漏针",
     "cost": '生成慢一半（31 vs 107 tok/s）；>94K 单遍开始漏针',
    "src": "reports/上下文-150K-200K-实测-20261030.md §3"},
    {"key": "llama", "idx": "03", "name": "llama.cpp 262K", "sub": "真 262,144 窗口",
     "tag": "通读全文", "headline": "窗口最大、能真读 15 万字：慢，但一次的答案就是全文的答案",
     "ctx": 262144, "ctxnote": "150K 单遍实测 8/8（另一套引擎，不是 NInfer）",
     "speed": "12.6", "speedunit": "tok/s", "speednote": "长上下文；短问 33–57",
     "ttft": "268 s", "ttftnote": "@150K；prefill 582.9 tok/s",
     "vram": "≈7,798 MiB", "need": "要先起 llama-server（要停掉 NInfer）", "action": "engine:llama",
     "dsh": "Ternary-Bonsai-2-27B-PTQ1_0-mtp-262k", "provider": "Bonsai · llama.cpp 262K",
     "yes": "一份 10–15 万字的材料，要模型自己通读后做全局归纳",
     "avoid": "别拿它当日常：150K 首读要 4.5 分钟，生成只有 12 字/秒",
     "cost": '要先停 NInfer；150K 首读 4.5 分钟、生成 12.6 tok/s',
    "src": "reports/上下文-150K-200K-实测-20261030.md §6.1"},
    {"key": "shard", "idx": "04", "name": "超池分片 150–200K", "sub": "72K 档 + 8086 代理切段取证",
     "tag": "超长文但要快", "headline": "把 15–20 万字的文档切成几段分别读、再合成——比 03 快 5–10 倍",
     "ctx": 200000, "ctxnote": "每片 ≤26K 都落在池内，所以每片都可信",
     "speed": "150K 170 s · 200K 211 s", "speedunit": "整篇", "speednote": "是整篇耗时，不是 tok/s",
     "ttft": "首段约 26 s", "ttftnote": "之后每段 20–26 s",
     "vram": "≈7,301 MiB", "need": "要 72K 档引擎 + 8086 代理同时在线", "action": "proxy:start",
     "dsh": "bonsai27b-ptq1-nomtp-rk2v4-shard200k", "provider": "NInfer KVMem · 超池分片",
     "yes": "超长材料只要「里面写了什么」的答案，越快越好",
     "avoid": "它不是单遍注意力：跨段推理/逐字引用不如 03 靠得住",
     "cost": '每段约 26 秒、整篇 2–4 分钟；跨段推理不如 03',
    "src": "reports/上下文-150K-200K-实测-20261030.md §5"},
]


def engine_key(model):
    if not model:
        return None
    if "40k" in model:
        return "p40"
    if "72k" in model:
        return "p72"
    return None


def collect():
    g = gpu()
    e = {"port": 8091, "open": listening(8091), "model": None, "models": []}
    j = get_json("http://127.0.0.1:8091/v1/models")
    if j:
        e["models"] = [m.get("id") for m in (j.get("data") or [])]
        e["model"] = e["models"][0] if e["models"] else None
    gw = {"port": 8081, "open": listening(8081)}
    pl = {"port": 8086, "open": listening(8086), "models": []}
    jp = get_json("http://127.0.0.1:8086/v1/models")
    if jp:
        pl["models"] = [m.get("id") for m in (jp.get("data") or [])]
    lm = {"port": 8089, "open": listening(8089), "model": None}
    jl = get_json("http://127.0.0.1:8089/v1/models", headers={"Authorization": "Bearer " + llama_key()})
    if jl:
        ids = [m.get("id") for m in (jl.get("data") or [])]
        lm["model"] = ids[0] if ids else None
    elif lm["open"]:
        lm["model"] = "(在听，需 key 才能读 id)"

    ek = engine_key(e["model"])
    running = None
    if ek:
        running = ek
    elif lm["open"]:
        running = "llama"

    pro = []
    for p in PROFILES:
        q = dict(p)
        if p["key"] == "llama":
            q["state"] = "ready" if lm["open"] else "switch"
            q["why"] = "" if lm["open"] else ("要停掉 NInfer 才能腾出显存" if e["open"] else "llama-server 没起，点一下会起")
        elif p["key"] == "shard":
            if ek == "p72" and pl["open"]:
                q["state"], q["why"] = "ready", ""
            elif ek == "p72":
                q["state"], q["why"] = "half", "引擎对了，分片代理 8086 没起"
            else:
                q["state"], q["why"] = "switch", "要 72K 档引擎 + 8086 代理"
        else:
            q["state"] = "ready" if ek == p["key"] else "switch"
            q["why"] = "" if ek == p["key"] else ("引擎当前是别的档，点一下就换" if e["open"] or lm["open"] else "引擎没起，点一下就起")
        pro.append(q)

    return {"ts": int(time.time()), "gpu": g, "engine": e, "gateway": gw, "proxy": pl, "llama": lm,
            "procs": procs(), "running": running, "profiles": pro, "logs": LOGS, "last": _LAST}


def status_cached(force=False):
    with _LOCK:
        if force or _CACHE["v"] is None or time.time() - _CACHE["t"] > 1.5:
            _CACHE["v"] = collect()
            _CACHE["t"] = time.time()
        return _CACHE["v"]


# 值里只写「bash 之后的参数」，spawn_bash 会自己补 bash 可执行文件（别再写 bash，否则变成 bash bash ...）
ACTIONS = {
    "engine:40k":   ("切到 40K 日常档", ["scripts/switch.sh", "ninfer"]),
    "engine:72k":   ("切到 72K 长文档档", ["scripts/switch.sh", "long72"]),
    "engine:llama": ("起 llama.cpp 262K", ["scripts/switch.sh", "llama"]),
    "proxy:start":  ("起分片代理 8086", ["scripts/longctx.sh", "start"]),
    "proxy:stop":   ("停分片代理 8086", ["scripts/longctx.sh", "stop"]),
}
KILLS = {
    "engine:stop": ["taskkill /F /IM ninfer-serve-89.exe", "taskkill /F /IM llama-server.exe"],
}


def bash_exe():
    import shutil
    for c in (shutil.which("bash"), r"C:\\Program Files\\Git\\bin\\bash.exe", r"C:\\Program Files\\Git\\usr\\bin\\bash.exe"):
        if c and os.path.exists(c):
            return c
    return "bash"


def spawn_bash(argv, logname):
    path = os.path.join(LOG, logname)
    f = open(path, "ab")
    flags = 0
    if os.name == "nt":
        flags = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    subprocess.Popen([bash_exe()] + argv, cwd=ROOT, stdout=f, stderr=subprocess.STDOUT,
                     stdin=subprocess.DEVNULL, creationflags=flags, close_fds=True)
    return path


def _mark(label, action, log="", ok=None):
    _LAST.update({"at": int(time.time()), "label": label, "action": action, "log": log, "ok": ok})


class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "localmodel-console"

    def log_message(self, fmt, *a):
        pass

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        p = self.path.split("?")[0].rstrip("/") or "/"
        if p == "/":
            return self._send(200, PAGE, "text/html; charset=utf-8")
        if p == "/api/status":
            return self._send(200, json.dumps(status_cached(True), ensure_ascii=False))
        if p == "/api/log":
            q = self.path.split("?", 1)[1] if "?" in self.path else ""
            name = q.replace("f=", "")
            if name not in LOGS:
                return self._send(400, json.dumps({"error": "bad log"}, ensure_ascii=False))
            path = os.path.join(LOG, name)
            try:
                sz = os.path.getsize(path)
                with open(path, "rb") as f:
                    f.seek(max(0, sz - 6000))
                    txt = f.read().decode("utf-8", "replace")
            except Exception as e:
                txt = "(读不到 %s: %s)" % (name, e)
            return self._send(200, json.dumps({"name": name, "tail": txt}, ensure_ascii=False))
        return self._send(404, json.dumps({"error": "not found"}, ensure_ascii=False))

    def do_POST(self):
        p = self.path.split("?")[0].rstrip("/")
        n = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(n).decode("utf-8") or "{}")
        except Exception:
            body = {}
        if p != "/api/action":
            return self._send(404, json.dumps({"error": "not found"}, ensure_ascii=False))
        act = body.get("action") or ""
        if act in KILLS:
            for c in KILLS[act]:
                subprocess.run(c, shell=True, capture_output=True)
            _CACHE["t"] = 0
            _mark("停掉引擎", act)
            return self._send(200, json.dumps({"ok": True, "action": act, "label": "停掉引擎",
                                               "note": "已杀引擎进程"}, ensure_ascii=False))
        if act not in ACTIONS:
            return self._send(400, json.dumps({"error": "unknown action %s" % act}, ensure_ascii=False))
        label, argv = ACTIONS[act]
        logname = "console-" + act.replace(":", "-") + ".log"
        try:
            path = spawn_bash(argv, logname)
        except Exception as e:
            return self._send(500, json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False))
        _CACHE["t"] = 0
        _mark(label, act, os.path.basename(path))
        return self._send(200, json.dumps({"ok": True, "action": act, "label": label,
                                           "log": os.path.basename(path)}, ensure_ascii=False))


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), H)
    print("[console] http://127.0.0.1:%d  (Ctrl+C 退出)" % PORT)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
