#!/usr/bin/env python3
import argparse,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from amap_tool.annotator import launch
p=argparse.ArgumentParser(); p.add_argument('--region',required=True); p.add_argument('--annotation'); a=p.parse_args(); launch(a.region,a.annotation)
