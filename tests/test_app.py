import sys,unittest,random,time,tempfile
from pathlib import Path
from unittest.mock import patch,Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
Path('work').mkdir(exist_ok=True)
import app
from ojos_reposo import IdleAnimator
from motion import LookMotion,PongMotion,FPS
from gamesense_client import GameSense,prepare_image,bitmap,PROFILES
from ojos_reloj import eyes,clock_image

class Tests(unittest.TestCase):
    def test_wireless_bitmap_and_event(self):
        source=eyes();before=source.tobytes()
        image=prepare_image(source,'arctis_pro_wireless')
        self.assertEqual(image.size,(128,48));self.assertEqual(len(bitmap(image)),768)
        self.assertEqual(source.tobytes(),before)
        self.assertEqual(len(bitmap(prepare_image(source,'gamedac'))),832)
        client=GameSense.__new__(GameSense)
        client.profile='arctis_pro_wireless';client.width=128;client.height=48
        client.server='http://127.0.0.1:1';client.sent=0;client.post=Mock()
        client.bind(source);client.send(source)
        binding=client.post.call_args_list[1].args[1]
        self.assertEqual(binding['handlers'][0]['device-type'],'screened-128x48')
        payload=client.post.call_args_list[2].args[1]
        self.assertEqual(set(payload['data']['frame']),{'image-data-128x48'})
        self.assertEqual(len(payload['data']['frame']['image-data-128x48']),768)
        for h in range(24):
            from datetime import datetime
            for m in range(60):
                self.assertEqual(len(bitmap(prepare_image(clock_image(datetime(2026,1,1,h,m)),'arctis_pro_wireless'))),768)

    def test_settings_migration(self):
        self.assertEqual(app.validate({'quality':'Alta'})['quality'],'High')
        self.assertEqual(app.validate({'quality':'Basica'})['quality'],'Basic')
        self.assertEqual(app.validate({})['device_profile'],'gamedac')
        with self.assertRaises(ValueError):app.validate({'device_profile':'unknown'})

    def test_live_profile_switch(self):
        class FakeKey:
            def __init__(self,*args):pass
            def pressed(self):return False
            def close(self):pass
        clients=[]
        class FakeClient:
            GAME='TEST';server='local'
            def __init__(self,profile='gamedac'):self.profile=profile;clients.append(self)
            def bind(self,image):pass
            def send(self,image):pass
            def post(self,*args):pass
            def close(self):pass
        with tempfile.TemporaryDirectory(dir='work') as d:
            with patch.object(app,'Hotkey',FakeKey),patch.object(app,'GameSense',FakeClient),patch.object(app,'log',Mock()),patch.object(app,'CONFIG',Path(d)/'settings.json'):
                e=app.Engine(app.validate({}));e.start()
                def wait_for(profile):
                    deadline=time.monotonic()+3
                    while time.monotonic()<deadline:
                        if clients and clients[-1].profile==profile:return
                        time.sleep(.02)
                    self.fail('Profile switch did not complete: '+profile)
                try:
                    wait_for('gamedac')
                    for profile in ('arctis_pro_wireless','gamedac'):
                        e.commands.put(('settings',app.validate({'device_profile':profile})));wait_for(profile)
                    self.assertTrue(e.connected)
                finally:e.stop.set();e.join(3)

    def test_continuous_motion(self):
        pong=PongMotion();look=LookMotion(-1,.75)
        for motion in (pong,look):
            sampled={fps:[motion.render(i/fps).tobytes() for i in range(round(motion.duration*fps)+1)] for fps in FPS.values()}
            self.assertGreater(len(set(sampled[60])),len(set(sampled[15])))
            for n in range(15):
                self.assertEqual(sampled[15][n],sampled[60][n*4])
            self.assertEqual(motion.render(0).tobytes(),motion.render(motion.duration).tobytes())

    def test_slow_http_does_not_limit_rendering(self):
        class FakeKey:
            def __init__(self,*args):pass
            def pressed(self):return False
            def close(self):pass
        class SlowClient:
            GAME='TEST';server='local';sent=0
            def __init__(self,**kwargs):pass
            def bind(self,image):pass
            def send(self,image):time.sleep(.12);type(self).sent+=1
            def post(self,*args):pass
            def close(self):pass
        class PlayingAnimator(IdleAnimator):
            def __init__(self,now):
                super().__init__(now);self.start('pong',self.animations['pong'],now-2)
        with patch.object(app,'Hotkey',FakeKey),patch.object(app,'GameSense',SlowClient),patch.object(app,'IdleAnimator',PlayingAnimator),patch.object(app,'log',Mock()):
            e=app.Engine(app.validate({'quality':'High'}));e.start();samples=set();end=time.monotonic()+1.5
            while time.monotonic()<end:samples.add(e.image.tobytes());time.sleep(.004)
            e.stop.set();e.join(3)
            self.assertGreater(len(samples),SlowClient.sent*2)
            self.assertFalse(e.is_alive())

    def test_validation_and_save(self):
        for values in ({'hold':0},{'speed':2},{'enabled':['other']},{'quality':'other'}):
            with self.assertRaises(ValueError):app.validate(values)
        with tempfile.TemporaryDirectory(dir='work') as d:
            with patch.object(app,'CONFIG',Path(d)/'settings.json'):
                settings=app.validate({'hotkey':'Ctrl+Alt+T','hold':12,'quality':'High'})
                app.save_settings(settings);self.assertEqual(app.load_settings(),settings)

    def test_smoothness_preserves_duration(self):
        durations=[];counts=[]
        for quality in ('Basic','Normal','High'):
            a=IdleAnimator(0);a.quality=quality;a.show_clock(0)
            durations.append(sum(dt for im,dt in a.queue));counts.append(len(a.queue))
        self.assertEqual(sorted(counts),counts)
        for dt in durations:self.assertAlmostEqual(dt,.9)

    def test_disabled_animations(self):
        a=IdleAnimator(0,rng=random.Random(8));a.enabled=set()
        modes=set()
        for i in range(6000):a.frame(i/10);modes.add(a.mode)
        self.assertEqual(modes,{'idle','blink','look'})

    def test_game_bag_and_clock(self):
        a=IdleAnimator(0,rng=random.Random(42))
        self.assertEqual(len({a.pick_game() for _ in range(8)}),8)
        for name in a.games:
            a.start(name,a.animations[name],0);a.frame(0);a.show_clock(.1)
            self.assertEqual(a.mode,'opening')
            for i in range(120):a.frame(.1+i/10)
            self.assertEqual(a.mode,'idle')

    def test_worker_reconnect_and_hotkey_conflict(self):
        class FakeKey:
            def __init__(self,value,identifier=1):
                if value=='occupied':raise OSError('occupied')
                self.identifier=identifier
            def pressed(self):return False
            def close(self):pass
        clients=[]
        class FakeClient:
            GAME='TEST';server='http://127.0.0.1:1'
            def __init__(self,**kwargs):clients.append(self)
            def bind(self,image):
                if len(clients)==1:raise OSError('GG restart')
            def send(self,image):pass
            def post(self,*args):pass
            def close(self):pass
        with tempfile.TemporaryDirectory(dir='work') as d:
            with patch.object(app,'Hotkey',FakeKey),patch.object(app,'GameSense',FakeClient),patch.object(app,'log',Mock()),patch.object(app,'CONFIG',Path(d)/'settings.json'):
                e=app.Engine(app.validate({}));e.start()
                invalid=app.validate({'hotkey':'occupied'})
                e.commands.put(('settings',invalid))
                deadline=time.monotonic()+7
                while time.monotonic()<deadline and not e.connected:time.sleep(.05)
                e.stop.set();e.join(3)
                self.assertFalse(e.is_alive());self.assertTrue(e.connected)
                self.assertGreaterEqual(len(clients),2)
                self.assertEqual(e.settings['hotkey'],'|')
                self.assertFalse(app.CONFIG.exists())

if __name__=='__main__':unittest.main()
