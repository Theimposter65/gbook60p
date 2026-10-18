"""Read-only installation prerequisites. Never downloads or changes hardware."""
import json,shutil,subprocess,pathlib,os,platform
from common import ROOT
import hardware
TOOLS=['python3','mke2fs','e2fsck','debugfs','mkfs.fat','fsck.fat','mcopy','mmd','findmnt','lsblk','efibootmgr','mokutil','partprobe','udevadm']
def main():
    info=hardware.inspect();print(json.dumps(info,indent=2));missing=[t for t in TOOLS if shutil.which(t) is None]
    print('\n'+subprocess.check_output(['lsblk','-d','-o','NAME,SIZE,MODEL,SERIAL,TRAN'],text=True))
    problems=[]
    if 'microsoft' in platform.release().lower():problems.append('WSL cannot install to physical disks. Boot a Linux live USB.')
    if missing:problems.append('Missing tools: '+', '.join(missing))
    try:hardware.validate(info)
    except Exception as e:problems.append(str(e))
    if problems:
        for s in problems:print('CHECK: '+s)
        raise SystemExit(1)
    print('Hardware and host tools match the supported installation profile. No disks changed.')
if __name__=='__main__':main()
