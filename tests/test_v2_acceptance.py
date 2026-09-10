import hashlib
import json
import sys
from pathlib import Path

from PIL import Image
from PySide6.QtCore import QPointF
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QComboBox, QPushButton

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


def test_v2_semantics_ui_flow_and_full_review_is_explicit(tmp_path):
    app = QApplication.instance() or QApplication([])
    rgb = tmp_path / "campus.png"
    Image.new("RGB", (1024, 1024), (80, 100, 70)).save(rgb)
    rgb_hash = hashlib.sha256(rgb.read_bytes()).hexdigest()
    window = AnnotatorWindow(state_store=AppStateStore(tmp_path / "state.json"))
    window.open_folder(tmp_path)
    edge_id = window.m.add_segment([[100, 500], [500, 500], [900, 500]])
    window.changed(model_already_changed=True)

    window.set_mode("EVIDENCE")
    window.evidence_selection = (edge_id, 300, 500)
    window.assign_selected_evidence("E")
    window.evidence_selection = (edge_id, 0, 300)
    window.assign_selected_evidence("A")
    window.evidence_selection = (edge_id, 500, 800)
    window.assign_selected_evidence("B")
    window.sel = ("edge", edge_id)
    window.update_inspector()
    assert window.m.segment(edge_id)["excluded_from_task"] is False
    assert len(window.m.data["segments"]) == 1
    assert len(window.m.segment(edge_id)["evidence_spans"]) == 3

    exclude_buttons = [
        button
        for button in window.findChildren(QPushButton)
        if button.text() == "排除整条路径"
    ]
    assert exclude_buttons
    QTest.mouseClick(exclude_buttons[-1], Qt.MouseButton.LeftButton)
    assert window.m.segment(edge_id)["excluded_from_task"] is True
    assert len(window.m.data["segments"]) == 1
    window.undo()
    assert window.m.segment(edge_id)["excluded_from_task"] is False
    window.redo()
    assert window.m.segment(edge_id)["excluded_from_task"] is True
    window.restore_edge(edge_id)
    assert window.m.segment(edge_id)["excluded_from_task"] is False

    window.sel = ("span", edge_id, 500.0, 800.0)
    window.update_inspector()
    issue_combos = [combo for combo in window.findChildren(QComboBox) if combo.findData("tree_canopy") >= 0]
    assert issue_combos
    issue_combos[-1].setCurrentIndex(issue_combos[-1].findData("tree_canopy"))
    assert window.m.segment(edge_id)["evidence_spans"][2]["visibility_issue"] == "tree_canopy"
    assert window.m.data["review_scope"] == "partial"
    window.mark_image_reviewed()
    assert window.m.data["annotation_status"] == "reviewed"
    assert window.m.data["review_scope"] == "partial"
    QTest.mouseClick(window.mark_full_review_button, Qt.MouseButton.LeftButton)
    assert window.m.data["review_scope"] == "full_image"
    assert hashlib.sha256(rgb.read_bytes()).hexdigest() == rgb_hash
    window.close()

    reopened = AnnotatorWindow(state_store=AppStateStore(tmp_path / "state-reopen.json"))
    reopened.open_folder(tmp_path)
    segment = reopened.m.segment(edge_id)
    assert reopened.m.data["review_scope"] == "full_image"
    assert segment["evidence_spans"][2]["visibility_issue"] == "tree_canopy"
    assert segment["excluded_from_task"] is False
    assert hashlib.sha256(rgb.read_bytes()).hexdigest() == rgb_hash
    reopened.close()
