from __future__ import annotations
import os, platform, shutil
from pathlib import Path

def find_system_browser():
    override=os.getenv('AMAP_BROWSER_EXECUTABLE')
    if override and Path(override).is_file(): return ('configured',Path(override))
    system=platform.system(); candidates=[]
    if system=='Darwin': candidates=[('Google Chrome',Path('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'))]
    elif system=='Windows':
        pf=os.getenv('PROGRAMFILES',''); pfx=os.getenv('PROGRAMFILES(X86)',''); local=os.getenv('LOCALAPPDATA','')
        candidates=[('Google Chrome',Path(x)/'Google/Chrome/Application/chrome.exe') for x in (pf,pfx,local) if x]
        candidates += [('Microsoft Edge',Path(x)/'Microsoft/Edge/Application/msedge.exe') for x in (pfx,pf,local) if x]
    for name,p in candidates:
        if p.is_file(): return name,p
    for cmd,name in [('chrome','Google Chrome'),('chrome.exe','Google Chrome'),('msedge','Microsoft Edge'),('msedge.exe','Microsoft Edge'),('chromium','Chromium')]:
        found=shutil.which(cmd)
        if found:return name,Path(found)
    return None,None
