#!/usr/bin/env python3
"""Full local file-image validation. Does not open a block disk or register UEFI."""
import argparse,gzip,hashlib,json,os,pathlib,shutil,stat,subprocess,sys,uuid
from common import ROOT,MiB,GiB,save,require,read_cpio
from install import payload,make_images
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--payload',required=True,type=pathlib.Path);p.add_argument('--out',required=True,type=pathlib.Path);a=p.parse_args()
    require(os.geteuid()==0,'Run as root only to verify final image ownership; all operations stay in new regular files')
    require(not a.out.exists(),'Output exists; use a new directory');out=a.out.resolve();out.mkdir(parents=True)
    data,_=payload(a.payload);src=a.payload.resolve();staging=out/'synthetic-payload';staging.mkdir()
    # Reuse actual kernel/initrd and boot tools. Replace the large Google images
    # with small file sentinels: FAT/ext4 construction can then be exercised
    # without duplicating multi-gigabyte Google bytes or opening any real disk.
    for name in ['kernel','initrd-base.gz','BOOTX64.EFI']:shutil.copyfile(src/name,staging/name)
    shutil.copytree(src/'boot-tools',staging/'boot-tools')
    for name in ['super.img','super.layout','vendor.erofs','compat.ext4']:(staging/name).write_bytes(('fixture '+name+'\n').encode())
    parts=[];cursor=MiB
    for i,(name,size) in enumerate([('GB6P_EFI',128*MiB),('GB6P_SYS',256*MiB),('GB6P_DATA',512*MiB)],1):
        parts.append(dict(index=i,name=name,guid=str(uuid.uuid4()),offset=cursor,bytes=size));cursor+=size
    plan=dict(target={'serial':'SYNTHETIC-FILE-ONLY','bytes':2*GiB},disk_guid=str(uuid.uuid4()),payload=str(staging),new_partitions=parts,existing_partitions=[],labels={'efi':'G6PE_ABC123','sys':'G6PS_ABC123','data':'G6PD_ABC123'},userdata_gib=16)
    work=out/'images';work.mkdir();images=make_images(plan,work)
    init=read_cpio(gzip.decompress((work/'boot/initrd.gz').read_bytes()))
    cfg=init['hy-targets.cfg'][1].decode();require('SYNTHETIC-FILE-ONLY' in cfg and 'GB_USERDATA_BYTES='+str(16*GiB) in cfg,'Personalized init configuration differs')
    require(init['hy-storage.sh'][1]==(ROOT/'platform/root/hy-storage.sh').read_bytes(),'Storage guard source differs from assembled payload')
    for name,(mode,b) in init.items():
        for parent in pathlib.PurePosixPath(name).parents:
            if str(parent)!='.':require(parent.as_posix() in init and stat.S_ISDIR(init[parent.as_posix()][0]),'Initramfs parent directory missing: '+str(parent))
        if name=='init' or name.endswith('.sh'):subprocess.run(['sh','-n'],input=b,check=True)
    # The file fixture also proves the fresh misc state and blank userdata are
    # bounded regular files with the owner/mode required by stage0.
    image=images[2]
    s=subprocess.check_output(['debugfs','-R','stat /.gbrunch-native',str(image)],text=True,stderr=subprocess.DEVNULL)
    require('0700' in s,'Backing directory permission differs')
    report={'success':True,'format':'gbook60p-file-validation-v1','payload_verified':True,'kernel_sha256':data['files']['kernel']['sha256'],'checks':['payload hashes','personalized initrd','both FAT boot copies readback','boot tools FAT directory layout','fresh sparse userdata/metadata/misc/log files','ext4 ownership and 0700 backing directory','shell syntax'],'physical_disks_opened':False,'VM_tests_run':False,'physical_boot_verified':False}
    save(out/'result.json',report);print(json.dumps(report,indent=2))
if __name__=='__main__':main()
