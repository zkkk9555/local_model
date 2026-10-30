
import json, struct, sys, collections
path = sys.argv[1]
with open(path,'rb') as fh:
    head = fh.read(32)
    mlen = struct.unpack('<Q', head[8:16])[0]
    man = json.loads(fh.read(mlen).decode('utf-8'))
objs = man['objects']
by_id = {o['id']: int(o['bytes']) for o in objs}
print('objects:', len(objs), 'sum bytes: %.3f GiB' % (sum(by_id.values())/1024**3))
# group objects by first path segment
grp = collections.Counter()
grpN = collections.Counter()
for o in objs:
    seg = o['id'].split('/')[0]
    grp[seg] += int(o['bytes']); grpN[seg] += 1
print('\n-- objects grouped by id prefix --')
for k,v in grp.most_common():
    print('  %-24s %14d  %7.3f GiB  (%d objs)' % (k, v, v/1024**3, grpN[k]))
# bindings grouped by name prefix
bind = man['bindings']
bgrp = collections.Counter(); bgrpN=collections.Counter()
for name, ref in bind.items():
    if not isinstance(ref, dict): continue
    ids = set()
    if isinstance(ref.get('object'), str): ids.add(ref['object'])
    for part in ref.get('parts') or []:
        if isinstance(part, dict) and isinstance(part.get('object'), str): ids.add(part['object'])
    tot = sum(by_id.get(i,0) for i in ids)
    seg = name.split('/')[0]
    bgrp[seg]+=tot; bgrpN[seg]+=1
print('\n-- binding bytes by name prefix --')
for k,v in bgrp.most_common():
    print('  %-24s %14d  %7.3f GiB  (%d names)' % (k, v, v/1024**3, bgrpN[k]))
print('\ntop 20 objects by size:')
for o in sorted(objs, key=lambda o:-int(o['bytes']))[:20]:
    print('  %-52s %14d' % (o['id'], int(o['bytes'])))
print('\nmeta/provenance:', json.dumps(man.get('metadata'), ensure_ascii=False)[:800])
print('files:', json.dumps(man.get('files'))[:400])
