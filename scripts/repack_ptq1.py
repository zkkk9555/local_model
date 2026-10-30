"""repack_ptq1.py -- rewrite a NInfer v3 artifact: drop optional components and
re-pack t2_g128_fp16 tensors into ptq1_g128_fp16 (same ternary coordinates, 2.125 -> 1.75 bits).

Usage:
  python repack_ptq1.py <src.ninfer> <dst.ninfer> [--drop dflash2,vision,proposal] [--recode] [--dry-run]
"""
import argparse
import os
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC_TREE = os.path.join(ROOT, "repos", "ninfer-fusion-kvmem", "src-tree", "fusion-engine-src")
sys.path.insert(0, os.path.abspath(SRC_TREE))

from tools.artifact.reader import Artifact  # noqa: E402
from tools.artifact.writer import ArtifactWriter  # noqa: E402
from tools.artifact.schema import ResourceObject, TensorSpec, ResourceSpec  # noqa: E402

T2 = "t2_g128_fp16"
PTQ1 = "ptq1_g128_fp16"


def referenced_ids(bindings):
    ids = set()
    for ref in bindings.values():
        if not isinstance(ref, dict):
            continue
        obj = ref.get("object")
        if isinstance(obj, str):
            ids.add(obj)
        for part in ref.get("parts") or []:
            if isinstance(part, dict) and isinstance(part.get("object"), str):
                ids.add(part["object"])
    return ids


def keep_use(entry, kept_binding_names):
    if not isinstance(entry, dict):
        return False
    if entry.get("parameter") not in kept_binding_names:
        return False
    auxiliaries = entry.get("auxiliaries") or {}
    if isinstance(auxiliaries, dict):
        for role in auxiliaries:
            if isinstance(auxiliaries[role], str) and auxiliaries[role] not in kept_binding_names:
                return False
    return True


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--drop", default="dflash2,vision,proposal")
    ap.add_argument("--recode", action="store_true", help="t2_g128_fp16 -> ptq1_g128_fp16")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    drop = tuple(x.strip() + "/" for x in args.drop.split(",") if x.strip())
    if os.path.abspath(args.src) == os.path.abspath(args.dst):
        print("REFUSE: same file")
        return 2
    if os.path.exists(args.dst):
        print("REFUSE: destination exists: %s" % args.dst)
        return 2

    art = Artifact(args.src)
    d = art.directory
    print("source        : %s" % os.path.basename(args.src))
    print("  file bytes  : %d" % os.path.getsize(args.src))
    print("  artifact_id : %s" % art.artifact_id.hex())
    print("  payload     : %d" % d.payload_bytes)
    print("  components  : %s" % ", ".join(sorted(d.components.keys())))

    kept_bindings = {k: v for k, v in d.bindings.items() if not k.startswith(drop)}
    dropped_binding_names = [k for k in d.bindings if k.startswith(drop)]
    kept_components = {}
    for name, comp in d.components.items():
        if any(name == p.rstrip("/") for p in drop):
            continue
        comp = dict(comp)
        comp.pop("proposal", None)
        kept_components[name] = comp

    keep_ids = referenced_ids(kept_bindings)
    for obj in d.objects:
        if isinstance(obj, ResourceObject):
            if obj.id.startswith("resource/text"):
                keep_ids.add(obj.id)
        elif obj.id.startswith("auxiliary/"):
            keep_ids.add(obj.id)
    kept_uses = [u for u in d.uses if keep_use(u, set(kept_bindings.keys()))]
    kept = [o for o in d.objects if o.id in keep_ids]
    dropped = [o for o in d.objects if o.id not in keep_ids]
    kept_bytes = sum(o.bytes for o in kept)
    dropped_bytes = sum(o.bytes for o in dropped)
    recoded = [o for o in kept if not isinstance(o, ResourceObject) and o.format == T2]
    recoded_in = sum(o.bytes for o in recoded)
    factor = 28.0 / 34.0
    recoded_out = int(recoded_in * factor)
    print("keep          : %d objects / %.3f GiB" % (len(kept), kept_bytes / 1024 ** 3))
    print("drop          : %d objects / %.3f GiB (%d binding names)" % (
        len(dropped), dropped_bytes / 1024 ** 3, len(dropped_binding_names)))
    if args.recode:
        print("recode t2->ptq1: %d objects / %.3f GiB -> %.3f GiB" % (
            len(recoded), recoded_in / 1024 ** 3, recoded_out / 1024 ** 3))
    new_total = kept_bytes - recoded_in + (recoded_out if args.recode else recoded_in)
    print("predicted dst : %d bytes = %.3f GiB (+~0.4 MB directory)" % (new_total, new_total / 1024 ** 3))
    print("components 保留: %s" % ", ".join(sorted(kept_components.keys())))
    if args.dry_run:
        art.close()
        print("[dry-run] nothing written")
        return 0

    specs = []
    for obj in kept:
        if isinstance(obj, ResourceObject):
            specs.append(ResourceSpec(id=obj.id, bytes=obj.bytes, encoding=obj.encoding))
        else:
            fmt = PTQ1 if (args.recode and obj.format == T2) else obj.format
            specs.append(TensorSpec(id=obj.id, shape=obj.shape, format=fmt,
                                    layout=obj.layout, divisors=obj.divisors))

    provenance = dict(d.provenance)
    provenance["repacked"] = {
        "by": "repack_ptq1.py",
        "when": datetime.now().isoformat(timespec="seconds"),
        "dropped_prefixes": [p.rstrip("/") for p in drop],
        "dropped_objects": len(dropped),
        "dropped_bytes": dropped_bytes,
        "recoded_tensors": len(recoded),
        "recoded_from": T2,
        "recoded_to": PTQ1 if args.recode else T2,
        "source_file": os.path.basename(args.src),
        "source_artifact_id": art.artifact_id.hex(),
    }

    writer = ArtifactWriter(
        args.dst, specs,
        components=kept_components,
        bindings=kept_bindings,
        uses=kept_uses,
        metadata=d.metadata,
        provenance=provenance,
        identity=getattr(d, "identity", None) or {},
    )
    written = 0
    try:
        for index, obj in enumerate(kept):
            if args.recode and not isinstance(obj, ResourceObject) and obj.format == T2:
                import torch
                from tools.artifact.codecs.row_split import decode_row_split_codes, encode_row_split
                payload = art.read_object(obj.id)
                scales, codes = decode_row_split_codes(payload, T2, obj.shape)
                codes = codes.to(torch.int8).contiguous()
                scales = scales.to(torch.float16).contiguous()
                new = encode_row_split(codes, scales, PTQ1, obj.shape)
                writer.write_object(obj.id, new)
                written += len(new)
                if index % 25 == 0 or obj is kept[-1]:
                    print("  [%d/%d] %s %s -> %d bytes" % (index + 1, len(kept), obj.id,
                                                           list(obj.shape), len(new)), flush=True)
            else:
                writer.write_object(obj.id, art.iter_object(obj.id))
                written += obj.bytes
        directory = writer.finish()
    except BaseException:
        writer.abort()
        raise
    finally:
        art.close()

    print("written       : %d bytes" % written)
    print("destination   : %s" % args.dst)
    print("  file bytes  : %d (%.3f GiB)" % (os.path.getsize(args.dst),
                                             os.path.getsize(args.dst) / 1024 ** 3))
    check = Artifact(args.dst)
    print("re-open OK    : artifact_id=%s payload=%d objects=%d components=%s" % (
        check.artifact_id.hex(), check.payload_bytes, len(check.objects),
        ",".join(sorted(check.directory.components.keys()))))
    check.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
