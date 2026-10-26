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
        subprocess.run(['gcc','-O2','-Wall','-Wextra','-Werror','-DCHARGE_BACKEND_TEST',str(ROOT/'platform/src/gbos-charge-hal.c'),'-o',str(cls.root/'charge')],check=True)
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
        self.assertNotIn('GpuMinFreq',unknown)
        # Arrow Lake-H hybrid PMUs: Atom E-cores plus low-power E-cores.
        put(r/'sys/devices/cpu_core/cpus','0-3');put(r/'sys/devices/cpu_atom/cpus','4-11');put(r/'sys/devices/cpu_lowpower/cpus','12-13')
        pmu={n['Name']:n for n in config()['Nodes']};self.assertEqual(pmu['CpuSet4']['Values'],['4,5,6,7,8,9,10,11,12,13']);self.assertEqual(pmu['CpuSet0']['Values'],nodes['CpuSet0']['Values'])
    def test_framework_charge_limit_maps_to_conservation(self):
        r=self.work;dev=r/'sys/bus/acpi/devices/VPC2004:00';put(dev/'conservation_mode',0)
        drv=r/'sys/bus/acpi/drivers/gbos_motobook_charge';drv.mkdir(parents=True);(dev/'driver').symlink_to(drv)
        def sustain(lower,upper):return subprocess.run([str(self.root/'charge'),str(r),str(lower),str(upper)],capture_output=True,text=True).stdout
        # DesktopChargingOptimizationController: on = sustain(80,80), off = sustain(-1,-1).
        self.assertIn('RESULT=0',sustain(80,80));self.assertEqual((dev/'conservation_mode').read_text().strip(),'1')
        self.assertIn('RESULT=0',sustain(-1,-1));self.assertEqual((dev/'conservation_mode').read_text().strip(),'0')
        self.assertIn('RESULT=-7',sustain(85,85));self.assertIn('RESULT=-3',sustain(81,80));self.assertEqual((dev/'conservation_mode').read_text().strip(),'0')
    def test_gpu_floor_is_finite_and_keeps_boot_minimum(self):
        r=self.work;put(r/'sys/devices/system/cpu/online','0-3')
        g=r/'sys/class/drm/card0/device/tile0/gt0/freq0'
        for n,v in {'min_freq':100,'rpe_freq':1450,'rp0_freq':2200,'max_freq':2200}.items():put(g/n,v)
        cfg=json.loads(subprocess.check_output([str(self.root/'powerhint'),'--root',str(r)],text=True))
        node=next(n for n in cfg['Nodes'] if n['Name']=='GpuMinFreq')
        self.assertEqual(node['Values'],['2200','1450','100']);self.assertEqual(node['Values'][node['DefaultIndex']],'100')
        acts=[a for a in cfg['Actions'] if a['Node']=='GpuMinFreq'];self.assertEqual({a['PowerHint'] for a in acts},{'LAUNCH','INTERACTION'})
        for a in acts:self.assertTrue(0<a['Duration']<=1000)
        self.assertFalse(any('max_freq' in n['Path'] for n in cfg['Nodes']))
        put(g/'max_freq',1000)
        self.assertNotIn('GpuMinFreq',[n['Name'] for n in json.loads(subprocess.check_output([str(self.root/'powerhint'),'--root',str(r)],text=True))['Nodes']])

if __name__=='__main__':unittest.main()
