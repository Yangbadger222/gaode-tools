import sys
from pathlib import Path

from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QGraphicsRectItem

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from amap_tool.annotator import View


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
