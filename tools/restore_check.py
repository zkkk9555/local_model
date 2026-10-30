#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""恢复自检：确认重建所需的件都在、字节数对得上（--deep 顺便算 SHA-256）。

用法：
  python tools/restore_check.py            只看文件与字节数（秒级）
  python tools/restore_check.py --deep     逐个大件算 SHA-256（6.4 GB 约 15-30 秒/个）

退出码：0 全部必需项 OK；1 有缺失/不符。
"""
import argparse, hashlib, os, shutil, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# (相对路径, 字节数, sha256 或 None, 是否必需, 说明)
# 引擎两支构建都接受：2026-10-08 的 801 MB 支 / 2026-10-13 packs 的 795 MB 支。
REQUIRED = [
    ("engine/ninfer-serve-89.exe", (801324544, 795030528), ("3b6f9af936a1e20520c3de3a4185f627ba59481139659cf3104bdead815ef6e4",
                                                                  "9fa7490bcbc4825a77673c5f8c6ffdbf25aab5b3e768a54d8bcebd7161ca41eb"), True, "引擎 sm_89"),
    ("models/bonsai2_27b_ternary_ptq1_native_mtp.ninfer", (6394697216,), ("5c4486c8a52687e3f62072c7dd2a320546d0e00d1c019bf137eb02cc944e21b8",), True, "Bonsai-2-27B PTQ1 权重"),
]

DLLS = [
    ("cudart64_13.dll", 551024),
    ("cublas64_13.dll", 51870320),
    ("cublasLt64_13.dll", 460301424),
    ("avcodec-63.dll", 91810816),
    ("avformat-63.dll", 23003136),
    ("avutil-61.dll", 3025408),
    ("swscale-10.dll", 2343936),
    ("swresample-7.dll", 747008),
    ("libcurl-x64.dll", 3722344),
]

OPTIONAL = [
    ("llama8g/bundle/models/Ternary-Bonsai-2-27B-PTQ1_0-mtp-procreations.gguf", (6397970272,),
     ("5f212d02ff57cb8eaad260fd7ff57bfaff87ae2bc9183a21dd2f127c27252505",), "llama.cpp 262K 路线权重"),
    ("llama8g/bundle/bin/llama-server.exe", None, None, "llama-server"),
    ("llama8g/bundle/artifacts/api_key.txt", None, None, "llama-server 的 key"),
    ("scripts/serve2.sh", None, None, "引擎启动脚本"),
    ("tools/chat_gateway.py", None, None, "护栏网关 8081"),
    ("tools/longctx_proxy.py", None, None, "超池分片代理 8086"),
    ("tools/console.py", None, None, "控制台 8090"),
]


def sha256(path, chunk=1 << 24):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def fmt(n):
    return "{:,}".format(n)


def check_one(rel, sizes, hashes, deep):
    path = os.path.join(ROOT, rel)
    if not os.path.exists(path):
        return ("MISSING", "缺文件")
    size = os.path.getsize(path)
    if sizes and size not in sizes:
        return ("BAD", "字节 {0}，期望 {1}".format(fmt(size), " / ".join(fmt(s) for s in sizes)))
    if deep and hashes:
        d = sha256(path)
        if d not in hashes:
            return ("BAD", "sha256 {0}… 不在白名单".format(d[:16]))
        return ("OK", "{} 字节  sha256 {}…".format(fmt(size), d[:16]))
    return ("OK", "{} 字节".format(fmt(size)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--deep", action="store_true", help="顺便算 SHA-256")
    args = ap.parse_args()
    print("[restore] root =", ROOT)
    ok = True

    if not all(ord(c) < 128 for c in ROOT):
        print("[restore] WARN 路径含非 ASCII 字符，引擎会抛 JSON UTF-8 异常")

    print("\n== 必需件 ==")
    for rel, sizes, hashes, must, note in REQUIRED:
        st, detail = check_one(rel, sizes, hashes, args.deep)
        print("  [{0:7}] {1:52} {2}".format(st, rel, detail))
        ok = ok and st == "OK"

    print("\n== 运行期 DLL（9 个，缺一个就是 0xC0000135）==")
    for name, size in DLLS:
        rel = "engine/" + name
        st, detail = check_one(rel, (size,), None, False)
        print("  [{0:7}] {1:52} {2}".format(st, rel, detail))
        ok = ok and st == "OK"

    print("\n== 可选件 ==")
    for rel, sizes, hashes, note in OPTIONAL:
        st, detail = check_one(rel, sizes, hashes, args.deep)
        tag = "info" if st == "MISSING" else st
        print("  [{0:7}] {1:52} {2}".format(tag, rel, detail))

    print("\n== 环境 ==")
    print("  python", sys.version.split()[0])
    nv = shutil.which("nvidia-smi")
    if nv:
        try:
            out = subprocess.run([nv, "--query-gpu=name,memory.total,memory.used,driver_version",
                                  "--format=csv,noheader"], capture_output=True, text=True, timeout=20).stdout.strip()
            print("  gpu   ", out or "(nvidia-smi 无输出)")
        except Exception as e:
            print("  gpu    nvidia-smi 调用失败:", e)
    else:
        print("  gpu    找不到 nvidia-smi")
    print("  bash  ", shutil.which("bash") or "(缺 bash：装 Git for Windows)")

    print("\n== 下一步 ==")
    if ok:
        print("  1) bash scripts/switch.sh ninfer      # 起 40K 日常档（8091）")
        print("  2) bash tools/verify_all.sh           # 探活 + DSH 配置一致性")
        print("  3) bash scripts/console.sh open       # 控制台 8090")
    else:
        print("  先把上面标 MISSING / BAD 的件按 RESTORE.md §3 补齐再起服")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())