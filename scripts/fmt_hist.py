
import json, struct, sys, collections
path = sys.argv[1]
with open(path,'rb') as fh:
    head = fh.read(32); mlen = struct.unpack('<Q', head[8:16])[0]
    man = json.loads(fh.read(mlen).decode('utf-8'))
objs = man['objects']
print('object kinds:', collections.Counter(o.get('kind') for o in objs))
fmt = collections.Counter(); bytes_fmt = collections.Counter()
for o in objs:
    if o.get('kind') != 'tensor': continue
    f = o.get('format')
    fmt[f]+=1; bytes_fmt[f]+=int(o['bytes'])
print('\n-- tensor formats --')
for f,c in fmt.most_common():
    print('  %-20s %5d objs  %10d B  %6.3f GiB' % (f, c, bytes_fmt[f], bytes_fmt[f]/1024**3))
print('\n-- sample tensors (first 12 tensors) --')
n=0
for o in objs:
    if o.get('kind')!='tensor': continue
    print('  ', json.dumps({k:o[k] for k in o if k in ('id','shape','format','layout','divisors','bytes','encoding')}, ensure_ascii=False)[:220])
    n+=1
    if n>=12: break
print('\n-- largest tensors with format --')
tt=[o for o in objs if o.get('kind')=='tensor']
for o in sorted(tt, key=lambda o:-int(o['bytes']))[:12]:
    print('  %-14s %-18s %-22s %12d' % (o['id'], o.get('format'), str(o.get('shape'))[:20], int(o['bytes'])))
