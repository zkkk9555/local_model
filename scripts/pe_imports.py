
import struct, sys

def u16(b,o): return struct.unpack_from('<H',b,o)[0]
def u32(b,o): return struct.unpack_from('<I',b,o)[0]
def u64(b,o): return struct.unpack_from('<Q',b,o)[0]

path = sys.argv[1]
f = open(path,'rb')
head = f.read(0x1000)
pe = u32(head,0x3c)
assert head[pe:pe+4] == b'PE\0\0', 'not PE'
coff = pe+4
nsec = u16(head,coff+2)
opt = coff+20
magic = u16(head,opt)
if magic == 0x20b:
    nrva_off = opt+108
    dd = opt+112
else:
    nrva_off = opt+92
    dd = opt+96
f.seek(dd)
datadirs = f.read(16*16)
sections=[]
f.seek(opt+u16(head,coff+16))
secraw = f.read(nsec*40)
for i in range(nsec):
    o=i*40
    name=secraw[o:o+8].rstrip(b'\0').decode('latin1')
    vsize=u32(secraw,o+8); va=u32(secraw,o+12); rsize=u32(secraw,o+16); rptr=u32(secraw,o+20)
    sections.append((name,va,vsize,rptr,rsize))

def rva2off(rva):
    for name,va,vsize,rptr,rsize in sections:
        if va <= rva < va+max(vsize,rsize):
            return rptr + (rva-va)
    return None

def read_cstr(off):
    f.seek(off)
    out=b''
    while True:
        c=f.read(1)
        if not c or c==b'\0': break
        out+=c
        if len(out)>260: break
    return out.decode('latin1')

def dump(diridx, label):
    rva = u32(datadirs, diridx*16)
    size = u32(datadirs, diridx*16+4)
    print('%s rva=0x%x size=%d' % (label, rva, size))
    if rva == 0:
        print('   (none)')
        return
    off = rva2off(rva)
    if off is None:
        print('   <bad rva>')
        return
    names=[]
    while True:
        f.seek(off)
        d=f.read(20)
        if len(d)<20: break
        ilt=u32(d,0); oft=u32(d,16)
        if oft==0 and ilt==0: break
        n=rva2off(oft)
        if n is None: break
        names.append(read_cstr(n))
        off+=20
    for n in names: print('   ', n)

dump(1,'IMPORT')
dump(13,'DELAYLOAD')
print('SECTIONS:')
for s in sections: print('   ', s)
