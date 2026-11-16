"""Monochrome 128x52 eyes, clock glyphs and image transitions."""
from datetime import datetime
from PIL import Image, ImageDraw

SIZE = (128, 52)
FONT = {
    '0':['01110','10001','10001','10001','10001','10001','01110'],
    '1':['00100','01100','00100','00100','00100','00100','01110'],
    '2':['01110','10001','00001','00010','00100','01000','11111'],
    '3':['11110','00001','00001','01110','00001','00001','11110'],
    '4':['10010','10010','10010','11111','00010','00010','00010'],
    '5':['11111','10000','10000','11110','00001','00001','11110'],
    '6':['01110','10000','10000','11110','10001','10001','01110'],
    '7':['11111','00001','00010','00100','01000','01000','01000'],
    '8':['01110','10001','10001','01110','10001','10001','01110'],
    '9':['01110','10001','10001','01111','00001','00001','01110'],
}

def eyes(offset=0):
    im = Image.new('1', SIZE)
    d = ImageDraw.Draw(im)
    for x in (29+round(offset),70+round(offset)):
        d.rounded_rectangle((x,12,x+27,39),radius=8,fill=1)
    return im

def clock_image(now=None):
    """Genera HH:MM en 24 horas; consulta el reloj local, no una tabla de sprites."""
    text = (now or datetime.now()).strftime('%H%M')
    im = Image.new('1', SIZE)
    d = ImageDraw.Draw(im)
    for x, digit in zip((10,34,74,98), text):
        for row, bits in enumerate(FONT[digit]):
            for col, bit in enumerate(bits):
                if bit == '1':
                    xx,yy = x+col*4,12+row*4
                    d.rectangle((xx,yy,xx+3,yy+3),fill=1)
    for y in (19,31): d.rectangle((62,y,65,y+3),fill=1)
    return im

def distance_to(mask, white):
    w,h=SIZE; inf=10000
    a=[0 if bool(p)==white else inf for p in mask.convert('L').tobytes()]
    for y in range(h):
        for x in range(w):
            i=y*w+x
            if x: a[i]=min(a[i],a[i-1]+1)
            if y: a[i]=min(a[i],a[i-w]+1)
    for y in range(h-1,-1,-1):
        for x in range(w-1,-1,-1):
            i=y*w+x
            if x<w-1: a[i]=min(a[i],a[i+1]+1)
            if y<h-1: a[i]=min(a[i],a[i+w]+1)
    return a

def signed_distance(mask):
    inside=distance_to(mask,False); outside=distance_to(mask,True)
    return [i-o for i,o in zip(inside,outside)]

def transition_frames(source, target, count=18):
    """Morph monocromatico entre dos mascaras, reutilizable con cualquier hora."""
    a,b=signed_distance(source),signed_distance(target)
    result=[source.copy()]
    for step in range(1,count):
        t=step/count; t=t*t*(3-2*t)
        im=Image.new('1',SIZE)
        im.putdata([255 if x*(1-t)+y*t>0 else 0 for x,y in zip(a,b)])
        result.append(im)
    result.append(target.copy())
    return result




