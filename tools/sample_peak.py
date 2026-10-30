#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""采样显存占用与进程 WS（RAM），用于测 Strata 起服/推理期间的峰值。
用法: python sample_peak.py --out ../reports/data/peak.csv --seconds 900 --match strata
"""
import argparse, csv, subprocess, time


def gpu_used():
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=10).stdout.strip().splitlines()
        return int(out[0].strip()) if out else -1
    except Exception:
        return -1


def procs(match):
    total = 0
    n = 0
    try:
        ps = subprocess.run(["powershell", "-NoProfile", "-Command",
                             "Get-CimInstance Win32_Process | Where-Object { $_.Name -match '" + match + "' } | Select-Object -ExpandProperty WorkingSetSize"],
                             capture_output=True, text=True, timeout=25).stdout
        for ln in ps.splitlines():
            ln = ln.strip()
            if ln.isdigit():
                total += int(ln)
                n += 1
    except Exception:
        pass
    return total, n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="C:/Project/local_model/reports/data/peak.csv")
    ap.add_argument("--seconds", type=int, default=900)
    ap.add_argument("--interval", type=float, default=1.0)
    ap.add_argument("--match", default="strata")
    a = ap.parse_args()
    t_end = time.time() + a.seconds
    peak_gpu = 0
    peak_ws = 0
    with open(a.out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["t", "gpu_mib", "proc_count", "ws_bytes"])
        while time.time() < t_end:
            g = gpu_used()
            ws, n = procs(a.match)
            peak_gpu = max(peak_gpu, g if g > 0 else 0)
            peak_ws = max(peak_ws, ws)
            w.writerow(["%.1f" % time.time(), g, n, ws])
            f.flush()
            time.sleep(a.interval)
    print("peak_gpu_mib=%d peak_ws_bytes=%d (%.2f GiB)" % (peak_gpu, peak_ws, peak_ws / 1073741824.0))


if __name__ == "__main__":
    main()