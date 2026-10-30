#!/usr/bin/env python3
# 把 DSH 里的「本地模型」痕迹撤掉：3 个 provider + 默认模型回退 + 2 个凭据键。
# 默认 dry-run；只有 --apply 才写盘（并先备份 .bak-final-<ts>）。
import argparse, os, re, shutil, sys, time
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import yaml

YML = r"C:/Users/Administrator/.dsh/profiles/desktop/cordis.patch.yml"
CRED = r"C:/Users/Administrator/.dsh/.credentials.yaml"
DROP = ("ninfer", "llama", "ninfer-long")
KEEP = ("opencode-go", "wb")
DEFAULT_BACK = [("provider", "wb"), ("model", "deepseek-v4.1-flash"), ("reasoningEffort", "max")]
DROP_REFS = ("LOCAL_LLM_KEY", "LLAMA_API_KEY")


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def plan_yml(text):
    lines = text.split("\n")
    idx = {}
    for i, ln in enumerate(lines):
        m = re.match(r"^ {6}([a-z0-9\-]+):\s*$", ln)
        if m:
            idx.setdefault(m.group(1), i)
    missing = [k for k in KEEP + DROP if k not in idx]
    if missing:
        raise SystemExit("[abort] provider 键缺失: %r (找到 %r)" % (missing, list(idx)))
    if not (idx["opencode-go"] < idx["ninfer"] < idx["llama"] < idx["ninfer-long"] < idx["wb"]):
        raise SystemExit("[abort] provider 顺序不对: %r" % idx)
    start, end = idx["ninfer"], idx["wb"]
    for i in range(start + 1, end):
        ln = lines[i]
        if not ln.strip() or ln.lstrip().startswith("#"):
            continue
        if re.match(r"^ {6}(" + "|".join(DROP) + r"):\s*$", ln):
            continue
        if not ln.startswith(" " * 8):
            raise SystemExit("[abort] 待删区间里有非嵌套内容（第 %d 行）: %s" % (i + 1, ln))
    # 默认模型回退
    d = [i for i, ln in enumerate(lines) if ln.strip() == "- id: agent-default-model"]
    if len(d) != 1:
        raise SystemExit("[abort] agent-default-model 条目数=%d" % len(d))
    head = d[0]
    cfg = [i for i in range(head, min(head + 8, len(lines))) if lines[i].strip() == "config:"]
    if not cfg:
        raise SystemExit("[abort] agent-default-model 下没有 config:")
    cfg = cfg[0]
    base = len(lines[cfg]) - len(lines[cfg].lstrip()) + 2
    j = cfg + 1
    while j < len(lines) and (lines[j].startswith(" " * base) or not lines[j].strip()):
        j += 1
    block = lines[cfg + 1:j]
    while block and not block[-1].strip():
        block.pop()
        j -= 1
    newblock = [" " * base + k + ": " + v for k, v in DEFAULT_BACK]
    return lines, start, end, cfg, j, block, newblock


def apply_yml(text, apply):
    lines, start, end, cfg, j, block, newblock = plan_yml(text)
    out = lines[:start] + lines[end:]
    shift = end - start
    delta = shift if cfg > start else 0
    out = out[:cfg - delta + 1] + newblock + out[j - delta:]
    new = "\n".join(out)
    data = yaml.safe_load(new)
    provs = None
    for e in data:
        if isinstance(e, dict) and e.get("id") == "llm-pi-ai":
            provs = e["config"]["providers"]
        if isinstance(e, dict) and e.get("id") == "agent-default-model":
            dm = e["config"]
    assert provs is not None and set(provs) == set(KEEP), "provider 结果不对: %r" % (set(provs) if provs else None)
    assert dm == {"provider": "wb", "model": "deepseek-v4.1-flash", "reasoningEffort": "max"}, dm
    print("[ok] yml 校验通过：providers=%r  默认模型=%r" % (sorted(provs), dm))
    print("[plan] 删除行区间 %d-%d（%d 行，3 个 provider + ninfer-direct 注释块）" % (start + 1, end, shift))
    print("[plan] 默认模型 %r -> %r" % (block, newblock))
    return new


def plan_cred(text):
    lines = text.split("\n")
    hits = [i for i, ln in enumerate(lines) if re.match(r"^ {2}(%s):" % "|".join(DROP_REFS), ln)]
    return lines, hits


def apply_cred(text, apply):
    lines, hits = plan_cred(text)
    if len(hits) != len(DROP_REFS):
        raise SystemExit("[abort] 期望删 %d 条凭据，实际匹配 %d 条" % (len(DROP_REFS), len(hits)))
    out = [ln for i, ln in enumerate(lines) if i not in set(hits)]
    new = "\n".join(out)
    data = yaml.safe_load(new)
    refs = data.get("refs") or {}
    assert not (set(refs) & set(DROP_REFS)), "凭据仍有残留: %r" % (set(refs) & set(DROP_REFS))
    print("[ok] 凭据校验通过：refs=%r" % sorted(refs))
    print("[plan] 删除凭据行 %r" % [i + 1 for i in hits])
    return new


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="真正写盘（默认只演算）")
    a = ap.parse_args()
    ts = time.strftime("%Y%m%d%H%M%S")
    ytext, ctext = read(YML), read(CRED)
    newy = apply_yml(ytext, a.apply)
    newc = apply_cred(ctext, a.apply)
    if a.apply:
        for p, t in ((YML, ytext), (CRED, ctext)):
            b = p + ".bak-final-" + ts
            shutil.copy2(p, b)
            print("[backup] %s" % b)
        with open(YML, "w", encoding="utf-8", newline="\n") as f:
            f.write(newy)
        with open(CRED, "w", encoding="utf-8", newline="\n") as f:
            f.write(newc)
        print("[done] 已写盘。重启 DSH 应用与宿主后生效。")
    else:
        print("[dry-run] 未写任何文件。加 --apply 才执行。")


if __name__ == "__main__":
    main()