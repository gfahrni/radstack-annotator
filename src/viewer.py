"""
RadStack Annotator — PyQt6 graphical window to browse a folder of images
slice by slice, with annotation tools and stamp interpolation.
"""

import os
import math
import subprocess
import tempfile
import shutil

import numpy as np
from PIL import Image as PILImage

from PyQt6.QtCore import Qt, QRectF, QPointF, QSettings, QTimer
from PyQt6.QtGui import (
    QPixmap, QImage, QPainter, QPen, QColor, QBrush, QFont, QIcon,
    QAction, QKeySequence, QPainterPath, QPolygonF,
)
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QGraphicsView, QGraphicsScene,
    QGraphicsPixmapItem, QGraphicsPathItem, QGraphicsRectItem,
    QGraphicsEllipseItem, QGraphicsTextItem, QGraphicsPolygonItem,
    QVBoxLayout, QHBoxLayout, QWidget, QSlider,
    QPushButton, QCheckBox, QButtonGroup, QFileDialog, QInputDialog,
    QMessageBox, QStatusBar, QLabel, QLineEdit, QDialog, QDialogButtonBox,
    QFormLayout, QComboBox, QSpinBox, QColorDialog,
)

from io import BytesIO
from .loader import load_images, validate_image_folder
from .annotations import Arrow, Rect, Oval, TextBox, LinkedGroup, render_annotations, _RENDER_SCALE
from .saver import save_annotated_stack, collect_annotations
from . import project


PALETTE_COLORS = ['#00e5ff', '#ffee58', '#ff9100', '#ff4081',
                  '#76ff03', '#e040fb', '#ffffff', '#ff1744']
PALETTE_COLORS_RGB = [
    (0, 229, 255), (255, 238, 88), (255, 145, 0), (255, 64, 129),
    (118, 255, 3), (224, 64, 251), (255, 255, 255), (255, 23, 68),
]
BORDER_WIDTHS = [1, 3, 6]
TOOL_TIDS = ['arrow', 'rect', 'oval', 'text']
TOOL_LABELS = {
    'arrow': '\u2192  Arrow', 'rect': '\u25ad  Rectangle',
    'oval': '\u25ef  Oval', 'text': '[T]  Text',
}
ACTION_CFG = [
    ('open', 'Open Folder'),
    ('save_images', 'Save Images'),
    ('save_video', 'Save Video'),
    ('reset', '\u21ba  Reset'),
    ('invert', '\u21c4  Invert'),
]
HIT_TOLERANCE = 12


class _GraphicsView(QGraphicsView):
    """Custom view that forwards mouse/wheel/key events to the parent viewer."""

    def __init__(self, viewer=None):
        super().__init__()
        self._viewer = viewer
        self.setAcceptDrops(True)

    def wheelEvent(self, event):
        if self._viewer:
            self._viewer._on_scroll(event)
        event.accept()

    def mousePressEvent(self, event):
        if self._viewer and event.button() == Qt.MouseButton.LeftButton:
            self._viewer._on_press(self.mapToScene(event.position().toPoint()))
        event.accept()

    def mouseMoveEvent(self, event):
        if self._viewer:
            self._viewer._on_motion(self.mapToScene(event.position().toPoint()))
        event.accept()

    def mouseReleaseEvent(self, event):
        if self._viewer and event.button() == Qt.MouseButton.LeftButton:
            self._viewer._on_release(self.mapToScene(event.position().toPoint()))
        event.accept()

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        if self._viewer:
            self._viewer._on_drop(event)
        event.acceptProposedAction()

    def keyPressEvent(self, event):
        if self._viewer:
            self._viewer._on_key_press(event)
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            event.accept()
        else:
            super().keyPressEvent(event)


class PreferencesDialog(QDialog):
    """Preferences dialog — replaces settings.json with QSettings."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Preferences')
        self.s = QSettings('RadStack', 'RadStack Annotator')

        layout = QFormLayout(self)

        self.bg_btn = QPushButton()
        self.bg_btn.setFixedSize(60, 28)
        self.bg_color = self.s.value('display/bg_color', '#2b2b2b')
        self._update_bg_btn()
        self.bg_btn.clicked.connect(self._pick_bg)
        layout.addRow('Background:', self.bg_btn)

        self.fmt_combo = QComboBox()
        self.fmt_combo.addItems(['jpeg', 'png'])
        self.fmt_combo.setCurrentText(self.s.value('save/format', 'jpeg'))
        layout.addRow('Save format:', self.fmt_combo)

        self.quality_spin = QSpinBox()
        self.quality_spin.setRange(1, 100)
        self.quality_spin.setValue(int(self.s.value('save/quality', 100)))
        layout.addRow('JPEG quality:', self.quality_spin)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addRow(btns)

    def _update_bg_btn(self):
        self.bg_btn.setStyleSheet(
            f'background-color: {self.bg_color}; border: 2px solid #666; border-radius: 4px;')

    def _pick_bg(self):
        c = QColorDialog.getColor(QColor(self.bg_color), self, 'Background Color')
        if c.isValid():
            self.bg_color = c.name()
            self._update_bg_btn()

    def accept(self):
        self.s.setValue('display/bg_color', self.bg_color)
        self.s.setValue('save/format', self.fmt_combo.currentText())
        self.s.setValue('save/quality', self.quality_spin.value())
        super().accept()


class TextInputDialog(QDialog):
    """Dialog for entering text + choosing font size."""

    def __init__(self, parent=None, show_bg=True):
        super().__init__(parent)
        self.setWindowTitle('Enter Text')

        layout = QVBoxLayout(self)

        self.text_edit = QLineEdit()
        self.text_edit.setPlaceholderText('Type your text here...')
        layout.addWidget(self.text_edit)

        size_layout = QHBoxLayout()
        size_layout.addWidget(QLabel('Size:'))

        self.size_spin = QSpinBox()
        self.size_spin.setRange(6, 72)
        self.size_spin.setValue(10)
        size_layout.addWidget(self.size_spin)

        self.size_slider = QSlider(Qt.Orientation.Horizontal)
        self.size_slider.setRange(6, 72)
        self.size_slider.setValue(10)
        size_layout.addWidget(self.size_slider)

        layout.addLayout(size_layout)

        self.bg_check = QCheckBox('Background')
        self.bg_check.setChecked(show_bg)
        layout.addWidget(self.bg_check)

        self.size_spin.valueChanged.connect(self.size_slider.setValue)
        self.size_slider.valueChanged.connect(self.size_spin.setValue)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

        self.text_edit.setFocus()


class ImageStackViewer(QMainWindow):

    def __init__(self, data_path=None):
        super().__init__()
        self.settings = QSettings('RadStack', 'RadStack Annotator')
        self._init_state()
        self._init_ui()
        self._connect_signals()
        self._restore_geometry()
        if data_path is not None:
            self.load_folder(data_path)

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    def _init_state(self):
        self.data_path = None
        self._project_path = None
        self._slices = []
        self.num_slices = 0
        self._slice_idx = 0
        self._vmin_max = []
        self._annotations = {}
        self._linked_groups = []
        self._selected_anno = None
        self._selected_interp_group = None
        self._active_tool = None
        self._current_color = PALETTE_COLORS_RGB[0]
        self._current_width = BORDER_WIDTHS[0]
        self._drawing = False
        self._draw_start = None
        self._preview_items = []
        self._stamp_mode = False
        self._stamp_eligible = False
        self._dragging = False
        self._drag_mode = None
        self._drag_start = None
        self._loaded = False
        self._pixmap_item = None
        self._annotation_items = []
        self._handle_items = []
        self._ghost_items = []
        self._last_show_bg = True

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _init_ui(self):
        self.setWindowTitle('RadStack Annotator')
        self.setAcceptDrops(True)
        self.setMinimumSize(900, 700)

        # Menu bar
        menubar = self.menuBar()
        file_menu = menubar.addMenu('&File')
        open_act = QAction('&Open Folder...', self)
        open_act.setShortcut(QKeySequence('Ctrl+O'))
        open_act.triggered.connect(self._open_folder_dialog)
        file_menu.addAction(open_act)
        open_proj_act = QAction('Open &Project...', self)
        open_proj_act.setShortcut(QKeySequence('Ctrl+Shift+O'))
        open_proj_act.triggered.connect(self._open_project)
        file_menu.addAction(open_proj_act)
        file_menu.addSeparator()
        save_proj_act = QAction('&Save Project', self)
        save_proj_act.setShortcut(QKeySequence('Ctrl+P'))
        save_proj_act.triggered.connect(self._save_project)
        file_menu.addAction(save_proj_act)
        save_proj_as_act = QAction('Save Project &As...', self)
        save_proj_as_act.triggered.connect(self._save_project_as)
        file_menu.addAction(save_proj_as_act)
        file_menu.addSeparator()
        save_img_act = QAction('&Save Images', self)
        save_img_act.setShortcut(QKeySequence('Ctrl+S'))
        save_img_act.triggered.connect(lambda: self._on_action('save_images'))
        file_menu.addAction(save_img_act)
        save_vid_act = QAction('Save &Video', self)
        save_vid_act.triggered.connect(lambda: self._on_action('save_video'))
        file_menu.addAction(save_vid_act)
        file_menu.addSeparator()
        pref_act = QAction('&Preferences...', self)
        pref_act.setShortcut(QKeySequence('Ctrl+,'))
        pref_act.triggered.connect(self._show_preferences)
        file_menu.addAction(pref_act)
        file_menu.addSeparator()
        quit_act = QAction('&Quit', self)
        quit_act.setShortcut(QKeySequence('Ctrl+Q'))
        quit_act.triggered.connect(self.close)
        file_menu.addAction(quit_act)

        # Central widget
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(6, 6, 6, 6)
        main_layout.setSpacing(6)

        # Left panel
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(4)

        # Tool row
        tool_row = QHBoxLayout()
        self._tool_btns = {}
        for tid in TOOL_TIDS:
            btn = QPushButton(TOOL_LABELS[tid])
            btn.setCheckable(True)
            btn.clicked.connect(lambda checked, t=tid: self._on_tool_click(t))
            tool_row.addWidget(btn)
            self._tool_btns[tid] = btn
        left_layout.addLayout(tool_row)

        # Action row
        action_row = QHBoxLayout()
        self._action_btns = {}
        for aid, label in ACTION_CFG:
            btn = QPushButton(label)
            btn.clicked.connect(lambda checked, a=aid: self._on_action(a))
            action_row.addWidget(btn)
            self._action_btns[aid] = btn
        left_layout.addLayout(action_row)

        # Graphics view
        self.scene = QGraphicsScene()
        self.view = _GraphicsView(self)
        self.view.setScene(self.scene)
        self.view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.view.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.view.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        bg = self.settings.value('display/bg_color', '#2b2b2b')
        self.view.setStyleSheet(f'background-color: {bg}; border: none;')
        self.view.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.view.setCursor(Qt.CursorShape.ArrowCursor)
        left_layout.addWidget(self.view, 1)

        main_layout.addWidget(left, 1)

        # Right panel
        right = QWidget()
        right.setFixedWidth(56)
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(3, 3, 3, 3)
        right_layout.setSpacing(3)

        lbl = QLabel('Colors')
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setStyleSheet('color: #ccc; font-size: 11px; font-weight: bold;')
        right_layout.addWidget(lbl)

        self._palette_group = QButtonGroup(self)
        self._palette_group.setExclusive(True)
        for i, hex_color in enumerate(PALETTE_COLORS):
            btn = QPushButton()
            btn.setFixedSize(42, 24)
            btn.setCheckable(True)
            c = QColor(hex_color)
            border = '#fff' if c.lightness() < 128 else '#333'
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {hex_color};
                    border: 2px solid {border};
                    border-radius: 3px;
                }}
                QPushButton:checked {{
                    border: 3px solid white;
                }}
            """)
            self._palette_group.addButton(btn, i)
            right_layout.addWidget(btn, alignment=Qt.AlignmentFlag.AlignCenter)
        self._palette_group.button(0).setChecked(True)
        self._palette_group.idClicked.connect(self._on_color_selected)

        right_layout.addSpacing(8)

        lbl2 = QLabel('Borders')
        lbl2.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl2.setStyleSheet('color: #ccc; font-size: 11px; font-weight: bold;')
        right_layout.addWidget(lbl2)

        self._width_group = QButtonGroup(self)
        self._width_group.setExclusive(True)
        for i, w in enumerate(BORDER_WIDTHS):
            btn = QPushButton()
            btn.setFixedSize(42, 24)
            btn.setCheckable(True)
            pix = QPixmap(42, 24)
            pix.fill(Qt.GlobalColor.transparent)
            p = QPainter(pix)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            p.setPen(QPen(QColor('#cccccc'), w))
            p.drawLine(6, 12, 36, 12)
            p.end()
            btn.setIcon(QIcon(pix))
            btn.setIconSize(pix.size())
            btn.setStyleSheet("""
                QPushButton {
                    background: #3a3a3a;
                    border: 1px solid #555;
                    border-radius: 3px;
                }
                QPushButton:checked {
                    border: 3px solid white;
                }
            """)
            self._width_group.addButton(btn, i)
            right_layout.addWidget(btn, alignment=Qt.AlignmentFlag.AlignCenter)
        self._width_group.button(0).setChecked(True)
        self._width_group.idClicked.connect(self._on_width_selected)

        right_layout.addStretch()

        # Slider
        self._slider = QSlider(Qt.Orientation.Vertical)
        self._slider.setInvertedAppearance(True)

        self._slider.setStyleSheet("""
            QSlider::groove:vertical {
                background: #555; width: 6px; border-radius: 3px;
            }
            QSlider::handle:vertical {
                background: #aaa; height: 16px; border-radius: 8px;
                margin: 0 -5px;
            }
        """)
        right_layout.addWidget(self._slider, 1)

        main_layout.addWidget(right)

        # Status bar
        self._status = QStatusBar()
        self._status.setStyleSheet('QStatusBar { color: #ccc; background: #333; }')
        self.setStatusBar(self._status)

        self._show_placeholder()

    def _connect_signals(self):
        self._slider.valueChanged.connect(self._on_slider)

    def _restore_geometry(self):
        geom = self.settings.value('window/geometry')
        if geom is not None:
            self.restoreGeometry(geom)
        else:
            self.resize(1000, 800)

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, self._refit_view)

    def closeEvent(self, event):
        self.settings.setValue('window/geometry', self.saveGeometry())
        if self._loaded and self._annotations and self._project_path:
            project.save(self._project_path, self._annotations,
                         self._linked_groups, self._slice_idx,
                         self._current_color, self._current_width)
        super().closeEvent(event)

    # ------------------------------------------------------------------
    # Folder loading
    # ------------------------------------------------------------------

    def _on_drop(self, event):
        urls = event.mimeData().urls()
        if not urls:
            return
        path = urls[0].toLocalFile()
        if path.endswith('.radproj'):
            if not self._loaded:
                QMessageBox.warning(self, 'No Data', 'Load an image folder first.')
                return
            self._restore_project(path)
        elif os.path.isdir(path):
            self.load_folder(path)
        else:
            self.load_folder(os.path.dirname(path))

    def _open_folder_dialog(self):
        last = self.settings.value('last/path', '')
        folder = QFileDialog.getExistingDirectory(
            self, 'Select folder with images', last if os.path.isdir(last) else '')
        if folder:
            self.load_folder(folder)

    def load_folder(self, data_path):
        valid, msg = validate_image_folder(data_path)
        if not valid:
            QMessageBox.critical(self, 'Invalid Folder', msg)
            return

        self._reset_state()
        self.data_path = data_path
        self.settings.setValue('last/path', data_path)

        QApplication.processEvents()
        self._status.showMessage(f'Loading images from {os.path.basename(data_path)}...')
        QApplication.processEvents()

        self._slices = load_images(data_path)
        self.num_slices = len(self._slices)
        self._slice_idx = 0
        self._precompute_windowing()
        self._loaded = True

        self._setup_slider()
        self._show_slice()
        self._update_title()

        self._project_path = project.default_path(data_path)

    def _reset_state(self):
        self._slices = []
        self.num_slices = 0
        self._slice_idx = 0
        self._project_path = None
        self._vmin_max = []
        self._annotations = {}
        self._linked_groups = []
        self._selected_anno = None
        self._selected_interp_group = None
        self._active_tool = None
        self._stamp_mode = False
        self._stamp_eligible = False
        self._drawing = False
        self._draw_start = None
        self._loaded = False
        self._clear_annotation_items()
        self._deselect_all_tools()
        self._slider.setRange(0, 0)

    def _show_placeholder(self):
        self.scene.clear()
        self._pixmap_item = None
        self._annotation_items = []
        self._handle_items = []
        self._ghost_items = []
        txt = self.scene.addText(
            'Click "Open Folder"\nto load JPG or PNG images',
            QFont('sans-serif', 16))
        txt.setDefaultTextColor(QColor('#888'))
        txt.setPos(20, 20)
        self._annotation_items.append(txt)
        self.view.fitInView(self.scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def _setup_slider(self):
        self._slider.setRange(0, self.num_slices - 1)
        self._slider.blockSignals(True)
        self._slider.setValue(0)
        self._slider.blockSignals(False)

    # ------------------------------------------------------------------
    # Tool / Action handling
    # ------------------------------------------------------------------

    def _deselect_all_tools(self):
        for btn in self._tool_btns.values():
            btn.setChecked(False)
        self._active_tool = None
        self.view.setCursor(Qt.CursorShape.ArrowCursor)

    def _on_tool_click(self, tid):
        if not self._loaded:
            QMessageBox.warning(self, 'No Data', 'Load a folder first.')
            return
        btn = self._tool_btns[tid]
        if self._active_tool == tid:
            btn.setChecked(False)
            self._active_tool = None
            self.view.setCursor(Qt.CursorShape.ArrowCursor)
        else:
            self._deselect_all_tools()
            btn.setChecked(True)
            self._active_tool = tid
            self.view.setCursor(Qt.CursorShape.CrossCursor)
        self._update_title()
        self._update_status()

    def _on_action(self, aid):
        if aid == 'open':
            self._open_folder_dialog()
        elif aid == 'save_images':
            if not self._loaded:
                QMessageBox.warning(self, 'No Data', 'No images loaded.')
                return
            self._save_images()
        elif aid == 'save_video':
            if not self._loaded:
                QMessageBox.warning(self, 'No Data', 'No images loaded.')
                return
            self._save_video()
        elif aid == 'reset':
            if not self._loaded:
                return
            self._reset_all()
        elif aid == 'invert':
            if not self._loaded:
                return
            self._invert_order()

    def _on_color_selected(self, idx):
        self._current_color = PALETTE_COLORS_RGB[idx]
        if self._selected_anno is not None:
            self._selected_anno.color = self._current_color
            group = self._is_linked_anchor(self._selected_anno)
            if group is not None:
                group.start_anno.color = self._current_color
                group.end_anno.color = self._current_color
            elif self._selected_interp_group is not None:
                grp, _ = self._selected_interp_group
                grp.start_anno.color = self._current_color
                grp.end_anno.color = self._current_color
        self._redraw_annotations()

    def _on_width_selected(self, idx):
        self._current_width = BORDER_WIDTHS[idx]
        if self._selected_anno is not None:
            self._selected_anno.width = self._current_width
            group = self._is_linked_anchor(self._selected_anno)
            if group is not None:
                group.start_anno.width = self._current_width
                group.end_anno.width = self._current_width
            elif self._selected_interp_group is not None:
                grp, _ = self._selected_interp_group
                grp.start_anno.width = self._current_width
                grp.end_anno.width = self._current_width
        self._redraw_annotations()

    def _show_preferences(self):
        dialog = PreferencesDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            bg = self.settings.value('display/bg_color', '#2b2b2b')
            self.view.setStyleSheet(f'background-color: {bg}; border: none;')

    # ------------------------------------------------------------------
    # Project save / load
    # ------------------------------------------------------------------

    def _save_project(self):
        if not self._loaded:
            QMessageBox.warning(self, 'No Data', 'No images loaded.')
            return
        if not self._annotations:
            QMessageBox.warning(self, 'No Annotations', 'Nothing to save.')
            return
        if self._project_path:
            project.save(self._project_path, self._annotations,
                         self._linked_groups, self._slice_idx,
                         self._current_color, self._current_width)
            self._status.showMessage(f'Project saved to {os.path.basename(self._project_path)}')
            QMessageBox.information(self, 'Save Complete',
                                    f'Project saved to:\n{self._project_path}')
        else:
            self._save_project_as()

    def _save_project_as(self):
        if not self._loaded:
            QMessageBox.warning(self, 'No Data', 'No images loaded.')
            return
        default = self._project_path or project.default_path(self.data_path)
        path, _ = QFileDialog.getSaveFileName(
            self, 'Save Project As', default,
            'RadStack Project (*.radproj);;All Files (*)')
        if not path:
            return
        if not path.endswith('.radproj'):
            path += '.radproj'
        self._project_path = path
        project.save(path, self._annotations,
                     self._linked_groups, self._slice_idx,
                     self._current_color, self._current_width)
        self._status.showMessage(f'Project saved to {os.path.basename(path)}')
        QMessageBox.information(self, 'Save Complete',
                                f'Project saved to:\n{path}')

    def _open_project(self):
        if not self._loaded:
            QMessageBox.warning(self, 'No Data', 'Load an image folder first.')
            return
        path, _ = QFileDialog.getOpenFileName(
            self, 'Open Project', '',
            'RadStack Project (*.radproj);;All Files (*)')
        if not path:
            return
        ret = QMessageBox.question(
            self, 'Open Project',
            'Open project file? Current annotations will be replaced.',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if ret != QMessageBox.StandardButton.Yes:
            return
        self._restore_project(path)

    def _restore_project(self, path):
        state = project.load(path)
        if state is None:
            QMessageBox.critical(self, 'Error', 'Failed to load project file.')
            return
        self.deselect_all()
        self._annotations = state["annotations"]
        self._linked_groups = state["linked_groups"]
        self._project_path = path
        idx = state["slice_idx"]
        if 0 <= idx < self.num_slices:
            self._slice_idx = idx
            self._slider.blockSignals(True)
            self._slider.setValue(idx)
            self._slider.blockSignals(False)
        self._current_color = state["current_color"]
        self._current_width = state["current_width"]
        self._show_slice()
        self._status.showMessage(f'Restored {sum(len(v) for v in self._annotations.values())} annotations from project')

    def deselect_all(self):
        self._selected_anno = None
        self._selected_interp_group = None
        self._stamp_mode = False

    # ------------------------------------------------------------------
    # Save / Export
    # ------------------------------------------------------------------

    def _save_images(self):
        fmt = self.settings.value('save/format', 'jpeg')
        quality = int(self.settings.value('save/quality', 100))
        sd = {'save_format': fmt, 'save_quality': quality}
        self._status.showMessage('Saving annotated images...')
        QApplication.processEvents()
        save_annotated_stack(self._slices, self._annotations,
                             self._linked_groups, self.data_path, sd)
        out_dir = self.data_path.rstrip('/') + '_annotated'
        self._status.showMessage(f'Done! Saved to {out_dir}')
        QMessageBox.information(self, 'Save Complete',
                                f'Annotated images saved to:\n{out_dir}')

    def _save_video(self):
        quality = int(self.settings.value('save/quality', 100))
        tmp = tempfile.mkdtemp(prefix='radstack_video_')
        try:
            self._status.showMessage('Rendering frames...')
            QApplication.processEvents()
            for idx, arr in enumerate(self._slices):
                annos = collect_annotations(self._annotations,
                                            self._linked_groups, idx)
                if annos:
                    rendered = render_annotations(arr, annos)
                else:
                    pimg = PILImage.fromarray(arr.copy())
                    if pimg.mode != 'RGB':
                        pimg = pimg.convert('RGB')
                    rendered = np.array(pimg.resize(
                        (arr.shape[1] * _RENDER_SCALE, arr.shape[0] * _RENDER_SCALE),
                        PILImage.NEAREST))
                if rendered.dtype in (np.float32, np.float64):
                    rendered = (np.clip(rendered, 0, 1) * 255).astype(np.uint8)
                dpi = 72 * _RENDER_SCALE
                PILImage.fromarray(rendered).save(
                    os.path.join(tmp, f'frame_{idx:04d}.jpg'),
                    quality=quality, subsampling=0, dpi=(dpi, dpi))
            list_file = os.path.join(tmp, 'ffmpeg_list.txt')
            with open(list_file, 'w') as f:
                for idx in range(len(self._slices)):
                    f.write(f"file 'frame_{idx:04d}.jpg'\n")
            out_path = os.path.join(
                os.path.dirname(self.data_path.rstrip('/')), 'annotated-video.mp4')
            self._status.showMessage('Encoding video with ffmpeg...')
            QApplication.processEvents()
            subprocess.run([
                'ffmpeg', '-y', '-f', 'concat', '-safe', '0',
                '-i', list_file, '-r', '30',
                '-c:v', 'libx264',
                '-preset', 'slow',
                '-crf', '23',
                '-pix_fmt', 'yuv420p', out_path,
            ], check=True)
            self._status.showMessage(f'Video saved to {out_path}')
            QMessageBox.information(self, 'Save Complete',
                                    f'Video saved to:\n{out_path}')
        except subprocess.CalledProcessError:
            QMessageBox.critical(self, 'Error',
                                 'ffmpeg failed. Is it installed on your PATH?')
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def _reset_all(self):
        if not self._annotations and not self._linked_groups:
            return
        reply = QMessageBox.question(
            self, 'Reset All',
            'Are you sure you want to clear all annotations?',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes:
            return
        if self._drawing:
            self._cancel_drawing()
        self._annotations = {}
        self._linked_groups = []
        self._selected_anno = None
        self._selected_interp_group = None
        self._stamp_mode = False
        self._stamp_eligible = False
        self._deselect_all_tools()
        self._clear_annotation_items()
        self._show_slice()
        self._status.showMessage('Reset — all annotations cleared')

    def _invert_order(self):
        if not self._loaded:
            return
        n = self.num_slices
        if n == 0:
            return
        self._slices = list(reversed(self._slices))
        self._vmin_max = list(reversed(self._vmin_max))
        new_annotations = {}
        for idx, annos in self._annotations.items():
            new_idx = n - 1 - idx
            for a in annos:
                a.slice_idx = new_idx
            new_annotations[new_idx] = annos
        self._annotations = new_annotations
        for group in self._linked_groups:
            group.start_slice = n - 1 - group.start_slice
            group.end_slice = n - 1 - group.end_slice
        self._slice_idx = 0
        self._selected_anno = None
        self._stamp_mode = False
        self._slider.blockSignals(True)
        self._slider.setValue(0)
        self._slider.blockSignals(False)
        self._show_slice()
        self._status.showMessage(
            f'Image order inverted — now showing slice 1/{n}')

    # ------------------------------------------------------------------
    # Windowing
    # ------------------------------------------------------------------

    def _precompute_windowing(self):
        self._vmin_max = []
        for arr in self._slices:
            self._vmin_max.append((float(arr.min()), float(arr.max())))

    # ------------------------------------------------------------------
    # Display
    # ------------------------------------------------------------------

    def _update_title(self):
        if not self._loaded:
            self.setWindowTitle('RadStack Annotator')
            return
        folder = os.path.basename(self.data_path or '')
        info = f'Image {self._slice_idx + 1}/{self.num_slices}'
        if self._active_tool:
            info += f'  [{self._active_tool}]'
        if self._stamp_mode:
            info += '  [stamp]'
        self.setWindowTitle(f'RadStack Annotator — {folder} — {info}')

    def _update_status(self):
        if not self._loaded:
            self._status.showMessage('')
            return
        parts = [f'Slice {self._slice_idx + 1}/{self.num_slices}']
        if self._active_tool:
            parts.append(f'Tool: {self._active_tool}')
        if self._stamp_mode:
            parts.append('Stamp mode')
        n_annos = len(self._annotations.get(self._slice_idx, []))
        if n_annos:
            parts.append(f'{n_annos} annotation(s)')
        n_groups = len(self._linked_groups)
        if n_groups:
            parts.append(f'{n_groups} link(s)')
        self._status.showMessage('  |  '.join(parts))

    def _arr_to_qpixmap(self, arr):
        vmin, vmax = self._vmin_max[self._slice_idx]
        if arr.dtype in (np.float32, np.float64):
            if arr.ndim == 2:
                arr = (np.clip((arr - vmin) / (vmax - vmin), 0, 1) * 255).astype(np.uint8)
            else:
                arr = (np.clip(arr, 0, 1) * 255).astype(np.uint8)

        if arr.ndim == 2:
            img = PILImage.fromarray(arr, mode='L')
        elif arr.shape[2] >= 3:
            img = PILImage.fromarray(arr[:, :, :3], mode='RGB')
        else:
            img = PILImage.fromarray(arr.reshape(arr.shape[0], arr.shape[1]), mode='L')

        buf = BytesIO()
        img.save(buf, format='PNG')
        pixmap = QPixmap()
        pixmap.loadFromData(buf.getvalue())
        return pixmap

    def _show_slice(self):
        if not self._loaded:
            return
        arr = self._slices[self._slice_idx]
        pixmap = self._arr_to_qpixmap(arr)
        self.scene.clear()
        self._pixmap_item = self.scene.addPixmap(pixmap)
        self._pixmap_item.setZValue(0)
        self._annotation_items = []
        self._handle_items = []
        self._ghost_items = []
        self._preview_items = []
        self.scene.setSceneRect(
            QRectF(0, 0, pixmap.width(), pixmap.height()))
        self._redraw_annotations()

        self._slider.blockSignals(True)
        self._slider.setValue(self._slice_idx)
        self._slider.blockSignals(False)

        self.view.fitInView(
            self.scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
        QTimer.singleShot(0, self._refit_view)

        self._update_title()
        self._update_status()

    def _refit_view(self):
        if self._loaded:
            self.view.fitInView(
                self.scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    # ------------------------------------------------------------------
    # Annotation management
    # ------------------------------------------------------------------

    def _get_annotations(self, idx=None):
        if idx is None:
            idx = self._slice_idx
        return self._annotations.get(idx, [])

    def _add_annotation(self, anno):
        idx = anno.slice_idx
        if idx not in self._annotations:
            self._annotations[idx] = []
        self._annotations[idx].append(anno)

    def _remove_annotation(self, anno):
        idx = anno.slice_idx
        if idx in self._annotations and anno in self._annotations[idx]:
            self._annotations[idx].remove(anno)
        for g in self._linked_groups[:]:
            if anno is g.start_anno:
                if g.end_anno in self._annotations.get(g.end_slice, []):
                    self._annotations[g.end_slice].remove(g.end_anno)
                self._linked_groups.remove(g)
            elif anno is g.end_anno:
                if g.start_anno in self._annotations.get(g.start_slice, []):
                    self._annotations[g.start_slice].remove(g.start_anno)
                self._linked_groups.remove(g)

    def _clear_annotation_items(self):
        for item in self._annotation_items:
            self.scene.removeItem(item)
        for item in self._handle_items:
            self.scene.removeItem(item)
        for item in self._ghost_items:
            self.scene.removeItem(item)
        for item in self._preview_items:
            self.scene.removeItem(item)
        self._annotation_items = []
        self._handle_items = []
        self._ghost_items = []
        self._preview_items = []

    def _anno_qcolor(self, anno):
        return QColor(*anno.color)

    def _make_annotation_items(self, anno):
        """Create QGraphicsItem(s) for an annotation. Returns a list."""
        x1, y1, x2, y2 = anno.x1, anno.y1, anno.x2, anno.y2
        c = self._anno_qcolor(anno)
        pen = QPen(c, anno.width)
        items = []

        if isinstance(anno, TextBox):
            bx, by = min(x1, x2), min(y1, y2)
            rw, rh = abs(x2 - x1), abs(y2 - y1)
            if anno.show_background:
                bg = QGraphicsRectItem(bx, by, rw, rh)
                bg.setPen(QPen(Qt.PenStyle.NoPen))
                bg.setBrush(QBrush(QColor(0, 0, 0, 128)))
                bg.setZValue(1)
                items.append(bg)
            txt = QGraphicsTextItem(anno.text)
            txt.setDefaultTextColor(c)
            txt.setFont(QFont('sans-serif', anno.font_size, QFont.Weight.Bold))
            bbox = txt.boundingRect()
            txt.setPos((x1 + x2) / 2 - bbox.width() / 2,
                       (y1 + y2) / 2 - bbox.height() / 2)
            txt.setZValue(2)
            items.append(txt)

        elif isinstance(anno, Rect):
            bx, by = min(x1, x2), min(y1, y2)
            rw, rh = abs(x2 - x1), abs(y2 - y1)
            rect = QGraphicsRectItem(bx, by, rw, rh)
            rect.setPen(pen)
            rect.setBrush(QBrush(Qt.BrushStyle.NoBrush))
            rect.setZValue(1)
            items.append(rect)

        elif isinstance(anno, Oval):
            bx, by = min(x1, x2), min(y1, y2)
            rw, rh = abs(x2 - x1), abs(y2 - y1)
            ellipse = QGraphicsEllipseItem(bx, by, rw, rh)
            ellipse.setPen(pen)
            ellipse.setBrush(QBrush(Qt.BrushStyle.NoBrush))
            ellipse.setZValue(1)
            items.append(ellipse)

        else:
            dx, dy = x2 - x1, y2 - y1
            angle = math.atan2(dy, dx)
            shorten = anno.width * 2
            path = QPainterPath()
            path.moveTo(x1, y1)
            path.lineTo(x2 - shorten * math.cos(angle),
                        y2 - shorten * math.sin(angle))
            line = QGraphicsPathItem(path)
            line.setPen(pen)
            line.setZValue(1)
            items.append(line)
            sz = max(10, anno.width * 3)
            spread = math.pi / 6
            tip1 = QPointF(x2 - sz * math.cos(angle - spread),
                           y2 - sz * math.sin(angle - spread))
            tip2 = QPointF(x2 - sz * math.cos(angle + spread),
                           y2 - sz * math.sin(angle + spread))
            poly = QPolygonF([QPointF(x2, y2), tip1, tip2])
            head = QGraphicsPolygonItem(poly)
            head.setBrush(QBrush(c))
            head.setPen(QPen(Qt.PenStyle.NoPen))
            head.setZValue(1)
            items.append(head)

        return items

    def _redraw_annotations(self):
        self._clear_annotation_items()
        if not self._loaded:
            return

        for anno in self._get_annotations():
            is_sel = (anno is self._selected_anno and
                      anno.slice_idx == self._slice_idx)
            items = self._make_annotation_items(anno)
            sel_color = QColor(*self._current_color)
            for item in items:
                if is_sel:
                    if isinstance(item, QGraphicsTextItem):
                        item.setDefaultTextColor(sel_color)
                    else:
                        item.setPen(QPen(sel_color, anno.width))
                self.scene.addItem(item)
                self._annotation_items.append(item)
            if is_sel:
                self._add_handle_items(anno)

        for group in self._linked_groups:
            if group.contains_slice(self._slice_idx):
                interp = group.get_interpolated(self._slice_idx)
                is_sel = (self._selected_interp_group is not None and
                          self._selected_interp_group[0] is group and
                          self._selected_interp_group[1] == self._slice_idx)
                items = self._make_annotation_items(interp)
                sel_color = QColor(*self._current_color)
                for item in items:
                    if is_sel:
                        if isinstance(item, QGraphicsTextItem):
                            item.setDefaultTextColor(sel_color)
                        else:
                            item.setPen(QPen(sel_color, interp.width))
                    self.scene.addItem(item)
                    self._annotation_items.append(item)
                if is_sel:
                    self._add_handle_items(interp)

        self._sync_sidebar_to_selection()

    def _sync_sidebar_to_selection(self):
        if self._selected_anno is not None and self._selected_anno.slice_idx == self._slice_idx:
            w = self._selected_anno.width
            if w != self._current_width:
                self._current_width = w
                for i, bw in enumerate(BORDER_WIDTHS):
                    if bw == w:
                        self._width_group.blockSignals(True)
                        self._width_group.button(i).setChecked(True)
                        self._width_group.blockSignals(False)
                        break

    def _add_handle_items(self, anno):
        x1, y1, x2, y2 = anno.x1, anno.y1, anno.x2, anno.y2
        pts = [(x1, y1), (x2, y2)]
        if not isinstance(anno, Arrow):
            pts = [(x1, y1), (x1, y2), (x2, y1), (x2, y2)]
        for px, py in pts:
            h = QGraphicsEllipseItem(px - 4, py - 4, 8, 8)
            h.setPen(QPen(QColor('white'), 1.5))
            h.setBrush(QBrush(QColor(*self._current_color)))
            h.setZValue(10)
            self.scene.addItem(h)
            self._handle_items.append(h)

    # ------------------------------------------------------------------
    # Stamp mode
    # ------------------------------------------------------------------

    def _enter_stamp_mode(self):
        if (self._selected_anno is not None and
                self._selected_anno.slice_idx != self._slice_idx):
            self._stamp_mode = True
            self.view.setCursor(Qt.CursorShape.CrossCursor)
            self._update_title()
            self._update_status()

    def _exit_stamp_mode(self):
        if self._stamp_mode:
            self._stamp_mode = False
            for item in self._ghost_items:
                self.scene.removeItem(item)
            self._ghost_items = []
            self.view.setCursor(Qt.CursorShape.ArrowCursor)
            self._redraw_annotations()
            self._update_title()
            self._update_status()

    def _is_linked_anchor(self, anno):
        for g in self._linked_groups:
            if anno is g.start_anno or anno is g.end_anno:
                return g
        return None

    def _update_ghost(self, scene_pos):
        src = self._selected_anno
        if src is None:
            return
        x, y = scene_pos.x(), scene_pos.y()
        dx = src.x2 - src.x1
        dy = src.y2 - src.y1
        gx1 = x - dx / 2
        gy1 = y - dy / 2
        gx2 = x + dx / 2
        gy2 = y + dy / 2
        for item in self._ghost_items:
            self.scene.removeItem(item)
        self._ghost_items = []
        pen = QPen(QColor(*self._current_color), src.width, Qt.PenStyle.DashLine)

        if isinstance(src, (Rect, TextBox)):
            bx, by = min(gx1, gx2), min(gy1, gy2)
            rw, rh = abs(gx2 - gx1), abs(gy2 - gy1)
            rect = QGraphicsRectItem(bx, by, rw, rh)
            rect.setPen(pen)
            rect.setZValue(7)
            self.scene.addItem(rect)
            self._ghost_items.append(rect)
            if isinstance(src, TextBox) and src.text:
                txt = QGraphicsTextItem(src.text)
                txt.setDefaultTextColor(QColor(*self._current_color))
                txt.setFont(QFont('sans-serif', src.font_size, QFont.Weight.Bold))
                bbox = txt.boundingRect()
                txt.setPos((gx1 + gx2) / 2 - bbox.width() / 2,
                           (gy1 + gy2) / 2 - bbox.height() / 2)
                txt.setZValue(8)
                self.scene.addItem(txt)
                self._ghost_items.append(txt)
        elif isinstance(src, Oval):
            bx, by = min(gx1, gx2), min(gy1, gy2)
            rw, rh = abs(gx2 - gx1), abs(gy2 - gy1)
            ellipse = QGraphicsEllipseItem(bx, by, rw, rh)
            ellipse.setPen(pen)
            ellipse.setZValue(7)
            self.scene.addItem(ellipse)
            self._ghost_items.append(ellipse)
        else:
            dx2, dy2 = gx2 - gx1, gy2 - gy1
            angle = math.atan2(dy2, dx2)
            shorten = src.width * 2
            path = QPainterPath()
            path.moveTo(gx1, gy1)
            path.lineTo(gx2 - shorten * math.cos(angle),
                        gy2 - shorten * math.sin(angle))
            line = QGraphicsPathItem(path)
            line.setPen(pen)
            line.setZValue(7)
            self.scene.addItem(line)
            self._ghost_items.append(line)
            sz = max(10, src.width * 3)
            spread = math.pi / 6
            tip1 = QPointF(gx2 - sz * math.cos(angle - spread),
                           gy2 - sz * math.sin(angle - spread))
            tip2 = QPointF(gx2 - sz * math.cos(angle + spread),
                           gy2 - sz * math.sin(angle + spread))
            poly = QPolygonF([QPointF(gx2, gy2), tip1, tip2])
            head = QGraphicsPolygonItem(poly)
            head.setBrush(QBrush(QColor(*self._current_color)))
            head.setPen(QPen(Qt.PenStyle.NoPen))
            head.setZValue(7)
            self.scene.addItem(head)
            self._ghost_items.append(head)

    def _do_stamp(self, x, y):
        src = self._selected_anno
        if src is None or src.slice_idx == self._slice_idx:
            return
        dx = src.x2 - src.x1
        dy = src.y2 - src.y1
        dst = src.copy_transformed(x - dx / 2, y - dy / 2,
                                   x + dx / 2, y + dy / 2,
                                   self._slice_idx)
        src.color = self._current_color
        src.width = self._current_width
        dst.color = self._current_color
        dst.width = self._current_width
        self._add_annotation(dst)
        group = LinkedGroup(src.slice_idx, self._slice_idx, src, dst)
        self._linked_groups.append(group)
        kind = type(src).__name__
        self._status.showMessage(
            f'Stamped {kind} from slice {src.slice_idx} -> '
            f'{self._slice_idx} (interp {group.start_slice}-{group.end_slice})')
        self._selected_anno = None
        self._exit_stamp_mode()
        self._deselect_all_tools()
        self._update_title()
        self._update_status()

    # ------------------------------------------------------------------
    # Mouse events
    # ------------------------------------------------------------------

    def _cancel_drawing(self):
        for item in self._preview_items:
            self.scene.removeItem(item)
        self._preview_items = []
        self._drawing = False
        self._draw_start = None
        self._update_title()

    def _on_press(self, scene_pos):
        if not self._loaded:
            return
        x, y = scene_pos.x(), scene_pos.y()

        if self._stamp_mode:
            self._do_stamp(x, y)
            return

        if self._active_tool in ('arrow', 'rect', 'oval', 'text') and not self._drawing:
            anno, mode, group = self._find_nearest(x, y)
            if anno is not None:
                self._selected_anno = anno
                self._selected_interp_group = (group, self._slice_idx) if group else None
                self._stamp_eligible = False
                self._deselect_all_tools()
                self._redraw_annotations()
                self._update_status()
                return
            self._drawing = True
            self._draw_start = (x, y)
            return

        if (self._selected_anno is not None and
                self._selected_anno.slice_idx == self._slice_idx):
            mode = self._hit_test(x, y, self._selected_anno)
            if mode:
                self._dragging = True
                self._drag_mode = mode
                self._drag_start = (x, y)
                return

        anno, mode, group = self._find_nearest(x, y)
        if anno is not None:
            self._selected_anno = anno
            self._selected_interp_group = (group, self._slice_idx) if group else None
            self._stamp_eligible = False
            self._redraw_annotations()
            self._update_status()
            return

        if self._selected_anno is not None:
            self._selected_anno = None
            self._selected_interp_group = None
            self._stamp_eligible = False
            self._exit_stamp_mode()
            self._redraw_annotations()
            self._update_status()

    def _on_release(self, scene_pos):
        if self._drawing and self._draw_start is not None:
            x1, y1 = self._draw_start
            x2, y2 = scene_pos.x(), scene_pos.y()
            self._cancel_drawing()
            if (abs(x2 - x1) > 5 or abs(y2 - y1) > 5):
                cls = {'arrow': Arrow, 'rect': Rect,
                       'oval': Oval, 'text': TextBox}.get(
                    self._active_tool, Arrow)
                kwargs = {'width': self._current_width}
                if self._current_color is not None:
                    kwargs['color'] = self._current_color
                anno = cls(x1, y1, x2, y2, self._slice_idx, **kwargs)
                if isinstance(anno, TextBox):
                    anno.text = ''
                    self._add_annotation(anno)
                    dialog = TextInputDialog(self, show_bg=self._last_show_bg)
                    right_x = max(x1, x2)
                    top_y = min(y1, y2)
                    dialog.move(
                        self.view.mapToGlobal(
                            self.view.mapFromScene(QPointF(right_x + 5, top_y))))
                    dialog.text_edit.textChanged.connect(
                        lambda txt: setattr(anno, 'text', txt) or self._redraw_annotations())
                    dialog.size_spin.valueChanged.connect(
                        lambda fs: setattr(anno, 'font_size', fs) or self._redraw_annotations())
                    dialog.bg_check.toggled.connect(
                        lambda checked: setattr(anno, 'show_background', checked) or self._redraw_annotations())
                    if dialog.exec() == QDialog.DialogCode.Accepted:
                        anno.text = dialog.text_edit.text()
                        anno.font_size = dialog.size_spin.value()
                        anno.show_background = dialog.bg_check.isChecked()
                        self._last_show_bg = dialog.bg_check.isChecked()
                    else:
                        self._last_show_bg = dialog.bg_check.isChecked()
                        self._remove_annotation(anno)
                        self._redraw_annotations()
                        self._drawing = False
                        self._draw_start = None
                        return
                else:
                    self._add_annotation(anno)
                self._selected_anno = anno
                self._selected_interp_group = None
                self._stamp_eligible = True
                self._deselect_all_tools()
                self._redraw_annotations()
                self._update_status()
            self._drawing = False
            self._draw_start = None
            return

        self._dragging = False
        self._drag_mode = None
        self._drag_start = None

    def _on_motion(self, scene_pos):
        if not self._loaded:
            return
        x, y = scene_pos.x(), scene_pos.y()

        if self._stamp_mode and self._selected_anno is not None:
            self._update_ghost(scene_pos)
            return

        if self._drawing and self._draw_start is not None:
            for item in self._preview_items:
                self.scene.removeItem(item)
            self._preview_items = []
            x1, y1 = self._draw_start
            pen = QPen(QColor(*self._current_color), self._current_width, Qt.PenStyle.DashLine)

            if self._active_tool == 'arrow':
                dx, dy = x - x1, y - y1
                angle = math.atan2(dy, dx)
                shorten = self._current_width * 2
                path = QPainterPath()
                path.moveTo(x1, y1)
                path.lineTo(x - shorten * math.cos(angle),
                            y - shorten * math.sin(angle))
                line = QGraphicsPathItem(path)
                line.setPen(pen)
                line.setZValue(6)
                self.scene.addItem(line)
                self._preview_items.append(line)
                sz = max(10, self._current_width * 3)
                spread = math.pi / 6
                tip1 = QPointF(x - sz * math.cos(angle - spread),
                               y - sz * math.sin(angle - spread))
                tip2 = QPointF(x - sz * math.cos(angle + spread),
                               y - sz * math.sin(angle + spread))
                poly = QPolygonF([QPointF(x, y), tip1, tip2])
                head = QGraphicsPolygonItem(poly)
                head.setBrush(QBrush(QColor(*self._current_color)))
                head.setPen(QPen(Qt.PenStyle.NoPen))
                head.setZValue(6)
                self.scene.addItem(head)
                self._preview_items.append(head)
            elif self._active_tool == 'oval':
                bx, by = min(x1, x), min(y1, y)
                rw, rh = abs(x - x1), abs(y - y1)
                ellipse = QGraphicsEllipseItem(bx, by, rw, rh)
                ellipse.setPen(pen)
                ellipse.setZValue(6)
                self.scene.addItem(ellipse)
                self._preview_items.append(ellipse)
            else:
                bx, by = min(x1, x), min(y1, y)
                rw, rh = abs(x - x1), abs(y - y1)
                rect = QGraphicsRectItem(bx, by, rw, rh)
                rect.setPen(pen)
                rect.setZValue(6)
                self.scene.addItem(rect)
                self._preview_items.append(rect)
            return

        if not self._dragging or self._selected_anno is None:
            return

        if getattr(self._selected_anno, 'locked', False):
            self._dragging = False
            self._drag_mode = None
            self._drag_start = None
            return

        if self._selected_interp_group is not None:
            group, _ = self._selected_interp_group
            if self._drag_mode == 'body':
                mx, my = self._selected_anno.midpoint()
                dx = x - mx
                dy = y - my
                group.start_anno.translate(dx, dy)
                group.end_anno.translate(dx, dy)
            elif self._drag_mode == 'head':
                dx2 = x - self._selected_anno.x2
                dy2 = y - self._selected_anno.y2
                group.start_anno.x2 += dx2
                group.start_anno.y2 += dy2
                group.end_anno.x2 += dx2
                group.end_anno.y2 += dy2
            elif self._drag_mode == 'tail':
                dx1 = x - self._selected_anno.x1
                dy1 = y - self._selected_anno.y1
                group.start_anno.x1 += dx1
                group.start_anno.y1 += dy1
                group.end_anno.x1 += dx1
                group.end_anno.y1 += dy1
            self._selected_anno = group.get_interpolated(self._slice_idx)
        elif self._drag_mode == 'body':
            mx, my = self._selected_anno.midpoint()
            dx = x - mx
            dy = y - my
            self._selected_anno.translate(dx, dy)
        elif self._drag_mode == 'head':
            self._selected_anno.x2 = x
            self._selected_anno.y2 = y
        elif self._drag_mode == 'tail':
            self._selected_anno.x1 = x
            self._selected_anno.y1 = y

        # Unify size across LinkedGroup so all slices share the same dimensions
        linked = self._selected_interp_group
        if linked is None:
            linked = self._is_linked_anchor(self._selected_anno)
        if linked is not None:
            group = linked[0] if isinstance(linked, tuple) else linked
            w = abs(self._selected_anno.x2 - self._selected_anno.x1)
            h = abs(self._selected_anno.y2 - self._selected_anno.y1)
            for ann in (group.start_anno, group.end_anno):
                sx = 1 if ann.x2 >= ann.x1 else -1
                sy = 1 if ann.y2 >= ann.y1 else -1
                ann.x2 = ann.x1 + sx * w
                ann.y2 = ann.y1 + sy * h

        self._redraw_annotations()

    def _on_scroll(self, event):
        if not self._loaded:
            return
        old_idx = self._slice_idx
        delta = event.angleDelta().y()
        if delta > 0:
            self._slice_idx = max(0, self._slice_idx - 1)
        elif delta < 0:
            self._slice_idx = min(self.num_slices - 1, self._slice_idx + 1)
        if self._slice_idx != old_idx:
            self._selected_interp_group = None
            if (self._selected_anno is not None and
                    self._selected_anno.slice_idx != self._slice_idx):
                if self._stamp_eligible and not self._stamp_mode:
                    self._enter_stamp_mode()
            elif self._stamp_mode and self._selected_anno is not None:
                if self._selected_anno.slice_idx == self._slice_idx:
                    self._exit_stamp_mode()
        self._show_slice()

    def _on_key_press(self, event):
        key = event.key()
        if key in (Qt.Key.Key_Up, Qt.Key.Key_Down):
            old_idx = self._slice_idx
            if key == Qt.Key.Key_Up:
                self._slice_idx = max(0, self._slice_idx - 1)
            else:
                self._slice_idx = min(self.num_slices - 1, self._slice_idx + 1)
            if self._slice_idx != old_idx:
                self._selected_interp_group = None
                if (self._selected_anno is not None and
                        self._selected_anno.slice_idx != self._slice_idx):
                    if self._stamp_eligible and not self._stamp_mode:
                        self._enter_stamp_mode()
                elif self._stamp_mode and self._selected_anno is not None:
                    if self._selected_anno.slice_idx == self._slice_idx:
                        self._exit_stamp_mode()
                self._show_slice()
            return

        tool_map = {
            Qt.Key.Key_A: 'arrow',
            Qt.Key.Key_R: 'rect',
            Qt.Key.Key_O: 'oval',
            Qt.Key.Key_T: 'text',
        }
        if key in tool_map:
            self._on_tool_click(tool_map[key])
            return

        if (key in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace) and
                self._selected_anno is not None):
            anno = self._selected_anno
            group_info = self._selected_interp_group
            self._selected_anno = None
            self._selected_interp_group = None
            self._stamp_eligible = False
            self._exit_stamp_mode()
            if group_info is not None:
                group, _ = group_info
                if group in self._linked_groups:
                    self._remove_annotation(group.start_anno)
            else:
                self._remove_annotation(anno)
            self._redraw_annotations()
            self._update_status()

    # ------------------------------------------------------------------
    # Slider
    # ------------------------------------------------------------------

    def _on_slider(self, val):
        if not self._loaded:
            return
        old_idx = self._slice_idx
        self._slice_idx = int(val)
        if self._slice_idx != old_idx:
            self._selected_interp_group = None
        if self._selected_anno is not None:
            if self._selected_anno.slice_idx != self._slice_idx:
                if self._stamp_eligible and not self._stamp_mode:
                    self._enter_stamp_mode()
            else:
                if self._stamp_mode:
                    self._exit_stamp_mode()
        self._show_slice()

    # ------------------------------------------------------------------
    # Hit testing
    # ------------------------------------------------------------------

    def _hit_test(self, x, y, anno, tol=None):
        if tol is None:
            tol = HIT_TOLERANCE
        if isinstance(anno, Arrow):
            if anno.end_dist(x, y) < tol:
                return 'head'
            if anno.start_dist(x, y) < tol:
                return 'tail'
            if anno.line_dist(x, y) < tol:
                return 'body'
            return None
        x1, y1, x2, y2 = anno.x1, anno.y1, anno.x2, anno.y2
        for (cx, cy) in [(x1, y1), (x1, y2), (x2, y1), (x2, y2)]:
            if math.hypot(x - cx, y - cy) < tol:
                return 'head' if (cx, cy) == (x2, y2) else 'tail'
        if isinstance(anno, Oval):
            rx, ry = abs(x2 - x1) / 2, abs(y2 - y1) / 2
            if rx < 1 or ry < 1:
                return None
            cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
            if ((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2 <= 1:
                return 'body'
        else:
            if (min(x1, x2) <= x <= max(x1, x2) and
                    min(y1, y2) <= y <= max(y1, y2)):
                return 'body'
        return None

    def _find_nearest(self, x, y, tol=None):
        if tol is None:
            tol = HIT_TOLERANCE + 3
        for anno in self._get_annotations():
            mode = self._hit_test(x, y, anno, tol)
            if mode:
                return anno, mode, None
        for group in self._linked_groups:
            if group.contains_slice(self._slice_idx):
                interp = group.get_interpolated(self._slice_idx)
                mode = self._hit_test(x, y, interp, tol)
                if mode:
                    return interp, mode, group
        return None, None, None
