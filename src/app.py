"""DAC Pixel Eyes 0.1.0 — version de prueba para Windows."""
from pathlib import Path
import ctypes
from ctypes import wintypes
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from queue import Queue,Empty
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk,messagebox
import winreg
from PIL import Image,ImageDraw,ImageTk
import pystray
from ojos_reloj import eyes
from ojos_reposo import IdleAnimator
from gamesense_client import GameSense,prepare_image,PROFILES
from win_hotkey import Hotkey
from motion import FPS

VERSION='0.1.2-test'
DATA=Path(os.environ['LOCALAPPDATA'])/'DACPixelEyes'
DATA.mkdir(parents=True,exist_ok=True)
CONFIG=DATA/'settings.json'
LABELS={'curiosidad':'Curiosity','confusion':'Confused','risa':'Laughing',
        'pong':'Pong','breakout':'Breakout','carrera':'Racing','invasores':'Space Invaders',
        'tetris':'Tetris','snake':'Snake','pingpong_ojos':'Eye ping-pong','vaqueros':'Cowboy duel'}
DEFAULT={'hotkey':'|','hold':8.,'quality':'Normal','speed':1.,'enabled':list(LABELS),'autostart':False,'device_profile':'gamedac'}
log=logging.getLogger('DACPixelEyes');log.setLevel(logging.INFO)
handler=RotatingFileHandler(DATA/'app.log',maxBytes=1_000_000,backupCount=3,encoding='utf-8')
handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'));log.addHandler(handler)

def validate(value):
    s=dict(DEFAULT);s.update(value)
    s['quality']={'Basica':'Basic','Alta':'High'}.get(s['quality'],s['quality'])
    if s['device_profile'] not in PROFILES:raise ValueError('Unknown display profile.')
    if not isinstance(s['hotkey'],str) or not s['hotkey'].strip():raise ValueError('Choose a key or key combination.')
    if s['quality'] not in ('Basic','Normal','High'):raise ValueError('Invalid smoothness setting.')
    s['hold']=float(s['hold']);s['speed']=float(s['speed'])
    if not 2<=s['hold']<=60:raise ValueError('Clock display duration must be between 2 and 60 seconds.')
    if not .5<=s['speed']<=1.5:raise ValueError('Speed must be between 0.5 and 1.5.')
    if not isinstance(s['enabled'],list) or not all(n in LABELS for n in s['enabled']):raise ValueError('Unknown animation.')
    s['autostart']=bool(s['autostart'])
    return s

def load_settings():
    try:return validate(json.loads(CONFIG.read_text(encoding='utf-8')))
    except FileNotFoundError:return validate({})
    except Exception:
        log.exception('Could not load settings; using defaults.')
        return validate({})

def save_settings(s):
    temp=CONFIG.with_suffix('.tmp');temp.write_text(json.dumps(s,ensure_ascii=False,indent=2),encoding='utf-8');temp.replace(CONFIG)

def startup_command():
    if getattr(sys,'frozen',False):return f'"{sys.executable}" --background'
    pythonw=Path(sys.executable).with_name('pythonw.exe')
    return f'"{pythonw}" "{Path(__file__).resolve()}" --background'

def set_startup(enabled):
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER,r'Software\Microsoft\Windows\CurrentVersion\Run') as key:
        if enabled:winreg.SetValueEx(key,'DACPixelEyes',0,winreg.REG_SZ,startup_command())
        else:
            try:winreg.DeleteValue(key,'DACPixelEyes')
            except FileNotFoundError:pass

def icon_image():
    im=Image.new('RGBA',(64,64),(24,32,40,255));d=ImageDraw.Draw(im)
    for x in (9,36):d.rounded_rectangle((x,20,x+18,43),radius=5,fill=(115,245,207,255))
    return im

class DisplaySender(threading.Thread):
    """Envia solo la imagen mas reciente; HTTP nunca bloquea el movimiento."""
    def __init__(self,engine):
        super().__init__(daemon=True);self.engine=engine
    def run(self):
        owner=self.engine;client=None;next_connect=0;previous=None;last_send=0;was_paused=False
        active_profile=None
        stats_start=time.monotonic();sent=0;log_start=stats_start
        try:
            while not owner.stop.is_set():
                tick=time.monotonic()
                if owner.paused:
                    if not was_paused and client:
                        try:client.post('stop_game',{'game':client.GAME})
                        except Exception:log.exception('Could not release the screen when pausing')
                    was_paused=True;owner.stop.wait(.05);continue
                if was_paused:previous=None;was_paused=False
                profile=owner.settings['device_profile']
                if client and active_profile!=profile:
                    try:client.post('stop_game',{'game':client.GAME})
                    except Exception:log.warning('Could not release the previous display profile')
                    client.close();client=None;previous=None;next_connect=0
                if client is None and tick>=next_connect:
                    try:
                        client=GameSense(profile=profile);client.bind(owner.image);active_profile=profile
                        owner.connected=True;owner.event('connection','Connected to GameSense')
                        log.info('GameSense connected at %s',client.server);previous=None
                    except Exception as exc:
                        if client:client.close();client=None
                        owner.connected=False;next_connect=tick+5
                        owner.event('connection','Waiting for GG · retrying automatically')
                        log.warning('Connection unavailable: %s',exc)
                if client:
                    image=owner.image;data=image.tobytes()
                    if data!=previous or tick-last_send>=3:
                        try:
                            client.send(image);previous=data;last_send=time.monotonic();sent+=1
                        except Exception as exc:
                            log.warning('Connection lost: %s',exc);client.close();client=None
                            owner.connected=False;next_connect=tick+2
                            owner.event('connection','Connection lost · reconnecting to GG')
                if tick-stats_start>=2:
                    owner.sent_fps=sent/(tick-stats_start);sent=0;stats_start=tick
                if tick-log_start>=30:
                    log.info('Frame rate: target=%s fps; sent=%.1f fps',owner.target_fps,owner.sent_fps);log_start=tick
                owner.frame_event.wait(.2);owner.frame_event.clear()
        finally:
            if client:
                try:client.post('stop_game',{'game':client.GAME})
                except Exception:pass
                client.close()

class Engine(threading.Thread):
    def __init__(self,settings):
        super().__init__(daemon=True);self.settings=settings
        self.commands=Queue();self.events=Queue();self.stop=threading.Event()
        self.image=eyes();self.connected=False;self.paused=False
        self.target_fps=FPS[settings['quality']];self.sent_fps=0.
        self.frame_event=threading.Event()

    def event(self,kind,value):self.events.put((kind,value))

    def run(self):
        hotkey=None;previous_mode=None;comparison=[];comparison_due=0;comparison_quality=None
        animator=IdleAnimator(time.monotonic());showcase=[];showcase_due=0
        self.animator=animator
        def apply_animator(s):
            animator.hold=s['hold'];animator.speed=s['speed'];animator.quality=s['quality']
            animator.enabled=set(s['enabled']);animator.bag=[];animator.game_bag=[]
        apply_animator(self.settings)
        sender=DisplaySender(self);sender.start()
        try:
            try:hotkey=Hotkey(self.settings['hotkey']);self.event('hotkey','Global hotkey active')
            except Exception as exc:
                log.exception('Could not register the hotkey');self.event('error',f'The hotkey is in use or invalid. Choose another shortcut. {exc}')
            while not self.stop.is_set():
                tick=time.monotonic()
                while True:
                    try:command,payload=self.commands.get_nowait()
                    except Empty:break
                    if command=='settings':
                        candidate=None
                        try:
                            new=validate(payload)
                            if not hotkey or new['hotkey']!=self.settings['hotkey']:
                                candidate=Hotkey(new['hotkey'],2 if hotkey and hotkey.identifier==1 else 1)
                            if new['autostart']!=self.settings['autostart']:set_startup(new['autostart'])
                            save_settings(new)
                            if candidate:
                                if hotkey:hotkey.close()
                                hotkey=candidate;candidate=None
                            self.settings=new;apply_animator(new)
                            log.info('Settings saved: quality=%s speed=%s',new['quality'],new['speed'])
                            self.event('saved',new)
                        except Exception as exc:
                            if candidate:candidate.close()
                            log.exception('Settings were not applied');self.event('error',f'Changes were not saved: {exc}')
                    elif command=='clock' and not self.paused:
                        comparison=[];comparison_quality=None;animator.autoplay=True;apply_animator(self.settings);animator.show_clock(tick)
                    elif command=='capture':
                        if payload:
                            if hotkey:hotkey.close();hotkey=None
                        elif not hotkey:
                            try:hotkey=Hotkey(self.settings['hotkey'])
                            except Exception as exc:self.event('error',f'Could not restore the hotkey: {exc}')
                    elif command=='pause':
                        self.paused=not self.paused;self.event('paused',self.paused)
                        if not self.paused:animator.schedule(tick)
                    elif command=='showcase':
                        showcase=[n for n in animator.games if n in animator.enabled]
                        showcase_due=tick
                    elif command=='compare':
                        comparison=[('look','Basic'),('look','High'),('pong','Basic'),('pong','High')]
                        comparison_due=tick;showcase=[]
                        animator.motion=None;animator.queue.clear();animator.mode='idle';animator.image=eyes()
                        animator.autoplay=False
                if hotkey and hotkey.pressed() and not self.paused:
                    comparison=[];comparison_quality=None;animator.autoplay=True;apply_animator(self.settings)
                    animator.show_clock(tick);log.info('Clock requested by hotkey')
                if self.paused:
                    self.stop.wait(.1);continue
                if comparison and animator.mode=='idle' and tick>=comparison_due:
                    name,comparison_quality=comparison.pop(0);animator.quality=comparison_quality
                    # Comparacion a velocidad 1x, sin modificar los ajustes guardados.
                    animator.speed=1.;animator.look_side=-1;animator.look_hold=.75
                    animator.start(name,[] if name=='look' else animator.animations[name],tick)
                    duration=animator.motion.duration
                    comparison_due=tick+duration+2
                    self.event('comparison',f'Comparing {LABELS.get(name,"look")}: {comparison_quality} · {FPS[comparison_quality]} FPS · speed 1×')
                elif not comparison and comparison_quality and animator.mode=='idle':
                    comparison_quality=None;animator.autoplay=True;apply_animator(self.settings);self.event('comparison','Comparison finished. Your saved settings have been restored.')
                if showcase and animator.mode=='idle' and tick>=showcase_due:
                    name=showcase.pop(0);seq=animator.animations[name]
                    animator.start(name,seq,tick);showcase_due=tick+animator.duration_for(name)+3
                self.image=animator.frame(tick)
                self.frame_event.set()
                if animator.mode!=previous_mode:
                    previous_mode=animator.mode;self.event('mode',previous_mode);log.info('State: %s',previous_mode)
                fps=FPS[comparison_quality or self.settings['quality']];self.target_fps=fps
                self.stop.wait(max(.005,1/fps-(time.monotonic()-tick)))
        except Exception:
            log.exception('Unexpected animation engine error');self.event('error','The animation engine stopped. Check the logs and restart the app.')
        finally:
            self.stop.set();sender.join(5)
            if hotkey:hotkey.close()
            log.info('Engine stopped; hotkey released')

class Window:
    def __init__(self,event_handle):
        self.root=tk.Tk();self.root.title('DAC Pixel Eyes · '+VERSION)
        self.root.geometry('900x960');self.root.minsize(840,650)
        self.root.configure(bg='#f1f4f7');self.root.protocol('WM_DELETE_WINDOW',self.hide)
        self.event_handle=event_handle;self.settings=load_settings()
        self.wait_event=ctypes.WinDLL('kernel32').WaitForSingleObject
        self.wait_event.argtypes=[wintypes.HANDLE,wintypes.DWORD];self.wait_event.restype=wintypes.DWORD
        style=ttk.Style();style.theme_use('clam')
        style.configure('TFrame',background='#f1f4f7');style.configure('TLabel',background='#f1f4f7',font=('Segoe UI',10))
        style.configure('TCheckbutton',background='#f1f4f7',font=('Segoe UI',10))
        style.configure('TLabelframe',background='#f1f4f7');style.configure('TLabelframe.Label',background='#f1f4f7',font=('Segoe UI',11,'bold'))
        style.configure('TButton',font=('Segoe UI',10),padding=(12,6))
        self.engine=Engine(self.settings);self.actions=Queue();self.capture_dialog=None
        self.hotkey=tk.StringVar(value=self.settings['hotkey']);self.hold=tk.StringVar(value=str(int(self.settings['hold'])))
        self.quality=tk.StringVar(value=self.settings['quality']);self.speed=tk.DoubleVar(value=self.settings['speed'])
        self.autostart=tk.BooleanVar(value=self.settings['autostart'])
        self.device_profile=tk.StringVar(value=self.settings['device_profile'])
        self.enabled={n:tk.BooleanVar(value=n in self.settings['enabled']) for n in LABELS}
        header=tk.Frame(self.root,bg='#182028',height=70);header.pack(fill='x')
        tk.Label(header,text='DAC PIXEL EYES',bg='#182028',fg='#73f5cf',font=('Segoe UI',22,'bold')).pack(anchor='w',padx=24,pady=(12,0))
        tk.Label(header,text='Animated eyes, games and a clock for your GameDAC · test release',bg='#182028',fg='#c7d2de',font=('Segoe UI',10)).pack(anchor='w',padx=24,pady=(0,12))
        outer=ttk.Frame(self.root);outer.pack(fill='both',expand=True)
        canvas=tk.Canvas(outer,bg='#f1f4f7',highlightthickness=0)
        scrollbar=ttk.Scrollbar(outer,orient='vertical',command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side='right',fill='y');canvas.pack(side='left',fill='both',expand=True)
        body=ttk.Frame(canvas,padding=(22,12));body_window=canvas.create_window((0,0),window=body,anchor='nw')
        body.bind('<Configure>',lambda event:canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>',lambda event:canvas.itemconfigure(body_window,width=event.width))
        def scroll(event):
            if event.widget.winfo_class() not in ('TCombobox','TSpinbox','TScale') and event.delta:
                canvas.yview_scroll(-1 if event.delta>0 else 1,'units')
        self.root.bind_all('<MouseWheel>',scroll)
        top=ttk.Frame(body);top.pack(fill='x')
        self.preview=tk.Label(top,bg='black',width=384,height=156);self.preview.pack(side='left')
        info=ttk.Frame(top,padding=(20,0));info.pack(side='left',fill='both',expand=True)
        self.status=tk.StringVar(value='Connecting to GG…');ttk.Label(info,textvariable=self.status,wraplength=310).pack(anchor='w',pady=(8,8))
        self.state=tk.StringVar(value='Idle');ttk.Label(info,textvariable=self.state).pack(anchor='w')
        ttk.Button(info,text='Show clock now',command=lambda:self.engine.commands.put(('clock',None))).pack(anchor='w',pady=8)
        self.pause=ttk.Button(info,text='Pause',command=lambda:self.engine.commands.put(('pause',None)));self.pause.pack(anchor='w')
        device=ttk.LabelFrame(body,text='Display profile',padding=10);device.pack(fill='x',pady=(12,0))
        ttk.Radiobutton(device,text='GameDAC / Arctis Nova Pro — 128×52',variable=self.device_profile,value='gamedac').pack(anchor='w')
        ttk.Radiobutton(device,text='Arctis Pro Wireless (Test)',variable=self.device_profile,value='arctis_pro_wireless').pack(anchor='w',pady=4)
        ttk.Label(device,text='Test output: 128×48. Not verified on hardware. This is not Nova Pro Wireless. Save & apply to activate.',wraplength=780).pack(anchor='w')
        settings=ttk.LabelFrame(body,text='Motion and clock',padding=12);settings.pack(fill='x',pady=12)
        ttk.Label(settings,text='Smoothness').grid(row=0,column=0,sticky='w',padx=(0,12))
        ttk.Combobox(settings,textvariable=self.quality,values=('Basic','Normal','High'),state='readonly',width=13).grid(row=0,column=1,sticky='w')
        ttk.Label(settings,text='Speed').grid(row=0,column=2,padx=(24,8))
        ttk.Scale(settings,variable=self.speed,from_=.5,to=1.5,length=145).grid(row=0,column=3)
        self.speedlabel=ttk.Label(settings,width=6);self.speedlabel.grid(row=0,column=4)
        ttk.Label(settings,text='Clock shortcut').grid(row=1,column=0,sticky='w',pady=12)
        ttk.Entry(settings,textvariable=self.hotkey,width=16).grid(row=1,column=1,sticky='w')
        ttk.Button(settings,text='Capture shortcut',command=self.capture).grid(row=1,column=2,columnspan=2,sticky='w',padx=24)
        ttk.Label(settings,text='Clock duration').grid(row=2,column=0,sticky='w')
        ttk.Spinbox(settings,from_=2,to=60,textvariable=self.hold,width=6).grid(row=2,column=1,sticky='w')
        ttk.Label(settings,text='seconds · shortcut works while other apps are active').grid(row=2,column=2,columnspan=3,sticky='w',padx=24)
        ttk.Label(settings,text='15 / 30 / 60 FPS targets. Pong and looks use continuous motion; other games use their original frames.',wraplength=750).grid(row=3,column=0,columnspan=5,sticky='w',pady=(10,0))
        ttk.Button(settings,text='Compare Basic and High',command=lambda:self.engine.commands.put(('compare',None))).grid(row=4,column=0,columnspan=2,sticky='w',pady=(8,0))
        self.fluency=tk.StringVar(value='')
        ttk.Label(settings,textvariable=self.fluency).grid(row=4,column=2,columnspan=3,sticky='w',padx=24)
        games=ttk.LabelFrame(body,text='Random animations',padding=10);games.pack(fill='x')
        for i,(name,label) in enumerate(LABELS.items()):ttk.Checkbutton(games,text=label,variable=self.enabled[name]).grid(row=i//4,column=i%4,sticky='w',padx=(0,18),pady=3)
        ttk.Button(games,text='Preview all games',command=lambda:self.engine.commands.put(('showcase',None))).grid(row=3,column=0,columnspan=2,sticky='w',pady=(8,0))
        ttk.Checkbutton(body,text='Start with Windows',variable=self.autostart).pack(anchor='w',pady=(12,5))
        foot=ttk.Frame(body);foot.pack(fill='x',pady=(3,0))
        self.savebutton=ttk.Button(foot,text='Save & apply',command=self.save);self.savebutton.pack(side='left')
        ttk.Button(foot,text='Hide to tray',command=self.hide).pack(side='left',padx=8)
        ttk.Button(foot,text='Open logs folder',command=lambda:os.startfile(DATA)).pack(side='right')
        self.notice=tk.StringVar(value='Keep SteelSeries GG running. Closing this window keeps the eyes active in the system tray.')
        ttk.Label(body,textvariable=self.notice,wraplength=750).pack(anchor='w',pady=(10,0))
        self.photo=None;self.last_preview=None
        self.tray=pystray.Icon('DACPixelEyes',icon_image(),'DAC Pixel Eyes',menu=pystray.Menu(
            pystray.MenuItem('Open settings',lambda:self.actions.put('show'),default=True),
            pystray.MenuItem('Show clock',lambda:self.engine.commands.put(('clock',None))),
            pystray.MenuItem('Pause / resume',lambda:self.engine.commands.put(('pause',None))),
            pystray.MenuItem('Exit',lambda:self.actions.put('quit'))))
        threading.Thread(target=self.tray.run,daemon=True).start()
        self.engine.start();self.root.after(100,self.poll)
        if '--background' in sys.argv:self.root.withdraw()

    def show(self):self.root.deiconify();self.root.lift();self.root.focus_force()
    def hide(self):self.root.withdraw()
    def capture(self):
        if self.capture_dialog and self.capture_dialog.winfo_exists():return
        dialog=tk.Toplevel(self.root);self.capture_dialog=dialog;dialog.title('Choose a shortcut')
        self.engine.commands.put(('capture',True))
        def cancel():
            self.engine.commands.put(('capture',False));dialog.destroy()
        dialog.protocol('WM_DELETE_WINDOW',cancel)
        dialog.geometry('440x150');dialog.transient(self.root);dialog.grab_set()
        ttk.Label(dialog,text='Press a key or key combination.\nExample: | or Ctrl + Alt + T',padding=20).pack()
        ttk.Button(dialog,text='Cancel',command=cancel).pack()
        def on_key(event):
            if event.keysym in ('Control_L','Control_R','Alt_L','Alt_R','Shift_L','Shift_R'):return 'break'
            modifiers=[]
            if ctypes.windll.user32.GetKeyState(0x11)&0x8000:modifiers.append('Ctrl')
            if ctypes.windll.user32.GetKeyState(0x12)&0x8000:modifiers.append('Alt')
            key=event.char if event.char and event.char.isprintable() and event.char!=' ' else event.keysym
            key={'space':'Space','Return':'Enter','Prior':'PageUp','Next':'PageDown'}.get(key,key)
            if event.state&1 and (len(key)!=1 or key.isalpha()):modifiers.append('Shift')
            self.hotkey.set('+'.join(modifiers+[key]));cancel();return 'break'
        dialog.bind('<KeyPress>',on_key);dialog.focus_force()

    def save(self):
        try:
            value=validate({'hotkey':self.hotkey.get().strip(),'hold':self.hold.get(),'quality':self.quality.get(),
                'speed':round(self.speed.get(),2),'enabled':[n for n,v in self.enabled.items() if v.get()],'autostart':self.autostart.get(),'device_profile':self.device_profile.get()})
            self.savebutton.configure(state='disabled');self.notice.set('Applying settings…')
            self.engine.commands.put(('settings',value))
        except Exception as exc:messagebox.showerror('Check settings',str(exc),parent=self.root)

    def poll(self):
        while True:
            try:action=self.actions.get_nowait()
            except Empty:break
            if action=='quit':self.quit();return
            if action=='show':self.show()
        if self.wait_event(self.event_handle,0)==0:self.show()
        while True:
            try:kind,value=self.engine.events.get_nowait()
            except Empty:break
            if kind=='connection':self.status.set(value)
            elif kind=='mode':self.state.set('Animation: '+LABELS.get(value,{'idle':'Idle','blink':'Blink','look':'Look','opening':'Transforming into clock','clock':'PC time','closing':'Returning to eyes'}.get(value,value)))
            elif kind=='saved':self.settings=value;self.notice.set('Settings saved.');self.savebutton.configure(state='normal')
            elif kind=='error':self.notice.set(value);self.savebutton.configure(state='normal');log.warning(value)
            elif kind=='paused':self.pause.configure(text='Resume' if value else 'Pause');self.status.set('Paused' if value else ('Connected to GameSense' if self.engine.connected else 'Reconnecting…'))
            elif kind=='comparison':self.notice.set(value)
        self.fluency.set(f'Target: {self.engine.target_fps} FPS · sent to GG: {self.engine.sent_fps:.0f} FPS')
        self.speedlabel.configure(text=f'{self.speed.get():.2f}×')
        image=self.engine.image
        profile=self.engine.settings['device_profile']
        data=(image.tobytes(),profile)
        if data!=self.last_preview:
            output=prepare_image(image,profile)
            self.photo=ImageTk.PhotoImage(output.convert('RGB').resize((384,output.height*3),Image.Resampling.NEAREST))
            self.preview.configure(image=self.photo);self.last_preview=data
        self.root.after(max(10,round(1000/self.engine.target_fps)),self.poll)

    def quit(self):
        self.root.withdraw();self.engine.stop.set()
        def finish():
            if self.engine.is_alive():self.root.after(100,finish);return
            self.tray.stop();self.root.destroy()
        finish()

def main():
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.CreateMutexW.argtypes=[ctypes.c_void_p,wintypes.BOOL,wintypes.LPCWSTR];kernel.CreateMutexW.restype=wintypes.HANDLE
    kernel.CreateEventW.argtypes=[ctypes.c_void_p,wintypes.BOOL,wintypes.BOOL,wintypes.LPCWSTR];kernel.CreateEventW.restype=wintypes.HANDLE
    kernel.SetEvent.argtypes=[wintypes.HANDLE];kernel.CloseHandle.argtypes=[wintypes.HANDLE]
    kernel.WaitForSingleObject.argtypes=[wintypes.HANDLE,wintypes.DWORD]
    event=kernel.CreateEventW(None,False,False,'Local\\DACPixelEyes.OpenSettings')
    mutex=kernel.CreateMutexW(None,False,'Local\\DACPixelEyes.SingleInstance')
    if ctypes.get_last_error()==183:
        kernel.SetEvent(event);kernel.CloseHandle(event);kernel.CloseHandle(mutex);return
    log.info('Starting DAC Pixel Eyes %s',VERSION)
    try:Window(event).root.mainloop()
    except Exception:
        log.exception('Application startup failed')
        messagebox.showerror('DAC Pixel Eyes','Could not start. See '+str(DATA/'app.log'))
    finally:kernel.CloseHandle(event);kernel.CloseHandle(mutex)

if __name__=='__main__':main()
