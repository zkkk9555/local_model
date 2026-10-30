#!/bin/bash
# Phase A: NInfer 150K/200K sharded repeatability (pool 72K, shard 26K)
set -u
cd /c/Project/local_model || exit 1
LOG=tmp/exp/repeat-$(date +%H%M%S).log
exec > >(tee -a "$LOG") 2>&1
echo "== start $(date +%H:%M:%S)"
Q="这份文档里出现过哪些形如「动物-四位数字」的校验码？请按出现顺序全部列出，一个不漏，只列校验码本身。"
for i in 1 2; do
  echo "== 150K run $i"
  python -u tools/longdoc.py --doc tmp/exp/doc-150k8.txt --question "$Q" \
    --engine http://127.0.0.1:8091/v1 --model bonsai27b-ptq1-nomtp-rk2v4-72k \
    --shard-tokens 26000 --max-excerpt-tokens 1024 --out tmp/exp/rep150-$i.md | tail -4
  python -c "import sys;sys.stdout.reconfigure(encoding='utf-8');t=open('tmp/exp/rep150-$i.md',encoding='utf-8').read();B=['白色鲸鱼-3141','灰色鹦鹉-5926','橙色章鱼-8412','青色刺猬-2673','褐色獾子-7058','粉色火烈鸟-1936','墨绿壁虎-4482','杏色绵羊-6207'];print('HITS',sum(b in t for b in B),'/8')"
done
echo "== 200K run"
python -u tools/longdoc.py --doc tmp/exp/doc-200k.txt --question "$Q" \
  --engine http://127.0.0.1:8091/v1 --model bonsai27b-ptq1-nomtp-rk2v4-72k \
  --shard-tokens 26000 --max-excerpt-tokens 1024 --out tmp/exp/rep200.md | tail -4
python -c "import sys;sys.stdout.reconfigure(encoding='utf-8');t=open('tmp/exp/rep200.md',encoding='utf-8').read();C=['珊瑚水獭-1526','墨黑山猫-6733','银灰鹭鸶-3948','草绿螳螂-8205','绛紫狐猴-4691','象牙野猪-2377','海蓝螯虾-5860','赭石野兔-7112'];print('HITS',sum(b in t for b in C),'/8')"
echo "== done $(date +%H:%M:%S)"