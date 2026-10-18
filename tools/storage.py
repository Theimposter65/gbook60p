"""GPT planning primitives adapted from GBRUNCH (MIT), with no physical write API."""
import fcntl,hashlib,os,pathlib,stat,struct,uuid,zlib
from common import require,MiB
ESP='c12a7328-f81f-11d2-ba4b-00a0c93ec93b'
LINUX='0fc63daf-8483-4772-8e79-3d69d8477de4'
BASIC='ebd0a0a2-b9e5-4433-87c0-68b6b72699c7'
def capacity(path):
    s=os.stat(path)
    if stat.S_ISREG(s.st_mode):return s.st_size
    with open(path,'rb') as f:return struct.unpack('Q',fcntl.ioctl(f,0x80081272,bytes(8)))[0]
def identity(path):
    p=pathlib.Path(path).resolve();s=p.stat()
    require(stat.S_ISBLK(s.st_mode),'Installer targets must be physical block disks')
    node=pathlib.Path('/sys/class/block')/p.name
    require(node.is_dir() and not (node/'partition').exists(),'Select a whole disk')
    require(p.name.startswith('nvme') and '/usb' not in (node/'device').resolve().as_posix(),'Only internal NVMe disks are supported')
    serial=(node/'device/serial').read_text().strip()
    require(serial and serial!='NO-SERIAL','A readable disk serial is required')
    with p.open('rb') as f:require(struct.unpack('I',fcntl.ioctl(f,0x1268,bytes(4)))[0]==512,'Only 512-byte logical sectors supported')
    return dict(path=str(p),bytes=capacity(p),rdev=s.st_rdev,serial=serial,sysfs=str(node.resolve()))
def unmounted(path):
    p=pathlib.Path(path).resolve();node=pathlib.Path('/sys/class/block')/p.name
    nodes=[node,*[x for x in node.glob('*') if (x/'partition').exists()]]
    ids={(x/'dev').read_text().strip() for x in nodes}
    for r in pathlib.Path('/proc/self/mountinfo').read_text().splitlines():require(r.split()[2] not in ids,'Target has a mounted filesystem; unmount it first')
    for r in pathlib.Path('/proc/swaps').read_text().splitlines()[1:]:
        q=pathlib.Path(r.split()[0])
        if q.exists() and stat.S_ISBLK(q.stat().st_mode):
            s=q.stat();require('%d:%d'%(os.major(s.st_rdev),os.minor(s.st_rdev)) not in ids,'Target has active swap')
    for n in nodes:require(not any((n/'holders').glob('*')),'Target has mapped, RAID or encryption holders')
def read_layout(path):
    size=capacity(path)
    with open(path,'rb') as f:
        mbr=f.read(512);h=f.read(512)
        require(mbr[510:]==b'\x55\xaa' and mbr[450]==0xee and all(mbr[450+16*i]==0 for i in (1,2,3)),'Only protective GPT MBRs accepted')
        require(h[:8]==b'EFI PART' and struct.unpack_from('<I',h,12)[0]==92,'Unsupported GPT header')
        def check(b):
            c=bytearray(b[:92]);crc=struct.unpack_from('<I',c,16)[0];c[16:20]=bytes(4)
            require(zlib.crc32(c)==crc,'GPT header checksum failed')
        check(h)
        current,backup,first,last=struct.unpack_from('<QQQQ',h,24)
        tlba,count,esz=struct.unpack_from('<QII',h,72)
        require(current==1 and backup==size//512-1 and tlba==2 and count==128 and esz==128 and first>=34 and last<backup-32,'Nonstandard or stale GPT geometry')
        f.seek(1024);table=f.read(16384)
        require(zlib.crc32(table)==struct.unpack_from('<I',h,88)[0],'GPT table checksum failed')
        f.seek((backup-32)*512);tail=f.read(33*512);bh=tail[-512:];check(bh)
        require(tail[:16384]==table and bh[:8]==b'EFI PART' and bh[56:72]==h[56:72] and bh[40:56]==h[40:56] and bh[88:92]==h[88:92],'Backup GPT mismatch')
        require(struct.unpack_from('<QQ',bh,24)==(backup,1) and struct.unpack_from('<Q',bh,72)[0]==backup-32,'Backup GPT geometry mismatch')
    parts=[]
    for i in range(128):
        e=table[i*128:(i+1)*128]
        if not any(e[:16]):
            require(not any(e),'Partially populated unused GPT entry');continue
        a,b,attrs=struct.unpack_from('<QQQ',e,32)
        require(first<=a<=b<=last,'Partition outside usable disk')
        parts.append(dict(index=i+1,name=e[56:128].decode('utf-16le').rstrip('\0'),guid=str(uuid.UUID(bytes_le=e[16:32])),type_guid=str(uuid.UUID(bytes_le=e[:16])),offset=a*512,bytes=(b-a+1)*512,attributes=attrs))
    spans=sorted((p['offset'],p['offset']+p['bytes']) for p in parts)
    require(all(a[1]<=b[0] for a,b in zip(spans,spans[1:])),'Overlapping existing partitions')
    require(len({p['guid'] for p in parts})==len(parts),'Duplicate partition GUIDs')
    return dict(parts=parts,mbr=mbr,header=h,table=table,tail=tail,backup=backup,first=first,last=last,disk_guid=str(uuid.UUID(bytes_le=h[56:72])),hash=hashlib.sha256(mbr+h+table+tail).hexdigest())
def allocate(layout,sizes,names,types):
    require(len(sizes)==len(names)==len(types)==3 and all(x>0 and x%MiB==0 for x in sizes),'Invalid allocation request')
    total=sum(sizes);cursor=((layout['first']*512+MiB-1)//MiB)*MiB;gaps=[]
    for p in sorted(layout['parts'],key=lambda p:p['offset']):
        if cursor<p['offset']:gaps.append((cursor,p['offset']))
        cursor=((p['offset']+p['bytes']+MiB-1)//MiB)*MiB
    gaps.append((cursor,(layout['last']+1)*512))
    gap=next(((a,b) for a,b in gaps if b-a>=total),None)
    require(gap is not None,'Need one unallocated extent of %.2f GiB; shrink in Windows Disk Management first'%(total/(1<<30)))
    slots=[i for i in range(1,129) if i not in {p['index'] for p in layout['parts']}]
    require(len(slots)>=3,'Three empty GPT slots required')
    result=[];cursor=gap[0]
    for slot,size,name,typ in zip(slots,sizes,names,types):
        result.append(dict(index=slot,name=name,type_guid=typ,guid=str(uuid.uuid4()),offset=cursor,bytes=size,attributes=0));cursor+=size
    return result
def validate_allocation(layout,parts,sizes):
    require(len(parts)==3 and [p['bytes'] for p in parts]==sizes,'Partition sizes changed')
    used={p['index'] for p in layout['parts']};guids={p['guid'] for p in layout['parts']}
    require(len({p['index'] for p in parts})==len(parts) and len({p['guid'] for p in parts})==len(parts),'Duplicate new partition identity')
    require([p['type_guid'] for p in parts]==[ESP,BASIC,LINUX],'Unexpected partition types')
    spans=[]
    for p in parts:
        uuid.UUID(p['guid']);require(1<=p['index']<=128 and p['index'] not in used and p['guid'] not in guids,'Occupied GPT slot/GUID')
        a,b=p['offset'],p['offset']+p['bytes']
        require(a%MiB==0 and layout['first']*512<=a<b<=(layout['last']+1)*512 and p['attributes']==0,'Invalid new extent')
        require(all(b<=x['offset'] or a>=x['offset']+x['bytes'] for x in layout['parts']),'New extent overlaps an existing partition')
        spans.append((a,b))
    require(all(a[1]<=b[0] for a,b in zip(sorted(spans),sorted(spans)[1:])),'New extents overlap')
def gpt_payload(layout,parts):
    table=bytearray(layout['table'])
    for p in parts:
        i=(p['index']-1)*128;require(not any(table[i:i+128]),'GPT entry already occupied')
        entry=bytearray(128);entry[:16]=uuid.UUID(p['type_guid']).bytes_le;entry[16:32]=uuid.UUID(p['guid']).bytes_le
        struct.pack_into('<QQQ',entry,32,p['offset']//512,(p['offset']+p['bytes'])//512-1,p['attributes'])
        n=p['name'].encode('utf-16le');require(len(n)<=72,'GPT name too long');entry[56:56+len(n)]=n;table[i:i+128]=entry
    h=bytearray(layout['header']);struct.pack_into('<I',h,88,zlib.crc32(table));h[16:20]=bytes(4);struct.pack_into('<I',h,16,zlib.crc32(h[:92]))
    bh=bytearray(h);struct.pack_into('<QQ',bh,24,layout['backup'],1);struct.pack_into('<Q',bh,72,layout['backup']-32);bh[16:20]=bytes(4);struct.pack_into('<I',bh,16,zlib.crc32(bh[:92]))
    return bytes(table),bytes(h),bytes(bh)
def write_all(fd,data,offset):
    while data:
        n=os.pwrite(fd,data,offset);require(n>0,'Short disk write');data=data[n:];offset+=n
class BoundedWriter:
    def __init__(self,fd,parts):self.fd=fd;self.parts=parts
    def write(self,offset,data):
        require(any(p['offset']<=offset and offset+len(data)<=p['offset']+p['bytes'] for p in self.parts),'Write outside the newly allocated partitions')
        write_all(self.fd,data,offset)
