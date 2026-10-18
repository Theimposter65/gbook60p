"""Check only tracked source paths; never print matched secret values."""
import pathlib,re,subprocess,sys
from common import ROOT
def main():
    names=subprocess.check_output(['git','-C',str(ROOT),'ls-files','-z']).decode().split('\0');bad=[];size=0
    private=re.compile(rb'(?:gh[pousr]_[A-Za-z0-9_]{25,}|github_pat_[A-Za-z0-9_]{25,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)')
    forbidden={'.img','.ext4','.fat','.erofs','.vhdx','.qcow2','.zip','.apk','.ko','.so','.pem','.key'}
    for name in filter(None,names):
        p=ROOT/name
        if p.is_symlink() or not p.is_file():bad.append(name+': unsupported file type');continue
        b=p.read_bytes();size+=len(b)
        if p.suffix.lower() in forbidden or name.startswith(('assets/','dist/','cache/','work/','backup/')):bad.append(name+': generated/private payload')
        if len(b)>2*(1<<20):bad.append(name+': unexpectedly large source file')
        if private.search(b):bad.append(name+': possible credential')
        if re.search(rb'[A-Z]:\\Users\\[^\\\r\n ]+|/mnt/[a-z]/(?:VMs|Users)/|/opt/(?:googlebook)/',b):bad.append(name+': private workstation path')
    if size>4*(1<<20):bad.append('Tracked source exceeds 4 MiB budget')
    if bad:
        print('\n'.join(bad));raise SystemExit(1)
    print('Tracked source checked: %d files, %.2f MiB; no generated payloads, workstation paths or credential patterns.'%(len(list(filter(None,names))),size/(1<<20)))
if __name__=='__main__':main()
