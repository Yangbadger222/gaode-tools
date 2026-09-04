#!/usr/bin/env python3
import importlib.util,os,platform,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from dotenv import load_dotenv
from amap_tool.browser_locator import find_system_browser
load_dotenv(Path(__file__).resolve().parents[1]/'.env')
print('Platform:',platform.platform());print('Python:',sys.version.split()[0]);print('Executable:',sys.executable);print('Architecture:',platform.machine())
try:
 import PySide6
 from PySide6.QtCore import QLibraryInfo,qVersion
 plugins=Path(QLibraryInfo.path(QLibraryInfo.LibraryPath.PluginsPath)); target=plugins/'platforms'/('qwindows.dll' if platform.system()=='Windows' else 'libqcocoa.dylib')
 print('PySide6:',PySide6.__version__);print('Qt:',qVersion());print('Qt plugins:',plugins);print('Platform plugin:',target.name,'YES' if target.exists() else 'NO')
except Exception as e: print('PySide6: ERROR',e)
name,browser=find_system_browser();print('Browser:',name or 'NOT FOUND');print('Browser executable:',str(browser) if browser else 'NOT FOUND');print('Playwright:','YES' if importlib.util.find_spec('playwright') else 'NO');print('AMAP key configured:','YES' if os.getenv('AMAP_JS_API_KEY') else 'NO')
