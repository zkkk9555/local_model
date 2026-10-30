
import struct, sys
def u16(b,o): return struct.unpack_from('<H',b,o)[0]
def u32(b,o): return struct.unpack_from('<I',b,o)[0]
path=sys.argv[1]
f=open(path,'rb'); head=f.read(0x1000)
pe=u32(head,0x3c); coff=pe+4; opt=coff+20
magic=u16(head,opt); nrva=u32(head,opt+108); dd=opt+112
print('magic=0x%x nrva=%d dd_off=0x%x' % (magic,nrva,dd))
names=['export','import','resource','exception','security','basereloc','debug','arch','globalptr','tls','loadconfig','boundimport','iat','delayimport','clr','reserved']
f.seek(dd); raw=f.read(16*16)
for i in range(16):
    print('%2d %-12s rva=0x%08x size=%d' % (i,names[i],u32(raw,i*16),u32(raw,i*16+4)))
