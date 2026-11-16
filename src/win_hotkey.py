"""Windows global hotkey registration using the current keyboard layout."""
import ctypes
from ctypes import wintypes

class Hotkey:
    def __init__(self, value, identifier=1):
        self.identifier=identifier
        self.api=ctypes.WinDLL('user32',use_last_error=True)
        self.api.VkKeyScanW.argtypes=[wintypes.WCHAR]
        self.api.VkKeyScanW.restype=ctypes.c_short
        self.api.RegisterHotKey.argtypes=[wintypes.HWND,ctypes.c_int,wintypes.UINT,wintypes.UINT]
        self.api.RegisterHotKey.restype=wintypes.BOOL
        self.api.UnregisterHotKey.argtypes=[wintypes.HWND,ctypes.c_int]
        self.api.PeekMessageW.argtypes=[ctypes.POINTER(wintypes.MSG),wintypes.HWND,wintypes.UINT,wintypes.UINT,wintypes.UINT]
        self.api.PeekMessageW.restype=wintypes.BOOL
        parts=value.split('+')
        mods=0
        mapping={'ctrl':2,'control':2,'alt':1,'shift':4}
        for part in parts[:-1]:
            if part.lower() not in mapping: raise ValueError('Unknown modifier: '+part)
            mods |= mapping[part.lower()]
        key=parts[-1]
        if len(key)==1:
            # Letras con Ctrl/Alt no requieren Shift solo por estar en mayusculas.
            code=self.api.VkKeyScanW(key.lower() if key.isalpha() else key)
            if code==-1: raise ValueError('The keyboard layout does not contain '+key)
            vk=code&255; shift=(code>>8)&255
            if shift&1: mods|=4
            if shift&2: mods|=2
            if shift&4: mods|=1
        elif key.lower() in {'space','tab','enter','escape','backspace','delete','insert','home','end','pageup','pagedown','up','down','left','right'}:
            vk={'space':32,'tab':9,'enter':13,'escape':27,'backspace':8,'delete':46,'insert':45,'home':36,'end':35,'pageup':33,'pagedown':34,'up':38,'down':40,'left':37,'right':39}[key.lower()]
        elif key.upper().startswith('F') and key[1:].isdigit() and 1<=int(key[1:])<=11:
            vk=111+int(key[1:])
        else: raise ValueError('Use a character, a named key, or F1 to F11')
        if not self.api.RegisterHotKey(None,self.identifier,mods|0x4000,vk):
            raise ctypes.WinError(ctypes.get_last_error())
        print(f'Global hotkey registered: {value}; VK={vk:#x}, modifiers={mods:#x}',flush=True)

    def pressed(self):
        msg=wintypes.MSG(); found=False
        while self.api.PeekMessageW(ctypes.byref(msg),None,0x312,0x312,1):
            if msg.wParam==self.identifier: found=True
        return found

    def close(self): self.api.UnregisterHotKey(None,self.identifier)
