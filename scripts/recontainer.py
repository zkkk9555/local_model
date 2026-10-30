import argparse
import json
import os
import struct
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC_TREE = os.path.join(ROOT, "repos", "ninfer-fusion-kvmem", "src-tree", "fusion-engine-src")
sys.path.insert(0, SRC_TREE)

from tools.artifact.framing import HEADER, MAGIC, PAYLOAD_ALIGNMENT
from tools.artifact.layouts import align_up
from tools.artifact.schema import TensorSpec, ResourceSpec, plan_objects, encode_directory

T2 = "t2_g128_fp16"
PTQ1 = "ptq1_g128_fp16"
COPY_CHUNK = 8 << 20


def read_manifest(path):
    with open(path, "rb") as handle:
        head = handle.read(HEADER.size)
        magic, manifest_bytes, artifact_id = HEADER.unpack(head)
        if magic != MAGIC:
            raise SystemExit("not a NINFER v3 container")
        raw = handle.read(manifest_bytes)
    return json.loads(raw), artifact_id, align_up(HEADER.size + manifest_bytes, PAYLOAD_ALIGNMENT)


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


def keep_use(entry, kept_names):
    if not isinstance(entry, dict):
        return False
    if entry.get("parameter") not in kept_names:
        return False
    auxiliaries = entry.get("auxiliaries") or {}
    if isinstance(auxiliaries, dict):
        for role in auxiliaries:
            if isinstance(auxiliaries[role], str) and auxiliaries[role] not in kept_names:
                return False
    return True

def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--drop", default="dflash2,vision,proposal")
    ap.add_argument("--recode", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    if os.path.abspath(args.src) == os.path.abspath(args.dst):
        print("REFUSE: same path")
        return 2
    if os.path.exists(args.dst):
        print("REFUSE: destination exists: %s" % args.dst)
        return 2

    directory, artifact_id, source_payload = read_manifest(args.src)
    drop = tuple(x.strip() + "/" for x in args.drop.split(",") if x.strip())
    print("source        : %s (%d bytes)" % (os.path.basename(args.src), os.path.getsize(args.src)))
    print("  artifact_id : %s" % artifact_id.hex())
    print("  payload at  : %d, bytes %d" % (source_payload, directory["files"][0]["payload_bytes"]))
    print("  components  : %s" % ", ".join(sorted(directory["components"])))
    expected_total = source_payload + directory["files"][0]["payload_bytes"]
    actual_total = os.path.getsize(args.src)
    if actual_total != expected_total:
        print("REFUSE: source is truncated: %d of %d bytes" % (actual_total, expected_total))
        return 2

    kept_bindings = {k: v for k, v in directory["bindings"].items() if not k.startswith(drop)}
    kept_components = {}
    for name, component in directory["components"].items():
        if any(name == p.rstrip("/") for p in drop):
            continue
        component = dict(component)
        component.pop("proposal", None)
        kept_components[name] = component

    keep_ids = referenced_ids(kept_bindings)
    for obj in directory["objects"]:
        if obj["id"].startswith("resource/text") or obj["id"].startswith("auxiliary/"):
            keep_ids.add(obj["id"])

    uses = [u for u in directory.get("uses", []) if keep_use(u, set(kept_bindings))]
    kept = [o for o in directory["objects"] if o["id"] in keep_ids]
    dropped = [o for o in directory["objects"] if o["id"] not in keep_ids]
    kept_bytes = sum(o["bytes"] for o in kept)
    source_offsets = {o["id"]: o["offset"] for o in kept}
    source_sizes = {o["id"]: o["bytes"] for o in kept}

    specs = []
    recode_ids = set()
    for obj in kept:
        if obj["kind"] == "resource":
            specs.append(ResourceSpec(id=obj["id"], bytes=obj["bytes"], encoding=obj["encoding"]))
        else:
            fmt = obj["format"]
            if args.recode and fmt == T2:
                fmt = PTQ1
                recode_ids.add(obj["id"])
            specs.append(TensorSpec(id=obj["id"], shape=tuple(obj["shape"]), format=fmt,
                                    layout=obj["layout"], divisors=obj.get("divisors", 1)))

    objects = plan_objects(specs)
    payload_bytes = objects[-1].offset + objects[-1].bytes

    provenance = dict(directory.get("provenance") or {})
    provenance["repacked"] = {
        "by": "recontainer.py",
        "when": datetime.now().isoformat(timespec="seconds"),
        "dropped_prefixes": [p.rstrip("/") for p in drop],
        "dropped_objects": len(dropped),
        "dropped_bytes": sum(o["bytes"] for o in dropped),
        "recoded_tensors": len(recode_ids),
        "recoded_from": T2,
        "recoded_to": PTQ1 if args.recode else T2,
        "source_file": os.path.basename(args.src),
        "source_artifact_id": artifact_id.hex(),
    }
    description = {
        "components": kept_components,
        "objects": [obj.to_json() for obj in objects],
        "bindings": kept_bindings,
        "uses": uses,
        "metadata": directory.get("metadata") or {},
        "provenance": provenance,
    }

    value = dict(description)
    value["files"] = [{"path": None, "payload_bytes": payload_bytes}]
    reserve = align_up(HEADER.size + len(encode_directory(value)), PAYLOAD_ALIGNMENT) - HEADER.size
    while True:
        value["files"] = [{"path": None, "payload_bytes": payload_bytes}]
        encoded = encode_directory(value)
        if len(encoded) <= reserve:
            break
        reserve = align_up(HEADER.size + len(encoded), PAYLOAD_ALIGNMENT) - HEADER.size
    payload_offset = HEADER.size + reserve

    print("keep          : %d objects / %.3f GiB" % (len(kept), kept_bytes / 1024 ** 3))
    print("drop          : %d objects / %.3f GiB" % (len(dropped), sum(o["bytes"] for o in dropped) / 1024 ** 3))
    print("recode        : %d tensors t2 to ptq1" % len(recode_ids))
    print("new payload   : %d bytes = %.3f GiB" % (payload_bytes, payload_bytes / 1024 ** 3))
    print("directory     : %d bytes, payload at %d" % (len(encoded), payload_offset))
    print("predicted dst : %d bytes = %.3f GiB" % (payload_offset + payload_bytes,
                                                   (payload_offset + payload_bytes) / 1024 ** 3))
    if args.dry_run:
        print("[dry-run] nothing written")
        return 0

    if args.recode:
        import torch
        from tools.artifact.codecs.row_split import decode_row_split_codes, encode_row_split

    total = payload_offset + payload_bytes
    with open(args.src, "rb") as src, open(args.dst, "w+b") as dst:
        dst.truncate(total)
        dst.seek(0)
        dst.write(HEADER.pack(MAGIC, len(encoded), artifact_id))
        dst.write(encoded)
        dst.write(b" " * (reserve - len(encoded)))
        for index, obj in enumerate(objects):
            src.seek(source_payload + source_offsets[obj.id])
            dst.seek(payload_offset + obj.offset)
            if obj.id in recode_ids:
                payload = src.read(source_sizes[obj.id])
                shape = tuple(obj.shape)
                scales, codes = decode_row_split_codes(payload, T2, shape)
                codes = codes.to(torch.int8).contiguous()
                scales = scales.to(torch.float16).contiguous()
                packed = encode_row_split(codes, scales, PTQ1, shape)
                if len(packed) != obj.bytes:
                    raise SystemExit("%s: ptq1 %d != planned %d" % (obj.id, len(packed), obj.bytes))
                dst.write(packed)
                print("  [%d/%d] recode %s %s -> %d B" % (index + 1, len(objects), obj.id,
                                                          list(shape), len(packed)), flush=True)
            else:
                remaining = obj.bytes
                while remaining:
                    chunk = src.read(min(COPY_CHUNK, remaining))
                    if not chunk:
                        raise SystemExit("%s: source truncated" % obj.id)
                    dst.write(chunk)
                    remaining -= len(chunk)
        dst.flush()
        os.fsync(dst.fileno())

    print("written       : %d bytes" % total)
    print("destination   : %s (%.3f GiB)" % (args.dst, os.path.getsize(args.dst) / 1024 ** 3))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
