#!/usr/bin/env python3
"""KV budget gate: predict engine VRAM before start, refuse when over the redline.

Formula from the author 3-arch pack (20261019) profiles.json:
  engine_est = spec_base_mib + ceil(pool/64) * slope_mib_per_page
    base : ptq1_mtp 7254 | ptq1_no_mtp 6643 | ptq2 8463   (MiB)
    slope: rk2v4-e8 0.8357 | k8v4 1.602 | rk4v4-e8 1.16 | nvfp4 1.19 | bf16 4.0
  redline = card_total - reserve(8G:400 else 500) - desktop_mib(300)
Exit code: 0 = may start, 2 = refuse.
"""
import argparse
import math

BASE = {"ptq1_mtp": 7254.0, "ptq1_no_mtp": 6643.0, "ptq2_mtp": 8463.0, "ptq2_no_mtp": 8463.0}
SLOPE = {"rk2v4-e8": 0.8357, "k8v4": 1.602, "rk4v4-e8": 1.16, "nvfp4": 1.19, "bf16": 4.0}
DESKTOP = 300.0


def reserve_for(card):
    return 400.0 if card < 9000 else 500.0


def compute(card, dtype, pool, mtp, quant="ptq1", reserve=None):
    pages = math.ceil(pool / 64.0)
    base = BASE[quant + ("_mtp" if mtp else "_no_mtp")]
    slope = SLOPE[dtype]
    est = base + pages * slope
    reserve = reserve_for(card) if reserve is None else reserve
    redline = card - reserve - DESKTOP
    return {
        "pages": pages, "base": base, "slope": slope, "est": est,
        "reserve": reserve, "redline": redline,
        "slack": redline - est, "ok": est <= redline,
    }


def max_pool(card, dtype, mtp, quant="ptq1", reserve=None):
    base = BASE[quant + ("_mtp" if mtp else "_no_mtp")]
    reserve = reserve_for(card) if reserve is None else reserve
    redline = card - reserve - DESKTOP
    pages = max(8, int((redline - base) // SLOPE[dtype]))
    return pages * 64


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--card", type=float, required=True, help="nvidia-smi memory.total in MiB")
    ap.add_argument("--dtype", default="rk2v4-e8", choices=sorted(SLOPE))
    ap.add_argument("--pool", type=int, default=0, help="--kv-capacity in tokens")
    ap.add_argument("--mtp", action="store_true", help="speculative decoding (MTP) enabled")
    ap.add_argument("--quant", default="ptq1", choices=["ptq1", "ptq2"])
    ap.add_argument("--fit", action="store_true", help="solve the largest pool that still fits")
    a = ap.parse_args()

    if a.fit:
        pool = max_pool(a.card, a.dtype, a.mtp, a.quant)
        r = compute(a.card, a.dtype, pool, a.mtp, a.quant)
        print("[gate] max pool: dtype=%s mtp=%s -> %d tokens (%d pages) est~%.0f MiB <= redline %.0f"
              % (a.dtype, a.mtp, pool, r["pages"], r["est"], r["redline"]))
        return 0

    if not a.pool:
        ap.error("need --pool or --fit")
    r = compute(a.card, a.dtype, a.pool, a.mtp, a.quant)
    print("[gate] pool=%d (%d pages) dtype=%s mtp=%d => engine_est~%.0f MiB | redline=%.0f "
          "(card %.0f - reserve %.0f - desktop %.0f) | slack %+.0f MiB => %s"
          % (a.pool, r["pages"], a.dtype, int(a.mtp), r["est"], r["redline"],
             a.card, r["reserve"], DESKTOP, r["slack"], "OK" if r["ok"] else "REFUSE"))
    return 0 if r["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
