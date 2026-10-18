#!/usr/bin/env python3
"""Plan/install to unallocated NVMe space; existing partition contents are never written."""
import argparse,fcntl,gzip,hashlib,json,os,pathlib,re,shlex,shutil,stat,struct,subprocess,tempfile,time,uuid
from common import ROOT,MiB,GiB,require,sha,digest,regular,save,run,read_cpio,write_cpio,put
from storage import ESP,BASIC,LINUX,capacity,identity,unmounted,read_layout,allocate,validate_allocation,gpt_payload,write_all,BoundedWriter
import hardware

def sizes(gib):
    require(type(gib) is int and 16<=gib<=512,'Choose 16..512 GiB of Android storage')
    return [512*MiB,6144*MiB,gib*GiB+1536*MiB]
def payload(path):
    path=pathlib.Path(path).resolve();manifest=regular(path/'payload.json');data=json.loads(manifest.read_text())
    require(data['format']=='gbook60p-payload-v1','Unknown payload format')
    required={'super.img','super.layout','vendor.erofs','compat.ext4','initrd-base.gz','kernel','BOOTX64.EFI'}
    require(required.issubset(data['files']),'Incomplete payload manifest')
    require(data['recovery']==json.loads((ROOT/'profiles/recovery.json').read_text()),'Wrong recovery profile')
    require(data['assets_manifest']==json.loads((ROOT/'profiles/assets.json').read_text())['manifest_sha256'],'Wrong precompiled asset profile')
    for n,row in data['files'].items():
        p=pathlib.PurePosixPath(n);require(not p.is_absolute() and '..' not in p.parts,'Unsafe payload path')
        f=regular(path/p);require(f.stat().st_size==row['bytes'] and sha(f)==row['sha256'],'Payload checksum mismatch: '+n)
    require(data['files']['kernel']['sha256']==json.loads((ROOT/'profiles/assets.json').read_text())['kernel_sha256'],'Wrong kernel')
    return data,sha(manifest)
def same_disk_source(path,target):
    """Refuse build/backup storage on any partition of the destination."""
    dev=subprocess.check_output(['findmnt','-n','-o','MAJ:MIN','-T',str(path)],text=True).strip()
    fs=subprocess.check_output(['findmnt','-n','-o','FSTYPE','-T',str(path)],text=True).strip()
    require(fs in ['ext4','btrfs','xfs'],'Keep the kit and backups on a persistent external Linux filesystem (ext4 recommended)')
    require(re.fullmatch(r'\d+:\d+',dev),'Cannot identify filesystem containing '+str(path))
    node=pathlib.Path('/sys/dev/block')/dev
    require(node.exists(),'Cannot establish persistent block backing for '+str(path))
    require(target['sysfs'] not in str(node.resolve()),'Payload, work and backup must be on a separate external disk')

def make_plan(args):
    info=hardware.validate(hardware.inspect());ti=identity(args.disk);unmounted(ti['path'])
    data,mh=payload(args.payload);same_disk_source(args.payload,ti)
    layout=read_layout(ti['path']);require(any(p['type_guid']==ESP for p in layout['parts']),'Existing Windows EFI partition required')
    require(any(p['type_guid']==BASIC for p in layout['parts']),'Existing Windows data partition required')
    require(not any(p['name'].startswith('GB6P_') for p in layout['parts']),'Googlebook already installed on this disk; fresh installer refuses to replace it')
    sid=uuid.uuid4().hex[:6].upper();labels={'efi':'G6PE_'+sid,'sys':'G6PS_'+sid,'data':'G6PD_'+sid}
    new=allocate(layout,sizes(args.userdata_gib),['GB6P_EFI','GB6P_SYS','GB6P_DATA'],[ESP,BASIC,LINUX])
    value=dict(format='gbook60p-plan-v1',target=ti,hardware=info,payload=str(args.payload.resolve()),payload_manifest_sha256=mh,target_gpt_sha256=layout['hash'],disk_guid=layout['disk_guid'],existing_partitions=layout['parts'],new_partitions=new,labels=labels,userdata_gib=args.userdata_gib,boot_order='Existing order retained; new Googlebook entry appended')
    value['plan_sha256']=digest(value);require(not args.plan.exists(),'Plan exists; use a new filename');save(args.plan,value);args.plan.chmod(0o600)
    print(json.dumps({'plan':str(args.plan),'disk':ti['path'],'serial':ti['serial'],'userdata_gib':args.userdata_gib,'new_partitions':new,'existing_partitions':'preserved','next':'Review this plan, then run install with this --plan and an external --backup directory'},indent=2))

def personalize(base,plan):
    require(set(plan['labels'])=={'efi','sys','data'},'Missing or unexpected label roles')
    require(all(re.fullmatch(prefix+r'[0-9A-F]{6}',plan['labels'][role]) for role,prefix in [('efi','G6PE_'),('sys','G6PS_'),('data','G6PD_')]),'Unexpected filesystem label')
    entries=read_cpio(gzip.decompress(base));efi,system,data=plan['new_partitions']
    cfg={'HY_SERIAL':plan['target']['serial'],'HY_DISK_GUID':plan['disk_guid'],'HY_DISK_SECTORS':plan['target']['bytes']//512,'HY_SYS_NUMBER':system['index'],'HY_SYS_LABEL':plan['labels']['sys'],'HY_DATA_LABEL':plan['labels']['data'],'HY_DATA_NUMBER':data['index'],'HY_DATA_GUID':data['guid'],'HY_DATA_START':data['offset']//512,'HY_DATA_SECTORS':data['bytes']//512,'HY_PARTITION_COUNT':len(plan['existing_partitions'])+3,'GB_USERDATA_BYTES':plan['userdata_gib']*GiB}
    put(entries,'hy-targets.cfg',(''.join(k+'='+shlex.quote(str(v))+'\n' for k,v in cfg.items())).encode())
    protected=[*plan['existing_partitions'],efi,system]
    rows=['%d %s %d %d'%(p['index'],p['guid'],p['offset']//512,p['bytes']//512) for p in protected]
    put(entries,'gbook-protected.cfg',('\n'.join(rows)+'\n').encode())
    return gzip.compress(write_cpio(entries),mtime=0)

def efi_loader(blob,label):
    # GRUB's embedded memdisk is an uncompressed tar. Same-size substitution
    # keeps its tar entry length and PE sections intact.
    old=b'search --no-floppy --label --set=root GBRUNCH_INT\n'
    new=('search --no-floppy --label --set=root '+label+'\n').encode()
    require(len(old)==len(new) and blob.count(old)==1,'Unexpected GRUB redirect')
    b=bytearray(blob.replace(old,new));pe=struct.unpack_from('<I',b,0x3c)[0];off=pe+4+20+64;b[off:off+4]=bytes(4);total=0
    for i in range(0,len(b),2):total+=int.from_bytes(b[i:i+2],'little');total=(total&0xffff)+(total>>16)
    total=(total&0xffff)+(total>>16);struct.pack_into('<I',b,off,(total&0xffff)+len(b))
    return bytes(b)

def sparse(path,length):
    with pathlib.Path(path).open('xb') as f:f.truncate(length)
def ext4(path,size,label,android=False,source=None):
    sparse(path,size)
    args=['mke2fs','-q','-t','ext4','-b','4096','-m','0','-L',label,'-E','nodiscard,lazy_itable_init=0,lazy_journal_init=0'+(',encoding=utf8' if android else '')]
    if android:args+=['-O','casefold,quota,project,verity,metadata_csum_seed']
    if source:args+=['-d',str(source)]
    run(*args,path)
def fat_copy(image,source,dest):run('mcopy','-o','-i',image,source,dest,stdout=subprocess.DEVNULL)
def make_images(plan,work):
    src=pathlib.Path(plan['payload']);boot=work/'boot';boot.mkdir();(boot/'initrd.gz').write_bytes(personalize((src/'initrd-base.gz').read_bytes(),plan))
    (boot/'BOOTX64.EFI').write_bytes(efi_loader((src/'BOOTX64.EFI').read_bytes(),plan['labels']['efi']))
    cfg=(ROOT/'platform/grub.template').read_bytes();(boot/'grub.cfg').write_bytes(cfg)
    shutil.copyfile(src/'kernel',boot/'kernel')
    result=[]
    for role,p in zip(['efi','sys'],plan['new_partitions'][:2]):
        image=work/(role+'.fat');sparse(image,p['bytes']);run('mkfs.fat','-F','32','-n',plan['labels'][role],image,stdout=subprocess.DEVNULL)
        for folder in ['::/EFI','::/EFI/BOOT','::/EFI/GBRUNCH']:run('mmd','-i',image,folder)
        fat_copy(image,boot/'BOOTX64.EFI','::/EFI/BOOT/BOOTX64.EFI')
        for n in ['kernel','initrd.gz','grub.cfg']:fat_copy(image,boot/n,'::/EFI/GBRUNCH/'+n)
        if role=='sys':
            run('mmd','-i',image,'::/gbos');run('mmd','-i',image,'::/gbos/firmware')
            for n in ['super.img','super.layout']:fat_copy(image,src/n,'::/gbos/'+n)
            for n in ['vendor.erofs','compat.ext4']:fat_copy(image,src/n,'::/EFI/GBRUNCH/'+n)
            run('mcopy','-s','-i',image,src/'boot-tools','::/gbos/installer')
        run('fsck.fat','-n',image,stdout=subprocess.DEVNULL)
        # Read back every file copied, including both boot-file copies.
        wanted={'/EFI/BOOT/BOOTX64.EFI':boot/'BOOTX64.EFI',**{'/EFI/GBRUNCH/'+n:boot/n for n in ['kernel','initrd.gz','grub.cfg']}}
        if role=='sys':
            wanted.update({'/gbos/'+n:src/n for n in ['super.img','super.layout']});wanted.update({'/EFI/GBRUNCH/'+n:src/n for n in ['vendor.erofs','compat.ext4']})
            wanted.update({'/gbos/installer/'+str(p.relative_to(src/'boot-tools')):p for p in (src/'boot-tools').rglob('*') if p.is_file()})
        for dest,file in wanted.items():
            h=hashlib.sha256();proc=subprocess.Popen(['mcopy','-i',str(image),'::'+dest,'-'],stdout=subprocess.PIPE)
            for b in iter(lambda:proc.stdout.read(8*MiB),b''):h.update(b)
            require(proc.wait()==0 and h.hexdigest()==sha(file),'FAT file readback mismatch: '+dest)
        result.append(image)
    staging=work/'backing';inner=staging/'.gbrunch-native';inner.mkdir(parents=True,mode=0o700);inner.chmod(0o700)
    ext4(inner/'data.ext4',plan['userdata_gib']*GiB,'GBRUNCH_DATA',android=True)
    ext4(inner/'metadata.ext4',32*MiB,'GBRUNCH_META')
    sparse(inner/'misc.bin',MiB)
    entries=read_cpio(gzip.decompress((src/'initrd-base.gz').read_bytes()))
    (inner/'logs.fat').write_bytes(gzip.decompress(entries['gbrunch-logs.fat.gz'][1]));(inner/'logs').mkdir(mode=0o700)
    for p in inner.iterdir():
        os.chown(p,0,0)
        if p.is_file():p.chmod(0o600)
    os.chown(inner,0,0)
    image=work/'data.ext4';ext4(image,plan['new_partitions'][2]['bytes'],plan['labels']['data'],source=staging)
    run('e2fsck','-fn',image,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    # Verify the populated root image without mounting it or trusting mke2fs -d.
    for name,size in [('data.ext4',plan['userdata_gib']*GiB),('metadata.ext4',32*MiB),('misc.bin',MiB),('logs.fat',64*MiB)]:
        s=subprocess.check_output(['debugfs','-R','stat /.gbrunch-native/'+name,str(image)],text=True,stderr=subprocess.DEVNULL)
        require(re.search(r'Size:\s+'+str(size)+r'\b',s) and re.search(r'User:\s+0\s+Group:\s+0',s),'Fresh Android backing image validation failed: '+name)
    result.append(image)
    return result

def range_hash(fd,offset,length):
    h=hashlib.sha256()
    while length:
        b=os.pread(fd,min(length,8*MiB),offset);require(b,'Short readback');h.update(b);offset+=len(b);length-=len(b)
    return h.hexdigest()
def copy_and_verify(fd,parts,images):
    writer=BoundedWriter(fd,parts)
    for part,image in zip(parts,images):
        require(regular(image).stat().st_size==part['bytes'],'Prepared image has wrong size')
        h=hashlib.sha256();offset=part['offset'];done=0;report=0
        with image.open('rb') as f:
            while True:
                b=f.read(8*MiB)
                if not b:break
                writer.write(offset,b);h.update(b);offset+=len(b);done+=len(b)
                if done>=report:print('%s: %.1f / %.1f GiB written'%(part['name'],done/GiB,part['bytes']/GiB),flush=True);report=done+4*GiB
        os.fsync(fd);print('Verifying '+part['name'],flush=True)
        require(range_hash(fd,part['offset'],part['bytes'])==h.hexdigest(),'Physical partition readback failed')

def apply(args):
    require(os.geteuid()==0,'Run install as root from a Linux live USB')
    plan=json.loads(regular(args.plan).read_text());seal=dict(plan);expected=seal.pop('plan_sha256');require(digest(seal)==expected and plan['format']=='gbook60p-plan-v1','Plan checksum/format mismatch')
    hardware.validate(hardware.inspect());target=identity(plan['target']['path']);require(target==plan['target'],'Disk identity changed since planning');unmounted(target['path'])
    layout=read_layout(target['path']);require(layout['hash']==plan['target_gpt_sha256'] and layout['disk_guid']==plan['disk_guid'] and layout['parts']==plan['existing_partitions'],'GPT changed since planning')
    validate_allocation(layout,plan['new_partitions'],sizes(plan['userdata_gib']))
    require([p['name'] for p in plan['new_partitions']]==['GB6P_EFI','GB6P_SYS','GB6P_DATA'],'Unexpected partition role names')
    data,mh=payload(plan['payload']);require(mh==plan['payload_manifest_sha256'],'Payload manifest changed')
    require(plan['labels']['efi']!=plan['labels']['sys']!=plan['labels']['data'],'Filesystem label roles collide')
    backup=args.backup.resolve();require(not backup.exists(),'Backup directory exists; choose a new directory')
    backup.parent.mkdir(parents=True,exist_ok=True);same_disk_source(backup.parent,target);same_disk_source(plan['payload'],target)
    require(os.statvfs(backup.parent).f_bavail*os.statvfs(backup.parent).f_frsize>12*GiB,'Need 12 GiB free on the external build/backup filesystem')
    print('Target: '+target['path']+'\nSerial: '+target['serial']+'\nExisting partitions are preserved. New Android storage: '+str(plan['userdata_gib'])+' GiB.',flush=True)
    require(os.isatty(0),'Install confirmation must be typed in an interactive terminal')
    require(input('Type the complete disk serial to install: ').strip()==target['serial'],'Disk serial did not match; no disk writes performed')
    backup.mkdir(mode=0o700);save(backup/'plan.json',plan);(backup/'primary-gpt.bin').write_bytes(layout['mbr']+layout['header']+layout['table']);(backup/'backup-gpt.bin').write_bytes(layout['tail'])
    boot_before=subprocess.check_output(['efibootmgr'],text=True);(backup/'firmware-before.txt').write_text(boot_before)
    work=backup/'prepared';work.mkdir();save(backup/'status.json',{'phase':'preparing regular files','gpt_committed':False})
    images=make_images(plan,work)
    # Revalidate after preparation and immediately before exclusive write access.
    require(identity(target['path'])==target and read_layout(target['path'])['hash']==layout['hash'],'Target changed during image preparation');unmounted(target['path'])
    fd=os.open(target['path'],os.O_RDWR|os.O_EXCL);gpt_started=False;committed=False
    try:
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        require(identity(target['path'])==target and read_layout(target['path'])['hash']==layout['hash'],'Target changed after locking')
        save(backup/'status.json',{'phase':'writing only newly allocated extents','gpt_committed':False})
        copy_and_verify(fd,plan['new_partitions'],images)
        require(read_layout(target['path'])['hash']==layout['hash'],'Existing GPT changed during copying')
        table,primary,bh=gpt_payload(layout,plan['new_partitions']);gpt_started=True
        # Backup table first; the protective MBR and existing partition entries
        # remain byte-identical. Recovery copies were synced before this point.
        write_all(fd,table,(layout['backup']-32)*512);write_all(fd,bh,layout['backup']*512);os.fsync(fd)
        write_all(fd,table,1024);write_all(fd,primary,512);os.fsync(fd)
        new=read_layout(target['path'])
        require(all(p in new['parts'] for p in layout['parts']) and new['parts']==sorted([*layout['parts'],*plan['new_partitions']],key=lambda p:p['index']),'GPT readback differs')
        committed=True
    except BaseException:
        if gpt_started and not committed:
            write_all(fd,layout['tail'],(layout['backup']-32)*512);os.fsync(fd);write_all(fd,layout['table'],1024);write_all(fd,layout['header'],512);os.fsync(fd)
            require(read_layout(target['path'])['hash']==layout['hash'],'GPT restore failed; retain backup and do not reboot')
        save(backup/'status.json',{'phase':'failed; keep the backup directory','gpt_committed':committed,'existing_partition_contents_written':False})
        raise
    finally:os.close(fd)
    save(backup/'status.json',{'phase':'installed and readback verified; registering boot entry','gpt_committed':True})
    # Registration failure does not roll back verified data or modify Windows.
    # A distinct new ESP also contains the standard /EFI/BOOT fallback path.
    try:
        run('partprobe',target['path']);run('udevadm','settle')
        before=set(re.findall(r'^Boot([0-9A-Fa-f]{4})',boot_before,re.M))
        run('efibootmgr','--create-only','--disk',target['path'],'--part',str(plan['new_partitions'][0]['index']),'--label','Googlebook OS (Motobook 60 Pro)','--loader',r'\EFI\BOOT\BOOTX64.EFI')
        after=subprocess.check_output(['efibootmgr'],text=True);created=set(re.findall(r'^Boot([0-9A-Fa-f]{4})',after,re.M))-before;require(len(created)==1,'Cannot identify the new UEFI entry')
        order=re.search(r'^BootOrder:\s*(\S+)',boot_before,re.M);require(order is not None,'Cannot read original BootOrder')
        run('efibootmgr','--bootorder',order[1]+','+next(iter(created)))
        final_boot=subprocess.check_output(['efibootmgr'],text=True);(backup/'firmware-after.txt').write_text(final_boot)
        require(re.search(r'^BootOrder:\s*(\S+)',final_boot,re.M)[1].upper()==(order[1]+','+next(iter(created))).upper(),'BootOrder readback differs; inspect firmware-after.txt')
        save(backup/'status.json',{'phase':'complete; choose Googlebook in F12 boot menu','gpt_committed':True,'existing_boot_order_retained':True,'native_boot_tested':False})
    except Exception as e:
        save(backup/'status.json',{'phase':'files installed; UEFI entry registration needs attention','gpt_committed':True,'error':str(e),'fallback':r'New EFI partition: \EFI\BOOT\BOOTX64.EFI'})
        print('Files are verified; UEFI registration needs attention. See status.json. Do not reinstall blindly.',flush=True);return
    print('Installation complete. Use F12 to select Googlebook OS. Backup: '+str(backup),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    a=sub.add_parser('plan');a.add_argument('--disk',required=True,type=pathlib.Path);a.add_argument('--payload',type=pathlib.Path,default=ROOT/'work/payload');a.add_argument('--userdata-gib',type=int,default=120);a.add_argument('--plan',type=pathlib.Path,default=ROOT/'work/install-plan.json')
    a=sub.add_parser('install');a.add_argument('--plan',required=True,type=pathlib.Path);a.add_argument('--backup',required=True,type=pathlib.Path)
    args=p.parse_args()
    try:make_plan(args) if args.command=='plan' else apply(args)
    except (ValueError,OSError,subprocess.CalledProcessError) as e:p.exit(1,'Stopped: '+str(e)+'\n')
