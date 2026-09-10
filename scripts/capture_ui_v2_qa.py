#!/usr/bin/env python3
"""Capture reproducible offscreen UI QA screens from an existing RGB region."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from amap_tool.qt_runtime import prepare_qt_runtime

prepare_qt_runtime()

from amap_tool.annotation_schema import polyline_length
from amap_tool.annotator import AnnotatorWindow
from amap_tool.app_state import AppStateStore
from PySide6.QtWidgets import QApplication


def snap(app, window, path: Path) -> None:
    app.processEvents()
    path.parent.mkdir(parents=True, exist_ok=True)
    if not window.grab().save(str(path)):
        raise RuntimeError(f"could not save {path}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--folder", type=Path)
    source.add_argument("--region", type=Path)
    parser.add_argument("--annotation", type=Path)
    parser.add_argument("--image-id", help="image id to use after --folder scan")
    parser.add_argument("--out-dir", type=Path, default=Path("docs/ui_v2"))
    args = parser.parse_args()

    app = QApplication.instance() or QApplication([])
    state = AppStateStore(args.out_dir / ".qa-state.json")
    window = AnnotatorWindow(args.region, args.annotation, state_store=state) if args.region else AnnotatorWindow(state_store=state)
    window.resize(1440, 900)
    window.show()
    if args.folder:
        window.open_folder(args.folder)
        if args.image_id:
            record = window.dataset.record_by_id(args.image_id)
            if record is None:
                raise SystemExit(f"image id not found: {args.image_id}")
            window.load_record(record)
            window.render()
    window.fit_image()
    if window.m.data.get("segments"):
        segment = max(window.m.data["segments"], key=lambda item: polyline_length(item["points"]))
        edge_id = segment["edge_id"]
        total = polyline_length(segment["points"])
        window.m.assign_evidence(edge_id, 0.0, total * 0.4, "clear_visual")
        window.m.assign_evidence(edge_id, total * 0.4, total * 0.72, "weak_visual")
        window.m.assign_evidence(edge_id, total * 0.72, total, "context_only")
        window.sel = ("edge", edge_id)
    window.render()
    window.update_ui_state()
    snap(app, window, args.out_dir / "01_default.png")

    window.toggle_clean_rgb(True)
    snap(app, window, args.out_dir / "02_clean_rgb.png")

    window.toggle_clean_rgb(False)
    window.set_mode("EVIDENCE")
    if window.m.data.get("segments"):
        segment = max(window.m.data["segments"], key=lambda item: polyline_length(item["points"]))
        total = polyline_length(segment["points"])
        window.evidence_selection = (segment["edge_id"], total * 0.4, total * 0.72)
    window.render()
    snap(app, window, args.out_dir / "03_evidence_mode.png")

    window.toggle_review_view(True)
    window.fit_image()
    snap(app, window, args.out_dir / "04_review_view.png")

    window.toggle_review_view(False)
    window.set_interpolation("Pixel")
    window.set_zoom(4)
    if window.m.data.get("segments"):
        segment = max(window.m.data["segments"], key=lambda item: polyline_length(item["points"]))
        window.sel = ("point", segment["edge_id"], min(1, len(segment["points"]) - 1))
        window.view.centerOn(*segment["points"][min(1, len(segment["points"]) - 1)])
    window.sidebar_dock.hide()
    window.inspector_dock.hide()
    window.render()
    snap(app, window, args.out_dir / "05_zoom_edit.png")
    window.dirty = False
    window.close()
    state.path.unlink(missing_ok=True)
    print(f"Saved 5 UI QA screenshots to {args.out_dir.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
