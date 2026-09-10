import hashlib
import json
import sys
from pathlib import Path

from PIL import Image
from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QApplication

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from amap_tool.annotator import AnnotatorWindow
from amap_tool.app_state import AppStateStore


def test_full_legacy_review_save_restart_workflow(tmp_path):
    app = QApplication.instance() or QApplication([])
    rgb = tmp_path / "campus.png"
    Image.new("RGB", (1024, 1024), (60, 90, 65)).save(rgb)
    rgb_hash = hashlib.sha256(rgb.read_bytes()).hexdigest()
    legacy_path = tmp_path / "campus.json"
    legacy = {
        "schema_version": "1.1",
        "region": {"region_id": "campus", "draft_source": "osm"},
        "nodes": [],
        "edges": [
            {
                "id": "e1",
                "polyline": [[100, 500], [500, 500], [900, 500]],
                "path_type": "pedestrian_path",
            }
        ],
    }
    legacy_path.write_text(json.dumps(legacy), encoding="utf-8")
    legacy_bytes = legacy_path.read_bytes()
    state_path = tmp_path / "app-state.json"
    first = AnnotatorWindow(state_store=AppStateStore(state_path))
    first.open_folder(tmp_path)

    first.toggle_clean_rgb(True)
    assert first.clean_rgb
    first.toggle_clean_rgb(False)
    first.sel = ("edge", "e1")
    first.set_mode("EVIDENCE")
    first.evidence_press(QPointF(250, 500))
    first.evidence_release(QPointF(450, 500))
    first.assign_selected_evidence("B")
    first.auto_advance.setChecked(False)
    first.evidence_press(QPointF(550, 500))
    first.evidence_release(QPointF(750, 500))
    first.assign_selected_evidence("C")
    spans_before_undo = first.m.snapshot()["segments"][0]["evidence_spans"]
    first.undo()
    first.redo()
    assert first.m.segment("e1")["evidence_spans"] == spans_before_undo

    first.m.move_point("e1", 1, [500, 520])
    first.changed(model_already_changed=True)
    assert first.save()
    saved_geometry = first.m.segment("e1")["points"]
    saved_spans = first.m.segment("e1")["evidence_spans"]
    first.close()

    second = AnnotatorWindow(state_store=AppStateStore(state_path))
    second.open_folder(tmp_path)

    assert second.m.segment("e1")["points"] == saved_geometry
    assert second.m.segment("e1")["evidence_spans"] == saved_spans
    assert legacy_path.read_bytes() == legacy_bytes
    assert hashlib.sha256(rgb.read_bytes()).hexdigest() == rgb_hash
    assert (tmp_path / "annotations_v2" / "campus.json").exists()
    second.close()
