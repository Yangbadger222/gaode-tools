import json
import sys
from pathlib import Path

from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QGraphicsRectItem
from PIL import Image

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from amap_tool.annotator import AnnotatorWindow, DelayedHelp, View
from amap_tool.app_state import AppStateStore


class _Window:
    mode = "SELECT"
    drag = None

    def __init__(self, drag=None):
        self.drag_to_start = drag
        self.clicks = 0
        self.moves = 0

    def click(self, *_args):
        self.clicks += 1
        self.drag = self.drag_to_start

    def move(self, *_args):
        self.moves += 1

    def release(self):
        pass

    def statusBar(self):
        return self

    def showMessage(self, *_args):
        pass


def test_middle_drag_pans_canvas():
    app = QApplication.instance() or QApplication([])
    view = View(_Window())
    view.resize(200, 200)
    view.scene().addItem(QGraphicsRectItem(0, 0, 2000, 2000))
    view.show()
    app.processEvents()

    start = view.horizontalScrollBar().value()
    QTest.mousePress(view.viewport(), Qt.MouseButton.MiddleButton, pos=QPoint(130, 100))
    QTest.mouseMove(view.viewport(), QPoint(70, 100))
    QTest.mouseRelease(view.viewport(), Qt.MouseButton.MiddleButton, pos=QPoint(70, 100))

    assert view.horizontalScrollBar().value() > start


def test_select_mode_left_drag_on_canvas_pans():
    app = QApplication.instance() or QApplication([])
    window = _Window()
    view = View(window)
    view.resize(200, 200)
    view.scene().addItem(QGraphicsRectItem(0, 0, 2000, 2000))
    view.show()
    app.processEvents()

    start = view.horizontalScrollBar().value()
    QTest.mousePress(view.viewport(), Qt.MouseButton.LeftButton, pos=QPoint(130, 100))
    QTest.mouseMove(view.viewport(), QPoint(70, 100))
    QTest.mouseRelease(view.viewport(), Qt.MouseButton.LeftButton, pos=QPoint(70, 100))

    assert window.clicks == 1
    assert view.horizontalScrollBar().value() > start
    assert window.moves == 0


def test_left_drag_on_node_remains_geometry_edit():
    app = QApplication.instance() or QApplication([])
    window = _Window(drag=("node", "n1"))
    view = View(window)
    view.resize(200, 200)
    view.scene().addItem(QGraphicsRectItem(0, 0, 2000, 2000))
    view.show()
    app.processEvents()

    start = view.horizontalScrollBar().value()
    QTest.mousePress(view.viewport(), Qt.MouseButton.LeftButton, pos=QPoint(130, 100))
    QTest.mouseMove(view.viewport(), QPoint(70, 100))
    QTest.mouseRelease(view.viewport(), Qt.MouseButton.LeftButton, pos=QPoint(70, 100))

    assert view.horizontalScrollBar().value() == start
    assert window.moves == 1


def test_trackpad_pixel_scroll_pans_canvas():
    app = QApplication.instance() or QApplication([])
    view = View(_Window())
    view.resize(200, 200)
    view.scene().addItem(QGraphicsRectItem(0, 0, 2000, 2000))
    view.show()
    app.processEvents()

    start = view.verticalScrollBar().value()
    event = QWheelEvent(
        QPointF(100, 100), QPointF(100, 100), QPoint(0, -40), QPoint(),
        Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.ScrollUpdate, False,
    )
    view.wheelEvent(event)

    assert view.verticalScrollBar().value() > start


def test_zoom_scale_is_clamped_to_a_usable_range():
    app = QApplication.instance() or QApplication([])
    view = View(_Window())

    view.apply_zoom(1000)
    assert view.transform().m11() <= View.MAX_ZOOM

    view.apply_zoom(0.000001)
    assert view.transform().m11() >= View.MIN_ZOOM


def test_next_image_saves_current_annotation_and_loads_next_region(tmp_path):
    app = QApplication.instance() or QApplication([])
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    first.write_text(json.dumps({"region_id": "first", "tiles": []}), encoding="utf-8")
    second.write_text(json.dumps({"region_id": "second", "tiles": []}), encoding="utf-8")
    first_output = tmp_path / "first.annotation.json"
    second_output = tmp_path / "second.annotation.json"
    window = AnnotatorWindow(
        first,
        first_output,
        [(first, first_output), (second, second_output)],
        state_store=AppStateStore(tmp_path / "state.json"),
    )

    window.m.add_segment([[1, 1], [10, 10]])
    window.dirty = True
    window.navigate(1)

    upgraded = tmp_path / "annotations_v2" / first_output.name
    assert json.loads(upgraded.read_text(encoding="utf-8"))["segments"][0]["edge_id"] == "e000001"
    assert window.region["region_id"] == "second"
    assert window.nav_label.text().strip() == "区域 2/2（共 0 张图）: second"
    assert window.previous_action.isEnabled()
    assert not window.next_action.isEnabled()
    window.close()


def test_clean_rgb_and_zoom_do_not_change_annotation(tmp_path):
    app = QApplication.instance() or QApplication([])
    region = tmp_path / "region.json"
    region.write_text(json.dumps({"region_id": "one", "tiles": []}), encoding="utf-8")
    window = AnnotatorWindow(region, tmp_path / "one.json", state_store=AppStateStore(tmp_path / "state.json"))
    window.m.add_segment([[0, 0], [100, 0]])
    before = window.m.snapshot()

    window.toggle_clean_rgb(True)
    window.set_zoom(4)
    window.set_layer("draft", False)

    assert window.m.data == before
    assert window.clean_rgb
    assert window.view.transform().m11() == 4
    window.dirty = False
    window.close()


def test_open_folder_starts_on_first_image_and_saves_only_on_first_action(tmp_path):
    app = QApplication.instance() or QApplication([])
    Image.new("RGB", (64, 48), "green").save(tmp_path / "a.png")
    output = tmp_path / "annotations_v2" / "a.json"
    window = AnnotatorWindow(state_store=AppStateStore(tmp_path / "state.json"))

    window.open_folder(tmp_path)

    assert window.current_record.image_id == "a"
    assert window.central_stack.currentIndex() == 1
    assert not output.exists()
    window.m.add_segment([[1, 1], [20, 20]])
    window.changed(model_already_changed=True)
    assert window.save()
    assert output.exists()
    assert json.loads(output.read_text())["schema_version"] == 2
    window.close()


def test_read_only_dataset_blocks_annotation_write(tmp_path):
    app = QApplication.instance() or QApplication([])
    Image.new("RGB", (64, 48), "green").save(tmp_path / "a.png")
    output = tmp_path / "annotations_v2" / "a.json"
    window = AnnotatorWindow(state_store=AppStateStore(tmp_path / "state.json"))
    window.open_folder(tmp_path, read_only=True)
    window.m.add_segment([[1, 1], [20, 20]])
    window.dirty = True

    assert not window.save()
    assert not output.exists()
    window.dirty = False
    window.close()


def test_refresh_folder_adds_new_images_without_losing_current_document(tmp_path):
    app = QApplication.instance() or QApplication([])
    Image.new("RGB", (64, 48), "green").save(tmp_path / "a.png")
    window = AnnotatorWindow(state_store=AppStateStore(tmp_path / "state.json"))
    window.open_folder(tmp_path)
    Image.new("RGB", (64, 48), "blue").save(tmp_path / "b.png")

    window.refresh_folder()

    assert {record.image_id for record in window.dataset.records} == {"a", "b"}
    assert window.current_record.image_id == "a"
    window.close()


def test_language_switch_is_live_and_persisted(tmp_path):
    app = QApplication.instance() or QApplication([])
    state_path = tmp_path / "state.json"
    window = AnnotatorWindow(state_store=AppStateStore(state_path))

    assert window.language == "zh_CN"
    assert window.open_action.text() == "打开文件夹"
    assert window.inspector_tabs.currentIndex() == 2
    window.set_language("en_US")

    assert window.open_action.text() == "Open Folder"
    assert window.inspector_tabs.tabText(2) == "Image Guide"
    assert AppStateStore(state_path).language() == "en_US"
    window.close()


def test_button_help_uses_three_second_delay(tmp_path):
    app = QApplication.instance() or QApplication([])
    window = AnnotatorWindow(state_store=AppStateStore(tmp_path / "state.json"))
    button = window.main_toolbar.widgetForAction(window.draw_action)

    assert window.delayed_help.timer.interval() == DelayedHelp.DELAY_MS == 3000
    assert button.property("delayedHelpKey") == "help_draw"
    button.setEnabled(True)
    QApplication.sendEvent(button, QEvent(QEvent.Type.Enter))
    assert window.delayed_help.timer.isActive()
    assert window.delayed_help.eventFilter(button, QEvent(QEvent.Type.ToolTip))
    QApplication.sendEvent(button, QEvent(QEvent.Type.Leave))
    assert not window.delayed_help.timer.isActive()
    window.close()


def test_image_guide_tracks_annotation_progress(tmp_path):
    app = QApplication.instance() or QApplication([])
    Image.new("RGB", (64, 48), "green").save(tmp_path / "a.png")
    window = AnnotatorWindow(state_store=AppStateStore(tmp_path / "state.json"))
    window.open_folder(tmp_path)

    assert "第 1 步" in window.guide_title.text()
    edge_id = window.m.add_segment([[1, 1], [21, 1]])
    window.changed(model_already_changed=True)
    assert "第 2 步" in window.guide_title.text()
    window.m.assign_evidence(edge_id, 0, 20, "clear_visual")
    window.changed(model_already_changed=True)
    assert "第 3 步" in window.guide_title.text()
    assert window.save()
    assert window.guide_title.text() == "本图已完成"
    window.close()


def test_legacy_folder_save_and_reopen_uses_v2_copy(tmp_path):
    app = QApplication.instance() or QApplication([])
    Image.new("RGB", (100, 80), "green").save(tmp_path / "a.png")
    legacy_path = tmp_path / "a.json"
    legacy = {
        "schema_version": "1.1",
        "region": {"region_id": "a", "draft_source": "osm"},
        "nodes": [],
        "edges": [{"id": "e1", "polyline": [[0, 0], [100, 0]], "path_type": "pedestrian_path"}],
    }
    legacy_path.write_text(json.dumps(legacy), encoding="utf-8")
    original = legacy_path.read_bytes()
    state_path = tmp_path / "state.json"
    first = AnnotatorWindow(state_store=AppStateStore(state_path))
    first.open_folder(tmp_path)
    first.m.assign_evidence("e1", 0, 100, "weak_visual")
    first.changed(model_already_changed=True)
    assert first.save()
    first.close()

    second = AnnotatorWindow(state_store=AppStateStore(state_path))
    second.open_folder(tmp_path)

    assert legacy_path.read_bytes() == original
    assert second.source_was_legacy is False
    assert second.m.segment("e1")["evidence_spans"][0]["evidence"] == "weak_visual"
    second.close()


def test_last_image_zoom_and_layer_session_restore(tmp_path):
    app = QApplication.instance() or QApplication([])
    Image.new("RGB", (64, 48), "green").save(tmp_path / "a.png")
    Image.new("RGB", (64, 48), "blue").save(tmp_path / "b.png")
    state_path = tmp_path / "state.json"
    first = AnnotatorWindow(state_store=AppStateStore(state_path))
    first.open_folder(tmp_path)
    first.load_record(first.dataset.record_by_id("b"))
    first.set_zoom(4)
    first.set_layer("draft", False)
    first.save_session_state()
    first.close()

    second = AnnotatorWindow(state_store=AppStateStore(state_path))
    second.open_folder(tmp_path)

    assert second.current_record.image_id == "b"
    assert second.view.transform().m11() == 4
    assert not second.layer_state["draft"]
    second.close()
