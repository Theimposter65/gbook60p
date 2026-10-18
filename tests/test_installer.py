"""Regular-file fixtures only. No VM, physical disks, firmware or mounts."""
import hashlib,os,pathlib,struct,sys,tempfile,unittest,uuid,zlib,gzip,stat,subprocess
ROOT=pathlib.Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
from common import MiB,GiB,digest,read_cpio,write_cpio,put
from storage import read_layout,allocate,validate_allocation,gpt_payload,BoundedWriter,identity,ESP,BASIC,LINUX
from install import personalize,efi_loader,sizes

def fixture(path):
    size=64*MiB
    with path.open('wb') as f:f.truncate(size)
    m=bytearray(512);m[450]=0xee;struct.pack_into('<II',m,454,1,size//512-1);m[510:]=b'\x55\xaa'
    t=bytearray(16384)
    for i,(typ,name,start,length) in enumerate([(ESP,'Windows EFI',MiB,MiB),(BASIC,'Windows',2*MiB,8*MiB)]):
        off=i*128;t[off:off+16]=uuid.UUID(typ).bytes_le;t[off+16:off+32]=uuid.uuid4().bytes_le;struct.pack_into('<QQQ',t,off+32,start//512,(start+length)//512-1,0);n=name.encode('utf-16le');t[off+56:off+56+len(n)]=n
    backup=size//512-1;h=bytearray(512);h[:8]=b'EFI PART';struct.pack_into('<IIIIQQQQ',h,8,0x10000,92,0,0,1,backup,34,backup-33);h[56:72]=uuid.uuid4().bytes_le;struct.pack_into('<QIII',h,72,2,128,128,zlib.crc32(t));struct.pack_into('<I',h,16,zlib.crc32(h[:92]))
    bh=bytearray(h);struct.pack_into('<QQ',bh,24,backup,1);struct.pack_into('<Q',bh,72,backup-32);bh[16:20]=bytes(4);struct.pack_into('<I',bh,16,zlib.crc32(bh[:92]))
    with path.open('r+b') as f:
        f.write(m);f.write(h);f.write(t);f.seek(backup*512-16384);f.write(t);f.write(bh);f.seek(MiB);f.write(b'WINDOWS_EFI_SENTINEL');f.seek(2*MiB);f.write(b'WINDOWS_DATA_SENTINEL')

class StorageTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.disk=pathlib.Path(self.tmp.name)/'fixture.raw';fixture(self.disk);self.layout=read_layout(self.disk)
        self.new=allocate(self.layout,[MiB,2*MiB,3*MiB],['GB6P_EFI','GB6P_SYS','GB6P_DATA'],[ESP,BASIC,LINUX])
    def test_file_cannot_be_live_install_target(self):
        with self.assertRaisesRegex(ValueError,'physical block'):identity(self.disk)
    def test_allocation_preserves_windows_and_existing_gpt_entries(self):
        validate_allocation(self.layout,self.new,[MiB,2*MiB,3*MiB]);t,h,bh=gpt_payload(self.layout,self.new)
        self.assertEqual(t[:256],self.layout['table'][:256])
        with self.disk.open('r+b') as f:
            f.seek(1024);f.write(t);f.seek(512);f.write(h);f.seek((self.layout['backup']-32)*512);f.write(t);f.write(bh)
        got=read_layout(self.disk);self.assertEqual(got['parts'][:2],self.layout['parts']);self.assertEqual(got['parts'][2:],self.new)
        with self.disk.open('rb') as f:f.seek(2*MiB);self.assertEqual(f.read(21),b'WINDOWS_DATA_SENTINEL')
    def test_crc_failures_stop(self):
        for off in [528,1100,self.layout['backup']*512+16,(self.layout['backup']-32)*512+64]:
            with self.subTest(offset=off):
                fixture(self.disk)
                with self.disk.open('r+b') as f:f.seek(off);b=f.read(1);f.seek(off);f.write(bytes([b[0]^1]))
                with self.assertRaises(ValueError):read_layout(self.disk)
    def test_overlap_and_tampered_size_rejected(self):
        for key,value in [('offset',2*MiB),('bytes',9*MiB),('index',1),('guid',self.layout['parts'][0]['guid'])]:
            parts=[dict(p) for p in self.new];parts[0][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):validate_allocation(self.layout,parts,[MiB,2*MiB,3*MiB])
    def test_full_disk_refuses_to_resize(self):
        with self.assertRaisesRegex(ValueError,'unallocated'):allocate(self.layout,[32*MiB]*3,['a','b','c'],[ESP,BASIC,LINUX])
    def test_writer_cannot_escape_new_extents(self):
        with self.disk.open('r+b',buffering=0) as f:
            w=BoundedWriter(f.fileno(),self.new)
            for offset,size in [(2*MiB,32),(self.new[0]['offset']-1,2),(self.new[-1]['offset']+self.new[-1]['bytes']-1,2)]:
                with self.assertRaises(ValueError):w.write(offset,b'x'*size)
            w.write(self.new[0]['offset'],b'new-only')
            f.seek(2*MiB);self.assertEqual(f.read(21),b'WINDOWS_DATA_SENTINEL')
    def test_personalization_uses_plan_identities_and_shell_quoting(self):
        plan={'target':{'serial':"serial'with;literal" ,'bytes':64*MiB},'disk_guid':self.layout['disk_guid'],'new_partitions':self.new,'existing_partitions':self.layout['parts'],'labels':{'efi':'G6PE_ABC123','sys':'G6PS_ABC123','data':'G6PD_ABC123'},'userdata_gib':120}
        base=write_cpio({'init':(stat.S_IFREG|0o755,b'owned-init')});b=personalize(gzip.compress(base),plan);got=read_cpio(gzip.decompress(b));cfg=got['hy-targets.cfg'][1].decode()
        self.assertIn('HY_DISK_GUID='+self.layout['disk_guid'],cfg);self.assertIn('GB_USERDATA_BYTES='+str(120*GiB),cfg);self.assertNotIn('serial\'with;literal\n',cfg)
        target=pathlib.Path(self.tmp.name)/'targets.cfg';target.write_text(cfg)
        value=subprocess.check_output(['sh','-c','. "$1"; printf "%s" "$HY_SERIAL"','fixture',str(target)],text=True)
        self.assertEqual(value,plan['target']['serial'])
        self.assertEqual(got['init'][1],b'owned-init');protected=got['gbook-protected.cfg'][1].decode();self.assertNotIn(self.new[2]['guid'],protected)
        for p in [*self.layout['parts'],*self.new[:2]]:self.assertIn(p['guid'],protected)
    def test_storage_sizes_include_overhead(self):
        self.assertEqual(sum(sizes(120)),128*GiB)
        for value in [0,15,513,True,1.5]:
            with self.assertRaises(ValueError):sizes(value)

class ArchiveTests(unittest.TestCase):
    def test_cpio_roundtrip_and_safety(self):
        entries={};put(entries,'etc/config',b'value');self.assertEqual(read_cpio(write_cpio(entries)),entries)
        for name in ['../escape','/absolute']:
            with self.assertRaises(ValueError):read_cpio(write_cpio({name:(stat.S_IFREG,b'bad')}))
    def test_grub_label_change_is_bounded(self):
        b=bytearray(1024);struct.pack_into('<I',b,0x3c,128);b+=b'search --no-floppy --label --set=root GBRUNCH_INT\n'
        got=efi_loader(bytes(b),'G6PE_A1B2C3');self.assertEqual(len(got),len(b));self.assertIn(b'--set=root G6PE_A1B2C3\n',got)
        with self.assertRaises(ValueError):efi_loader(bytes(b),'bad')
    def test_initramfs_includes_parent_directories_before_modules(self):
        blob=write_cpio({'lib/modules/test/xe.ko':(stat.S_IFREG|0o644,b'fixture')})
        got=read_cpio(blob)
        self.assertTrue(all(stat.S_ISDIR(got[n][0]) for n in ['lib','lib/modules','lib/modules/test']))
        self.assertLess(blob.index(b'lib/modules/test\0'),blob.index(b'lib/modules/test/xe.ko\0'))

if __name__=='__main__':unittest.main()
