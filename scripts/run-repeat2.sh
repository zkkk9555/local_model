#!/bin/bash
set -u
cd /c/Project/local_model || exit 1
Q="这份文档里出现过哪些形如「动物-四位数字」的校验码？请按出现顺序全部列出，一个不漏，只列校验码本身。"
run() {
  python -u tools/longdoc.py --doc "$1" --question "$Q" --engine http://127.0.0.1:8091/v1 \
    --model bonsai27b-ptq1-nomtp-rk2v4-72k --shard-tokens 26000 --max-excerpt-tokens 512 \
    --pool-tokens 72000 --out "$2" >/dev/null 2>&1
  python - "$2" "$3" <<PY
import sys
sys.stdout.reconfigure(encoding="utf-8")
p, names = sys.argv[1], sys.argv[2]
t = open(p, encoding="utf-8").read()
needles = {"A": ["白色鲸鱼-3141"], "C": ["珊瑚水獭-1526","墨黑山猫-6733","银灰鹭鸶-3948","草绿螳螂-8205","绛紫狐猴-4691","象牙野猪-2377","海蓝螯虾-5860","赭石野兔-7112"]}[names]
print("  HITS", sum(n in t for n in needles), "/", len(needles))
PY
}
for i in 1 2; do
  echo "== 200K run$i $(date +%H:%M:%S)"
  run tmp/exp/doc-200k8.txt tmp/exp/f200b-r$i.md C
done
echo "== 150K run3 $(date +%H:%M:%S)"
run tmp/exp/doc-150k8.txt tmp/exp/f150-r3.md A
echo "== done $(date +%H:%M:%S)"