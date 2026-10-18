#!/usr/bin/env python3
"""Build regular files only, from a pinned local recovery and precompiled assets."""
import argparse,gzip,hashlib,io,json,os,pathlib,shlex,shutil,stat,struct,subprocess,tarfile,zipfile,zlib
from common import ROOT,MiB,require,regular,sha,save,run,read_cpio,write_cpio,put
import erofs_metadata

def verify_assets(assets):
    pin=json.loads((ROOT/'profiles/assets.json').read_text())
    require(sha(assets/'MANIFEST.json')==pin['manifest_sha256'],'Asset manifest differs from the pinned release')
    manifest=json.loads((assets/'MANIFEST.json').read_text())
    for n,row in manifest['files'].items():
        p=pathlib.PurePosixPath(n);require(not p.is_absolute() and '..' not in p.parts,'Unsafe asset path')
        f=regular(assets/p)
        require(f.stat().st_size==row['bytes'] and sha(f)==row['sha256'],'Precompiled asset checksum failed: '+n)
    require(sha(assets/'kernel')==pin['kernel_sha256'],'Kernel checksum mismatch')
    return pin

class Forward:
    def __init__(self,f):self.f=f;self.pos=0
    def seek(self,pos):
        require(pos>=self.pos,'Recovery contains non-forward extents')
        while self.pos<pos:self.read(min(8*MiB,pos-self.pos))
    def read(self,n):
        b=self.f.read(n);require(len(b)==n,'Truncated recovery image');self.pos+=n;return b

def extract_parts(recovery,out):
    pin=json.loads((ROOT/'profiles/recovery.json').read_text())
    require(regular(recovery).stat().st_size==pin['bytes'] and sha(recovery)==pin['sha256'],'Recovery ZIP checksum mismatch')
    out.mkdir(parents=True,exist_ok=False)
    with zipfile.ZipFile(recovery) as z:
        entry=max(z.infolist(),key=lambda e:e.file_size)
        with z.open(entry) as stream:
            f=Forward(stream);prefix=f.read(34*512);h=prefix[512:1024];header=bytearray(h[:92]);crc=struct.unpack_from('<I',header,16)[0];header[16:20]=bytes(4)
            require(h[:8]==b'EFI PART' and zlib.crc32(header)==crc,'Recovery GPT checksum failed')
            lba,count,sz=struct.unpack_from('<QII',h,72)
            require((lba,count,sz)==(2,128,128),'Unknown recovery GPT profile')
            table=prefix[1024:34*512];require(zlib.crc32(table)==struct.unpack_from('<I',h,88)[0],'Recovery GPT table checksum failed')
            gpt={}
            for i in range(count):
                e=table[i*sz:(i+1)*sz]
                if any(e[:16]):gpt[e[56:128].decode('utf-16le').rstrip('\0')]=struct.unpack_from('<QQ',e,32)
            base=gpt['super'][0]*512
            f.seek(base+4096);geo=f.read(4096)
            require(struct.unpack_from('<I',geo)[0]==0x616c4467,'Bad liblp geometry')
            gg=bytearray(geo[:struct.unpack_from('<I',geo,4)[0]]);gg[8:40]=bytes(32)
            require(hashlib.sha256(gg).digest()==geo[8:40],'Bad liblp geometry hash')
            maxsize,slots,bs=struct.unpack_from('<III',geo,40)
            require(maxsize<=MiB and slots<=4 and bs==4096,'Unknown liblp geometry')
            f.seek(base+12288);meta=f.read(maxsize)
            require(struct.unpack_from('<I',meta)[0]==0x414c5030,'Bad liblp header')
            hs=struct.unpack_from('<I',meta,8)[0];ts=struct.unpack_from('<I',meta,44)[0]
            hh=bytearray(meta[:hs]);hh[12:44]=bytes(32);tables=meta[hs:hs+ts]
            require(hashlib.sha256(hh).digest()==meta[12:44] and hashlib.sha256(tables).digest()==meta[48:80],'Bad liblp metadata hash')
            po,pc,ps,eo,ec,es=struct.unpack_from('<6I',meta,80)
            jobs=[];outputs={};found=set()
            try:
                for i in range(pc):
                    e=tables[po+i*ps:po+(i+1)*ps];name=e[:36].split(b'\0')[0].decode()
                    if name not in pin['parts']:continue
                    require(name not in found,'Duplicate logical partition');found.add(name)
                    first,num=struct.unpack_from('<II',e,40);dst=0
                    o=(out/(name+'.img')).open('xb');outputs[name]=o
                    for j in range(first,first+num):
                        sectors,kind,sector,source=struct.unpack_from('<QIQI',tables,eo+j*es)
                        require(j<ec and kind in (0,1) and source==0,'Unsupported logical extent')
                        length=sectors*512
                        if kind==0:jobs.append((base+sector*512,length,name,dst))
                        dst+=length
                    o.truncate(dst)
                require(found==set(pin['parts']),'Recovery logical partitions missing')
                jobs.sort();require(all(a[0]+a[1]<=b[0] for a,b in zip(jobs,jobs[1:])),'Overlapping logical extents')
                for offset,length,name,dst in jobs:
                    f.seek(offset);o=outputs[name];o.seek(dst)
                    while length:
                        b=f.read(min(length,8*MiB));o.write(b);length-=len(b)
                    print('Extracted '+name,flush=True)
            finally:
                for o in outputs.values():o.close()

def build_tool_wrappers(assets,out):
    # Linux tools are bundled with their matching libc. No host packages are replaced.
    bindir=out/'build-bin';bindir.mkdir()
    runtime=assets/'build-tools';loader=runtime/'lib64/ld-linux-x86-64.so.2'
    lib=runtime/'lib/x86_64-linux-gnu'
    for name in ('extend-vendor-policy','mkfs.erofs','dump.erofs','fsck.erofs'):
        target=runtime/'bin'/name;target.chmod(0o755);loader.chmod(0o755)
        p=bindir/name;p.write_text('#!/bin/sh\nexec '+shlex.join([str(loader),'--library-path',str(lib),str(target)])+' "$@"\n');p.chmod(0o755)
    erofs_metadata.D=bindir/'dump.erofs'
    return bindir

def cat(tool,image,path):
    return subprocess.check_output([str(tool/'dump.erofs'),'--path='+path,'--cat',str(image)])

def vendor_view(parts,out,tools):
    source=parts/'vendor_a.img';pol=json.loads((ROOT/'profiles/policy.json').read_text())
    (out/'original-policy').write_bytes(cat(tools,source,'/etc/selinux/precompiled_sepolicy'))
    with (out/'policy.log').open('wb') as log:run(tools/'extend-vendor-policy',out/'original-policy',out/'policy',*pol['rules'],stdout=log)
    overlay={'etc/selinux/precompiled_sepolicy':(out/'policy').read_bytes()}
    for name in pol['disabled_tools']:
        try:erofs_metadata.metadata(source,'/bin/'+name)
        except (subprocess.CalledProcessError,TypeError):continue
        overlay['bin/'+name]=b'#!/system/bin/sh\necho GBRUNCH_HARDWARE_MAINTENANCE_DISABLED >&2\nexit 1\n'
    with tarfile.open(out/'vendor-overlay.tar','w',format=tarfile.PAX_FORMAT) as tf:
        parents={'.'}
        for n in overlay:
            parents.update(str(p) for p in pathlib.PurePosixPath(n).parents)
        for n in sorted(parents):
            m=erofs_metadata.metadata(source,'/' if n=='.' else '/'+n)
            ti=tarfile.TarInfo(n);ti.type=tarfile.DIRTYPE;ti.mode=m['mode']&0o7777;ti.uid=m['uid'];ti.gid=m['gid'];ti.mtime=m['mtime'];ti.pax_headers={} if n=='.' else {'SCHILY.xattr.'+k:v.decode() for k,v in m['xattrs'].items()};tf.addfile(ti)
        for n,b in overlay.items():
            m=erofs_metadata.metadata(source,'/'+n);ti=tarfile.TarInfo(n);ti.size=len(b);ti.mode=m['mode']&0o7777;ti.uid=m['uid'];ti.gid=m['gid'];ti.mtime=m['mtime'];ti.pax_headers={'SCHILY.xattr.'+k:v.decode() for k,v in m['xattrs'].items()};tf.addfile(ti,io.BytesIO(b))
    vendor=out/'vendor.erofs';shutil.copyfile(source,vendor)
    with vendor.open('rb') as f:
        f.seek(1024);sb=f.read(128);bs=1<<sb[12];root=struct.unpack_from('<I',sb,40)[0]*bs+struct.unpack_from('<H',sb,14)[0]*32;f.seek(root);old=f.read(64)
    run(tools/'mkfs.erofs','--incremental=data','--tar=f','-x0','-b4096','-T1230768000','-zlz4hc',vendor,out/'vendor-overlay.tar',stdout=subprocess.DEVNULL)
    with vendor.open('r+b') as f:
        f.seek(root);new=f.read(64);require(old[2:4]==new[2:4] and not(old[0]&1 or new[0]&1),'EROFS root inode profile changed')
        f.seek(root+32);f.write(old[32:48]);f.seek(1024);b=bytearray(f.read(bs-1024));b[4:8]=bytes(4);crc=0xffffffff
        for v in b:
            crc^=v
            for _ in range(8):crc=(crc>>1)^(0x82f63b78 if crc&1 else 0)
        f.seek(1028);f.write(struct.pack('<I',crc))
    run(tools/'fsck.erofs',vendor,stdout=subprocess.DEVNULL)
    for n,b in overlay.items():require(cat(tools,vendor,'/'+n)==b,'Vendor overlay readback failed: '+n)
    return vendor

def compatibility(assets,out):
    upstream=assets/'upstream/assets';compat=out/'compat.ext4';shutil.copyfile(upstream/'compat.ext4',compat)
    rc=(ROOT/'platform/root/gbrunch-runtime-init.rc').read_bytes();(out/'init.gbrunch.rc').write_bytes(rc)
    lines=[]
    for line in (upstream/'fstab.android-desktop').read_text().splitlines():
        if 'voldmanaged=' in line:continue
        fields=line.split()
        if fields and fields[0] in ['/dev/block/by-name/userdata','/dev/block/by-name/metadata']:
            fields[3]=','.join(v for v in fields[3].split(',') if v!='discard')
            fields[4]=','.join(v for v in fields[4].split(',') if v not in ['formattable','check'] and not v.startswith(('fileencryption=','keydirectory=')))
            line=' '.join(fields)
        lines.append(line)
    (out/'fstab.android-desktop').write_text('\n'.join(lines)+'\n')
    commands=[]
    for name in ['init.gbrunch.rc','fstab.android-desktop']:
        commands+=['rm /'+name,'write '+str(out/name)+' /'+name,'ea_set /'+name+' security.selinux u:object_r:'+('vendor_configs_file' if name.startswith('fstab') else 'vendor_file')+':s0','set_inode_field /'+name+' uid 0','set_inode_field /'+name+' gid 0','set_inode_field /'+name+' mode 0100644']
    p=out/'compat-update.commands';p.write_text('\n'.join(commands)+'\n')
    run('debugfs','-w','-f',p,compat,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    for name in ['init.gbrunch.rc','fstab.android-desktop']:
        require(subprocess.check_output(['debugfs','-R','cat /'+name,str(compat)],stderr=subprocess.DEVNULL)==(out/name).read_bytes(),'Compatibility readback failed')
    run('e2fsck','-fn',compat,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    return compat,hashlib.sha256(rc).hexdigest()

def ramdisk(parts,out,assets,tools,vendor,compat,rc_hash):
    entries=read_cpio(gzip.decompress((assets/'platform.cpio.gz').read_bytes()))
    for n in ['bin','sbin','dev','proc','sys','tmp','lib']:entries[n]=(stat.S_IFDIR|0o755,b'')
    for p in (ROOT/'platform/root').rglob('*'):
        if p.is_file():put(entries,str(p.relative_to(ROOT/'platform/root')),p.read_bytes(),0o755 if p.suffix=='.sh' else 0o644)
    original=cat(tools,parts/'system_a.img','/system/bin/init')
    require(hashlib.sha256(original).hexdigest()=='9c6d33419ac64c7938c117fc84f99ddd9bd03fcd16438d6e1085fbf7a529326a','Google init differs from reviewed bytes')
    b=bytearray(original);off=0x1154e5
    require(b[off:off+20]==bytes.fromhex('e846981a0083f8017422bf01000000e847981a00'),'Google init instruction signature differs')
    b[0x1154ec]=0;b[0x1154f0]=0;put(entries,'gbrunch-init-permissive',bytes(b),0o755)
    rows=[]
    for name,expected,offset in [('libgbm.so','64a0f2537a5917822cb3f538dc74229e7ccf4ca45a30265bb97f742678ba294e',0x18ea7),('libminigbm_gralloc.so','d48536951fd0e9643e71a5c8843e90833ce3e212e182782185470e2fbbfad673',0x14ea7)]:
        b=bytearray(cat(tools,parts/'vendor_a.img','/lib64/'+name));require(hashlib.sha256(b).hexdigest()==expected,'Minigbm source hash changed')
        require(b[offset-2:offset]==b'\x48\xbe' and struct.unpack_from('<Q',b,offset)[0]==0x100200021,'Minigbm mask instruction changed')
        struct.pack_into('<Q',b,offset,0x100200021|(1<<(0x7d51-0x7d40)));put(entries,'gbrunch-minigbm/'+name,bytes(b));rows.append(name+' '+expected+' '+hashlib.sha256(b).hexdigest())
    put(entries,'gbrunch-minigbm.cfg',('\n'.join(rows)+'\n').encode())
    put(entries,'gbrunch-hashes.cfg',('GB_VENDOR_HASH='+sha(vendor)+'\nGB_COMPAT_HASH='+sha(compat)+'\n').encode())
    init=(ROOT/'platform/init.template').read_text().replace('9e91b76d05d447ed7d964d88baacca2468de35e349bf9d0185753c9a31e5c086',rc_hash)
    run('sh','-n',input=init.encode());put(entries,'init',init.encode(),0o755)
    (out/'initrd-base.gz').write_bytes(gzip.compress(write_cpio(entries),mtime=0))

def build(args):
    assets=args.assets.resolve();out=args.out.resolve();require(not out.exists(),'Output exists; choose a new directory (nothing is deleted automatically)')
    require(not any(c.isspace() for c in str(out)),'Use a build directory without spaces (debugfs command files)')
    verify_assets(assets);out.mkdir(parents=True)
    parts=args.parts_dir
    if parts is None:
        require(args.recovery is not None,'Supply --recovery ZIP or --parts-dir DIR');parts=out/'parts';extract_parts(args.recovery,parts)
    parts=parts.resolve();pins=json.loads((ROOT/'profiles/parts.json').read_text())
    for name,row in pins.items():
        p=regular(parts/(name+'.img'));require(p.stat().st_size==row['bytes'] and sha(p)==row['sha256'],'Logical partition checksum failed: '+name)
    tools=build_tool_wrappers(assets,out)
    # Plain concatenation is intentional: stage0/dmctl use the explicit layout.
    order=['system_a','product_a','system_ext_a','vendor_a','system_dlkm_a','vendor_dlkm_a'];rows=[];start=0
    with (out/'super.img').open('xb') as f:
        for name in order:
            p=parts/(name+'.img');require(p.stat().st_size%512==0,'Unaligned EROFS image')
            sectors=p.stat().st_size//512;rows.append('%s %d %d'%(name,start,sectors));start+=sectors
            with p.open('rb') as src:shutil.copyfileobj(src,f,8*MiB)
    (out/'super.layout').write_text('\n'.join(rows)+'\n')
    require((out/'super.img').stat().st_size<4*(1<<30),'Super image exceeds FAT32 file limit')
    vendor=vendor_view(parts,out,tools);compat,rc_hash=compatibility(assets,out);ramdisk(parts,out,assets,tools,vendor,compat,rc_hash)
    shutil.copyfile(assets/'kernel',out/'kernel');shutil.copyfile(assets/'upstream/runtime/internal-BOOTX64.EFI',out/'BOOTX64.EFI')
    shutil.copytree(assets/'boot-tools',out/'boot-tools')
    files={}
    for name in ['super.img','super.layout','vendor.erofs','compat.ext4','initrd-base.gz','kernel','BOOTX64.EFI']:
        p=out/name;files[name]={'bytes':p.stat().st_size,'sha256':sha(p)}
    for p in (out/'boot-tools').rglob('*'):
        if p.is_file():files[str(p.relative_to(out))]={'bytes':p.stat().st_size,'sha256':sha(p)}
    save(out/'payload.json',{'format':'gbook60p-payload-v1','profile':json.loads((ROOT/'profiles/motobook60pro.json').read_text()),'assets_manifest':sha(assets/'MANIFEST.json'),'recovery':json.loads((ROOT/'profiles/recovery.json').read_text()),'files':files,'physical_boot_verified':False})
    print('Built and verified local payload: '+str(out),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--assets',type=pathlib.Path,default=ROOT/'assets');p.add_argument('--recovery',type=pathlib.Path);p.add_argument('--parts-dir',type=pathlib.Path);p.add_argument('--out',type=pathlib.Path,default=ROOT/'work/payload');build(p.parse_args())
