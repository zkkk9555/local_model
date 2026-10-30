
import sys, zipfile, os, hashlib, fnmatch
zpath, dst = sys.argv[1], sys.argv[2]
pats = sys.argv[3:]
os.makedirs(dst, exist_ok=True)
found = []
with zipfile.ZipFile(zpath) as z:
    for info in z.infolist():
        if info.is_dir():
            continue
        base = os.path.basename(info.filename)
        if any(fnmatch.fnmatch(base.lower(), p.lower()) for p in pats):
            data = z.read(info)
            out = os.path.join(dst, base)
            with open(out, 'wb') as f:
                f.write(data)
            h = hashlib.sha256(data).hexdigest().upper()
            found.append((base, len(data), h))
for base, n, h in found:
    print('%s\t%d\t%s' % (base, n, h))
if not found:
    print('NOTHING MATCHED for %s' % zpath)
    sys.exit(2)
