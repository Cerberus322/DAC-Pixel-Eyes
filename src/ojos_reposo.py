"""Planificador de reposo, independiente de GameSense y del teclado."""
from collections import deque
from datetime import datetime
from pathlib import Path
import random
from PIL import Image, ImageDraw
from ojos_reloj import eyes, clock_image, transition_frames
from motion import LookMotion,PongMotion

ROOT=Path(__file__).resolve().parent/'assets'

def load_animation(name):
    result=[]
    with Image.open(ROOT/name) as gif:
        for index in range(gif.n_frames):
            gif.seek(index)
            result.append((gif.convert('1').copy(),gif.info.get('duration',70)/1000))
    return result

class IdleAnimator:
    def __init__(self,now,hold=8,rng=None):
        self.rng=rng or random.Random()
        self.hold=hold; self.image=eyes(); self.mode='idle'
        self.queue=deque(); self.due=now; self.until=0
        self.motion=None;self.motion_start=now;self.motion_speed=1.
        self.autoplay=True
        self.look_side=-1;self.look_hold=.75
        self.animations={name:load_animation(file) for name,file in {
            'curiosidad':'ojos_curiosidad.gif','confusion':'ojos_confusion.gif',
            'risa':'ojos_risa.gif','pong':'ojos_pong_v4.gif'}.items()}
        self.games=['pong','breakout','carrera','invasores','tetris','snake','pingpong_ojos','vaqueros']
        for name in self.games[1:]:
            self.animations[name]=load_animation(f'juego_{name}.gif')
        self.game_bag=[]; self.last_game=None
        self.bag=[]
        self.previous=None
        self.enabled=set(self.animations)
        self.quality='Normal'
        self.speed=1.0
        self.schedule(now)

    def schedule(self,now):
        self.next_blink=now+self.rng.uniform(3,6)
        self.next_look=now+self.rng.uniform(12,24)
        self.next_expression=now+self.rng.uniform(35,65)
        self.next_pong=now+self.rng.uniform(100,160)

    def start(self,mode,frames,now):
        self.mode=mode; self.queue=deque((im,dt/self.speed) for im,dt in frames); self.due=now
        self.motion=PongMotion() if mode=='pong' else LookMotion(self.look_side,self.look_hold) if mode=='look' else None
        if self.motion:
            self.queue.clear();self.motion_start=now;self.motion_speed=self.speed

    def duration_for(self,name):
        return (PongMotion.duration if name=='pong' else sum(dt for im,dt in self.animations[name]))/self.speed

    def show_clock(self,now):
        if self.mode=='clock': self.until=now+self.hold; return
        if self.mode=='opening': return
        # Interrumpe incluso Pong y vuelve desde el fotograma actual al centro.
        count={'Basic':6,'Normal':12,'High':24}[self.quality]
        recenter=transition_frames(self.image,eyes(),count=max(4,count//2))
        morph=transition_frames(eyes(),clock_image(),count=count)[1:]
        self.start('opening',[(im,.3/len(recenter)) for im in recenter]+[(im,.6/len(morph)) for im in morph],now)

    def pick_expression(self):
        if not self.bag:
            self.bag=[n for n in ('curiosidad','confusion','risa') if n in self.enabled]; self.rng.shuffle(self.bag)
            if self.bag[-1]==self.previous: self.bag[0],self.bag[-1]=self.bag[-1],self.bag[0]
        self.previous=self.bag.pop()
        return self.previous

    def pick_game(self):
        if not self.game_bag:
            self.game_bag=[n for n in self.games if n in self.enabled]; self.rng.shuffle(self.game_bag)
            if self.game_bag[-1]==self.last_game:
                self.game_bag[0],self.game_bag[-1]=self.game_bag[-1],self.game_bag[0]
        self.last_game=self.game_bag.pop()
        return self.last_game

    def blink(self):
        frames=[]
        for h in (24,17,9,2,2,9,17,24,28):
            im=Image.new('1',(128,52)); d=ImageDraw.Draw(im)
            y=(52-h)//2
            for x in (29,70): d.rounded_rectangle((x,y,x+27,y+h-1),radius=min(8,h//2),fill=1)
            frames.append((im,.045))
        return frames

    def look(self):
        side=self.rng.choice((-1,1))
        self.look_side=side;self.look_hold=self.rng.uniform(.5,1)
        frames=[(eyes(side*x),.07) for x in (2,5,9,14,19,23)]
        frames.append((eyes(side*23),self.look_hold))
        frames.extend((eyes(side*x),.08) for x in (21,18,14,9,5,2,0))
        return frames

    def finish(self,now):
        mode=self.mode
        if mode=='opening': self.mode='clock'; self.until=now+self.hold; return
        self.mode='idle'; self.image=eyes()
        if mode=='closing': self.schedule(now)
        elif mode=='blink': self.next_blink=now+self.rng.uniform(3,6)
        elif mode=='look': self.next_look=now+self.rng.uniform(12,24)
        elif mode in self.games: self.next_pong=now+self.rng.uniform(100,160)
        elif mode in self.animations: self.next_expression=now+self.rng.uniform(35,65)

    def frame(self,now):
        if self.motion:
            elapsed=(now-self.motion_start)*self.motion_speed
            self.image=self.motion.render(elapsed)
            if elapsed>=self.motion.duration:
                self.motion=None;self.finish(now)
            return self.image
        if self.queue:
            # Usa los tiempos originales de los GIF; no depende de la latencia HTTP.
            while self.queue and now>=self.due:
                self.image,duration=self.queue.popleft(); self.due+=duration
            return self.image
        if self.mode not in ('idle','clock') and now>=self.due:
            self.finish(now)
        if self.mode=='clock':
            self.image=clock_image()
            if now>=self.until:
                count={'Basic':6,'Normal':12,'High':24}[self.quality]
                self.start('closing',[(im,.6/count) for im in transition_frames(self.image,eyes(),count=count)],now)
            return self.image
        if self.mode=='idle' and self.autoplay:
            if now>=self.next_pong and any(n in self.enabled for n in self.games):
                name=self.pick_game(); self.start(name,self.animations[name],now)
            elif now>=self.next_expression and any(n in self.enabled for n in ('curiosidad','confusion','risa')):
                name=self.pick_expression(); self.start(name,self.animations[name],now)
            elif now>=self.next_look: self.start('look',self.look(),now)
            elif now>=self.next_blink: self.start('blink',self.blink(),now)
        return self.image

