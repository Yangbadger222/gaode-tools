#!/usr/bin/env python3
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from amap_tool.graph_model import GraphModel
p=argparse.ArgumentParser(); p.add_argument('annotation'); a=p.parse_args(); d=json.loads(Path(a.annotation).read_text()); s=GraphModel(d).stats(); out=Path(a.annotation).with_name(Path(a.annotation).stem+'_stats.json'); out.write_text(json.dumps(s,ensure_ascii=False,indent=2),encoding='utf-8'); print(json.dumps(s,ensure_ascii=False,indent=2))
