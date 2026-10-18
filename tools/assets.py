"""Explicit, hash-pinned private-release retrieval and safe extraction."""
import argparse,json,pathlib,subprocess,tarfile,tempfile,os
from common import ROOT,sha,require,regular
from build import verify_assets
def main():
    p=argparse.ArgumentParser(description=__doc__);g=p.add_mutually_exclusive_group(required=True);g.add_argument('--archive',type=pathlib.Path);g.add_argument('--download',action='store_true');args=p.parse_args()
    pin=json.loads((ROOT/'profiles/assets.json').read_text());target=ROOT/'assets'
    if target.exists():
        verify_assets(target);print('Existing assets match the pinned release; nothing changed.');return
    archive=args.archive
    if args.download:
        print('Downloading private release %s/%s: %.1f MB'%(pin['repository'],pin['tag'],pin['bytes']/1e6),flush=True)
        cache=ROOT/'cache';cache.mkdir(exist_ok=True);archive=cache/pin['filename']
        if not archive.exists():subprocess.run(['gh','release','download',pin['tag'],'--repo',pin['repository'],'--pattern',pin['filename'],'--dir',str(cache)],check=True)
    require(regular(archive).stat().st_size==pin['bytes'] and sha(archive)==pin['sha256'],'Asset archive checksum failed')
    with tempfile.TemporaryDirectory(prefix='gbook-assets-',dir=ROOT) as d:
        root=pathlib.Path(d)
        with tarfile.open(archive) as tf:
            members=tf.getmembers();require(len({m.name for m in members})==len(members),'Duplicate archive members')
            for m in members:
                path=pathlib.PurePosixPath(m.name)
                require(m.isfile() and not path.is_absolute() and '..' not in path.parts,'Unsupported or unsafe asset member')
                dest=root/path;dest.parent.mkdir(parents=True,exist_ok=True)
                with tf.extractfile(m) as src,dest.open('xb') as out:
                    while True:
                        b=src.read(1<<20)
                        if not b:break
                        out.write(b)
                dest.chmod(m.mode&0o777)
        verify_assets(root);root.rename(target)
    print('Precompiled assets verified: '+str(target))
if __name__=='__main__':main()
