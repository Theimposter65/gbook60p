"""Read-only checks. Profile mismatch stops installation before disk writes."""
import json,pathlib,platform,re,subprocess
from common import ROOT,require
def inspect(sysroot=pathlib.Path('/sys'),procroot=pathlib.Path('/proc')):
    def text(p):
        try:return p.read_text().strip()
        except OSError:return ''
    cfg=json.loads((ROOT/'profiles/motobook60pro.json').read_text())
    gpu=sysroot/'bus/pci/devices/0000:00:02.0'
    mem=re.search(r'MemTotal:\s+(\d+)',text(procroot/'meminfo'))
    cpu=text(procroot/'cpuinfo')
    return dict(machine=platform.machine(),vendor=text(sysroot/'class/dmi/id/sys_vendor'),product=text(sysroot/'class/dmi/id/product_name'),gpu_vendor=text(gpu/'vendor'),gpu_device=text(gpu/'device'),ram_kib=int(mem[1]) if mem else 0,uefi=(sysroot/'firmware/efi').is_dir(),cpu=next((r.split(':',1)[1].strip() for r in cpu.splitlines() if r.startswith('model name')),''),profile=cfg['name'])
def validate(info):
    cfg=json.loads((ROOT/'profiles/motobook60pro.json').read_text())
    require('microsoft' not in platform.release().lower(),'Boot a native Linux live USB; physical installation from WSL is disabled')
    require(info['machine']=='x86_64','Native x86-64 Linux required')
    require(info['vendor']==cfg['dmi_vendor'] and info['product']==cfg['dmi_product'],'This kit supports Motobook 60 Pro DMI 83NY only')
    require(info['gpu_vendor']==cfg['gpu']['vendor'] and info['gpu_device']==cfg['gpu']['device'],'GPU differs from the reviewed Xe/Minigbm profile')
    require(info['ram_kib']>=cfg['minimum_ram_kib'],'16 GB RAM required for the retained RAM payload')
    require(info['uefi'],'Boot the Linux live USB in UEFI mode')
    # mokutil is provided by the documented live environment.
    s=subprocess.check_output(['mokutil','--sb-state'],text=True)
    require('SecureBoot disabled' in s,'Disable Secure Boot in firmware first')
    return info
if __name__=='__main__':print(json.dumps(inspect(),indent=2))
