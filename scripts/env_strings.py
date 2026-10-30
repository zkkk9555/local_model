
import re
data = open('engine/ninfer-serve-89.exe','rb').read()
seen = {}
for m in re.finditer(rb'NINFER_[A-Z0-9_]{2,40}', data):
    s = m.group().decode()
    seen.setdefault(s, 0)
    seen[s] += 1
for k in sorted(seen):
    print('%-40s %d' % (k, seen[k]))
