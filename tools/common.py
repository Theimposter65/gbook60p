"""Shared deterministic file helpers. No hardware access or network operations."""
import hashlib,json,os,pathlib,stat,subprocess
ROOT=pathlib.Path(__file__).resolve().parents[1]
MiB=1<<20
GiB=1<<30
def require(ok,message):
    if not ok:raise ValueError(message)
def sha(path):
    with open(path,'rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def save(path,value):
    path=pathlib.Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,indent=2)+'\n')
def run(*args,**kwargs):return subprocess.run([str(a) for a in args],check=True,**kwargs)
def regular(path):
    path=pathlib.Path(path);s=path.lstat()
    require(stat.S_ISREG(s.st_mode) and s.st_nlink==1,'Expected a non-symlink regular file: '+str(path))
    return path
def read_cpio(data):
    result={};pos=0
    while pos+110<=len(data):
        if data[pos:pos+6]==bytes(6):break
        require(data[pos:pos+6]==b'070701','Unsupported CPIO header')
        fields=[int(data[pos+6+i*8:pos+14+i*8],16) for i in range(13)]
        size,nlen=fields[6],fields[11];name=data[pos+110:pos+110+nlen-1].decode()
        start=(pos+110+nlen+3)&~3;end=start+size
        require(end<=len(data),'Truncated CPIO')
        pos=(end+3)&~3
        if name=='TRAILER!!!':break
        require(name and not name.startswith('/') and '..' not in pathlib.PurePosixPath(name).parts,'Unsafe CPIO path')
        require(name not in result,'Duplicate CPIO entry')
        result[name]=(fields[1],data[start:end])
    return result
def write_cpio(entries):
    entries=dict(entries)
    # The kernel's initramfs unpacker does not create missing parents for
    # ordinary file entries. Component bundles may omit directory records.
    for name in list(entries):
        for parent in pathlib.PurePosixPath(name).parents:
            if str(parent)!='.':
                entries.setdefault(str(parent),(stat.S_IFDIR|0o755,b''))
                require(stat.S_ISDIR(entries[str(parent)][0]),'CPIO parent is not a directory')
    blocks=[]
    for inode,(name,(mode,data)) in enumerate([*sorted(entries.items()),('TRAILER!!!',(stat.S_IFREG,b''))],1):
        name=name.encode()+b'\0';fields=[inode,mode,0,0,1,0,len(data),0,0,0,0,len(name),0]
        head=b'070701'+b''.join(('%08x'%v).encode() for v in fields)+name
        blocks.append(head+b'\0'*(-len(head)%4)+data+b'\0'*(-len(data)%4))
    return b''.join(blocks)
def put(entries,name,data,mode=0o644):
    for p in pathlib.PurePosixPath(name).parents:
        if str(p)!='.':entries[str(p)]=(stat.S_IFDIR|0o755,b'')
    entries[name]=(stat.S_IFREG|mode,data)
