"""Qt desktop annotator for complete paths and local evidence spans."""

from __future__ import annotations

import copy
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path

from .qt_runtime import prepare_qt_runtime

prepare_qt_runtime()

from PySide6.QtCore import QEvent, QPoint, QPointF, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import (
    QAction,
    QActionGroup,
    QBrush,
    QColor,
    QIcon,
    QKeySequence,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDockWidget,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGraphicsLineItem,
    QGraphicsItem,
    QGraphicsScene,
    QGraphicsView,
    QGroupBox,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSlider,
    QSplitter,
    QStackedWidget,
    QStatusBar,
    QTabWidget,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from .annotation_io import AnnotationWriteError, atomic_write_json
from .annotation_model import AnnotationModel
from .annotation_schema import (
    EVIDENCE_BY_KEY,
    EVIDENCE_COLORS,
    EVIDENCE_LABELS,
    empty_document,
    evidence_coverage,
    export_derived,
    polyline_length,
    polyline_slice,
    project_onto_polyline,
    upgrade_document,
)
from .app_state import AppStateStore
from .dataset_index import DatasetIndex, ImageRecord, dataset_from_files, scan_dataset
from .paths import portable_name, resolve_data_path


APP_TITLE = "AMap Path Annotator V2"
PATH_TYPES = ["vehicle_road", "pedestrian_path", "narrow_path", "service_path"]
PATH_COLORS = {
    "vehicle_road": "#b85c52",
    "pedestrian_path": "#d08b45",
    "narrow_path": "#64866b",
    "service_path": "#547b96",
}


def atomic_save(data, path):
    """Backward-compatible alias retained for scripts importing the old helper."""
    return atomic_write_json(data, path)


def _pen(color: str | QColor, width: float, *, opacity: float = 1.0, dashed: bool = False) -> QPen:
    value = QColor(color) if isinstance(color, str) else QColor(color)
    value.setAlphaF(max(0.0, min(1.0, opacity)))
    pen = QPen(value, width)
    pen.setCosmetic(True)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    if dashed:
        pen.setStyle(Qt.PenStyle.DashLine)
    return pen


def _path(points) -> QPainterPath:
    if not points:
        return QPainterPath()
    result = QPainterPath(QPointF(float(points[0][0]), float(points[0][1])))
    for point in points[1:]:
        result.lineTo(QPointF(float(point[0]), float(point[1])))
    return result


class View(QGraphicsView):
    """Image canvas with mouse, wheel, middle-drag and macOS gesture support."""

    MIN_ZOOM = 0.10
    MAX_ZOOM = 12.0

    def __init__(self, window, *, clean=False, interactive=True):
        super().__init__()
        self.w = window
        self.clean = clean
        self.interactive = interactive
        self.setScene(QGraphicsScene(self))
        self.setMouseTracking(True)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setBackgroundBrush(QColor("#2b2b29"))
        self.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self.pan_origin: QPoint | None = None
        self.space_down = False

    def apply_zoom(self, factor: float) -> None:
        current = self.transform().m11()
        target = max(self.MIN_ZOOM, min(self.MAX_ZOOM, current * factor))
        if current > 0:
            self.scale(target / current, target / current)
        if hasattr(self.w, "view_transform_changed"):
            self.w.view_transform_changed(self)
        else:
            self.w.statusBar().showMessage(f"Mode: {self.w.mode}  Zoom: {target:.2f}x")

    def set_native_scale(self, scale: float) -> None:
        self.resetTransform()
        self.scale(scale, scale)
        if hasattr(self.w, "view_transform_changed"):
            self.w.view_transform_changed(self)

    def begin_pan(self, event) -> None:
        self.pan_origin = event.position().toPoint()
        self.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.MiddleButton or (
            event.button() == Qt.MouseButton.LeftButton and self.space_down
        ):
            self.begin_pan(event)
            event.accept()
            return
        if not self.interactive:
            if event.button() == Qt.MouseButton.LeftButton:
                self.begin_pan(event)
            return
        scene_point = self.mapToScene(event.position().toPoint())
        if getattr(self.w, "mode", "SELECT") == "EVIDENCE" and event.button() == Qt.MouseButton.LeftButton:
            self.w.evidence_press(scene_point)
            event.accept()
            return
        self.w.click(scene_point, event)
        if (
            event.button() == Qt.MouseButton.LeftButton
            and getattr(self.w, "mode", "SELECT") in ("SELECT", "EDIT")
            and not getattr(self.w, "drag", None)
        ):
            self.begin_pan(event)

    def mouseMoveEvent(self, event) -> None:
        scene_point = self.mapToScene(event.position().toPoint())
        if hasattr(self.w, "cursor_moved"):
            self.w.cursor_moved(scene_point)
        if self.pan_origin is not None:
            current = event.position().toPoint()
            delta = current - self.pan_origin
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
            self.pan_origin = current
            if hasattr(self.w, "view_transform_changed"):
                self.w.view_transform_changed(self)
            event.accept()
            return
        if not self.interactive:
            return
        if getattr(self.w, "mode", "SELECT") == "EVIDENCE":
            self.w.evidence_move(scene_point)
        else:
            self.w.move(scene_point, event)

    def mouseReleaseEvent(self, event) -> None:
        scene_point = self.mapToScene(event.position().toPoint())
        if self.pan_origin is not None:
            self.pan_origin = None
            self.viewport().unsetCursor()
            if hasattr(self.w, "view_transform_changed"):
                self.w.view_transform_changed(self)
            event.accept()
            return
        if self.interactive and getattr(self.w, "mode", "SELECT") == "EVIDENCE":
            self.w.evidence_release(scene_point)
        elif self.interactive:
            self.w.release()
            self.w.drag = None

    def mouseDoubleClickEvent(self, event) -> None:
        if self.interactive:
            self.w.double_click(self.mapToScene(event.position().toPoint()), event)
        else:
            self.w.fit_image()

    def wheelEvent(self, event) -> None:
        pixel = event.pixelDelta()
        if not pixel.isNull() and not (
            event.modifiers() & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.MetaModifier)
        ):
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - pixel.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - pixel.y())
            if hasattr(self.w, "view_transform_changed"):
                self.w.view_transform_changed(self)
            event.accept()
            return
        delta = event.angleDelta().y() or pixel.y()
        if delta:
            self.apply_zoom(1.18 if delta > 0 else 1 / 1.18)
        event.accept()

    def event(self, event) -> bool:
        if event.type() == QEvent.Type.NativeGesture and event.gestureType() == Qt.NativeGestureType.ZoomNativeGesture:
            self.apply_zoom(max(0.1, 1.0 + event.value()))
            event.accept()
            return True
        return super().event(event)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Space:
            self.space_down = True
            self.viewport().setCursor(Qt.CursorShape.OpenHandCursor)
            event.accept()
            return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Space:
            self.space_down = False
            self.viewport().unsetCursor()
            event.accept()
            return
        super().keyReleaseEvent(event)

    def contextMenuEvent(self, event) -> None:
        if self.interactive and hasattr(self.w, "show_context_menu"):
            self.w.show_context_menu(event.globalPos(), self.mapToScene(event.pos()))
        else:
            super().contextMenuEvent(event)


class WelcomePage(QWidget):
    def __init__(self, window):
        super().__init__()
        self.window = window
        outer = QVBoxLayout(self)
        outer.addStretch(2)
        panel = QWidget()
        panel.setMaximumWidth(520)
        layout = QVBoxLayout(panel)
        title = QLabel("AMap Path Annotator")
        title.setObjectName("welcomeTitle")
        subtitle = QLabel("Open an image folder and start annotating. Original RGB files stay unchanged.")
        subtitle.setWordWrap(True)
        subtitle.setObjectName("muted")
        button = QPushButton("Open Folder")
        button.setObjectName("primaryButton")
        button.setMinimumHeight(40)
        button.clicked.connect(window.choose_folder)
        self.recent_title = QLabel("Recent Folders")
        self.recent_layout = QVBoxLayout()
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addSpacing(18)
        layout.addWidget(button)
        layout.addSpacing(26)
        layout.addWidget(self.recent_title)
        layout.addLayout(self.recent_layout)
        outer.addWidget(panel, alignment=Qt.AlignmentFlag.AlignHCenter)
        outer.addStretch(3)

    def refresh_recents(self, recents: list[dict]) -> None:
        while self.recent_layout.count():
            item = self.recent_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.recent_title.setVisible(bool(recents))
        for recent in recents:
            path = Path(recent.get("path", ""))
            opened = str(recent.get("last_opened", ""))[:10]
            row = QPushButton(f"{path.name or path}   {opened}  {'Missing' if not path.exists() else ''}".strip())
            row.setToolTip(str(path))
            row.setEnabled(path.exists())
            row.setObjectName("recentButton")
            row.clicked.connect(lambda _checked=False, value=path: self.window.open_folder(value))
            if path.exists():
                self.recent_layout.addWidget(row)
            else:
                wrapper = QWidget()
                layout = QHBoxLayout(wrapper)
                layout.setContentsMargins(0, 0, 0, 0)
                remove = QPushButton("Remove")
                remove.clicked.connect(lambda _checked=False, value=path: self.window.remove_recent(value))
                layout.addWidget(row, 1)
                layout.addWidget(remove)
                self.recent_layout.addWidget(wrapper)


class DatasetSettingsDialog(QDialog):
    def __init__(self, dataset: DatasetIndex, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Dataset Settings")
        form = QFormLayout(self)
        self.root = QLineEdit(str(dataset.root))
        self.root.setReadOnly(True)
        self.images = QLineEdit(str(dataset.image_root))
        self.annotations = QLineEdit(str(dataset.annotation_root or ""))
        self.output = QLineEdit(str(dataset.output_root))
        self.recursive = QCheckBox("Scan subfolders")
        self.recursive.setChecked(dataset.recursive)
        self.read_only = QCheckBox("Read Only / Sealed")
        self.read_only.setChecked(dataset.read_only)
        form.addRow("Root Folder", self.root)
        form.addRow("Image Folder", self.images)
        form.addRow("Annotation Folder", self.annotations)
        form.addRow("Output Folder", self.output)
        form.addRow("Recursive Scan", self.recursive)
        form.addRow("Safety", self.read_only)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)


class AnnotatorWindow(QMainWindow):
    def __init__(
        self,
        region_file=None,
        annotation_file=None,
        queue=None,
        queue_index=0,
        *,
        state_store: AppStateStore | None = None,
    ):
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.setAcceptDrops(True)
        self.state_store = state_store or AppStateStore()
        self.dataset: DatasetIndex | None = None
        self.queue = queue or []
        self.queue_index = 0
        self.current_record: ImageRecord | None = None
        self.m: AnnotationModel | None = None
        self.source_images: list[tuple[Path, float, float]] = []
        self.pixmap_cache: dict[Path, QPixmap] = {}
        self.canvas_rect = QRectF(0, 0, 1024, 1024)
        self.mode = "SELECT"
        self.sel = None
        self.temp: list[list[float]] = []
        self.preview_point: list[float] | None = None
        self.drag = None
        self.drag_before = None
        self.evidence_anchor = None
        self.evidence_selection = None
        self.hover_edge_id = None
        self.merge_pending_edge = None
        self.dirty = False
        self.source_was_legacy = False
        self.annotation_source: Path | None = None
        self.out: Path | None = None
        self.rpath: Path | None = None
        self.region: dict = {}
        self.layer_state = {
            "rgb": True,
            "draft": True,
            "manual": True,
            "evidence": True,
            "control_points": True,
        }
        self.clean_rgb = False
        self.review_view_enabled = False
        self.smooth_interpolation = True
        self.draft_opacity = 0.34
        self.evidence_opacity = 0.78
        self.last_cursor_point: QPointF | None = None
        self.review_cursor_items: dict[View, list[QGraphicsLineItem]] = {}
        self._syncing_views = False
        self._building_sidebar = False
        self._build_ui()
        self.autosave_timer = QTimer(self)
        self.autosave_timer.setSingleShot(True)
        self.autosave_timer.setInterval(900)
        self.autosave_timer.timeout.connect(self.autosave)
        self.session_timer = QTimer(self)
        self.session_timer.setSingleShot(True)
        self.session_timer.setInterval(400)
        self.session_timer.timeout.connect(self.save_session_state)

        if region_file is not None:
            self.queue = queue or [(Path(region_file), Path(annotation_file) if annotation_file else None)]
            self.queue_index = max(0, min(queue_index, len(self.queue) - 1))
            self.load_region(*self.queue[self.queue_index])
            self.show_editor()
        else:
            self.show_welcome()

    # ---------- UI construction ----------
    def _build_ui(self) -> None:
        self.setStyleSheet(self._stylesheet())
        self.central_stack = QStackedWidget()
        self.welcome = WelcomePage(self)
        self.central_stack.addWidget(self.welcome)
        self.central_stack.addWidget(self._build_canvas_page())
        self.setCentralWidget(self.central_stack)
        self._build_sidebar()
        self._build_inspector()
        self._build_toolbar()
        self._build_menus()
        self._build_status_bar()
        self.welcome.refresh_recents(self.state_store.recent_folders())

    def _build_canvas_page(self) -> QWidget:
        self.canvas_stack = QStackedWidget()
        self.view = View(self)
        self.canvas_stack.addWidget(self.view)

        self.review_clean = View(self, clean=True, interactive=False)
        self.review_overlay = View(self)
        review_splitter = QSplitter(Qt.Orientation.Horizontal)
        for label_text, view in (("Clean RGB", self.review_clean), ("Annotated", self.review_overlay)):
            wrapper = QWidget()
            layout = QVBoxLayout(wrapper)
            layout.setContentsMargins(0, 0, 0, 0)
            label = QLabel(label_text)
            label.setObjectName("canvasLabel")
            layout.addWidget(label)
            layout.addWidget(view, 1)
            review_splitter.addWidget(wrapper)
        review_splitter.setSizes([700, 700])
        self.canvas_stack.addWidget(review_splitter)
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.canvas_stack)
        return page

    def _build_sidebar(self) -> None:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 10, 10, 8)
        self.dataset_name = QLabel("No folder open")
        self.dataset_name.setObjectName("panelTitle")
        self.dataset_summary = QLabel("")
        self.dataset_summary.setObjectName("muted")
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search image_id")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.populate_sidebar)
        self.filter_combo = QComboBox()
        self.filter_combo.addItems(
            [
                "All",
                "Unreviewed",
                "Reviewed",
                "Has Ambiguity",
                "Has Context-only",
                "Has Misalignment",
                "Has Task mismatch",
            ]
        )
        self.filter_combo.currentTextChanged.connect(self.populate_sidebar)
        self.dataset_warnings = QPushButton("")
        self.dataset_warnings.setObjectName("warningButton")
        self.dataset_warnings.clicked.connect(self.show_dataset_issues)
        self.image_list = QListWidget()
        self.image_list.setIconSize(QSize(72, 54))
        self.image_list.setSpacing(1)
        self.image_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.image_list.currentItemChanged.connect(self.sidebar_selection_changed)
        layout.addWidget(self.dataset_name)
        layout.addWidget(self.dataset_summary)
        layout.addWidget(self.search)
        layout.addWidget(self.filter_combo)
        layout.addWidget(self.dataset_warnings)
        layout.addWidget(self.image_list, 1)
        self.sidebar_dock = QDockWidget("Dataset", self)
        self.sidebar_dock.setObjectName("DatasetDock")
        self.sidebar_dock.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetMovable)
        self.sidebar_dock.setWidget(panel)
        self.sidebar_dock.setMinimumWidth(230)
        self.sidebar_dock.setMaximumWidth(330)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.sidebar_dock)

    def _build_inspector(self) -> None:
        tabs = QTabWidget()
        properties_page = QWidget()
        self.form = QFormLayout(properties_page)
        self.form.addRow(QLabel("No selected path"))

        review_page = QWidget()
        review_layout = QVBoxLayout(review_page)
        self.review_progress = QLabel("Evidence reviewed: 0%")
        self.review_details = QLabel("Unreviewed path length: 0 px")
        self.review_details.setWordWrap(True)
        hint = QLabel(
            "B — Weak Visual\n图里还能指出具体视觉证据\n\n"
            "C — Context Only\n主要靠布局 / 常识推断"
        )
        hint.setWordWrap(True)
        hint.setObjectName("hintBox")
        self.auto_advance = QCheckBox("Auto-advance after evidence label")
        self.auto_advance.setChecked(True)
        self.mark_reviewed_button = QPushButton("Mark image reviewed")
        self.mark_reviewed_button.clicked.connect(self.mark_image_reviewed)
        review_layout.addWidget(self.review_progress)
        review_layout.addWidget(self.review_details)
        review_layout.addWidget(hint)
        review_layout.addWidget(self.auto_advance)
        review_layout.addWidget(self.mark_reviewed_button)
        review_layout.addStretch()

        layers_page = QWidget()
        layers_layout = QFormLayout(layers_page)
        self.layer_checks = {}
        for key, label in (
            ("rgb", "RGB"),
            ("draft", "Draft"),
            ("manual", "Manual Polyline"),
            ("evidence", "Evidence"),
            ("control_points", "Control Points"),
        ):
            check = QCheckBox(label)
            check.setChecked(self.layer_state[key])
            check.toggled.connect(lambda checked, name=key: self.set_layer(name, checked))
            self.layer_checks[key] = check
            layers_layout.addRow(check)
        self.draft_slider = QSlider(Qt.Orientation.Horizontal)
        self.draft_slider.setRange(5, 100)
        self.draft_slider.setValue(round(self.draft_opacity * 100))
        self.draft_slider.valueChanged.connect(self.set_draft_opacity)
        self.evidence_slider = QSlider(Qt.Orientation.Horizontal)
        self.evidence_slider.setRange(10, 100)
        self.evidence_slider.setValue(round(self.evidence_opacity * 100))
        self.evidence_slider.valueChanged.connect(self.set_evidence_opacity)
        self.interpolation_combo = QComboBox()
        self.interpolation_combo.addItems(["Smooth", "Pixel"])
        self.interpolation_combo.currentTextChanged.connect(self.set_interpolation)
        layers_layout.addRow("Draft opacity", self.draft_slider)
        layers_layout.addRow("Evidence opacity", self.evidence_slider)
        layers_layout.addRow("Display", self.interpolation_combo)

        self.warning_list = QListWidget()
        tabs.addTab(properties_page, "Inspector")
        tabs.addTab(review_page, "Review")
        tabs.addTab(layers_page, "Layers")
        tabs.addTab(self.warning_list, "Checks")
        self.inspector_dock = QDockWidget("Inspector / Review", self)
        self.inspector_dock.setObjectName("InspectorDock")
        self.inspector_dock.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetMovable)
        self.inspector_dock.setWidget(tabs)
        self.inspector_dock.setMinimumWidth(250)
        self.inspector_dock.setMaximumWidth(350)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.inspector_dock)

    def _action(self, text, callback, shortcut=None, tooltip=None, checkable=False) -> QAction:
        action = QAction(text, self)
        action.setCheckable(checkable)
        if shortcut:
            action.setShortcut(QKeySequence(shortcut))
        action.setToolTip(tooltip or text)
        action.setStatusTip(tooltip or text)
        action.triggered.connect(callback)
        return action

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("Main", self)
        toolbar.setObjectName("MainToolbar")
        toolbar.setMovable(False)
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        toolbar.setIconSize(QSize(16, 16))
        self.addToolBar(toolbar)
        self.open_action = self._action("Open Folder", self.choose_folder, "Ctrl+O", "Open an ordinary image folder")
        toolbar.addAction(self.open_action)
        toolbar.addSeparator()

        self.mode_group = QActionGroup(self)
        self.mode_group.setExclusive(True)
        self.select_action = self._action("Select", lambda: self.set_mode("SELECT"), "V", "Select and edit paths", True)
        self.draw_action = self._action("Draw", lambda: self.set_mode("DRAW_PATH"), "P", "Draw a complete path", True)
        self.edit_action = self._action("Edit", lambda: self.set_mode("EDIT"), None, "Edit control points", True)
        self.evidence_action = self._action("Evidence", lambda: self.set_mode("EVIDENCE"), "X", "Brush a local evidence span", True)
        for action in (self.select_action, self.draw_action, self.edit_action, self.evidence_action):
            self.mode_group.addAction(action)
            toolbar.addAction(action)
        self.select_action.setChecked(True)
        toolbar.addSeparator()

        self.undo_action = self._action("Undo", self.undo, "Ctrl+Z")
        self.redo_action = self._action("Redo", self.redo, "Ctrl+Shift+Z")
        toolbar.addAction(self.undo_action)
        toolbar.addAction(self.redo_action)
        toolbar.addSeparator()
        self.clean_action = self._action("Clean RGB", self.toggle_clean_rgb, "`", "Show only the untouched RGB", True)
        self.draft_action = self._action("Draft", self.toggle_draft_action, None, "Show/hide draft geometry", True)
        self.draft_action.setChecked(True)
        self.evidence_layer_action = self._action("Evidence color", self.toggle_evidence_action, None, "Show/hide evidence colors", True)
        self.evidence_layer_action.setChecked(True)
        self.review_action = self._action("Review View", self.toggle_review_view, "R", "Side-by-side clean and annotated views", True)
        toolbar.addAction(self.clean_action)
        toolbar.addAction(self.draft_action)
        toolbar.addAction(self.evidence_layer_action)
        toolbar.addAction(self.review_action)
        self.clean_badge = QLabel("CLEAN RGB")
        self.clean_badge.setObjectName("cleanBadge")
        self.clean_badge.hide()
        toolbar.addWidget(self.clean_badge)
        toolbar.addSeparator()
        self.zoom_combo = QComboBox()
        self.zoom_combo.addItems(["Fit", "100%", "200%", "400%", "800%"])
        self.zoom_combo.setToolTip("Canvas zoom; display scaling only")
        self.zoom_combo.activated.connect(self.zoom_preset)
        toolbar.addWidget(self.zoom_combo)
        toolbar.addSeparator()
        self.save_action = self._action("Save", self.save, "Ctrl+S", "Safe atomic save")
        self.previous_action = self._action("Last Image", lambda: self.navigate(-1), None, "Save changes and open previous image")
        self.next_action = self._action("Next Image", lambda: self.navigate(1), None, "Save changes and open next image")
        toolbar.addAction(self.save_action)
        toolbar.addAction(self.previous_action)
        toolbar.addAction(self.next_action)
        self.nav_label = QLabel("")
        self.nav_label.setObjectName("navLabel")
        toolbar.addWidget(self.nav_label)

        self.sidebar_toggle_action = self._action("Toggle Dataset Sidebar", self.toggle_sidebar, "Tab")
        self.inspector_toggle_action = self._action("Toggle Inspector", self.toggle_inspector, "Shift+Tab")
        self.addAction(self.sidebar_toggle_action)
        self.addAction(self.inspector_toggle_action)
        self.help_action = self._action("Keyboard Shortcuts", self.help, "?")
        self.addAction(self.help_action)
        self.fit_action = self._action("Fit Image", self.fit_image, "F")
        self.addAction(self.fit_action)
        for value in (1, 2, 4, 8):
            self.addAction(self._action(f"Zoom {value}00%", lambda _checked=False, scale=value: self.set_zoom(scale), str(value)))
        self.save_next_action = self._action("Save & Next", self.save_and_next, "Ctrl+Return")
        self.addAction(self.save_next_action)
        self.search_action = self._action("Search", self.focus_search, "Ctrl+F")
        self.addAction(self.search_action)

    def _build_menus(self) -> None:
        dataset_menu = self.menuBar().addMenu("Dataset")
        dataset_menu.addAction(self.open_action)
        self.refresh_action = self._action("Refresh Folder", self.refresh_folder, "Ctrl+R")
        self.settings_action = self._action("Dataset Settings", self.dataset_settings)
        self.info_action = self._action("Dataset Info", self.dataset_info)
        dataset_menu.addAction(self.refresh_action)
        dataset_menu.addAction(self.settings_action)
        dataset_menu.addAction(self.info_action)
        dataset_menu.addSeparator()
        dataset_menu.addAction(self._action("Export for Training…", lambda: self.export_dataset(False)))
        dataset_menu.addAction(self._action("Export Trusted Evaluation…", lambda: self.export_dataset(True)))
        edit_menu = self.menuBar().addMenu("Edit")
        edit_menu.addAction(self.undo_action)
        edit_menu.addAction(self.redo_action)
        edit_menu.addAction(self._action("Delete Selection", self.delete, "Delete"))
        view_menu = self.menuBar().addMenu("View")
        view_menu.addAction(self.clean_action)
        view_menu.addAction(self.review_action)
        view_menu.addAction(self.sidebar_toggle_action)
        view_menu.addAction(self.inspector_toggle_action)
        help_menu = self.menuBar().addMenu("Help")
        help_menu.addAction(self.help_action)

    def _build_status_bar(self) -> None:
        status = QStatusBar(self)
        self.setStatusBar(status)
        self.status_message = QLabel("Ready")
        self.native_label = QLabel("Native image: —")
        self.zoom_label = QLabel("Zoom: —")
        self.cursor_label = QLabel("Cursor: —")
        self.save_label = QLabel("")
        status.addWidget(self.status_message, 1)
        for label in (self.native_label, self.zoom_label, self.cursor_label, self.save_label):
            label.setObjectName("statusValue")
            status.addPermanentWidget(label)

    @staticmethod
    def _stylesheet() -> str:
        return """
        QMainWindow, QWidget { background: #f4f2ed; color: #292927; font-size: 13px; }
        QMenuBar, QMenu, QToolBar, QStatusBar { background: #eceae5; border-color: #d7d4cd; }
        QToolBar { spacing: 2px; padding: 4px 6px; border-bottom: 1px solid #d7d4cd; }
        QToolButton { padding: 5px 8px; border: 1px solid transparent; border-radius: 4px; }
        QToolButton:hover { background: #dedbd4; }
        QToolButton:checked { background: #d2d8d2; border-color: #aeb8af; }
        QDockWidget::title { background: #e8e6e0; padding: 6px; border-bottom: 1px solid #d7d4cd; }
        QLineEdit, QComboBox, QListWidget { background: #faf9f6; border: 1px solid #cfccc5; border-radius: 4px; padding: 4px; }
        QListWidget::item { padding: 5px 3px; border-bottom: 1px solid #e4e1da; }
        QListWidget::item:selected { background: #dbe1db; color: #222; }
        QPushButton { background: #e8e6e0; border: 1px solid #c9c6bf; border-radius: 5px; padding: 6px 10px; text-align: left; }
        QPushButton:hover { background: #dedbd4; }
        #primaryButton { background: #4f6857; color: white; border: none; text-align: center; font-weight: 600; }
        #recentButton { background: transparent; border: none; padding: 7px 2px; }
        #warningButton { color: #765a2e; background: transparent; border: none; padding: 3px 0; }
        #welcomeTitle { font-size: 24px; font-weight: 600; }
        #panelTitle { font-size: 15px; font-weight: 600; }
        #muted { color: #6f6d68; }
        #hintBox { color: #4d4b47; background: #ebe8e1; border: 1px solid #d7d3ca; border-radius: 5px; padding: 9px; }
        #canvasLabel { background: #343431; color: #e4e2dc; padding: 4px 8px; }
        #cleanBadge { color: #385845; background: #d7e1d8; border: 1px solid #b7c6b9; border-radius: 3px; padding: 3px 6px; font-size: 11px; }
        #navLabel, #statusValue { color: #65635f; padding: 0 6px; }
        QTabBar::tab { padding: 6px 8px; }
        """

    # ---------- dataset opening ----------
    def show_welcome(self) -> None:
        self.central_stack.setCurrentIndex(0)
        self.sidebar_dock.hide()
        self.inspector_dock.hide()
        self.set_editor_actions_enabled(False)
        self.welcome.refresh_recents(self.state_store.recent_folders())

    def show_editor(self, *, fit=True) -> None:
        self.central_stack.setCurrentIndex(1)
        self.sidebar_dock.show()
        self.inspector_dock.show()
        self.set_editor_actions_enabled(True)
        self.render()
        self.update_ui_state()
        if fit:
            QTimer.singleShot(0, self.fit_image)

    def set_editor_actions_enabled(self, enabled: bool) -> None:
        for action in (
            self.select_action,
            self.draw_action,
            self.edit_action,
            self.evidence_action,
            self.undo_action,
            self.redo_action,
            self.clean_action,
            self.draft_action,
            self.evidence_layer_action,
            self.review_action,
            self.save_action,
            self.next_action,
            self.previous_action,
        ):
            action.setEnabled(enabled)

    def choose_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Open image folder")
        if folder:
            self.open_folder(folder)

    def remove_recent(self, folder: str | Path) -> None:
        self.state_store.remove_recent(folder)
        self.welcome.refresh_recents(self.state_store.recent_folders())

    def open_folder(
        self,
        folder: str | Path,
        *,
        recursive: bool = True,
        image_root: str | Path | None = None,
        annotation_root: str | Path | None = None,
        output_root: str | Path | None = None,
        read_only: bool | None = None,
    ) -> None:
        if self.dirty and not self.save():
            return
        previous = self.state_store.session(folder)
        sealed = bool(previous.get("read_only", False)) if read_only is None else read_only
        dataset = scan_dataset(
            folder,
            recursive=recursive,
            image_root=image_root,
            annotation_root=annotation_root,
            output_root=output_root,
            read_only=sealed,
        )
        ambiguous = {"ambiguous_image_folder", "ambiguous_annotation_folder"}
        if (
            any(issue.code in ambiguous for issue in dataset.issues)
            and self.isVisible()
            and os.environ.get("QT_QPA_PLATFORM") != "offscreen"
        ):
            dialog = DatasetSettingsDialog(dataset, self)
            dialog.setWindowTitle("Confirm Folder Mapping")
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            dataset = scan_dataset(
                folder,
                recursive=dialog.recursive.isChecked(),
                image_root=dialog.images.text(),
                annotation_root=dialog.annotations.text() or None,
                output_root=dialog.output.text(),
                read_only=dialog.read_only.isChecked(),
            )
        if any(issue.code == "output_unwritable" for issue in dataset.issues):
            dataset.read_only = True
        self.dataset = dataset
        self.queue = []
        self.dataset_name.setText(dataset.root.name)
        self.state_store.add_recent(dataset.root)
        self.populate_sidebar()
        self.update_dataset_summary()
        if not dataset.records:
            self.show_welcome()
            QMessageBox.warning(self, "Open Folder", "No supported, readable images were found.\n\nPNG, JPEG, TIFF and WebP are supported.")
            return
        target_id = previous.get("last_image_id")
        target = dataset.record_by_id(target_id) if target_id else None
        if target is None:
            target = next((record for record in dataset.records if record.review_status != "reviewed"), dataset.records[0])
        self.load_record(target)
        self.show_editor(fit=not bool(previous))
        self.restore_session_view(previous)
        self.maybe_restore_recovery()
        self.status_message.setText(f"{len(dataset.records)} images loaded")
        self.maybe_show_onboarding()

    def load_record(self, record: ImageRecord) -> None:
        self.current_record = record
        self.rpath = record.source_path
        region_name = record.region or (self.dataset.root.name if self.dataset else "")
        self.region = {"region_id": region_name, "tiles": []}
        self.source_images = [(record.source_path, 0.0, 0.0)]
        self.pixmap_cache = {}
        self.canvas_rect = QRectF(0, 0, record.width, record.height)
        source = record.annotation_path
        if source is None and record.output_annotation_path and record.output_annotation_path.exists():
            source = record.output_annotation_path
        if source and source.exists():
            try:
                raw = json.loads(source.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                QMessageBox.warning(self, "Annotation", f"Could not read annotation; opening a clean session.\n{exc}")
                raw = empty_document(record.image_id, self.record_source_name(record), record.width, record.height, region=record.region)
            self.annotation_source = source
        else:
            raw = empty_document(record.image_id, self.record_source_name(record), record.width, record.height, region=record.region)
            self.annotation_source = None
        document, was_legacy = upgrade_document(
            raw,
            image_id=record.image_id,
            source_path=self.record_source_name(record),
            width=record.width,
            height=record.height,
        )
        self.source_was_legacy = was_legacy
        self.out = record.output_annotation_path
        self._install_document(document)
        self.setWindowTitle(f"{APP_TITLE} — {record.image_id}")
        self.select_sidebar_record(record.image_id)

    def record_source_name(self, record: ImageRecord) -> str:
        if self.dataset:
            try:
                return record.source_path.relative_to(self.dataset.root).as_posix()
            except ValueError:
                pass
        return record.relative_path.as_posix()

    def load_region(self, region_file, annotation_file=None) -> None:
        self.rpath = Path(region_file)
        self.region = json.loads(self.rpath.read_text(encoding="utf-8"))
        original_output = Path(annotation_file) if annotation_file else self.rpath.parent.parent / "annotations" / f"{self.region['region_id']}.json"
        upgraded_output = original_output.parent / "annotations_v2" / original_output.name
        source = upgraded_output if upgraded_output.exists() else original_output if original_output.exists() else None
        if source:
            raw = json.loads(source.read_text(encoding="utf-8"))
        else:
            raw = {
                "schema_version": "1.1",
                "region": {"region_id": self.region["region_id"], "source_region_file": portable_name(self.rpath)},
                "nodes": [],
                "edges": [],
                "ignore_regions": [],
            }
        self.source_images = []
        self.pixmap_cache = {}
        bounds = QRectF()
        first = True
        for tile in self.region.get("tiles", []):
            path = resolve_data_path(tile.get("output_file", ""), self.rpath, Path(__file__).resolve().parents[2])
            x = float(tile.get("global_x", tile.get("col", 0) * self.region.get("tile_width", 1024) * (1 - self.region.get("overlap", 0))))
            y = float(tile.get("global_y", tile.get("row", 0) * self.region.get("tile_height", 1024) * (1 - self.region.get("overlap", 0))))
            if path.exists():
                self.source_images.append((path, x, y))
                pixmap = QPixmap(str(path))
                rect = QRectF(x, y, pixmap.width(), pixmap.height())
                bounds = rect if first else bounds.united(rect)
                first = False
        self.canvas_rect = bounds if not first else QRectF(0, 0, self.region.get("tile_width", 1024), self.region.get("tile_height", 1024))
        document, was_legacy = upgrade_document(
            raw,
            image_id=self.region["region_id"],
            source_path=portable_name(self.rpath),
            width=round(self.canvas_rect.width()),
            height=round(self.canvas_rect.height()),
        )
        self.source_was_legacy = was_legacy
        self.annotation_source = source
        self.out = upgraded_output if was_legacy else source or original_output
        self.current_record = None
        self.dataset = None
        self._install_document(document)
        self.dataset_name.setText("Assigned regions")
        self.populate_region_sidebar()
        self.setWindowTitle(f"{APP_TITLE} — {self.region['region_id']}")
        self.update_navigation()

    def _install_document(self, document: dict) -> None:
        self.m = AnnotationModel(document)
        self.sel = None
        self.temp = []
        self.preview_point = None
        self.drag = None
        self.evidence_anchor = None
        self.evidence_selection = None
        self.hover_edge_id = None
        self.merge_pending_edge = None
        self.dirty = False
        self.mode = "SELECT"
        self.select_action.setChecked(True)
        self.clean_rgb = False
        self.clean_action.setChecked(False)
        self.clean_badge.hide()
        self.warning_list.clear()

    def refresh_folder(self) -> None:
        if not self.dataset:
            return
        current_id = self.current_record.image_id if self.current_record else ""
        if self.dirty and not self.save():
            return
        old_records = {record.image_id: record for record in self.dataset.records}
        refreshed = scan_dataset(
            self.dataset.root,
            recursive=self.dataset.recursive,
            image_root=self.dataset.image_root,
            annotation_root=self.dataset.annotation_root,
            output_root=self.dataset.output_root,
            read_only=self.dataset.read_only,
        )
        refreshed_ids = {record.image_id for record in refreshed.records}
        for image_id, old in old_records.items():
            if image_id not in refreshed_ids:
                missing = copy.deepcopy(old)
                missing.missing = True
                refreshed.records.append(missing)
        refreshed.records.sort(key=lambda record: record.image_id)
        self.dataset = refreshed
        self.populate_sidebar()
        self.update_dataset_summary()
        target = refreshed.record_by_id(current_id)
        if target and not target.missing:
            self.load_record(target)
            self.render()
        self.status_message.setText("Folder refreshed")

    # ---------- sidebar ----------
    def populate_sidebar(self, *_args) -> None:
        if not self.dataset:
            return
        current_id = self.current_record.image_id if self.current_record else ""
        self._building_sidebar = True
        self.image_list.clear()
        search = self.search.text().strip().lower()
        filter_name = self.filter_combo.currentText()
        for record in self.dataset.records:
            if search and search not in record.image_id.lower():
                continue
            if not self.record_matches_filter(record, filter_name):
                continue
            status = "Reviewed" if record.review_status == "reviewed" else "Unreviewed"
            if record.missing:
                status = "Missing"
            text = f"{record.image_id}\n● {status}   {record.path_count} paths\nEvidence {record.evidence_percent:.0f}%"
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, record.image_id)
            item.setToolTip(str(record.source_path))
            if record.source_path.exists():
                pixmap = QPixmap(str(record.source_path)).scaled(
                    72,
                    54,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                item.setIcon(QIcon(pixmap))
            self.image_list.addItem(item)
            if record.image_id == current_id:
                self.image_list.setCurrentItem(item)
        self._building_sidebar = False

    def populate_region_sidebar(self) -> None:
        self._building_sidebar = True
        self.image_list.clear()
        for index, (region_file, _annotation) in enumerate(self.queue):
            try:
                region = json.loads(Path(region_file).read_text(encoding="utf-8"))
                count = len(region.get("tiles", []))
                region_id = region.get("region_id", Path(region_file).parent.name)
            except (OSError, json.JSONDecodeError):
                count, region_id = 0, Path(region_file).parent.name
            item = QListWidgetItem(f"{region_id}\n{count} RGB tiles")
            item.setData(Qt.ItemDataRole.UserRole, index)
            self.image_list.addItem(item)
            if index == self.queue_index:
                self.image_list.setCurrentItem(item)
        self._building_sidebar = False
        self.dataset_summary.setText(f"{len(self.queue)} regions")
        self.dataset_warnings.hide()

    @staticmethod
    def record_matches_filter(record: ImageRecord, filter_name: str) -> bool:
        if filter_name == "Unreviewed":
            return record.review_status != "reviewed"
        if filter_name == "Reviewed":
            return record.review_status == "reviewed"
        mapping = {
            "Has Ambiguity": "uncertain",
            "Has Context-only": "context_only",
            "Has Misalignment": "draft_misalignment",
            "Has Task mismatch": "task_mismatch",
        }
        return mapping.get(filter_name) in record.evidence_flags if filter_name in mapping else True

    def sidebar_selection_changed(self, current, _previous) -> None:
        if self._building_sidebar or current is None:
            return
        value = current.data(Qt.ItemDataRole.UserRole)
        if self.dataset:
            record = self.dataset.record_by_id(value)
            if record and not record.missing and record is not self.current_record:
                if self.dirty and not self.save():
                    self.select_sidebar_record(self.current_record.image_id)
                    return
                self.load_record(record)
                self.render()
                self.fit_image()
                self.update_ui_state()
        elif isinstance(value, int) and value != self.queue_index:
            self.navigate(value - self.queue_index)

    def select_sidebar_record(self, image_id: str) -> None:
        self._building_sidebar = True
        for index in range(self.image_list.count()):
            item = self.image_list.item(index)
            if item.data(Qt.ItemDataRole.UserRole) == image_id:
                self.image_list.setCurrentItem(item)
                break
        self._building_sidebar = False

    def update_dataset_summary(self) -> None:
        if not self.dataset:
            return
        total = len(self.dataset.records)
        self.dataset_summary.setText(
            f"{total} images · {self.dataset.annotated_count} annotated · {total - self.dataset.reviewed_count} unreviewed"
        )
        count = len(self.dataset.issues)
        self.dataset_warnings.setText(f"⚠ {count} file{'s' if count != 1 else ''} need attention" if count else "")
        self.dataset_warnings.setVisible(bool(count))

    def show_dataset_issues(self) -> None:
        if not self.dataset or not self.dataset.issues:
            return
        details = "\n".join(f"• {issue.message}\n  {issue.path}" for issue in self.dataset.issues[:80])
        QMessageBox.information(self, "Folder scan details", details)

    # ---------- modes and interaction ----------
    def set_mode(self, mode: str) -> None:
        if self.is_read_only() and mode != "SELECT":
            self.status_message.setText("READ ONLY — editing tools are disabled")
            self.select_action.setChecked(True)
            return
        if self.mode == "DRAW_PATH" and self.temp and mode != "DRAW_PATH":
            self.temp = []
            self.preview_point = None
        self.mode = mode
        if mode == "EVIDENCE" and self.clean_rgb:
            self.clean_rgb = False
            self.clean_action.setChecked(False)
            self.clean_badge.hide()
        self.evidence_anchor = None
        if mode != "EVIDENCE":
            self.evidence_selection = None
            self.hover_edge_id = None
        action = {
            "SELECT": self.select_action,
            "EDIT": self.edit_action,
            "DRAW_PATH": self.draw_action,
            "EVIDENCE": self.evidence_action,
        }.get(mode)
        if action:
            action.setChecked(True)
        self.status_message.setText(f"Mode: {mode.replace('_', ' ').title()}")
        self.render()
        self.update_inspector()

    @staticmethod
    def _point(q: QPointF) -> tuple[float, float]:
        return q.x(), q.y()

    def click(self, q: QPointF, event) -> None:
        if not self.m:
            return
        x, y = self._point(q)
        if self.mode == "DRAW_PATH":
            self.temp.append([x, y])
            self.preview_point = [x, y]
            self.render()
            return
        if self.merge_pending_edge:
            hit = self.nearest_segment(x, y)
            if hit and hit[0] != self.merge_pending_edge and hit[3] <= self.hit_tolerance():
                try:
                    merged = self.m.merge_segments(self.merge_pending_edge, hit[0])
                    self.sel = ("edge", merged)
                    self.merge_pending_edge = None
                    self.changed()
                except ValueError as exc:
                    QMessageBox.warning(self, "Merge Path", str(exc))
            return
        hit = self.nearest_segment(x, y)
        if self.sel and self.sel[0] in ("edge", "point") and event.modifiers() & Qt.KeyboardModifier.AltModifier:
            if hit and hit[0] == self.sel[1] and hit[3] <= self.hit_tolerance():
                self.m.insert_point(hit[0], hit[1] + 1, hit[2])
                self.sel = ("point", hit[0], hit[1] + 1)
                self.changed()
                return
        point_hit = self.nearest_control_point(x, y)
        if point_hit:
            self.sel = ("point", *point_hit)
            self.drag = None if self.is_read_only() else self.sel
            self.drag_before = None if self.is_read_only() else self.m.snapshot()
        elif hit and hit[3] <= self.hit_tolerance():
            self.sel = ("edge", hit[0])
            self.drag = None
        else:
            self.sel = None
            self.drag = None
        self.render()
        self.update_inspector()

    def move(self, q: QPointF, _event) -> None:
        if not self.m:
            return
        x, y = self._point(q)
        self.preview_point = [x, y]
        if self.drag and self.drag[0] == "point":
            self.m.move_point_live(self.drag[1], self.drag[2], [x, y])
            self.dirty = True
            self.render()
            self.update_inspector()
        elif self.mode == "DRAW_PATH" and self.temp:
            self.render()

    def release(self) -> None:
        if self.drag and self.drag_before is not None and self.m:
            self.m._commit(self.drag_before)
            self.drag_before = None
            self.changed(model_already_changed=True)

    def double_click(self, q: QPointF, _event=None) -> None:
        if self.mode == "DRAW_PATH":
            self.finish(q)
            return
        x, y = self._point(q)
        hit = self.nearest_segment(x, y)
        if hit and hit[3] <= self.hit_tolerance() and self.m and not self.is_read_only():
            self.m.insert_point(hit[0], hit[1] + 1, hit[2])
            self.sel = ("point", hit[0], hit[1] + 1)
            self.changed()
        elif self.sel and self.sel[0] in ("edge", "point"):
            self.fit_selection()
        else:
            self.fit_image()

    def finish(self, _q=None) -> None:
        if self.mode == "DRAW_PATH" and len(self.temp) >= 2 and self.m and not self.is_read_only():
            edge_id = self.m.add_segment(self.temp, "pedestrian_path", "manual")
            self.sel = ("edge", edge_id)
            self.temp = []
            self.preview_point = None
            self.changed(model_already_changed=True)
            self.set_mode("SELECT")

    def finish_current(self) -> None:
        self.finish()

    def nearest_segment(self, x: float, y: float):
        if not self.m:
            return None
        hits = []
        for segment in self.m.data.get("segments", []):
            hit = project_onto_polyline((x, y), segment.get("points", []))
            if hit:
                hits.append((hit["distance"], segment["edge_id"], hit["segment_index"], hit["point"], hit["s"]))
        if not hits:
            return None
        distance, edge_id, index, projected, s = min(hits, key=lambda item: item[0])
        return edge_id, index, projected, distance, s

    def nearest_edge(self, x, y):
        """Compatibility name used by older tests and extensions."""
        return self.nearest_segment(x, y)

    def nearest_control_point(self, x: float, y: float):
        if not self.m:
            return None
        hits = []
        for segment in self.m.data.get("segments", []):
            for index, point in enumerate(segment.get("points", [])):
                hits.append((math.hypot(point[0] - x, point[1] - y), segment["edge_id"], index))
        if not hits:
            return None
        distance, edge_id, index = min(hits, key=lambda item: item[0])
        return (edge_id, index) if distance <= self.point_tolerance() else None

    def hit_tolerance(self) -> float:
        return 14.0 / max(self.active_view().transform().m11(), 1e-6)

    def point_tolerance(self) -> float:
        return 9.0 / max(self.active_view().transform().m11(), 1e-6)

    # ---------- evidence brush ----------
    def evidence_press(self, q: QPointF) -> None:
        hit = self.nearest_segment(q.x(), q.y())
        if hit and hit[3] <= self.hit_tolerance():
            self.evidence_anchor = (hit[0], hit[4])
            self.evidence_selection = (hit[0], hit[4], hit[4])
            self.sel = ("edge", hit[0])
            self.render()

    def evidence_move(self, q: QPointF) -> None:
        if not self.evidence_anchor:
            hit = self.nearest_segment(q.x(), q.y())
            hover = hit[0] if hit and hit[3] <= self.hit_tolerance() else None
            if hover != self.hover_edge_id:
                self.hover_edge_id = hover
                self.render()
            return
        hit = self.nearest_segment(q.x(), q.y())
        if hit and hit[0] == self.evidence_anchor[0]:
            self.evidence_selection = (hit[0], self.evidence_anchor[1], hit[4])
            self.render()

    def evidence_release(self, q: QPointF) -> None:
        self.evidence_move(q)
        self.evidence_anchor = None
        if self.evidence_selection:
            edge_id, start, end = self.evidence_selection
            if abs(end - start) < 1.0 and self.m:
                total = polyline_length(self.m.segment(edge_id)["points"])
                start, end = max(0.0, start - 12.0), min(total, end + 12.0)
                self.evidence_selection = (edge_id, start, end)
            self.status_message.setText("Span selected — press A / B / C / D / E / U")
            self.update_inspector()
            self.render()

    def assign_selected_evidence(self, key: str) -> None:
        if self.is_read_only():
            self.status_message.setText("READ ONLY — evidence was not changed")
            return
        if not self.m or not self.evidence_selection or key not in EVIDENCE_BY_KEY:
            self.status_message.setText("Drag along a path to select a span first")
            return
        edge_id, start, end = self.evidence_selection
        try:
            self.m.assign_evidence(edge_id, start, end, EVIDENCE_BY_KEY[key])
        except ValueError as exc:
            self.status_message.setText(str(exc))
            return
        self.sel = ("span", edge_id, min(start, end), max(start, end))
        self.evidence_selection = None
        self.changed(model_already_changed=True)
        self.status_message.setText(f"{key} — {EVIDENCE_LABELS[EVIDENCE_BY_KEY[key]]}")
        if self.auto_advance.isChecked():
            self.next_unreviewed_span(1)

    def next_unreviewed_span(self, direction: int = 1) -> bool:
        if not self.m:
            return False
        gaps = []
        for segment in self.m.data.get("segments", []):
            total = polyline_length(segment["points"])
            spans = sorted(segment.get("evidence_spans", []), key=lambda span: span["start_s"])
            cursor = 0.0
            for span in spans:
                if span["start_s"] > cursor + 0.5:
                    gaps.append((segment["edge_id"], cursor, span["start_s"]))
                cursor = max(cursor, span["end_s"])
            if cursor < total - 0.5:
                gaps.append((segment["edge_id"], cursor, total))
        if not gaps:
            self.status_message.setText("All path lengths have evidence labels")
            return False
        current = None
        if self.sel and self.sel[0] == "span":
            current = (self.sel[1], self.sel[2], self.sel[3])
        index = gaps.index(current) if current in gaps else (-1 if direction > 0 else 0)
        chosen = gaps[(index + direction) % len(gaps)]
        self.evidence_selection = chosen
        self.sel = ("span", *chosen)
        self.fit_span(*chosen)
        self.render()
        self.update_inspector()
        return True

    # ---------- editing ----------
    def delete(self) -> None:
        if not self.m or not self.sel or self.is_read_only():
            return
        if self.sel[0] == "edge":
            self.m.delete_segment(self.sel[1])
        elif self.sel[0] == "point":
            if not self.m.delete_point(self.sel[1], self.sel[2]):
                self.status_message.setText("Endpoint deletion would break the path; delete the path instead")
                return
        elif self.sel[0] == "span":
            self.status_message.setText("Repaint this span with another evidence class")
            return
        self.sel = None
        self.changed(model_already_changed=True)

    def nudge_selected_point(self, dx: float, dy: float) -> bool:
        if not self.m or not self.sel or self.sel[0] != "point" or self.is_read_only():
            return False
        segment = self.m.segment(self.sel[1])
        point = segment["points"][self.sel[2]]
        self.m.move_point(self.sel[1], self.sel[2], [point[0] + dx, point[1] + dy])
        self.changed(model_already_changed=True)
        return True

    def undo(self) -> None:
        if self.m and not self.is_read_only() and self.m.undo_once():
            self.dirty = True
            self.schedule_persistence()
            self.render()
            self.update_ui_state()

    def redo(self) -> None:
        if self.m and not self.is_read_only() and self.m.redo_once():
            self.dirty = True
            self.schedule_persistence()
            self.render()
            self.update_ui_state()

    def changed(self, *, model_already_changed=False) -> None:
        del model_already_changed
        self.dirty = True
        self.save_label.setText("Unsaved")
        self.schedule_persistence()
        self.render()
        self.update_ui_state()

    def schedule_persistence(self) -> None:
        if not self.m:
            return
        self.autosave_timer.start()
        self.state_store.save_recovery(
            {
                "dataset_root": str(self.dataset.root) if self.dataset else "",
                "image_id": self.m.data.get("image_id", ""),
                "output_path": str(self.out or ""),
                "saved_at": datetime.now(timezone.utc).isoformat(),
                "document": self.m.snapshot(),
            }
        )

    # ---------- rendering ----------
    def render(self) -> None:
        for view in (self.view, self.review_clean, self.review_overlay):
            self.render_view(view, force_clean=view.clean)

    def render_view(self, view: View, *, force_clean=False) -> None:
        scene = view.scene()
        scene.clear()
        self.review_cursor_items[view] = []
        scene.setSceneRect(self.canvas_rect.adjusted(-12, -12, 12, 12))
        if self.layer_state["rgb"]:
            for path, x, y in self.source_images:
                pixmap = self.pixmap_cache.get(path)
                if pixmap is None:
                    pixmap = QPixmap(str(path))
                    self.pixmap_cache[path] = pixmap
                item = scene.addPixmap(pixmap)
                item.setPos(x, y)
                item.setTransformationMode(
                    Qt.TransformationMode.SmoothTransformation
                    if self.smooth_interpolation
                    else Qt.TransformationMode.FastTransformation
                )
                item.setZValue(0)
        if force_clean or self.clean_rgb or not self.m:
            self.draw_review_cursor(view)
            return
        evidence_visible = self.layer_state["evidence"] and (self.mode == "EVIDENCE" or self.review_view_enabled)
        for segment in self.m.data.get("segments", []):
            source = segment.get("source", "manual")
            visible = self.layer_state["draft"] if source == "draft" else self.layer_state["manual"]
            if not visible:
                continue
            active = bool(
                (self.sel and self.sel[0] in ("edge", "point", "span") and self.sel[1] == segment["edge_id"])
                or (self.mode == "EVIDENCE" and self.hover_edge_id == segment["edge_id"])
            )
            if active:
                scene.addPath(_path(segment["points"]), _pen("#f2eee4", 7.0, opacity=0.72)).setZValue(9)
            base_color = "#a89f88" if source == "draft" else PATH_COLORS.get(segment.get("path_type"), "#b85c52")
            opacity = self.draft_opacity if source == "draft" else 0.86
            scene.addPath(
                _path(segment["points"]),
                _pen(base_color, 2.5 if not active else 3.5, opacity=opacity, dashed=source == "draft"),
            ).setZValue(10)
            if evidence_visible:
                for span in segment.get("evidence_spans", []):
                    points = polyline_slice(segment["points"], span["start_s"], span["end_s"])
                    color = EVIDENCE_COLORS.get(span.get("evidence"), "#607d8b")
                    scene.addPath(_path(points), _pen(color, 5.0, opacity=self.evidence_opacity)).setZValue(12)
            if active and self.layer_state["control_points"]:
                for index, point in enumerate(segment["points"]):
                    selected = self.sel == ("point", segment["edge_id"], index)
                    ellipse = scene.addEllipse(
                        -4,
                        -4,
                        8,
                        8,
                        _pen("#f7f5ef", 1.5),
                        QColor("#345f6f") if not selected else QColor("#b04e4b"),
                    )
                    ellipse.setPos(point[0], point[1])
                    ellipse.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, True)
                    ellipse.setZValue(20)
        selection = self.evidence_selection or (
            (self.sel[1], self.sel[2], self.sel[3]) if self.sel and self.sel[0] == "span" else None
        )
        if selection:
            edge_id, start, end = selection
            try:
                segment = self.m.segment(edge_id)
                points = polyline_slice(segment["points"], start, end)
                scene.addPath(_path(points), _pen("#fbfaf6", 9.0, opacity=0.6)).setZValue(30)
                scene.addPath(_path(points), _pen("#394b52", 5.0, opacity=0.95)).setZValue(31)
            except StopIteration:
                pass
        if self.temp:
            points = [*self.temp]
            if self.preview_point and self.preview_point != self.temp[-1]:
                points.append(self.preview_point)
            scene.addPath(_path(points), _pen("#4f8061", 3.0)).setZValue(40)
        for area in self.m.data.get("ignore_regions", []):
            polygon = area.get("polygon", [])
            if len(polygon) >= 3:
                item_path = _path(polygon)
                item_path.closeSubpath()
                fill = QColor("#6d6d68")
                fill.setAlphaF(0.16)
                scene.addPath(item_path, _pen("#6d6d68", 1.5, opacity=0.6, dashed=True), QBrush(fill)).setZValue(8)
        self.draw_review_cursor(view)

    def draw_review_cursor(self, view: View) -> None:
        if not self.review_view_enabled or view not in (self.review_clean, self.review_overlay) or self.last_cursor_point is None:
            return
        for item in self.review_cursor_items.get(view, []):
            if item.scene() is view.scene():
                view.scene().removeItem(item)
        scale = max(view.transform().m11(), 1e-6)
        radius = 8.0 / scale
        x, y = self.last_cursor_point.x(), self.last_cursor_point.y()
        pen = _pen("#f4f0e6", 1.0, opacity=0.82)
        items = [
            view.scene().addLine(x - radius, y, x + radius, y, pen),
            view.scene().addLine(x, y - radius, x, y + radius, pen),
        ]
        for item in items:
            item.setZValue(100)
        self.review_cursor_items[view] = items

    # ---------- view state ----------
    def active_view(self) -> View:
        return self.review_overlay if self.review_view_enabled else self.view

    def view_transform_changed(self, source: View) -> None:
        if self._syncing_views:
            return
        self._syncing_views = True
        try:
            if self.review_view_enabled and source in (self.review_clean, self.review_overlay):
                target = self.review_overlay if source is self.review_clean else self.review_clean
                center = source.mapToScene(source.viewport().rect().center())
                target.setTransform(source.transform())
                target.centerOn(center)
            self.zoom_label.setText(f"Zoom: {source.transform().m11() * 100:.0f}%")
            self.session_timer.start()
        finally:
            self._syncing_views = False

    def toggle_review_view(self, checked=False) -> None:
        enable = bool(checked) if isinstance(checked, bool) else not self.review_view_enabled
        old = self.active_view()
        center = old.mapToScene(old.viewport().rect().center())
        transform = old.transform()
        self.review_view_enabled = enable
        self.review_action.setChecked(enable)
        self.canvas_stack.setCurrentIndex(1 if enable else 0)
        for view in ([self.review_clean, self.review_overlay] if enable else [self.view]):
            view.setTransform(transform)
            view.centerOn(center)
        self.render()
        self.view_transform_changed(self.active_view())

    def toggle_clean_rgb(self, checked=False) -> None:
        self.clean_rgb = bool(checked) if isinstance(checked, bool) else not self.clean_rgb
        self.clean_action.setChecked(self.clean_rgb)
        self.clean_badge.setVisible(self.clean_rgb)
        self.status_message.setText("Clean RGB — overlays hidden" if self.clean_rgb else f"Mode: {self.mode.title()}")
        self.render()
        self.update_inspector()

    def toggle_draft_action(self) -> None:
        self.set_layer("draft", self.draft_action.isChecked())

    def toggle_evidence_action(self) -> None:
        self.set_layer("evidence", self.evidence_layer_action.isChecked())

    def set_layer(self, name: str, visible: bool) -> None:
        self.layer_state[name] = visible
        if name in self.layer_checks:
            self.layer_checks[name].blockSignals(True)
            self.layer_checks[name].setChecked(visible)
            self.layer_checks[name].blockSignals(False)
        if name == "draft":
            self.draft_action.setChecked(visible)
        elif name == "evidence":
            self.evidence_layer_action.setChecked(visible)
        self.render()
        self.session_timer.start()

    def set_draft_opacity(self, value: int) -> None:
        self.draft_opacity = value / 100.0
        self.render()

    def set_evidence_opacity(self, value: int) -> None:
        self.evidence_opacity = value / 100.0
        self.render()

    def set_interpolation(self, value: str) -> None:
        self.smooth_interpolation = value == "Smooth"
        self.render()

    def fit_image(self) -> None:
        views = [self.review_clean, self.review_overlay] if self.review_view_enabled else [self.view]
        for view in views:
            view.fitInView(self.canvas_rect, Qt.AspectRatioMode.KeepAspectRatio)
        self.view_transform_changed(self.active_view())

    def set_zoom(self, scale: float) -> None:
        center = self.active_view().mapToScene(self.active_view().viewport().rect().center())
        views = [self.review_clean, self.review_overlay] if self.review_view_enabled else [self.view]
        for view in views:
            view.set_native_scale(scale)
            view.centerOn(center)
        self.view_transform_changed(self.active_view())

    def zoom_preset(self, index: int) -> None:
        if index == 0:
            self.fit_image()
        else:
            self.set_zoom(float(2 ** (index - 1)))

    def fit_selection(self) -> None:
        if not self.m or not self.sel or self.sel[0] not in ("edge", "point", "span"):
            self.fit_image()
            return
        segment = self.m.segment(self.sel[1])
        points = segment["points"]
        if self.sel[0] == "span":
            points = polyline_slice(points, self.sel[2], self.sel[3])
        bounds = _path(points).boundingRect().adjusted(-24, -24, 24, 24)
        self.active_view().fitInView(bounds, Qt.AspectRatioMode.KeepAspectRatio)
        self.view_transform_changed(self.active_view())

    def fit_span(self, edge_id: str, start: float, end: float) -> None:
        if not self.m:
            return
        points = polyline_slice(self.m.segment(edge_id)["points"], start, end)
        bounds = _path(points).boundingRect().adjusted(-40, -40, 40, 40)
        self.active_view().fitInView(bounds, Qt.AspectRatioMode.KeepAspectRatio)
        self.view_transform_changed(self.active_view())

    def cursor_moved(self, q: QPointF) -> None:
        self.last_cursor_point = QPointF(q)
        self.cursor_label.setText(f"Cursor: x={q.x():.1f}, y={q.y():.1f}")
        if self.review_view_enabled:
            self.draw_review_cursor(self.review_clean)
            self.draw_review_cursor(self.review_overlay)

    # ---------- save/session/navigation ----------
    def save(self, *_args, force=True) -> bool:
        if not self.m or self.out is None:
            return False
        if self.dataset and self.dataset.read_only:
            self.save_label.setText("READ ONLY")
            self.status_message.setText("This dataset is sealed; annotations were not written")
            return False
        if not force and not self.dirty:
            return True
        try:
            atomic_write_json(self.m.data, self.out, backup=self.out.exists())
        except AnnotationWriteError as exc:
            self.save_label.setText("Save Failed")
            self.status_message.setText(f"Save failed: {exc}")
            return False
        self.dirty = False
        self.save_label.setText("Saved")
        self.status_message.setText(f"Saved {self.out.name}")
        self.state_store.clear_recovery()
        if self.current_record:
            self.current_record.annotation_path = self.out
            self.current_record.annotation_schema_version = "2"
            self.current_record.review_status = self.m.data.get("annotation_status", "unreviewed")
            stats = self.m.stats()
            self.current_record.path_count = stats["path_count"]
            self.current_record.evidence_percent = stats["percent"]
            self.current_record.evidence_flags = {
                span.get("evidence")
                for segment in self.m.data.get("segments", [])
                for span in segment.get("evidence_spans", [])
            }
            self.populate_sidebar()
            self.update_dataset_summary()
        self.save_session_state()
        return True

    def autosave(self) -> None:
        if self.dirty:
            self.save(force=False)

    def save_and_next(self) -> None:
        if self.save():
            self.navigate(1)

    def navigate(self, step: int) -> None:
        if self.dirty and not self.save():
            return
        if self.dataset:
            visible_ids = [
                self.image_list.item(index).data(Qt.ItemDataRole.UserRole)
                for index in range(self.image_list.count())
            ]
            if not visible_ids or not self.current_record:
                return
            current = visible_ids.index(self.current_record.image_id) if self.current_record.image_id in visible_ids else 0
            target_index = current + step
            if 0 <= target_index < len(visible_ids):
                target = self.dataset.record_by_id(visible_ids[target_index])
                if target and not target.missing:
                    self.load_record(target)
                    self.render()
                    self.fit_image()
                    self.update_ui_state()
            return
        target = self.queue_index + step
        if not 0 <= target < len(self.queue):
            return
        self.queue_index = target
        self.load_region(*self.queue[target])
        for view in (self.view, self.review_clean, self.review_overlay):
            view.resetTransform()
        self.render()
        self.fit_image()
        self.update_ui_state()
        self.status_message.setText(f"Opened region {target + 1}/{len(self.queue)}: {self.region['region_id']}")

    def update_navigation(self) -> None:
        if self.dataset and self.current_record:
            total = len(self.dataset.records)
            index = self.dataset.records.index(self.current_record)
            self.previous_action.setEnabled(index > 0)
            self.next_action.setEnabled(index < total - 1)
            self.nav_label.setText(f"  Image {index + 1}/{total}: {self.current_record.image_id}")
        elif self.queue:
            total = len(self.queue)
            image_total = 0
            for region_file, _ in self.queue:
                try:
                    image_total += len(json.loads(Path(region_file).read_text(encoding="utf-8")).get("tiles", []))
                except (OSError, json.JSONDecodeError):
                    pass
            self.previous_action.setEnabled(self.queue_index > 0)
            self.next_action.setEnabled(self.queue_index < total - 1)
            self.nav_label.setText(
                f"  区域 {self.queue_index + 1}/{total}（共 {image_total} 张图）: {self.region.get('region_id', '')}"
            )

    def save_session_state(self) -> None:
        if not self.dataset or not self.current_record:
            return
        view = self.active_view()
        center = view.mapToScene(view.viewport().rect().center())
        self.state_store.save_session(
            self.dataset.root,
            {
                "last_image_id": self.current_record.image_id,
                "zoom": view.transform().m11(),
                "center": [center.x(), center.y()],
                "mode": self.mode,
                "sidebar_scroll": self.image_list.verticalScrollBar().value(),
                "layers": copy.deepcopy(self.layer_state),
                "read_only": self.dataset.read_only,
            },
        )

    def restore_session_view(self, session: dict) -> None:
        if not session:
            return
        self.layer_state.update(session.get("layers", {}))
        for name, checked in self.layer_state.items():
            if name in self.layer_checks:
                self.layer_checks[name].setChecked(checked)
        valid_modes = {"SELECT", "EDIT", "DRAW_PATH", "EVIDENCE"}
        self.set_mode(session.get("mode", "SELECT") if session.get("mode") in valid_modes else "SELECT")
        zoom = float(session.get("zoom", 0.0))
        center = session.get("center", [])
        if zoom > 0:
            self.view.set_native_scale(zoom)
        if len(center) == 2:
            self.view.centerOn(float(center[0]), float(center[1]))
        self.image_list.verticalScrollBar().setValue(int(session.get("sidebar_scroll", 0)))

    def maybe_restore_recovery(self) -> None:
        recovery = self.state_store.recovery()
        if not recovery or not self.m or os.environ.get("QT_QPA_PLATFORM") == "offscreen":
            return
        if recovery.get("dataset_root") != str(self.dataset.root if self.dataset else ""):
            return
        if recovery.get("image_id") != self.m.data.get("image_id"):
            return
        answer = QMessageBox.question(
            self,
            "Restore previous session?",
            "Unsaved annotation work was found for this image. Restore it?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes and isinstance(recovery.get("document"), dict):
            self.m = AnnotationModel(recovery["document"])
            self.dirty = True
            self.render()
            self.update_ui_state()
        else:
            self.state_store.clear_recovery()

    # ---------- inspector / menus ----------
    def update_ui_state(self) -> None:
        self.update_navigation()
        self.update_inspector()
        if self.m:
            image = self.m.data.get("image", {})
            self.native_label.setText(f"Native image: {image.get('width', 0)}×{image.get('height', 0)}")
        self.zoom_label.setText(f"Zoom: {self.active_view().transform().m11() * 100:.0f}%")
        self.undo_action.setEnabled(bool(self.m and self.m.undo_stack))
        self.redo_action.setEnabled(bool(self.m and self.m.redo_stack))
        if self.dataset and self.dataset.read_only:
            self.save_label.setText("READ ONLY")
            self.save_action.setEnabled(False)
            self.draw_action.setEnabled(False)
            self.edit_action.setEnabled(False)
            self.evidence_action.setEnabled(False)
        else:
            self.save_action.setEnabled(True)
            self.draw_action.setEnabled(True)
            self.edit_action.setEnabled(True)
            self.evidence_action.setEnabled(True)

    def update_inspector(self) -> None:
        while self.form.count():
            item = self.form.takeAt(0)
            widget = item.widget()
            if widget:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()
        if not self.m:
            self.form.addRow(QLabel("No selected path"))
            return
        stats = self.m.stats()
        self.review_progress.setText(f"Evidence reviewed: {stats['percent']:.0f}%")
        context = stats["by_class_px"].get("context_only", 0.0)
        weak = stats["by_class_px"].get("weak_visual", 0.0)
        self.review_details.setText(
            f"Unreviewed path length: {stats['unreviewed_px']:.0f} px\n"
            f"Context-only: {context:.0f} px\nWeak visual: {weak:.0f} px"
        )
        if self.clean_rgb:
            self.form.addRow(QLabel("CLEAN RGB\nAnnotation details are hidden."))
            return
        if not self.sel:
            self.form.addRow(QLabel("No selected path"))
            self.form.addRow("Paths", QLabel(str(stats["path_count"])))
            return
        if self.sel[0] in ("edge", "point", "span"):
            segment = self.m.segment(self.sel[1])
            self.form.addRow("Edge", QLabel(segment["edge_id"]))
            combo = QComboBox()
            combo.setMinimumWidth(145)
            combo.addItems(PATH_TYPES)
            combo.setCurrentText(segment.get("path_type", "pedestrian_path"))
            combo.setEnabled(not self.is_read_only())
            combo.currentTextChanged.connect(lambda value: self.change_segment_attr("path_type", value))
            self.form.addRow("Path type", combo)
            coverage = evidence_coverage(segment)
            self.form.addRow("Review status", QLabel(segment.get("review_status", "unreviewed")))
            self.form.addRow("Evidence coverage", QLabel(f"{coverage['percent']:.0f}%"))
            for evidence, label in EVIDENCE_LABELS.items():
                length = coverage["by_class_px"].get(evidence, 0.0)
                if length > 0:
                    percent = 100.0 * length / coverage["total_px"] if coverage["total_px"] else 0.0
                    self.form.addRow(label, QLabel(f"{percent:.0f}%"))
            if self.sel[0] == "point":
                point = segment["points"][self.sel[2]]
                self.form.addRow("Control point", QLabel(str(self.sel[2])))
                self.form.addRow("Native X/Y", QLabel(f"{point[0]:.1f}, {point[1]:.1f}"))
            if self.sel[0] == "span":
                self.form.addRow("Selected span", QLabel(f"{self.sel[2]:.1f}–{self.sel[3]:.1f} px"))
                midpoint = (self.sel[2] + self.sel[3]) / 2.0
                span = next(
                    (
                        item
                        for item in segment.get("evidence_spans", [])
                        if item["start_s"] - 1e-6 <= midpoint <= item["end_s"] + 1e-6
                    ),
                    None,
                )
                if span:
                    self.form.addRow("Evidence", QLabel(EVIDENCE_LABELS.get(span.get("evidence"), span.get("evidence", ""))))
                    confidence = QComboBox()
                    confidence.addItems(["high", "medium", "low"])
                    confidence.setCurrentText(span.get("review_confidence", "medium"))
                    confidence.currentTextChanged.connect(
                        lambda value, edge=segment["edge_id"], start=self.sel[2], end=self.sel[3]: self.change_span_attr(
                            edge, start, end, "review_confidence", value
                        )
                    )
                    note = QLineEdit(span.get("note", ""))
                    note.setPlaceholderText("Optional review note")
                    note.editingFinished.connect(
                        lambda widget=note, edge=segment["edge_id"], start=self.sel[2], end=self.sel[3]: self.change_span_attr(
                            edge, start, end, "note", widget.text()
                        )
                    )
                    self.form.addRow("Confidence", confidence)
                    self.form.addRow("Note", note)
            details = QGroupBox("Details")
            details.setCheckable(True)
            details.setChecked(False)
            details_layout = QFormLayout(details)
            details_layout.addRow("Source", QLabel(segment.get("source", "manual")))
            details_layout.addRow("Geometry review", QLabel("Required" if segment.get("geometry_review_required") else "No"))
            self.form.addRow(details)

    def change_segment_attr(self, key: str, value) -> None:
        if self.m and self.sel and self.sel[0] in ("edge", "point", "span") and not self.is_read_only():
            self.m.set_attr(self.sel[1], key, value)
            self.changed(model_already_changed=True)

    def change_span_attr(self, edge_id: str, start: float, end: float, key: str, value) -> None:
        if not self.m or self.is_read_only():
            return
        try:
            self.m.set_evidence_span_attr(edge_id, start, end, key, value)
            self.changed(model_already_changed=True)
        except ValueError as exc:
            self.status_message.setText(str(exc))

    def mark_image_reviewed(self) -> None:
        if not self.m or self.is_read_only():
            return
        if self.m.data.get("segments") and self.m.stats()["unreviewed_px"] > 0.5:
            self.status_message.setText("Evidence is incomplete; use X then N to review remaining spans")
            return
        before = self.m.snapshot()
        self.m.data["annotation_status"] = "reviewed"
        self.m._commit(before)
        self.changed(model_already_changed=True)

    def show_context_menu(self, global_pos, scene_pos: QPointF) -> None:
        hit = self.nearest_segment(scene_pos.x(), scene_pos.y())
        if not hit or hit[3] > self.hit_tolerance() or not self.m:
            return
        edge_id = hit[0]
        self.sel = ("edge", edge_id)
        menu = QMenu(self)
        if self.is_read_only():
            menu.addAction("READ ONLY").setEnabled(False)
            menu.exec(global_pos)
            return
        menu.addAction("Edit Geometry", lambda: self.set_mode("EDIT"))
        menu.addAction("Insert Point Here", lambda: self.insert_context_point(edge_id, hit[1] + 1, hit[2]))
        menu.addAction("Split Path Here", lambda: self.split_context_path(edge_id, hit[4]))
        menu.addAction("Merge Path…", lambda: self.begin_merge(edge_id))
        path_menu = menu.addMenu("Set Path Type")
        for path_type in PATH_TYPES:
            path_menu.addAction(path_type, lambda _checked=False, value=path_type: self.set_path_type(edge_id, value))
        menu.addAction("Review Evidence", lambda: self.set_mode("EVIDENCE"))
        if self.m.segment(edge_id).get("excluded_from_task"):
            menu.addAction("Restore to Task", lambda: self.restore_edge(edge_id))
        else:
            menu.addAction("Mark Excluded", lambda: self.exclude_edge(edge_id))
        if self.m.segment(edge_id).get("geometry_review_required"):
            menu.addAction("Geometry Fixed", lambda: self.geometry_fixed(edge_id))
        menu.addSeparator()
        menu.addAction("Delete Path", self.delete)
        menu.exec(global_pos)

    def insert_context_point(self, edge_id, index, point) -> None:
        self.m.insert_point(edge_id, index, point)
        self.sel = ("point", edge_id, index)
        self.changed(model_already_changed=True)

    def split_context_path(self, edge_id, s) -> None:
        try:
            left, _right = self.m.split_segment(edge_id, s)
            self.sel = ("edge", left)
            self.changed(model_already_changed=True)
        except ValueError as exc:
            QMessageBox.warning(self, "Split Path", str(exc))

    def begin_merge(self, edge_id) -> None:
        self.merge_pending_edge = edge_id
        self.status_message.setText("Click a second path with a nearby endpoint to merge")

    def set_path_type(self, edge_id, path_type) -> None:
        self.m.set_attr(edge_id, "path_type", path_type)
        self.changed(model_already_changed=True)

    def exclude_edge(self, edge_id) -> None:
        segment = self.m.segment(edge_id)
        if polyline_length(segment["points"]) > 0:
            self.m.assign_evidence(edge_id, 0, polyline_length(segment["points"]), "task_mismatch")
        self.changed(model_already_changed=True)

    def restore_edge(self, edge_id) -> None:
        self.m.set_attr(edge_id, "excluded_from_task", False)
        self.changed(model_already_changed=True)
        self.status_message.setText("Edge restored; repaint any E span with A/B/C/D/U")

    def geometry_fixed(self, edge_id) -> None:
        self.m.mark_geometry_fixed(edge_id)
        self.changed(model_already_changed=True)
        self.status_message.setText("Geometry marked fixed; reassign this span as A/B/C/U")

    def is_read_only(self) -> bool:
        return bool(self.dataset and self.dataset.read_only)

    def toggle_sidebar(self) -> None:
        self.sidebar_dock.setVisible(not self.sidebar_dock.isVisible())

    def toggle_inspector(self) -> None:
        self.inspector_dock.setVisible(not self.inspector_dock.isVisible())

    def focus_search(self) -> None:
        self.sidebar_dock.show()
        self.search.setFocus()
        self.search.selectAll()

    def dataset_settings(self) -> None:
        if not self.dataset:
            return
        dialog = DatasetSettingsDialog(self.dataset, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.open_folder(
                self.dataset.root,
                recursive=dialog.recursive.isChecked(),
                image_root=dialog.images.text(),
                annotation_root=dialog.annotations.text() or None,
                output_root=dialog.output.text(),
                read_only=dialog.read_only.isChecked(),
            )

    def dataset_info(self) -> None:
        if not self.dataset:
            return
        paths = {}
        evidence = []
        for record in self.dataset.records:
            evidence.append(record.evidence_percent)
        if self.m:
            for segment in self.m.data.get("segments", []):
                kind = segment.get("path_type", "unknown")
                paths[kind] = paths.get(kind, 0) + 1
        text = (
            f"Images: {len(self.dataset.records)}\n"
            f"Annotations: {self.dataset.annotated_count}\n"
            f"Reviewed: {self.dataset.reviewed_count}\n"
            f"Unreviewed: {len(self.dataset.records) - self.dataset.reviewed_count}\n"
            f"Evidence coverage: {sum(evidence) / len(evidence) if evidence else 0:.0f}%\n"
            f"Missing annotations: {len(self.dataset.records) - self.dataset.annotated_count}\n"
            f"Orphan JSON: {sum(issue.code == 'orphan_annotation' for issue in self.dataset.issues)}\n"
            f"Issues: {len(self.dataset.issues)}\n\n"
            + "Path types in current image:\n"
            + "\n".join(f"{key}: {value}" for key, value in sorted(paths.items()))
        )
        QMessageBox.information(self, "Dataset Info", text)

    def export_dataset(self, trusted_only: bool) -> None:
        if not self.dataset:
            return
        if self.dataset.read_only:
            QMessageBox.warning(self, "Read Only", "Batch export is disabled for this sealed dataset.")
            return
        destination = QFileDialog.getExistingDirectory(self, "Choose derived export folder")
        if not destination:
            return
        output = Path(destination)
        count = 0
        for record in self.dataset.records:
            source = record.annotation_path or (
                record.output_annotation_path if record.output_annotation_path and record.output_annotation_path.exists() else None
            )
            if not source or not source.exists():
                continue
            try:
                raw = json.loads(source.read_text(encoding="utf-8"))
                document, _ = upgrade_document(
                    raw,
                    image_id=record.image_id,
                    source_path=self.record_source_name(record),
                    width=record.width,
                    height=record.height,
                )
                path = (output / record.relative_path).with_suffix(".json")
                atomic_write_json(export_derived(document, trusted_only=trusted_only), path, backup=path.exists())
                count += 1
            except (OSError, ValueError, AnnotationWriteError):
                continue
        self.status_message.setText(f"Exported {count} derived annotation files")

    def help(self) -> None:
        QMessageBox.information(
            self,
            "Keyboard Shortcuts",
            "Space + drag   Pan\n"
            "Wheel / pinch  Zoom\n"
            "F              Fit image\n"
            "1 / 2 / 4 / 8  Native zoom\n"
            "`              Clean RGB\n"
            "R              Review view\n"
            "V              Select / edit\n"
            "P              Draw path\n"
            "X              Evidence mode\n"
            "A/B/C/D/E/U    Evidence class\n"
            "N / Shift+N    Next / previous unreviewed span\n"
            "← / →          Last / next image\n"
            "Cmd/Ctrl+Z     Undo\n"
            "Cmd/Ctrl+Shift+Z  Redo\n"
            "Delete         Delete selection\n"
            "Cmd/Ctrl+S     Save\n"
            "Cmd/Ctrl+Enter Save & next\n\n"
            "B: 图里还能指出具体视觉证据。\n"
            "C: 主要靠布局 / 常识推断。",
        )

    def maybe_show_onboarding(self) -> None:
        if self.state_store.onboarding_seen() or os.environ.get("QT_QPA_PLATFORM") == "offscreen":
            return
        QMessageBox.information(
            self,
            "Three steps",
            "1. Press P to draw or V to edit paths.\n"
            "2. Press X for Evidence Review.\n"
            "3. Drag a span, then press A/B/C/D/E/U.",
        )
        self.state_store.set_onboarding_seen()

    # ---------- key, drag/drop, closing ----------
    def keyPressEvent(self, event) -> None:
        key = event.key()
        modifiers = event.modifiers()
        command = bool(modifiers & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.MetaModifier))
        evidence_key = chr(key).upper() if 0 <= key < 256 else ""
        if key == Qt.Key.Key_Escape:
            if self.temp:
                self.temp = []
                self.preview_point = None
            self.set_mode("SELECT")
        elif self.mode == "DRAW_PATH" and key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.finish_current()
        elif self.mode == "DRAW_PATH" and key == Qt.Key.Key_Backspace:
            if self.temp:
                self.temp.pop()
                self.render()
        elif self.mode == "EVIDENCE" and evidence_key in EVIDENCE_BY_KEY:
            self.assign_selected_evidence(evidence_key)
        elif key == Qt.Key.Key_N:
            direction = -1 if modifiers & Qt.KeyboardModifier.ShiftModifier else 1
            if self.mode == "EVIDENCE" or self.review_view_enabled:
                self.next_unreviewed_span(direction)
            else:
                self.navigate(direction)
        elif key in (Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Up, Qt.Key.Key_Down) and self.sel and self.sel[0] == "point":
            amount = 5 if modifiers & Qt.KeyboardModifier.ShiftModifier else 1
            dx = -amount if key == Qt.Key.Key_Left else amount if key == Qt.Key.Key_Right else 0
            dy = -amount if key == Qt.Key.Key_Up else amount if key == Qt.Key.Key_Down else 0
            self.nudge_selected_point(dx, dy)
        elif key in (Qt.Key.Key_Left, Qt.Key.Key_Right):
            self.navigate(-1 if key == Qt.Key.Key_Left else 1)
        elif key in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self.delete()
        elif key == Qt.Key.Key_Z and command:
            self.redo() if modifiers & Qt.KeyboardModifier.ShiftModifier else self.undo()
        else:
            super().keyPressEvent(event)

    def dragEnterEvent(self, event) -> None:
        urls = event.mimeData().urls()
        if any(url.isLocalFile() for url in urls):
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        paths = [Path(url.toLocalFile()) for url in event.mimeData().urls() if url.isLocalFile()]
        folders = [path for path in paths if path.is_dir()]
        images = [path for path in paths if path.is_file()]
        if len(folders) == 1 and not images:
            self.open_folder(folders[0])
            event.acceptProposedAction()
            return
        if images:
            suggested = images[0].parent / "annotations_v2"
            output = QFileDialog.getExistingDirectory(self, "Choose annotation output folder", str(suggested))
            if output:
                self.dataset = dataset_from_files(images, output)
                self.dataset_name.setText("Temporary image set")
                self.populate_sidebar()
                self.update_dataset_summary()
                if self.dataset.records:
                    self.load_record(self.dataset.records[0])
                    self.show_editor()
            event.acceptProposedAction()

    def closeEvent(self, event) -> None:
        if self.dirty and not self.save():
            event.ignore()
            return
        self.save_session_state()
        event.accept()


def launch(region_file=None, annotation_file=None, queue=None, queue_index=0) -> None:
    app = QApplication.instance() or QApplication([])
    app.setApplicationName(APP_TITLE)
    app.setOrganizationName("gaode-tools")
    window = AnnotatorWindow(region_file, annotation_file, queue, queue_index)
    window.resize(1440, 900)
    window.show()
    app.exec()
