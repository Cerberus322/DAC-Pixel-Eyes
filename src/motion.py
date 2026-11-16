"""Movimientos continuos: se calculan para cualquier instante, sin GIF intermedio."""
from PIL import Image,ImageDraw
from ojos_reloj import eyes

FPS={'Basic':15,'Normal':30,'High':60}

def clamp(x,a,b):return max(a,min(b,x))
def smooth(t):
    t=clamp(t,0,1);return t*t*(3-2*t)
def reflect(value,low,high):
    width=high-low;q=(value-low)%(2*width)
    return low+(q if q<=width else 2*width-q)

class LookMotion:
    def __init__(self,side=-1,hold=.75):
        self.side=side;self.hold=hold;self.duration=.42+hold+.56
        self.points=[(0,0)]+[(.07*(i+1),x) for i,x in enumerate((2,5,9,14,19,23))]
        self.points.append((.42+hold,23))
        self.points +=[(.42+hold+.08*(i+1),x) for i,x in enumerate((21,18,14,9,5,2,0))]
    def offset(self,t):
        t=clamp(t,0,self.duration)
        for (ta,a),(tb,b) in zip(self.points,self.points[1:]):
            if t<=tb:return self.side*(a+(b-a)*(t-ta)/(tb-ta))
        return 0
    def render(self,t):return eyes(self.offset(t))

class PongMotion:
    duration=13.58
    def geometry(self,t):
        if t<.5:return (0,26,26,None)
        if t<1.34:return (smooth((t-.5)/.84),26,26,None)
        if t<1.64:return (1,26,26,None)
        play=clamp(t-1.64,0,9.6)
        x=reflect(63+45*play,11,116)
        y=reflect(26+27.5*play,3,48)
        left=26+(y-26)*(1-smooth((x-11)/65))
        right=26+(y-26)*smooth((x-51)/65)
        left=clamp(left,9,42);right=clamp(right,9,42)
        if t<11.24:return (1,left,right,(x,y))
        if t<11.84:
            k=smooth((t-11.24)/.6)
            return (1,left+(26-left)*k,right+(26-right)*k,None)
        if t<12.68:return (1-smooth((t-11.84)/.84),26,26,None)
        return (0,26,26,None)
    def render(self,t):
        morph,ly,ry,ball=self.geometry(t)
        im=Image.new('1',(128,52));d=ImageDraw.Draw(im)
        width=round(28-24*morph);height=round(28-12*morph);radius=round(8-7*morph)
        for start,end,cy in ((42.5,7.5,ly),(83.5,119.5,ry)):
            cx=start+(end-start)*morph
            x=round(cx-(width-1)/2);y=round(cy-(height-1)/2)
            d.rounded_rectangle((x,y,x+width-1,y+height-1),radius=radius,fill=1)
        if ball:
            x,y=map(round,ball);d.rectangle((x-1,y-1,x+1,y+1),fill=1)
        return im
