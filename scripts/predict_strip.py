
import json, struct, sys
path = sys.argv[1]
with open(path,'rb') as fh:
    head = fh.read(32); mlen = struct.unpack('<Q', head[8:16])[0]
    man = json.loads(fh.read(mlen).decode('utf-8'))
objs = man['objects']; by_id={o['id']:int(o['bytes']) for o in objs}

def referenced_ids(bindings):
    ids=set()
    for ref in bindings.values():
        if not isinstance(ref,dict): continue
        if isinstance(ref.get('object'),str): ids.add(ref['object'])
        for p in ref.get('parts') or []:
            if isinstance(p,dict) and isinstance(p.get('object'),str): ids.add(p['object'])
    return ids

drop=('dflash2/','vision/','proposal/','mtp/')
for droplist,label in [(('dflash2/','vision/','proposal/'),'strip default (keep text+mtp)'),
                       (('dflash2/','vision/','proposal/','mtp/'),'strip all (text only)'),
                       ((),'full file')]:
    kept_bind={k:v for k,v in man['bindings'].items() if not k.startswith(droplist)}
    ids=set(referenced_ids(kept_bind))
    for o in objs:
        if o['id'].startswith('resource/text'): ids.add(o['id'])
        if o['id'].startswith('auxiliary/'): ids.add(o['id'])
    kept=[o for o in objs if o['id'] in ids]
    dropped=[o for o in objs if o['id'] not in ids]
    kb=sum(int(o['bytes']) for o in kept); db=sum(int(o['bytes']) for o in dropped)
    print('%-32s keep %6d objs %10d B = %6.3f GiB | drop %5d objs %10d B = %6.3f GiB | new file ~ %.3f GiB' % (
        label, len(kept), kb, kb/1024**3, len(dropped), db, db/1024**3, (kb+405504+4096)/1024**3))
    # top kept objects
    if label.startswith('strip default'):
        print('   kept top10:')
        for o in sorted(kept,key=lambda o:-int(o['bytes']))[:10]:
            print('     %-40s %12d' % (o['id'], int(o['bytes'])))
