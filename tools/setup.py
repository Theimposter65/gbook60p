#!/usr/bin/env python3
"""Guided native-Linux installation. Every download is explicitly requested."""
import json,os,pathlib,shlex,subprocess,sys,time,urllib.request
from common import ROOT,require,sha,regular
def command(*args):subprocess.run([str(a) for a in args],check=True)
def yes(prompt):return input(prompt+' [y/N] ').strip().lower()=='y'
def recovery():
    pin=json.loads((ROOT/'profiles/recovery.json').read_text())
    path=input('Path to the Lapis 16452207 recovery ZIP (Enter to download): ').strip()
    if path:return regular(pathlib.Path(path).expanduser().resolve())
    print('Google recovery: '+pin['url']+'\nDownload: %.2f GB, verified with pinned SHA-256.'%(pin['bytes']/1e9))
    require(yes('Download this recovery now?'),'Download cancelled')
    cache=ROOT/'cache';cache.mkdir(exist_ok=True);dst=cache/'lapis-16452207-recovery.zip'
    if dst.exists():
        require(sha(dst)==pin['sha256'],'Existing ZIP differs; preserved for inspection');return dst
    partial=dst.with_suffix('.zip.partial');require(not partial.exists(),'Partial download exists and was preserved; rename it before retrying')
    done=0;report=0
    with urllib.request.urlopen(pin['url'],timeout=120) as src,partial.open('xb') as out:
        while True:
            b=src.read(4<<20)
            if not b:break
            done+=len(b);require(done<=pin['bytes'],'Download exceeded pinned size');out.write(b)
            if done>=report:print('Downloaded %.2f / %.2f GB'%(done/1e9,pin['bytes']/1e9),flush=True);report=done+(256<<20)
    require(done==pin['bytes'] and sha(partial)==pin['sha256'],'Recovery checksum mismatch; partial retained')
    partial.rename(dst);return dst
def main():
    print('Googlebook OS for Motobook 60 Pro\nThis creates a fresh Android installation in unallocated space. Keep this kit on a separate external Linux filesystem.\n')
    command(sys.executable,ROOT/'tools/doctor.py')
    print('Need at least 128 GiB unallocated on the destination for 120 GiB Android storage. Windows partitions are not resized.')
    if not (ROOT/'assets').exists():
        pin=json.loads((ROOT/'profiles/assets.json').read_text());print('Precompiled release assets: %.1f MB from private GitHub repository %s'%(pin['bytes']/1e6,pin['repository']))
        local=ROOT/'dist'/pin['filename']
        if local.exists():command(sys.executable,ROOT/'tools/assets.py','--archive',local)
        else:
            require(yes('Download the pinned assets using GitHub CLI?'),'Asset download cancelled')
            command(sys.executable,ROOT/'tools/assets.py','--download')
    if not (ROOT/'work/payload/payload.json').exists():command(sys.executable,ROOT/'tools/build.py','--recovery',recovery())
    disk=input('Destination NVMe disk path from the list above (example /dev/nvme1n1): ').strip()
    gib=int(input('Android storage in GiB [120]: ').strip() or '120')
    sudo=[] if os.geteuid()==0 else ['sudo']
    plan=ROOT/'work'/('install-plan-'+time.strftime('%Y%m%d-%H%M%S')+'.json')
    command(*sudo,sys.executable,ROOT/'tools/install.py','plan','--disk',disk,'--userdata-gib',str(gib),'--plan',plan)
    print('Review the disk, serial and three new partition extents above. Existing partition contents are preserved.')
    require(yes('Proceed with this installation plan?'),'Plan saved; installation cancelled')
    backup=ROOT/'work'/('installation-'+time.strftime('%Y%m%d-%H%M%S'))
    command(*sudo,sys.executable,ROOT/'tools/install.py','install','--plan',plan,'--backup',backup)
if __name__=='__main__':
    try:main()
    except (ValueError,OSError,subprocess.CalledProcessError) as e:raise SystemExit('Stopped: '+str(e))
