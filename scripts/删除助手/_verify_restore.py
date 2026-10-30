import sys, difflib
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, r"C:/Project/删除助手")
import dsh_uninstall as m
new = m.apply_yml(m.read(m.YML), False)
open(r"C:/Project/删除助手/_new.yml", "w", encoding="utf-8", newline="\n").write(new)
def strip(t):
    return [l for l in t.split("\n") if l.strip() and not l.lstrip().startswith("#")]
a = strip(m.read(m.YML + ".bak-before-local"))
b = strip(new)
d = list(difflib.unified_diff(a, b, "bak-before-local", "simulated", n=1))
print("diff 行数:", len(d))
print("\n".join(d[:40]) if d else "[IDENTICAL] 模拟结果与「装本地模型之前」的配置逐行一致（忽略注释/空行）")