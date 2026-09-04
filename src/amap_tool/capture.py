from __future__ import annotations

import csv
import json
import math
import os
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv
from .browser_locator import find_system_browser

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")


from .mercator import meters_per_pixel


def metadata_row(image_id, lat, lon, zoom, width, height, output_file, note=""):
    mpp = meters_per_pixel(lat, zoom)
    return {
        "image_id": image_id, "source": "amap_js_api", "map_type": "satellite",
        "lat": lat, "lon": lon, "zoom": zoom, "width": width, "height": height,
        "output_file": str(output_file),
        "capture_time": datetime.now(timezone.utc).isoformat(), "api_mode": "js api",
        "note": note, "estimated_meters_per_pixel": round(mpp, 6),
        "estimated_ground_width_m": round(mpp * width, 3),
        "estimated_ground_height_m": round(mpp * height, 3),
    }


def _html(key, security_code, lat, lon, zoom, width, height):
    # Values are JSON encoded to avoid accidental script injection from CLI input.
    cfg = json.dumps({"key": key, "security": security_code or "", "lat": lat, "lon": lon,
                      "zoom": zoom, "width": width, "height": height})
    return f'''<!doctype html><html><head><meta charset="utf-8"><style>
html,body,#map{{margin:0;width:{width}px;height:{height}px;overflow:hidden;background:#ddd}}
.amap-logo,.amap-copyright{{opacity:.65;transform:scale(.75);transform-origin:left bottom}}
</style></head><body><div id="map"></div><script>
const C={cfg};
window._mapReady=false; window._mapError='';
window._AMapSecurityConfig={{securityJsCode:C.security}};
</script><script src="https://webapi.amap.com/maps?v=2.0&key={key}&callback=initMap"></script>
<script>function initMap(){{try{{const map=new AMap.Map('map',{{zoom:C.zoom,center:[C.lon,C.lat],viewMode:'2D',zoomEnable:false,dragEnable:false,rotateEnable:false,resizeEnable:false,showLabel:false,features:[]}});map.addLayer(new AMap.TileLayer.Satellite());map.on('complete',()=>{{setTimeout(()=>window._mapReady=true,1200)}});}}catch(e){{window._mapError=String(e)}}}}
setTimeout(()=>{{if(!window._mapReady&&!window._mapError)window._mapError='Timed out waiting for AMap';}},30000);</script></body></html>'''


class _Handler(BaseHTTPRequestHandler):
    html = ""
    def do_GET(self):
        if urlparse(self.path).path != "/": self.send_error(404); return
        body = self.html.encode()
        self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
    def log_message(self, *_): pass


def capture_one(lat, lon, zoom, output, width=1024, height=1024, image_id="image", timeout_ms=60000):
    key = os.getenv("AMAP_JS_API_KEY")
    if not key or key == "your_key_here": raise RuntimeError("AMAP_JS_API_KEY is missing in .env or environment")
    output = Path(output); output.parent.mkdir(parents=True, exist_ok=True)
    _Handler.html = _html(key, os.getenv("AMAP_JS_SECURITY_CODE"), lat, lon, zoom, width, height)
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            _, executable = find_system_browser()
            try: browser = p.chromium.launch(headless=True, executable_path=str(executable)) if executable else p.chromium.launch(headless=True)
            except Exception as exc:
                raise RuntimeError('No supported Chromium browser was found. Install Google Chrome / Microsoft Edge or run: playwright install chromium') from exc
            page = browser.new_page(viewport={"width": width, "height": height}, device_scale_factor=1)
            page.goto(f"http://127.0.0.1:{server.server_port}/", wait_until="domcontentloaded", timeout=timeout_ms)
            page.wait_for_function("window._mapReady || window._mapError", timeout=timeout_ms)
            error = page.evaluate("window._mapError")
            if error: raise RuntimeError(f"AMap failed to load: {error}")
            page.locator("#map").screenshot(path=str(output), type="png")
            browser.close()
    finally:
        server.shutdown(); server.server_close()
    return metadata_row(image_id, lat, lon, zoom, width, height, output)


def write_metadata(rows, path):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0].keys()) if rows else []
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(rows)
