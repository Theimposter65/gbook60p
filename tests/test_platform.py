"""Run source-built helpers against synthetic sysfs; never host CPU or power policy."""
import json,os,pathlib,shutil,subprocess,sys,tempfile,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(str(v)+'\n')
@unittest.skipUnless(shutil.which('gcc'),'gcc required for native helper fixtures')
class PlatformTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.root=pathlib.Path(cls.tmp.name)
        for source,name in [('gbos-telemetry.c','telemetry'),('gbos-powerhint.c','powerhint')]:
            subprocess.run(['gcc','-O2','-Wall','-Wextra','-Werror',str(ROOT/'platform/src'/source),'-o',str(cls.root/name)],check=True)
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def setUp(self):self.work=pathlib.Path(tempfile.mkdtemp(dir=self.root))
    def test_battery_live_inode_and_real_current(self):
        src=self.work/'battery';view=self.work/'view';view.mkdir()
        values={'type':'Battery','status':'Discharging','energy_now':30000000,'energy_full':60000000,'energy_full_design':60000000,'voltage_min_design':11310000,'voltage_now':12000000,'power_now':12000000}
        for n,v in values.items():put(src/n,v)
        def convert():subprocess.run([str(self.root/'telemetry'),'--battery',str(src),str(view)],check=True)
        convert();before=(view/'charge_now').stat().st_ino
        # Production runs as root and exposes read-only aliases. Give this
        # unprivileged test owner write access inside its private fixture only.
        for file in view.iterdir():
            self.assertEqual(file.stat().st_mode&0o777,0o444)
            file.chmod(0o644)
        with (view/'charge_now').open('rb') as f:
            put(src/'energy_now',10000000);convert();f.seek(0);self.assertEqual(int(f.read()),10000000*1000000//11310000)
        self.assertEqual((view/'charge_now').stat().st_ino,before);self.assertEqual(int((view/'current_now').read_text()),-1000000);self.assertFalse((view/'temp').exists());self.assertEqual((src/'status').read_text(),'Discharging\n')
    def test_efficiency_preserves_foreground_cores_and_turbo_bounds(self):
        r=self.work;put(r/'sys/devices/system/cpu/online','0-13')
        for name in ['top-app','foreground','foreground_window','camera-daemon','background','system-background','restricted']:put(r/('dev/cpuset/'+name+'/cpus'),'0-13')
        put(r/'dev/cpuctl/top-app/cpu.uclamp.min',0)
        for i in range(14):
            put(r/f'sys/devices/system/cpu/cpu{i}/topology/core_type',2 if i<4 else 1)
            put(r/f'sys/devices/system/cpu/cpufreq/policy{i}/energy_performance_available_preferences','performance balance_performance balance_power power')
            put(r/f'sys/devices/system/cpu/cpufreq/policy{i}/energy_performance_preference','balance_performance')
        def config():return json.loads(subprocess.check_output([str(self.root/'powerhint'),'--root',str(r)],text=True))
        cfg=config();nodes={n['Name']:n for n in cfg['Nodes']}
        self.assertEqual(nodes['CpuSet0']['Values'],['0,1,2,3,4,5,6,7,8,9,10,11,12,13']);self.assertEqual(nodes['CpuSet4']['Values'],['4,5,6,7,8,9,10,11,12,13'])
        self.assertEqual(len([n for n in nodes if n.startswith('Epp')]),14)
        for n in nodes.values():self.assertFalse(any(s in n['Path'] for s in ['scaling_min_freq','scaling_max_freq','power_limit','thermal']))
        for a in cfg['Actions']:
            self.assertIn(a['Value'],nodes[a['Node']]['Values'])
            if a['PowerHint'] in ['LAUNCH','INTERACTION']:self.assertTrue(0<a['Duration']<=1000)
        for i in range(14):(r/f'sys/devices/system/cpu/cpu{i}/topology/core_type').unlink()
        unknown={n['Name']:n for n in config()['Nodes']};self.assertEqual(unknown['CpuSet4']['Values'],nodes['CpuSet0']['Values'])

if __name__=='__main__':unittest.main()
