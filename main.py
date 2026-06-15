import sys
import os
import json
import math
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QFileDialog, QInputDialog, QMessageBox, QLabel,
    QListWidgetItem, QColorDialog, QMenu, QDialog, QVBoxLayout, QListWidget,
    QComboBox, QLineEdit, QTextEdit, QPlainTextEdit,
    QPushButton, QHBoxLayout, QTreeWidgetItem
)
from PySide6.QtCore import Qt, QPointF, QRectF, QSettings, QSize, QTimer
from PySide6.QtGui import (
    QPolygonF, QColor, QBrush, QPixmap, QIcon, QPalette, QCursor, QPainter, QPen,
    QShortcut, QKeySequence
)

from main_dataset_tool import DatasetToolWindow
from ui.main_window import Ui_MainWindow
from core.canvas import Canvas, CanvasMode
from core.sam_client import SAMClient
from core.exporter import Exporter
from core.shapes import BaseShape, RectShape, PolyShape, PointShape, RotatedRectShape, color_for_label
from utils.message import DialogOver

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_SAM3_PATH = os.path.join(BASE_DIR, "models", "sam3.pt")


class LabelSelectDialog(QDialog):
    def __init__(self, labels, current_label="", parent=None):
        super().__init__(parent)
        self.setWindowTitle("选择类别")
        self.resize(320, 420)
        self.selected_label = None
        self.labels = labels[:]

        layout = QVBoxLayout(self)
        self.list_widget = QListWidget()
        for index, label in enumerate(labels, 1):
            prefix = f"{index}. " if index <= 9 else ""
            item = QListWidgetItem(f"{prefix}{label}")
            item.setData(Qt.UserRole, label)
            self.list_widget.addItem(item)
            if label == current_label:
                self.list_widget.setCurrentItem(item)
        layout.addWidget(self.list_widget)

        button_row = QHBoxLayout()
        self.ok_button = QPushButton("确定")
        self.cancel_button = QPushButton("取消")
        self.new_button = QPushButton("新建类别")
        button_row.addWidget(self.new_button)
        button_row.addStretch()
        button_row.addWidget(self.ok_button)
        button_row.addWidget(self.cancel_button)
        layout.addLayout(button_row)

        self.list_widget.itemDoubleClicked.connect(self.accept_selection)
        self.ok_button.clicked.connect(self.accept_selection)
        self.cancel_button.clicked.connect(self.reject)
        self.new_button.clicked.connect(self.create_new_label)

    def create_new_label(self):
        text, ok = QInputDialog.getText(self, "新建类别", "输入类别名称：")
        if ok and text.strip():
            self.selected_label = text.strip()
            self.accept()

    def accept_selection(self):
        item = self.list_widget.currentItem()
        if item:
            self.selected_label = item.data(Qt.UserRole)
            self.accept()

    def keyPressEvent(self, event):
        key = event.key()
        if Qt.Key_1 <= key <= Qt.Key_9:
            index = key - Qt.Key_1
            if index < self.list_widget.count():
                self.list_widget.setCurrentRow(index)
                self.accept_selection()
                return
        super().keyPressEvent(event)

    def showEvent(self, event):
        super().showEvent(event)
        self._move_near_cursor()

    def _move_near_cursor(self):
        cursor_pos = QCursor.pos()
        screen = QApplication.screenAt(cursor_pos) or QApplication.primaryScreen()
        if not screen:
            self.move(cursor_pos)
            return
        available = screen.availableGeometry()
        x = min(max(cursor_pos.x() + 12, available.left()), available.right() - self.width())
        y = min(max(cursor_pos.y() + 12, available.top()), available.bottom() - self.height())
        self.move(x, y)


class LabelEditDialog(QDialog):
    def __init__(self, labels, selected_index=0, parent=None):
        super().__init__(parent)
        self.setWindowTitle("修改类别")
        self.resize(320, 120)
        self.selected_label = ""

        layout = QVBoxLayout(self)
        self.combo = QComboBox()
        self.combo.addItems(labels)
        if labels:
            self.combo.setCurrentIndex(max(0, min(selected_index, len(labels) - 1)))
        layout.addWidget(self.combo)

        button_row = QHBoxLayout()
        button_row.addStretch()
        self.ok_button = QPushButton("确定")
        self.cancel_button = QPushButton("取消")
        button_row.addWidget(self.ok_button)
        button_row.addWidget(self.cancel_button)
        layout.addLayout(button_row)

        self.ok_button.clicked.connect(self.accept_selection)
        self.cancel_button.clicked.connect(self.reject)
        self.combo.activated.connect(lambda _index: self.ok_button.setFocus())
        self.ok_button.setFocus()

    def accept_selection(self):
        self.selected_label = self.combo.currentText().strip()
        if self.selected_label:
            self.accept()

    def selected_index(self):
        return self.combo.currentIndex()

    def showEvent(self, event):
        super().showEvent(event)
        self._move_near_cursor()

    def _move_near_cursor(self):
        cursor_pos = QCursor.pos()
        screen = QApplication.screenAt(cursor_pos) or QApplication.primaryScreen()
        if not screen:
            self.move(cursor_pos)
            return
        available = screen.availableGeometry()
        x = min(max(cursor_pos.x() + 12, available.left()), available.right() - self.width())
        y = min(max(cursor_pos.y() + 12, available.top()), available.bottom() - self.height())
        self.move(x, y)


class MainWindow(QMainWindow, Ui_MainWindow):
    def __init__(self):
        super().__init__()
        self.setupUi(self)

        self.scene = Canvas(self)
        self.view.setScene(self.scene)

        self.current_image_path = None
        self.current_dir = None
        self.class_list = []
        self.class_colors = {}
        self.class_visibility = {}
        self.prompt_aliases = {}
        self.pending_prompt_targets = {}
        self.settings = QSettings("LuoHuaLabel", "LuoHuaLabel")
        self.current_format = self.settings.value("last_format", "yolo", str)
        self.current_theme = self.settings.value("theme", "system", str)
        self.breathing_highlight_enabled = self._settings_bool("breathing_highlight", True)
        self.active_label = self.settings.value("active_label", "", str)
        self.last_edit_label_index = self.settings.value("last_edit_label_index", 0, int)
        self.annotation_item_syncing = False
        self.shape_to_item = {}
        self._default_palette = QApplication.instance().palette()
        self._last_right_panel_width = 320
        self._file_grid_icon_size = QSize()

        self.modeLabel = QLabel("模式: 矩形标注")
        self.statusBar.addWidget(self.modeLabel)

        self.helpLabel = QLabel("状态: 正在初始化")
        self.statusBar.addWidget(self.helpLabel)
        self.activeLabelIndicator = QLabel("当前标签: 未选择")
        self.statusBar.addPermanentWidget(self.activeLabelIndicator)

        self.sam_client = SAMClient(self)
        self.sam_client.inference_result.connect(self.scene.handle_sam_result)
        self.sam_client.text_result_ready.connect(self.handle_text_results)
        self.sam_client.model_status_changed.connect(self.update_model_status)
        self.scene.sam_client = self.sam_client

        # 撤销/重做数据栈
        self.undo_stack = []
        self.redo_stack = []
        self.max_history_steps = 20
        self.scene.state_changed.connect(self.push_state)
        self._breathing_phase = 0.0
        self._breathing_timer = QTimer(self)
        self._breathing_timer.setInterval(60)
        self._breathing_timer.timeout.connect(self._tick_breathing_highlight)

        self._connect_signals()
        self._update_file_grid_metrics()
        self._setup_shortcuts()
        self.formatWidget.set_format(self.current_format)
        self.themeWidget.set_theme(self.current_theme)
        self.actionBreathingHighlight.setChecked(self.breathing_highlight_enabled)
        self.set_breathing_highlight_enabled(self.breathing_highlight_enabled, persist=False)
        self._set_mode(CanvasMode.RECT)
        self._connect_system_theme_signal()
        self.apply_theme(self.current_theme)
        self.update_active_label_indicator()
        self.sam_client.load_model_async(DEFAULT_SAM3_PATH)
        self.restore_last_session()

    def _connect_signals(self):
        self.actionOpen.triggered.connect(self.open_dir)
        self.actionSave.triggered.connect(lambda checked=False: self.save_annotation(self.current_format))
        self.actionBreathingHighlight.toggled.connect(self.set_breathing_highlight_enabled)

        self.formatWidget.format_changed.connect(self.set_current_format)
        self.themeWidget.theme_changed.connect(self.apply_theme)

        self.btnDatasetTool.clicked.connect(self.open_dataset_tool)

        # self.actionFormatJSON.triggered.connect(lambda: self.set_current_format("json"))
        # self.actionFormatYOLO.triggered.connect(lambda: self.set_current_format("yolo"))
        # self.actionFormatXML.triggered.connect(lambda: self.set_current_format("xml"))

        self.actionRect.triggered.connect(lambda checked=False: self._set_mode(CanvasMode.RECT))
        self.actionPoly.triggered.connect(lambda checked=False: self._set_mode(CanvasMode.POLY))
        self.actionPoint.triggered.connect(lambda checked=False: self._set_mode(CanvasMode.POINT))
        self.actionRBox.triggered.connect(lambda checked=False: self._set_mode(CanvasMode.RBOX))
        self.actionToggleRightPanel.toggled.connect(self.set_right_panel_visible)

        self.samSwitch.toggled.connect(self.on_sam_toggled)

        self.samPromptBtn.clicked.connect(self.trigger_sam_prompt)
        self.samRefBtn.clicked.connect(self.trigger_reference_search)
        self.samPromptInput.lineEdit().returnPressed.connect(self.trigger_sam_prompt)

        self.listFiles.currentItemChanged.connect(self.on_file_selected)
        self.listFiles.setContextMenuPolicy(Qt.CustomContextMenu)
        self.listFiles.customContextMenuRequested.connect(self.show_file_list_context_menu)
        self.view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.view.customContextMenuRequested.connect(self.show_canvas_label_menu)
        self.scene.mouse_moved.connect(self.update_coordinate_label)
        self.scene.shape_drawn.connect(self.handle_new_shape)
        self.scene.selectionChanged.connect(self.sync_annotation_selection_from_scene)

        self.scene.shape_double_clicked.connect(self.edit_shape_label)

        self.listClasses.itemChanged.connect(self.on_list_item_changed)
        self.listClasses.currentItemChanged.connect(self.on_class_item_selected)
        self.listClasses.itemDoubleClicked.connect(self.on_class_tree_item_double_clicked)
        self.listClasses.customContextMenuRequested.connect(self.show_class_context_menu)
        self.annotationToolBox.currentChanged.connect(self.on_annotation_group_changed)
        for widget in self.annotation_list_widgets():
            widget.itemSelectionChanged.connect(
                lambda list_widget=widget: self.on_annotation_selection_changed(list_widget)
            )
            widget.itemDoubleClicked.connect(
                lambda item, list_widget=widget: self.edit_annotation_item(item, list_widget)
            )
            widget.setContextMenuPolicy(Qt.CustomContextMenu)
            widget.customContextMenuRequested.connect(
                lambda pos, list_widget=widget: self.show_annotation_context_menu(list_widget, pos)
            )

        self.btnHelp.clicked.connect(self.show_help_dialog)

    def _settings_bool(self, key, default=False):
        value = self.settings.value(key, default)
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in ("1", "true", "yes", "on")
        return bool(value)

    def set_breathing_highlight_enabled(self, enabled, persist=True):
        self.breathing_highlight_enabled = bool(enabled)
        BaseShape.breathing_enabled = self.breathing_highlight_enabled
        if self.breathing_highlight_enabled:
            if not self._breathing_timer.isActive():
                self._breathing_timer.start()
        else:
            self._breathing_timer.stop()
            BaseShape.breathing_alpha = BaseShape.fill_alpha
            self._refresh_breathing_highlight()
        if persist:
            self.settings.setValue("breathing_highlight", self.breathing_highlight_enabled)

    def _tick_breathing_highlight(self):
        self._breathing_phase = (self._breathing_phase + 0.16) % (math.pi * 2)
        wave = (math.sin(self._breathing_phase) + 1.0) / 2.0
        BaseShape.breathing_alpha = int(BaseShape.fill_alpha + wave * 60)
        self._refresh_breathing_highlight()

    def _refresh_breathing_highlight(self):
        if not hasattr(self, "scene") or self.scene is None:
            return
        for item in self.scene.items():
            if isinstance(item, (RectShape, PolyShape, RotatedRectShape)):
                item.refresh_breathing_brush()

    def _setup_shortcuts(self):
        self._shortcuts = []
        shortcut_map = [
            ("Ctrl+S", lambda: self.save_annotation(self.current_format), True),
            ("Ctrl+Z", self.undo, True),
            ("Ctrl+Y", self.redo, True),
            ("Ctrl+Shift+Z", self.redo, True),
            ("A", self.previous_image, False),
            ("Left", self.previous_image, False),
            ("D", self.next_image, False),
            ("Right", self.next_image, False),
            ("Delete", self.delete_selected_shapes, False),
            ("Backspace", self.delete_selected_shapes, False),
            ("E", self.edit_selected_shape_label, False),
            ("F1", self.show_help_dialog, True),
            ("R", lambda: self._set_mode(CanvasMode.RECT), False),
            ("P", lambda: self._set_mode(CanvasMode.POLY), False),
            ("T", lambda: self._set_mode(CanvasMode.POINT), False),
            ("O", lambda: self._set_mode(CanvasMode.RBOX), False),
            ("Q", self.toggle_sam_shortcut, False),
            ("Space", self.toggle_sam_shortcut, False),
        ]
        for sequence, callback, allow_text_focus in shortcut_map:
            self._add_shortcut(sequence, callback, allow_text_focus)
        for index in range(1, 10):
            self._add_shortcut(str(index), lambda idx=index - 1: self.set_label_by_index(idx), False)

    def _add_shortcut(self, sequence, callback, allow_text_focus=False):
        shortcut = QShortcut(QKeySequence(sequence), self)
        shortcut.setContext(Qt.ApplicationShortcut)
        shortcut.activated.connect(lambda cb=callback, allow=allow_text_focus: self._run_shortcut(cb, allow))
        self._shortcuts.append(shortcut)

    def _run_shortcut(self, callback, allow_text_focus=False):
        if not allow_text_focus and self._text_input_has_focus():
            return
        callback()

    def _text_input_has_focus(self):
        widget = QApplication.focusWidget()
        return isinstance(widget, (QLineEdit, QTextEdit, QPlainTextEdit))

    def set_label_by_index(self, index):
        if 0 <= index < len(self.class_list):
            self.set_active_label(self.class_list[index])

    def previous_image(self):
        current_idx = self.listFiles.currentRow()
        if current_idx > 0:
            self.listFiles.setCurrentRow(current_idx - 1)

    def next_image(self):
        current_idx = self.listFiles.currentRow()
        if current_idx < self.listFiles.count() - 1:
            self.listFiles.setCurrentRow(current_idx + 1)

    def set_right_panel_visible(self, visible):
        sizes = self.splitter.sizes()
        if len(sizes) < 3:
            self.rightPanel.setVisible(visible)
            return
        if visible:
            right_width = self._last_right_panel_width or 320
            remaining = max(1, sizes[1] - right_width)
            self.rightPanel.setVisible(True)
            self.splitter.setSizes([sizes[0], remaining, right_width])
            return
        if sizes[2] > 0:
            self._last_right_panel_width = sizes[2]
        self.splitter.setSizes([sizes[0], sizes[1] + sizes[2], 0])
        self.rightPanel.setVisible(False)

    def delete_selected_shapes(self):
        selected_items = [
            item for item in self.scene.selectedItems()
            if isinstance(item, (RectShape, PolyShape, PointShape, RotatedRectShape))
        ]
        if not selected_items:
            return
        for item in selected_items:
            self.scene.removeItem(item)
        self.scene.state_changed.emit()
        self.update_annotation_panel()
        self.auto_save_annotation()

    def edit_selected_shape_label(self):
        for item in self.scene.selectedItems():
            if hasattr(item, "label"):
                self.edit_shape_label(item)
                break

    def toggle_sam_shortcut(self):
        if self.scene.mode == CanvasMode.POINT:
            DialogOver(self, "点标注模式下不可使用 SAM 提示词提取", "提示", "warning")
            return
        self.samSwitch.setChecked(not self.samSwitch.isChecked())

    def _update_file_grid_metrics(self):
        panel_width = max(1, self.leftPanel.width() or self.listFiles.width())
        columns = max(1, panel_width // 112)
        item_width = max(92, (panel_width - 18) // columns)
        icon_width = max(72, item_width - 14)
        icon_height = max(56, int(icon_width * 0.72))
        icon_size = QSize(icon_width, icon_height)
        if icon_size == self._file_grid_icon_size:
            return
        self._file_grid_icon_size = icon_size
        self.listFiles.setIconSize(icon_size)
        self.listFiles.setGridSize(QSize(item_width, icon_height + 38))

    def _make_color_icon(self, color_value):
        pixmap = QPixmap(12, 12)
        pixmap.fill(Qt.transparent)
        color = QColor(color_value)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing, False)
        painter.setPen(QPen(QColor(90, 90, 90)))
        painter.setBrush(QBrush(color))
        painter.drawRect(1, 1, 10, 10)
        painter.end()
        return QIcon(pixmap)

    def _make_file_thumbnail_icon(self, image_path):
        source = QPixmap(image_path)
        if source.isNull():
            return QIcon()
        target_size = self.listFiles.iconSize()
        thumb = QPixmap(target_size)
        thumb.fill(Qt.transparent)
        scaled = source.scaled(
            target_size,
            Qt.KeepAspectRatioByExpanding,
            Qt.SmoothTransformation
        )
        x = max(0, (scaled.width() - target_size.width()) // 2)
        y = max(0, (scaled.height() - target_size.height()) // 2)
        cropped = scaled.copy(x, y, target_size.width(), target_size.height())
        painter = QPainter(thumb)
        painter.drawPixmap(0, 0, cropped)
        painter.end()
        return QIcon(thumb)

    def has_annotation_for_image(self, image_path):
        base_path = os.path.splitext(image_path)[0]
        return any(os.path.exists(base_path + ext) for ext in (".json", ".txt", ".xml"))

    def annotation_paths_for_image(self, image_path):
        base_path = os.path.splitext(image_path)[0]
        return [base_path + ext for ext in (".json", ".txt", ".xml") if os.path.exists(base_path + ext)]

    def load_class_visibility(self, dir_path):
        self.class_visibility.clear()
        visibility_file = os.path.join(dir_path, "class_visibility.json")
        if os.path.exists(visibility_file):
            try:
                with open(visibility_file, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                if isinstance(loaded, dict):
                    self.class_visibility.update({k: bool(v) for k, v in loaded.items()})
            except Exception:
                pass

    def save_class_visibility(self):
        if not self.current_dir:
            return
        visibility_file = os.path.join(self.current_dir, "class_visibility.json")
        with open(visibility_file, "w", encoding="utf-8") as f:
            json.dump(self.class_visibility, f, ensure_ascii=False, indent=2)

    def is_label_visible(self, label):
        return self.class_visibility.get(label, True)

    def apply_label_visibility(self, label):
        visible = self.is_label_visible(label)
        changed = False
        for shape in self.scene.items():
            if isinstance(shape, (RectShape, PolyShape, PointShape, RotatedRectShape)):
                if getattr(shape, "label", "") == label:
                    shape.setVisible(visible)
                    if not visible and shape.isSelected():
                        shape.setSelected(False)
                    changed = True
        if changed:
            self.update_annotation_panel()

    def apply_all_label_visibility(self):
        for cls_name in self.class_list:
            self.apply_label_visibility(cls_name)

    def refresh_file_item_status(self, image_path=None):
        target_path = image_path or self.current_image_path
        if not target_path:
            return
        for index in range(self.listFiles.count()):
            item = self.listFiles.item(index)
            if item.data(Qt.UserRole) == target_path:
                file_name = item.data(Qt.UserRole + 1) or os.path.basename(target_path)
                status_text = "已标注" if self.has_annotation_for_image(target_path) else "未标注"
                item.setText(f"{file_name}\n[{status_text}]")
                break

    def add_class_to_list(self, cls_name):
        if cls_name not in self.class_list:
            self.class_list.append(cls_name)
            self.class_colors.setdefault(cls_name, color_for_label(cls_name).name())
            self.class_visibility.setdefault(cls_name, True)
            item = self._create_class_tree_item(cls_name)
            self.listClasses.addTopLevelItem(item)
            self._populate_prompt_alias_children(item, cls_name)
            item.setExpanded(True)
            self._apply_class_item_style(item, cls_name)
            if not self.active_label:
                self.set_active_label(cls_name)

    def _create_class_tree_item(self, cls_name):
        item = QTreeWidgetItem([cls_name])
        item.setFlags(item.flags() | Qt.ItemIsEditable | Qt.ItemIsUserCheckable)
        item.setData(0, Qt.UserRole, cls_name)
        item.setData(0, Qt.UserRole + 1, "class")
        item.setCheckState(0, Qt.Checked if self.is_label_visible(cls_name) else Qt.Unchecked)
        return item

    def _create_prompt_tree_item(self, label, prompt):
        item = QTreeWidgetItem([prompt])
        item.setFlags(item.flags() | Qt.ItemIsEditable)
        item.setData(0, Qt.UserRole, prompt)
        item.setData(0, Qt.UserRole + 1, "prompt")
        item.setData(0, Qt.UserRole + 2, label)
        item.setToolTip(0, f"{label} -> {prompt}")
        return item

    def _populate_prompt_alias_children(self, class_item, cls_name):
        for prompt in self.prompt_aliases_for_label(cls_name):
            class_item.addChild(self._create_prompt_tree_item(cls_name, prompt))

    def _find_class_item(self, cls_name):
        for index in range(self.listClasses.topLevelItemCount()):
            item = self.listClasses.topLevelItem(index)
            if item.data(0, Qt.UserRole) == cls_name:
                return item
        return None

    def _find_prompt_item(self, cls_name, prompt):
        class_item = self._find_class_item(cls_name)
        if class_item is None:
            return None
        for index in range(class_item.childCount()):
            child = class_item.child(index)
            if child.data(0, Qt.UserRole) == prompt:
                return child
        return None

    def _apply_class_item_style(self, item, cls_name):
        color = QColor(self.class_colors.get(cls_name, color_for_label(cls_name).name()))
        item.setIcon(0, self._make_color_icon(color))
        item.setToolTip(0, cls_name)

    def _apply_shape_label_style(self, shape, label):
        setattr(shape, "custom_color", self.class_colors.get(label, color_for_label(label).name()))
        if hasattr(shape, "set_label_style"):
            shape.set_label_style(label)
        shape.setVisible(self.is_label_visible(label))

    def _shape_group_name(self, shape):
        if isinstance(shape, RectShape):
            return "rectangle"
        if isinstance(shape, PolyShape):
            return "polygon"
        if isinstance(shape, PointShape):
            return "point"
        if isinstance(shape, RotatedRectShape):
            return "rbox"
        return None

    def _annotation_group_config(self):
        return {
            "rectangle": (self.rectStatsList, self.rectStatsIndex, CanvasMode.RECT, "矩形标注"),
            "polygon": (self.polyStatsList, self.polyStatsIndex, CanvasMode.POLY, "多边形标注"),
            "point": (self.pointStatsList, self.pointStatsIndex, CanvasMode.POINT, "点标注"),
            "rbox": (self.rboxStatsList, self.rboxStatsIndex, CanvasMode.RBOX, "旋转框标注"),
        }

    def annotation_list_widgets(self):
        return [self.rectStatsList, self.polyStatsList, self.pointStatsList, self.rboxStatsList]

    def _render_annotation_group(self, widget, shapes):
        widget.blockSignals(True)
        try:
            widget.clear()
            visible_shapes = [shape for shape in shapes if self.is_label_visible(getattr(shape, "label", "").strip())]
            if not visible_shapes:
                empty_item = QListWidgetItem("暂无")
                empty_item.setFlags(empty_item.flags() & ~Qt.ItemIsSelectable)
                widget.addItem(empty_item)
                return

            for index, shape in enumerate(visible_shapes, 1):
                label = getattr(shape, "label", "").strip() or "未命名"
                item = QListWidgetItem(f"{index}. {label}")
                item.setData(Qt.UserRole, shape)
                color = QColor(self.class_colors.get(label, color_for_label(label).name()))
                item.setIcon(self._make_color_icon(color))
                item.setToolTip(label)
                widget.addItem(item)
                self.shape_to_item[id(shape)] = (widget, item)
        finally:
            widget.blockSignals(False)

    def _set_status(self, text, color=None):
        self.helpLabel.setText(text)
        self.helpLabel.setStyleSheet("")

    def _connect_system_theme_signal(self):
        app = QApplication.instance()
        try:
            app.styleHints().colorSchemeChanged.connect(self.on_system_color_scheme_changed)
        except Exception:
            pass

    def on_system_color_scheme_changed(self, *_args):
        if self.current_theme == "system":
            self.apply_theme("system", persist=False)

    def _build_dark_palette(self):
        palette = QPalette(self._default_palette)
        role_colors = {
            QPalette.Window: QColor(17, 24, 39),
            QPalette.WindowText: QColor(229, 231, 235),
            QPalette.Base: QColor(15, 23, 42),
            QPalette.AlternateBase: QColor(22, 32, 51),
            QPalette.ToolTipBase: QColor(15, 23, 42),
            QPalette.ToolTipText: QColor(248, 250, 252),
            QPalette.Text: QColor(248, 250, 252),
            QPalette.Button: QColor(23, 32, 51),
            QPalette.ButtonText: QColor(248, 250, 252),
            QPalette.BrightText: QColor(255, 85, 85),
            QPalette.Link: QColor(22, 163, 74),
            QPalette.Highlight: QColor(22, 163, 74),
            QPalette.HighlightedText: QColor(255, 255, 255),
            QPalette.PlaceholderText: QColor(148, 163, 184),
        }
        for group in (QPalette.Active, QPalette.Inactive, QPalette.Disabled):
            for role, color in role_colors.items():
                if group == QPalette.Disabled and role in (QPalette.Text, QPalette.ButtonText, QPalette.WindowText):
                    palette.setColor(group, role, QColor(140, 140, 140))
                else:
                    palette.setColor(group, role, color)
        return palette

    def _build_light_palette(self):
        palette = QPalette(self._default_palette)
        role_colors = {
            QPalette.Window: QColor(238, 242, 247),
            QPalette.WindowText: QColor(15, 23, 42),
            QPalette.Base: QColor(255, 255, 255),
            QPalette.AlternateBase: QColor(248, 250, 252),
            QPalette.ToolTipBase: QColor(255, 255, 255),
            QPalette.ToolTipText: QColor(15, 23, 42),
            QPalette.Text: QColor(15, 23, 42),
            QPalette.Button: QColor(255, 255, 255),
            QPalette.ButtonText: QColor(15, 23, 42),
            QPalette.BrightText: QColor(220, 38, 38),
            QPalette.Link: QColor(21, 128, 61),
            QPalette.Highlight: QColor(34, 197, 94),
            QPalette.HighlightedText: QColor(255, 255, 255),
            QPalette.PlaceholderText: QColor(100, 116, 139),
        }
        for group in (QPalette.Active, QPalette.Inactive, QPalette.Disabled):
            for role, color in role_colors.items():
                if group == QPalette.Disabled and role in (QPalette.Text, QPalette.ButtonText, QPalette.WindowText):
                    palette.setColor(group, role, QColor(148, 163, 184))
                else:
                    palette.setColor(group, role, color)
        return palette

    def _load_theme_stylesheet(self, resolved_theme):
        filename = "style.qss" if resolved_theme == "dark" else "style_light.qss"
        qss_path = os.path.join(BASE_DIR, "ui", filename)
        try:
            with open(qss_path, "r", encoding="utf-8") as f:
                return f.read()
        except OSError:
            return ""

    def _resolved_system_theme(self):
        app = QApplication.instance()
        try:
            scheme = app.styleHints().colorScheme()
            return "dark" if scheme == Qt.ColorScheme.Dark else "light"
        except Exception:
            return "light"

    def apply_theme(self, theme_key, persist=True):
        self.current_theme = theme_key
        app = QApplication.instance()
        resolved = self._resolved_system_theme() if theme_key == "system" else theme_key
        if resolved == "dark":
            app.setPalette(self._build_dark_palette())
            app.setStyleSheet(self._load_theme_stylesheet("dark"))
        else:
            app.setPalette(self._build_light_palette())
            app.setStyleSheet(self._load_theme_stylesheet("light"))
        self.themeWidget.set_theme(theme_key)
        if hasattr(self, "dataset_window") and self.dataset_window is not None:
            self.dataset_window.apply_theme(resolved)
        if persist:
            self.settings.setValue("theme", theme_key)

    def update_active_label_indicator(self):
        if self.active_label:
            self.activeLabelIndicator.setText(f"当前标签: {self.active_label}")
            if hasattr(self, "activeLabelHeader"):
                self.activeLabelHeader.setText(f"当前标签  {self.active_label}")
        else:
            self.activeLabelIndicator.setText("当前标签: 未选择")
            if hasattr(self, "activeLabelHeader"):
                self.activeLabelHeader.setText("当前标签  未选择")
        self.activeLabelIndicator.setStyleSheet("")

    def set_active_label(self, label, persist=True):
        normalized = (label or "").strip()
        self.active_label = normalized if normalized in self.class_list else normalized
        self.update_active_label_indicator()
        if persist:
            self.settings.setValue("active_label", self.active_label)
        found = False
        for index in range(self.listClasses.topLevelItemCount()):
            item = self.listClasses.topLevelItem(index)
            if item.data(0, Qt.UserRole) == self.active_label:
                self.listClasses.blockSignals(True)
                self.listClasses.setCurrentItem(item)
                self.listClasses.blockSignals(False)
                found = True
                break
        if not found:
            self.listClasses.blockSignals(True)
            self.listClasses.clearSelection()
            self.listClasses.setCurrentItem(None)
            self.listClasses.blockSignals(False)
        self.refresh_prompt_combo()

    def ensure_active_label(self):
        if self.active_label in self.class_list:
            return self.active_label
        if self.class_list:
            self.set_active_label(self.class_list[0])
            return self.active_label
        text, ok = QInputDialog.getText(self, "新建类别", "请先创建一个标签：")
        text = text.strip() if ok and text else ""
        if not text:
            return ""
        self.add_class_to_list(text)
        self.save_classes()
        self.set_active_label(text)
        return text

    def prompt_aliases_for_label(self, label):
        aliases = []
        for prompt in self.prompt_aliases.get(label, []):
            prompt = str(prompt).strip()
            if prompt and prompt not in aliases:
                aliases.append(prompt)
        if not aliases and label:
            aliases.append(label)
        return aliases

    def refresh_prompt_combo(self):
        current_text = self.samPromptInput.currentText().strip()
        aliases = self.prompt_aliases_for_label(self.active_label)
        self.samPromptInput.blockSignals(True)
        try:
            self.samPromptInput.clear()
            self.samPromptInput.addItems(aliases)
            if current_text and current_text in aliases:
                self.samPromptInput.setEditText(current_text)
            elif aliases:
                self.samPromptInput.setEditText(aliases[0])
            else:
                self.samPromptInput.setEditText("")
        finally:
            self.samPromptInput.blockSignals(False)

    def add_prompt_alias(self, label, prompt):
        label = (label or "").strip()
        prompt = (prompt or "").strip()
        if not label or not prompt:
            return False
        aliases = self.prompt_aliases.setdefault(label, [])
        seeded_default = False
        if not aliases and prompt != label:
            aliases.append(label)
            seeded_default = True
        if prompt in aliases:
            return False
        aliases.append(prompt)
        class_item = self._find_class_item(label)
        if class_item is not None:
            if seeded_default and self._find_prompt_item(label, label) is None:
                class_item.addChild(self._create_prompt_tree_item(label, label))
            if self._find_prompt_item(label, prompt) is None:
                class_item.addChild(self._create_prompt_tree_item(label, prompt))
            class_item.setExpanded(True)
        self.save_prompt_aliases()
        self.refresh_prompt_combo()
        return True

    def remove_prompt_alias(self, label, prompt):
        aliases = self.prompt_aliases.get(label, [])
        if prompt in aliases:
            aliases.remove(prompt)
            if not aliases:
                self.prompt_aliases.pop(label, None)
            self.save_prompt_aliases()
        prompt_item = self._find_prompt_item(label, prompt)
        if prompt_item is not None and prompt_item.parent() is not None:
            prompt_item.parent().removeChild(prompt_item)
        self.refresh_prompt_combo()

    def prompt_label_selection(self, current_label=""):
        dialog = LabelSelectDialog(self.class_list, current_label=current_label, parent=self)
        if dialog.exec() == QDialog.Accepted and dialog.selected_label:
            return dialog.selected_label.strip(), True
        return "", False

    def _focus_shape_in_view(self, shape):
        self.view.centerOn(shape.sceneBoundingRect().center())
        self.view.ensureVisible(shape.sceneBoundingRect(), 80, 80)
        self.view.setFocus()

    def _select_shape_on_canvas(self, shape, focus_view=False):
        for selected in self.scene.selectedItems():
            if selected is not shape:
                selected.setSelected(False)
        shape.setSelected(True)
        if focus_view:
            self._focus_shape_in_view(shape)

    def _select_shapes_on_canvas(self, shapes, focus_view=False):
        target_ids = {id(shape) for shape in shapes}
        for selected in self.scene.selectedItems():
            if id(selected) not in target_ids:
                selected.setSelected(False)
        for shape in shapes:
            shape.setSelected(True)
        if focus_view and shapes:
            self._focus_shape_in_view(shapes[0])

    def delete_shape(self, shape):
        if shape is None:
            return
        self.scene.removeItem(shape)
        self.update_annotation_panel()
        self.auto_save_annotation()
        self.push_state()

    def delete_shapes(self, shapes):
        valid_shapes = [
            shape for shape in shapes
            if isinstance(shape, (RectShape, PolyShape, PointShape, RotatedRectShape)) and shape.scene() is self.scene
        ]
        if not valid_shapes:
            return
        for shape in valid_shapes:
            self.scene.removeItem(shape)
        self.scene.state_changed.emit()
        self.update_annotation_panel()
        self.auto_save_annotation()
        self.push_state()

    def edit_annotation_item(self, item, widget):
        shape = item.data(Qt.UserRole) if item else None
        if shape is not None:
            self._select_shape_on_canvas(shape, focus_view=True)
            self.edit_shape_label(shape)

    def show_canvas_label_menu(self, pos):
        menu = QMenu(self)
        for index, cls_name in enumerate(self.class_list[:9], 1):
            action = menu.addAction(f"{index}. {cls_name}")
            action.setData(cls_name)
            if cls_name == self.active_label:
                font = action.font()
                font.setBold(True)
                action.setFont(font)
        if self.class_list:
            menu.addSeparator()
        create_action = menu.addAction("新建标签")
        chosen = menu.exec(self.view.mapToGlobal(pos))
        if not chosen:
            return
        if chosen == create_action:
            text, ok = QInputDialog.getText(self, "新建类别", "输入类别名称：")
            text = text.strip() if ok and text else ""
            if not text:
                return
            if text not in self.class_list:
                self.add_class_to_list(text)
                self.save_classes()
            self.set_active_label(text)
            return
        cls_name = chosen.data()
        if cls_name:
            self.set_active_label(cls_name)

    def show_annotation_context_menu(self, widget, pos):
        item = widget.itemAt(pos)
        if not item or item.data(Qt.UserRole) is None:
            return
        if not item.isSelected():
            widget.clearSelection()
            widget.setCurrentItem(item)
            item.setSelected(True)
        selected_shapes = [
            selected.data(Qt.UserRole)
            for selected in widget.selectedItems()
            if selected.data(Qt.UserRole) is not None
        ]
        self._select_shapes_on_canvas(selected_shapes, focus_view=True)
        menu = QMenu(self)
        edit_action = menu.addAction("修改标签")
        edit_action.setEnabled(len(selected_shapes) == 1)
        delete_action = menu.addAction(f"删除 {len(selected_shapes)} 个标注")
        action = menu.exec(widget.mapToGlobal(pos))
        if action == edit_action and selected_shapes:
            self.edit_shape_label(selected_shapes[0])
        elif action == delete_action:
            self.delete_shapes(selected_shapes)
        return
        widget.setCurrentItem(item)
        shape = item.data(Qt.UserRole)
        self._select_shape_on_canvas(shape, focus_view=True)
        menu = QMenu(self)
        edit_action = menu.addAction("修改标签")
        delete_action = menu.addAction("删除标注")
        action = menu.exec(widget.mapToGlobal(pos))
        if action == edit_action:
            self.edit_shape_label(shape)
        elif action == delete_action:
            self.delete_shape(shape)

    def show_file_list_context_menu(self, pos):
        item = self.listFiles.itemAt(pos)
        if not item:
            return
        self.listFiles.setCurrentItem(item)
        image_path = item.data(Qt.UserRole)
        file_name = item.data(Qt.UserRole + 1) or os.path.basename(image_path)

        menu = QMenu(self)
        copy_action = menu.addAction("复制文件名")
        delete_action = menu.addAction("删除图片")
        action = menu.exec(self.listFiles.mapToGlobal(pos))

        if action == copy_action:
            QApplication.clipboard().setText(file_name)
            DialogOver(self, f"已复制文件名：{file_name}", "复制成功", "success")
        elif action == delete_action:
            self.delete_image_item(item)

    def delete_image_item(self, item):
        image_path = item.data(Qt.UserRole)
        file_name = item.data(Qt.UserRole + 1) or os.path.basename(image_path)
        annotation_paths = self.annotation_paths_for_image(image_path)
        extra_text = "\n将同时删除同名标注文件。" if annotation_paths else ""
        reply = QMessageBox.question(
            self,
            "确认删除",
            f"确定删除图片“{file_name}”吗？{extra_text}",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        try:
            if self.current_image_path == image_path:
                self.auto_save_annotation()
            if os.path.exists(image_path):
                os.remove(image_path)
            for path in annotation_paths:
                if os.path.exists(path):
                    os.remove(path)
        except Exception as e:
            DialogOver(self, f"删除失败: {e}", "操作失败", "danger")
            return

        current_row = self.listFiles.row(item)
        self.listFiles.takeItem(current_row)
        if self.listFiles.count() > 0:
            self.listFiles.setCurrentRow(min(current_row, self.listFiles.count() - 1))
        else:
            self.current_image_path = None
            self.scene.clear_shapes()
            if self.scene.img_item:
                self.scene.removeItem(self.scene.img_item)
                self.scene.img_item = None
            self.update_annotation_panel()
        DialogOver(self, f"已删除图片：{file_name}", "删除成功", "success")

    def update_annotation_panel(self):
        previous_sync_state = self.annotation_item_syncing
        self.annotation_item_syncing = True
        try:
            self.shape_to_item = {}
            grouped_shapes = {key: [] for key in self._annotation_group_config()}
            for shape in reversed(self.scene.items()):
                group = self._shape_group_name(shape)
                if group:
                    grouped_shapes[group].append(shape)

            for key, (widget, toolbox_index, _mode, title) in self._annotation_group_config().items():
                visible_count = sum(
                    1 for shape in grouped_shapes[key]
                    if self.is_label_visible(getattr(shape, "label", "").strip())
                )
                self.annotationToolBox.setItemText(toolbox_index, f"{title} ({visible_count})")
                self._render_annotation_group(widget, grouped_shapes[key])
        finally:
            self.annotation_item_syncing = previous_sync_state

        self.sync_annotation_selection_from_scene()

    def push_state(self):
        # ??????????
        self.update_annotation_panel()
        if not self.current_image_path: return
        current_state = Exporter.extract_shapes(self.scene)

        # 如果拖了一下鼠标但什么都没变，就不存，节约内存
        if self.undo_stack:
            last_state = self.undo_stack[-1]
            if json.dumps(last_state, sort_keys=True) == json.dumps(current_state, sort_keys=True):
                return

        self.undo_stack.append(current_state)
        # 限制最大步数
        if len(self.undo_stack) > self.max_history_steps:
            self.undo_stack.pop(0)

        # 一旦有新操作，重做（前进）堆栈必须清空
        self.redo_stack.clear()

    def undo(self):
        """撤销 (Ctrl+Z)"""
        if len(self.undo_stack) > 1:
            # 把现在的状态拿出来，放到重做栈里去
            current_state = self.undo_stack.pop()
            self.redo_stack.append(current_state)
            # 获取上一步的状态并还原
            previous_state = self.undo_stack[-1]
            self.restore_state(previous_state)

    def redo(self):
        """重做/前进 (Ctrl+Y 或 Ctrl+Shift+Z)"""
        if self.redo_stack:
            # 从重做栈里拿出来，塞回撤销栈
            next_state = self.redo_stack.pop()
            self.undo_stack.append(next_state)
            # 还原该状态
            self.restore_state(next_state)

    def restore_state(self, state):
        """根据快照数据，完全重建画板元素"""
        self.scene.clear_shapes()
        for shape_data in state:
            label = shape_data.get("label", "")
            shape_type = shape_data.get("type", "")
            points = shape_data.get("points", [])

            # 同步类别列表
            if label and label not in self.class_list:
                # self.class_list.append(label)
                # self.listClasses.addItem(label)
                self.add_class_to_list(label)
                self.save_classes()

            shape = None
            if shape_type == "rectangle" and len(points) == 2:
                rect = QRectF(points[0][0], points[0][1], points[1][0] - points[0][0], points[1][1] - points[0][1])
                shape = RectShape(rect, label)
            elif shape_type == "polygon" and len(points) >= 3:
                qpoints = [QPointF(p[0], p[1]) for p in points]
                shape = PolyShape(QPolygonF(qpoints), label)
            elif shape_type == "point" and len(points) == 1:
                shape = PointShape(QPointF(points[0][0], points[0][1]), label)
            elif shape_type == "obb":
                rect_data = shape_data.get("rect")
                angle = shape_data.get("angle", 0)
                if rect_data and len(rect_data) == 4:
                    cx, cy, w, h = rect_data[0], rect_data[1], rect_data[2], rect_data[3]
                    shape = RotatedRectShape(cx, cy, w, h, angle, label)

            if shape:
                self.scene.addItem(shape)
                self._apply_shape_label_style(shape, label)
                if hasattr(shape, 'update_label_text'):
                    shape.update_label_text(label)
                if hasattr(shape, 'update_label_position'):
                    shape.update_label_position(shape)
                if hasattr(shape, 'update_label_visibility'):
                    shape.update_label_visibility(shape, is_selected=False, is_hovered=False)

        self.update_annotation_panel()
        self.auto_save_annotation()

    def open_dataset_tool(self):
        try:
            if not hasattr(self, 'dataset_window') or self.dataset_window is None:
                resolved = self._resolved_system_theme() if self.current_theme == "system" else self.current_theme
                self.dataset_window = DatasetToolWindow(resolved)
            # 显示窗口
            self.dataset_window.show()
            # 把窗口强制拉到最前面
            self.dataset_window.raise_()
            self.dataset_window.activateWindow()

        except Exception as e:
            DialogOver(self, f"启动失败: {e}", "系统错误", "danger")

    def trigger_sam_prompt(self):
        if self.scene.mode == CanvasMode.POINT:
            DialogOver(self, "点标注模式下不可使用 SAM 提示词提取", "提示", "warning")
            return

        label = self.ensure_active_label()
        if not label:
            DialogOver(self, "请先选择或创建一个标签", "提示", "warning")
            return

        prompt = self.samPromptInput.currentText().strip()
        if prompt:
            self.pending_prompt_targets[prompt] = label
            self.samSwitch.setChecked(True)
            self._set_status(f"正在用提示词“{prompt}”检索，结果将标注为“{label}”...", "orange")
            self.sam_client.request_text_inference(prompt)

    def _shape_scene_rect(self, shape):
        if isinstance(shape, RotatedRectShape):
            return shape.mapToScene(shape.boundingRect()).boundingRect()
        return shape.sceneBoundingRect()

    def _iou_xyxy(self, box_a, box_b):
        ax1, ay1, ax2, ay2 = box_a
        bx1, by1, bx2, by2 = box_b
        inter_x1 = max(ax1, bx1)
        inter_y1 = max(ay1, by1)
        inter_x2 = min(ax2, bx2)
        inter_y2 = min(ay2, by2)
        if inter_x2 <= inter_x1 or inter_y2 <= inter_y1:
            return 0.0
        inter = (inter_x2 - inter_x1) * (inter_y2 - inter_y1)
        area_a = max(1, (ax2 - ax1) * (ay2 - ay1))
        area_b = max(1, (bx2 - bx1) * (by2 - by1))
        return inter / float(area_a + area_b - inter)

    def _box_area_xyxy(self, box):
        x1, y1, x2, y2 = box
        return max(1, x2 - x1) * max(1, y2 - y1)

    def trigger_reference_search(self):
        import cv2
        import numpy as np

        if not self.current_image_path or not self.scene.img_item:
            DialogOver(self, "请先打开图片", "提示", "warning")
            return

        selected_shapes = [
            item for item in self.scene.selectedItems()
            if isinstance(item, (RectShape, PolyShape, PointShape, RotatedRectShape))
        ]
        if len(selected_shapes) != 1:
            DialogOver(self, "请先选中一个目标作为参考样本", "提示", "warning")
            return

        ref_shape = selected_shapes[0]
        ref_rect = self._shape_scene_rect(ref_shape).normalized()
        x1 = max(0, int(ref_rect.left()))
        y1 = max(0, int(ref_rect.top()))
        x2 = int(ref_rect.right())
        y2 = int(ref_rect.bottom())
        if x2 - x1 < 8 or y2 - y1 < 8:
            DialogOver(self, "参考目标太小，无法稳定查找", "提示", "warning")
            return

        image = cv2.imread(self.current_image_path)
        if image is None:
            DialogOver(self, "读取当前图片失败", "系统错误", "danger")
            return

        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        template = gray[y1:y2, x1:x2]
        if template.size == 0:
            DialogOver(self, "参考区域无效", "提示", "warning")
            return

        label = self.ensure_active_label()
        if not label:
            DialogOver(self, "请先选择或创建一个标签", "提示", "warning")
            return

        self._set_status("正在按参考目标查找相似目标...")
        QApplication.processEvents()

        original_box = (x1, y1, x2, y2)
        candidates = []
        scales = [0.8, 0.9, 1.0, 1.1, 1.2]
        for scale in scales:
            width = max(8, int(template.shape[1] * scale))
            height = max(8, int(template.shape[0] * scale))
            resized = cv2.resize(template, (width, height), interpolation=cv2.INTER_LINEAR)
            if resized.shape[0] >= gray.shape[0] or resized.shape[1] >= gray.shape[1]:
                continue
            result = cv2.matchTemplate(gray, resized, cv2.TM_CCOEFF_NORMED)
            ys, xs = np.where(result >= 0.58)
            for py, px in zip(ys, xs):
                score = float(result[py, px])
                box = (int(px), int(py), int(px + resized.shape[1]), int(py + resized.shape[0]))
                if self._iou_xyxy(box, original_box) > 0.6:
                    continue
                candidates.append((score, box))

        candidates.sort(key=lambda item: (self._box_area_xyxy(item[1]), -item[0]))
        deduped = []
        for score, box in candidates:
            replaced = False
            for index, (existing_score, existing_box) in enumerate(deduped):
                if self._iou_xyxy(box, existing_box) > 0.45:
                    if self._box_area_xyxy(box) < self._box_area_xyxy(existing_box):
                        deduped[index] = (score, box)
                    replaced = True
                    break
            if replaced:
                continue
            deduped.append((score, box))
            if len(deduped) >= 20:
                break

        existing_same_label_shapes = [
            shape for shape in self.scene.items()
            if isinstance(shape, (RectShape, PolyShape, PointShape, RotatedRectShape))
            and getattr(shape, "label", "").strip() == label
        ]

        added = 0
        for score, box in deduped:
            should_add = True
            new_area = self._box_area_xyxy(box)
            overlapping_shapes_to_remove = []
            for shape in existing_same_label_shapes:
                existing_rect = self._shape_scene_rect(shape).normalized()
                existing_box = (
                    int(existing_rect.left()),
                    int(existing_rect.top()),
                    int(existing_rect.right()),
                    int(existing_rect.bottom()),
                )
                if self._iou_xyxy(box, existing_box) > 0.45:
                    existing_area = self._box_area_xyxy(existing_box)
                    if new_area < existing_area:
                        overlapping_shapes_to_remove.append(shape)
                    else:
                        should_add = False
                    break

            if not should_add:
                continue

            for shape in overlapping_shapes_to_remove:
                if shape in existing_same_label_shapes:
                    existing_same_label_shapes.remove(shape)
                self.scene.removeItem(shape)

            left, top, right, bottom = box
            rect = QRectF(left, top, right - left, bottom - top)
            shape = RectShape(rect, label)
            self.scene.addItem(shape)
            self._apply_shape_label_style(shape, label)
            if hasattr(shape, 'update_label_text'):
                shape.update_label_text(label)
            if hasattr(shape, 'update_label_position'):
                shape.update_label_position(shape)
            if hasattr(shape, 'update_label_visibility'):
                shape.update_label_visibility(shape, is_selected=False, is_hovered=False)
            existing_same_label_shapes.append(shape)
            added += 1

        if added == 0:
            self._set_status("未找到足够相似的目标")
            DialogOver(self, "未找到足够相似的目标，可换一个更标准的参考样本", "提示", "warning")
            return

        self.update_annotation_panel()
        self.auto_save_annotation()
        self.push_state()
        self._set_status(f"参考查找完成，新增 {added} 个相似目标")

    def handle_text_results(self, results, prompt_text):
        target_label = self.pending_prompt_targets.pop(prompt_text, self.active_label)
        if target_label not in self.class_list:
            self._set_status(f"提示词“{prompt_text}”已有结果，但没有可用的目标标签", "red")
            DialogOver(self, "请先选择或创建一个标签，再使用提示词检索", "提示", "warning")
            return

        if not results:
            self._set_status(f"提取完成：未发现与“{prompt_text}”相关的目标", "red")
            return

        self._set_status(f"提取完成：用提示词“{prompt_text}”找到 {len(results)} 个目标，已标注为“{target_label}”", "green")
        self.add_prompt_alias(target_label, prompt_text)

        for res in results:
            if self.scene.mode == CanvasMode.RECT:
                x, y, w, h = res["rect"]
                shape = RectShape(QRectF(x, y, w, h), target_label)
            else:
                qpts = [QPointF(p[0], p[1]) for p in res["poly_pts"]]
                shape = PolyShape(QPolygonF(qpts), target_label)

            self.scene.addItem(shape)
            self._apply_shape_label_style(shape, target_label)
            if hasattr(shape, 'update_label_text'):
                shape.update_label_text(target_label)
            if hasattr(shape, 'update_label_position'):
                shape.update_label_position(shape)
            if hasattr(shape, 'update_label_visibility'):
                shape.update_label_visibility(shape, is_selected=False, is_hovered=False)

        self.update_annotation_panel()
        self.auto_save_annotation()
        self.push_state()

    def show_help_dialog(self):
        help_text = (
            "快捷键：\n"
            "A / D：上一张 / 下一张\n"
            "Ctrl + S：保存标注\n"
            "Ctrl + Z / Ctrl + Y：撤销 / 重做\n"
            "1 - 9：切换当前标签\n"
            "Q：切换 SAM\n"
            "R / P / T / O：矩形 / 多边形 / 点 / 旋转框\n"
            "E：修改当前标注标签\n"
            "Delete：删除当前标注\n"
            "F1：打开帮助\n\n"
            "标签选择：\n"
            "先在右侧选择当前标签，后续新标注直接使用该标签\n"
            "也可在画布上右键切换当前标签\n\n"
            "参考查找：\n"
            "先选中一个目标，再点“参考查找”\n"
            "程序会在当前图片中查找相似目标并直接生成同标签标注"
        )
        QMessageBox.about(self, "LuoHuaLabel 帮助", help_text)

    def update_coordinate_label(self, x, y):
        self.coordLabel.setText(f"坐标: X: {x}, Y: {y}")
    def on_sam_toggled(self, checked):
        self.scene.set_sam_enabled(checked)
        self._update_help_text(self.scene.mode)

    def _set_mode(self, mode):
        self.scene.set_mode(mode)
        mode_name = CanvasMode.get_mode_name(mode)
        self.modeLabel.setText(f"模式: {mode_name}标注")
        self._update_help_text(mode)

        if mode == CanvasMode.RECT:
            self.actionRect.setChecked(True)
        elif mode == CanvasMode.POLY:
            self.actionPoly.setChecked(True)
        elif mode == CanvasMode.POINT:
            self.actionPoint.setChecked(True)
        elif mode == CanvasMode.RBOX:
            self.actionRBox.setChecked(True)

        if mode == CanvasMode.POINT:
            if self.samSwitch.isChecked():
                self.samSwitch.setChecked(False)

            self.samSwitch.setEnabled(False)
            self.samPromptInput.setEnabled(False)
            self.samPromptBtn.setEnabled(False)
            self.samPromptInput.lineEdit().setPlaceholderText("点标注模式下不可使用 SAM")
        else:
            self.samSwitch.setEnabled(True)
            self.samPromptInput.setEnabled(True)
            self.samPromptBtn.setEnabled(True)
            self.samPromptInput.lineEdit().setPlaceholderText("输入或选择提示词提取（如: dog）")

    def _update_help_text(self, mode):
        is_sam = self.samSwitch.isChecked()
        if mode == CanvasMode.RECT:
            if is_sam:
                self.helpLabel.setText("操作: 悬停预览，左键确认矩形")
            else:
                self.helpLabel.setText("操作: 拖动鼠标绘制矩形")
        elif mode == CanvasMode.POLY:
            if is_sam:
                self.helpLabel.setText("操作: 悬停预览，左键确认多边形")
            else:
                self.helpLabel.setText("操作: 点击添加顶点，双击闭合")
        elif mode == CanvasMode.POINT:
            self.helpLabel.setText("操作: 点击添加点标注")
        elif mode == CanvasMode.RBOX:
            self.helpLabel.setText("操作: 拖动绘制旋转框，Z/X/C/V 调整角度")

    def load_classes(self, dir_path):
        self.class_list.clear()
        self.class_colors.clear()
        self.class_visibility.clear()
        self.prompt_aliases.clear()
        self.listClasses.clear()
        self.load_prompt_aliases(dir_path)
        class_file = os.path.join(dir_path, "classes.txt")
        if os.path.exists(class_file):
            with open(class_file, "r", encoding="utf-8") as f:
                for line in f:
                    cls_name = line.strip()
                    if cls_name:
                        self.add_class_to_list(cls_name)
        self.load_class_colors(dir_path)
        self.load_class_visibility(dir_path)
        for index in range(self.listClasses.topLevelItemCount()):
            item = self.listClasses.topLevelItem(index)
            cls_name = item.data(0, Qt.UserRole)
            self._apply_class_item_style(item, cls_name)
            item.setCheckState(0, Qt.Checked if self.is_label_visible(cls_name) else Qt.Unchecked)
        if self.active_label in self.class_list:
            self.set_active_label(self.active_label, persist=False)
        elif self.class_list:
            self.set_active_label(self.class_list[0], persist=False)
        else:
            self.set_active_label("", persist=False)

    def save_classes(self):
        if self.current_dir:
            class_file = os.path.join(self.current_dir, "classes.txt")
            with open(class_file, "w", encoding="utf-8") as f:
                for cls_name in self.class_list:
                    f.write(cls_name + "\n")
            self.save_class_colors()
            self.save_class_visibility()
            self.save_prompt_aliases()

    def load_prompt_aliases(self, dir_path):
        aliases_file = os.path.join(dir_path, "prompt_aliases.json")
        if not os.path.exists(aliases_file):
            return
        try:
            with open(aliases_file, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                cleaned = {}
                for label, prompts in loaded.items():
                    label = str(label).strip()
                    if not label or not isinstance(prompts, list):
                        continue
                    seen = []
                    for prompt in prompts:
                        prompt = str(prompt).strip()
                        if prompt and prompt not in seen:
                            seen.append(prompt)
                    if seen:
                        cleaned[label] = seen
                self.prompt_aliases.update(cleaned)
        except Exception:
            pass

    def save_prompt_aliases(self):
        if not self.current_dir:
            return
        aliases_file = os.path.join(self.current_dir, "prompt_aliases.json")
        cleaned = {}
        for label in self.class_list:
            prompts = []
            for prompt in self.prompt_aliases.get(label, []):
                prompt = str(prompt).strip()
                if prompt and prompt not in prompts:
                    prompts.append(prompt)
            if prompts:
                cleaned[label] = prompts
        with open(aliases_file, "w", encoding="utf-8") as f:
            json.dump(cleaned, f, ensure_ascii=False, indent=2)

    def load_class_colors(self, dir_path):
        color_file = os.path.join(dir_path, "class_colors.json")
        if os.path.exists(color_file):
            try:
                with open(color_file, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                if isinstance(loaded, dict):
                    self.class_colors.update({k: str(v) for k, v in loaded.items()})
            except Exception:
                pass

    def save_class_colors(self):
        if not self.current_dir:
            return
        color_file = os.path.join(self.current_dir, "class_colors.json")
        with open(color_file, "w", encoding="utf-8") as f:
            json.dump(self.class_colors, f, ensure_ascii=False, indent=2)

    def show_class_context_menu(self, pos):
        item = self.listClasses.itemAt(pos)
        menu = QMenu(self)
        new_class_action = menu.addAction("新增标签")
        current_action = add_prompt_action = search_prompt_action = rename_prompt_action = delete_prompt_action = None
        toggle_action = color_action = delete_class_action = None

        kind = item.data(0, Qt.UserRole + 1) if item else ""
        if item is not None:
            menu.addSeparator()
            if kind == "class":
                current_action = menu.addAction("设为当前标签")
                add_prompt_action = menu.addAction("新增该类提示词")
                visible = item.checkState(0) == Qt.Checked
                toggle_action = menu.addAction("隐藏该标签" if visible else "显示该标签")
                color_action = menu.addAction("修改颜色")
                delete_class_action = menu.addAction("删除标签")
            elif kind == "prompt":
                search_prompt_action = menu.addAction("用该提示词检索")
                rename_prompt_action = menu.addAction("重命名提示词")
                delete_prompt_action = menu.addAction("删除提示词")
        action = menu.exec(self.listClasses.mapToGlobal(pos))

        if action == new_class_action:
            self.create_class_from_input()
        elif action == current_action:
            self.set_active_label(item.data(0, Qt.UserRole))
        elif action == add_prompt_action:
            self.create_prompt_alias_for_item(item)
        elif action == toggle_action:
            item.setCheckState(0, Qt.Unchecked if item.checkState(0) == Qt.Checked else Qt.Checked)
        elif action == color_action:
            self.change_class_color(item)
        elif action == delete_class_action:
            self.delete_class_item(item)
        elif action == search_prompt_action:
            self.trigger_prompt_item_search(item)
        elif action == rename_prompt_action:
            self.listClasses.editItem(item, 0)
        elif action == delete_prompt_action:
            self.remove_prompt_alias(item.data(0, Qt.UserRole + 2), item.data(0, Qt.UserRole))

    def on_class_item_selected(self, current, previous):
        if current is None:
            return
        kind = current.data(0, Qt.UserRole + 1)
        if kind == "prompt":
            cls_name = current.data(0, Qt.UserRole + 2)
            prompt = current.data(0, Qt.UserRole)
            if cls_name in self.class_list:
                self.active_label = cls_name
                self.settings.setValue("active_label", self.active_label)
                self.update_active_label_indicator()
                self.refresh_prompt_combo()
                self.samPromptInput.setEditText(prompt)
        else:
            cls_name = current.data(0, Qt.UserRole)
            self.set_active_label(cls_name)

    def on_class_tree_item_double_clicked(self, item, column):
        if item.data(0, Qt.UserRole + 1) == "prompt":
            self.trigger_prompt_item_search(item)

    def create_class_from_input(self):
        text, ok = QInputDialog.getText(self, "新建类别", "输入类别名称：")
        text = text.strip() if ok and text else ""
        if not text:
            return
        if text not in self.class_list:
            self.add_class_to_list(text)
            self.save_classes()
        self.set_active_label(text)

    def delete_class_item(self, item):
        cls_name = item.data(0, Qt.UserRole)
        if cls_name not in self.class_list:
            return

        related_shapes = [
            shape for shape in self.scene.items()
            if isinstance(shape, (RectShape, PolyShape, PointShape, RotatedRectShape))
            and getattr(shape, "label", "") == cls_name
        ]
        extra = ""
        if related_shapes:
            extra = f"\n当前图片中 {len(related_shapes)} 个“{cls_name}”标注也会一起删除。"
        if self.current_format == "yolo":
            extra += "\n注意：删除 YOLO 类会改变后续类别的 class id 顺序。"

        reply = QMessageBox.question(
            self,
            "确认删除标签",
            f"确定删除标签“{cls_name}”吗？{extra}",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        for shape in related_shapes:
            self.scene.removeItem(shape)

        self.class_list.remove(cls_name)
        self.class_colors.pop(cls_name, None)
        self.class_visibility.pop(cls_name, None)
        self.prompt_aliases.pop(cls_name, None)
        self.pending_prompt_targets = {
            prompt: label
            for prompt, label in self.pending_prompt_targets.items()
            if label != cls_name
        }

        parent = item.parent()
        if parent is None:
            index = self.listClasses.indexOfTopLevelItem(item)
            if index >= 0:
                self.listClasses.takeTopLevelItem(index)
        else:
            parent.removeChild(item)

        if self.active_label == cls_name:
            self.set_active_label(self.class_list[0] if self.class_list else "")
        else:
            self.refresh_prompt_combo()

        self.save_classes()
        self.update_annotation_panel()
        self.auto_save_annotation()
        self.push_state()
        DialogOver(self, f"已删除标签“{cls_name}”", "删除成功", "success")

    def create_prompt_alias_for_item(self, item):
        label = item.data(0, Qt.UserRole)
        text, ok = QInputDialog.getText(self, "新增提示词", f"为“{label}”输入提示词：")
        text = text.strip() if ok and text else ""
        if text:
            self.add_prompt_alias(label, text)

    def trigger_prompt_item_search(self, item):
        label = item.data(0, Qt.UserRole + 2)
        prompt = item.data(0, Qt.UserRole)
        if label in self.class_list and prompt:
            self.active_label = label
            self.settings.setValue("active_label", self.active_label)
            self.update_active_label_indicator()
            self.refresh_prompt_combo()
            self.samPromptInput.setEditText(prompt)
            self.trigger_sam_prompt()

    def change_class_color(self, item):
        cls_name = item.data(0, Qt.UserRole)
        initial = QColor(self.class_colors.get(cls_name, color_for_label(cls_name).name()))
        color = QColorDialog.getColor(initial, self, f"选择标签颜色 - {cls_name}")
        if not color.isValid():
            return
        self.class_colors[cls_name] = color.name()
        self._apply_class_item_style(item, cls_name)
        for shape in self.scene.items():
            if getattr(shape, "label", "") == cls_name:
                self._apply_shape_label_style(shape, cls_name)
                if hasattr(shape, "update_label_text"):
                    shape.update_label_text(cls_name)
        self.save_class_colors()
        self.update_annotation_panel()

    def on_annotation_group_changed(self, index):
        group_map = {
            self.rectStatsIndex: CanvasMode.RECT,
            self.polyStatsIndex: CanvasMode.POLY,
            self.pointStatsIndex: CanvasMode.POINT,
            self.rboxStatsIndex: CanvasMode.RBOX,
        }
        mode = group_map.get(index)
        if mode is not None and self.scene.mode != mode:
            self._set_mode(mode)

    def on_annotation_selection_changed(self, widget):
        if self.annotation_item_syncing:
            return
        selected_items = widget.selectedItems()
        shapes = [item.data(Qt.UserRole) for item in selected_items if item.data(Qt.UserRole) is not None]
        if not shapes:
            return
        self.annotation_item_syncing = True
        try:
            self._select_shapes_on_canvas(shapes, focus_view=True)
        finally:
            self.annotation_item_syncing = False

    def sync_annotation_selection_from_scene(self):
        if self.annotation_item_syncing:
            return
        self.annotation_item_syncing = True
        try:
            for widget, _toolbox_index, _mode, _title in self._annotation_group_config().values():
                widget.blockSignals(True)
                widget.clearSelection()
                widget.blockSignals(False)

            items = self.scene.selectedItems()
            if not items:
                return
            first_mapping = None
            for shape in items:
                mapping = self.shape_to_item.get(id(shape))
                if not mapping:
                    continue
                widget, item = mapping
                if first_mapping is None:
                    first_mapping = mapping
                widget.blockSignals(True)
                item.setSelected(True)
                widget.blockSignals(False)
            if first_mapping:
                widget, item = first_mapping
                for key, (group_widget, toolbox_index, _mode, _title) in self._annotation_group_config().items():
                    if group_widget is widget:
                        self.annotationToolBox.setCurrentIndex(toolbox_index)
                        break
                widget.scrollToItem(item)
                widget.setCurrentItem(item)
                widget.setFocus()
        finally:
            self.annotation_item_syncing = False

    def populate_file_list(self, dir_path):
        self.current_dir = dir_path
        self.settings.setValue("last_dir", dir_path)
        self.listFiles.clear()
        self._update_file_grid_metrics()
        self.load_classes(dir_path)
        for f in sorted(os.listdir(dir_path)):
            if f.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp')):
                full_path = os.path.join(dir_path, f)
                annotated = self.has_annotation_for_image(full_path)
                status_text = "已标注" if annotated else "未标注"
                item = QListWidgetItem(f"{f}\n[{status_text}]")
                item.setData(Qt.UserRole, full_path)
                item.setData(Qt.UserRole + 1, f)
                item.setToolTip(full_path)
                icon = self._make_file_thumbnail_icon(full_path)
                if not icon.isNull():
                    item.setIcon(icon)
                item.setTextAlignment(Qt.AlignCenter)
                self.listFiles.addItem(item)
        if self.listFiles.count() > 0:
            self.listFiles.setCurrentRow(0)
        else:
            self.update_annotation_panel()

    def restore_last_session(self):
        last_dir = self.settings.value("last_dir", "", str)
        if last_dir and os.path.isdir(last_dir):
            self.populate_file_list(last_dir)

    def handle_new_shape(self, shape):
        self.scene.addItem(shape)
        QApplication.processEvents()
        cls_name = self.ensure_active_label()
        if not cls_name:
            self.scene.removeItem(shape)
            self.update_annotation_panel()
            return

        shape.label = cls_name
        self._apply_shape_label_style(shape, cls_name)
        if hasattr(shape, 'update_label_text'):
            shape.update_label_text(cls_name)
        if hasattr(shape, 'update_label_position'):
            shape.update_label_position(shape)
        if hasattr(shape, 'update_label_visibility'):
            shape.update_label_visibility(shape, is_selected=True, is_hovered=False)
        self._select_shape_on_canvas(shape)
        self.update_annotation_panel()
        self.push_state()

    def edit_shape_label(self, shape):
        dialog = LabelEditDialog(self.class_list, selected_index=self.last_edit_label_index, parent=self)
        if dialog.exec() != QDialog.Accepted:
            return

        cls_name = dialog.selected_label.strip()
        if not cls_name:
            return

        combo_index = dialog.selected_index()
        if combo_index >= 0:
            self.last_edit_label_index = combo_index
            self.settings.setValue("last_edit_label_index", combo_index)

        if cls_name not in self.class_list:
            self.add_class_to_list(cls_name)
            self.save_classes()
            self.last_edit_label_index = self.class_list.index(cls_name)
            self.settings.setValue("last_edit_label_index", self.last_edit_label_index)

        shape.label = cls_name
        self._apply_shape_label_style(shape, cls_name)
        if hasattr(shape, 'update_label_text'):
            shape.update_label_text(cls_name)

        self.update_annotation_panel()
        self.auto_save_annotation()
        self.push_state()

    def on_list_item_changed(self, item, column=0):
        kind = item.data(0, Qt.UserRole + 1)
        if kind == "prompt":
            self.on_prompt_item_changed(item)
            return

        new_name = item.text(0).strip()
        old_name = item.data(0, Qt.UserRole)

        if old_name:
            visible = item.checkState(0) == Qt.Checked
            if self.class_visibility.get(old_name, True) != visible:
                self.class_visibility[old_name] = visible
                self.save_class_visibility()
                self.apply_label_visibility(old_name)

        if not old_name or new_name == old_name:
            return

        self.listClasses.blockSignals(True)
        try:
            if not new_name:
                DialogOver(self, "标签名称不能为空", "名称错误", "warning")
                item.setText(0, old_name)
                return

            if new_name in self.class_list:
                DialogOver(self, f"标签“{new_name}”已存在", "名称冲突", "warning")
                item.setText(0, old_name)
                return

            idx = self.class_list.index(old_name)
            self.class_list[idx] = new_name
            if self.active_label == old_name:
                self.active_label = new_name
            if old_name in self.class_colors:
                self.class_colors[new_name] = self.class_colors.pop(old_name)
            if old_name in self.class_visibility:
                self.class_visibility[new_name] = self.class_visibility.pop(old_name)
            if old_name in self.prompt_aliases:
                self.prompt_aliases[new_name] = self.prompt_aliases.pop(old_name)
            item.setData(0, Qt.UserRole, new_name)
            for child_index in range(item.childCount()):
                child = item.child(child_index)
                child.setData(0, Qt.UserRole + 2, new_name)
                child.setToolTip(0, f"{new_name} -> {child.data(0, Qt.UserRole)}")
            self._apply_class_item_style(item, new_name)

            changed = False
            for shape in self.scene.items():
                if isinstance(shape, (RectShape, PolyShape, PointShape, RotatedRectShape)):
                    if getattr(shape, 'label', '') == old_name:
                        shape.label = new_name
                        self._apply_shape_label_style(shape, new_name)
                        if hasattr(shape, 'update_label_text'):
                            shape.update_label_text(new_name)
                        changed = True

            self.save_classes()
            if changed:
                self.update_annotation_panel()
                self.auto_save_annotation()
                self.push_state()

            self.set_active_label(self.active_label or new_name)
            DialogOver(self, f"已将所有“{old_name}”批量改为“{new_name}”", "修改成功", "success")
        finally:
            self.listClasses.blockSignals(False)

    def on_prompt_item_changed(self, item):
        new_prompt = item.text(0).strip()
        old_prompt = item.data(0, Qt.UserRole)
        label = item.data(0, Qt.UserRole + 2)
        if not old_prompt or new_prompt == old_prompt:
            return

        self.listClasses.blockSignals(True)
        try:
            if not new_prompt:
                DialogOver(self, "提示词不能为空", "名称错误", "warning")
                item.setText(0, old_prompt)
                return
            aliases = self.prompt_aliases.setdefault(label, [])
            if not aliases:
                aliases.append(old_prompt)
            if new_prompt in aliases and new_prompt != old_prompt:
                DialogOver(self, f"提示词“{new_prompt}”已存在", "名称冲突", "warning")
                item.setText(0, old_prompt)
                return
            if old_prompt in aliases:
                aliases[aliases.index(old_prompt)] = new_prompt
            else:
                aliases.append(new_prompt)
            item.setData(0, Qt.UserRole, new_prompt)
            item.setToolTip(0, f"{label} -> {new_prompt}")
            self.save_prompt_aliases()
            self.refresh_prompt_combo()
        finally:
            self.listClasses.blockSignals(False)

    def open_dir(self):
        start_dir = self.current_dir or self.settings.value("last_dir", "", str)
        dir_path = QFileDialog.getExistingDirectory(self, "选择图片目录", start_dir)
        if dir_path:
            self.populate_file_list(dir_path)

    # def update_model_status(self, success, msg):
    #     self.helpLabel.setText(msg)
    #     if success:
    #         self.helpLabel.setStyleSheet("color: green;")
    #     else:
    #         self.helpLabel.setStyleSheet("color: red;")

    def update_model_status(self, success, msg):
        self._set_status(msg)
        if success and self.current_image_path:
            self._set_status("模型已就绪，正在自动分析当前图片特征...")
            QApplication.processEvents()
            self.sam_client.set_image(self.current_image_path)
            self._set_status("分析完成，可以开始智能标注")

    def on_file_selected(self, current, previous):
        if previous:
            self.auto_save_annotation()

        if current:
            path = current.data(Qt.UserRole) or current.text()
            self.current_image_path = path
            self.scene.load_image(path)
            self.view.fitInView(self.scene.sceneRect(), Qt.KeepAspectRatio)
            self.load_annotations(path)
            self.update_annotation_panel()

            self.undo_stack.clear()
            self.redo_stack.clear()
            self.push_state()

            if self.sam_client.model:
                self._set_status("正在分析图片智能特征...", "orange")
                QApplication.processEvents()
                self.sam_client.set_image(path)
                self._set_status("分析完成，可以开始智能标注", "green")
            else:
                self._set_status("等待后台加载模型，稍后将自动分析图片...", "orange")

    def auto_save_annotation(self):
        if not self.current_image_path or not self.scene.img_item: return
        shapes_data = Exporter.extract_shapes(self.scene)
        # if not shapes_data: return

        img_rect = self.scene.img_item.pixmap().rect()
        base_name = os.path.splitext(self.current_image_path)[0]

        try:
            if self.current_format == "json":
                out_path = base_name + ".json"
                Exporter.save_json(out_path, self.current_image_path, img_rect.width(), img_rect.height(), shapes_data)
            elif self.current_format == "yolo":
                out_path = base_name + ".txt"
                Exporter.save_yolo(out_path, img_rect.width(), img_rect.height(), shapes_data, self.class_list)
            elif self.current_format == "xml":
                out_path = base_name + ".xml"
                Exporter.save_xml(out_path, self.current_image_path, img_rect.width(), img_rect.height(), shapes_data)
            self.refresh_file_item_status(self.current_image_path)
        except Exception as e:
            print(f"自动保存失败: {str(e)}")

    def set_current_format(self, format_type):
        self.current_format = format_type
        self.settings.setValue("last_format", format_type)
        self.formatWidget.set_format(format_type)

        if self.current_image_path:
            self.scene.clear_shapes()
            self.load_annotations(self.current_image_path)
            self.update_annotation_panel()
        DialogOver(self, f"当前读写格式已切换为 {format_type.upper()}", "格式切换", "info")

    def load_annotations(self, image_path):
        if not self.scene.img_item: return

        img_w = self.scene.img_item.pixmap().width()
        img_h = self.scene.img_item.pixmap().height()
        base_path = os.path.splitext(image_path)[0]

        if self.current_format == "json":
            self._load_json(base_path + ".json")
        elif self.current_format == "yolo":
            self._load_yolo(base_path + ".txt", img_w, img_h)
        elif self.current_format == "xml":
            self._load_xml(base_path + ".xml")

    def _add_shape_to_scene(self, shape, label):
        # docstring removed
        if label not in self.class_list:
            # self.class_list.append(label)
            # self.listClasses.addItem(label)
            self.add_class_to_list(label)
            self.save_classes()
        self.scene.addItem(shape)
        self._apply_shape_label_style(shape, label)
        self.update_annotation_panel()

    def _load_json(self, json_path):
        if not os.path.exists(json_path): return
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for shape_data in data.get("shapes", []):
                label = shape_data.get("label", "")
                points = shape_data.get("points", [])
                shape_type = shape_data.get("shape_type", "rectangle")

                if shape_type == "rectangle" and len(points) == 2:
                    rect = QRectF(points[0][0], points[0][1], points[1][0] - points[0][0], points[1][1] - points[0][1])
                    shape = RectShape(rect, label)
                elif shape_type == "polygon" and len(points) >= 3:
                    qpoints = [QPointF(p[0], p[1]) for p in points]
                    shape = PolyShape(QPolygonF(qpoints), label)
                elif shape_type == "point" and len(points) == 1:
                    shape = PointShape(QPointF(points[0][0], points[0][1]), label)
                # 鏃嬭浆妗?(OBB) 鐨勮В鏋愬垎鏀?
                elif shape_type == "obb":
                    rect_data = shape_data.get("rect")
                    angle = shape_data.get("angle", 0)
                    if rect_data and len(rect_data) == 4:
                        cx, cy, w, h = rect_data[0], rect_data[1], rect_data[2], rect_data[3]
                        shape = RotatedRectShape(cx, cy, w, h, angle, label)
                    else:
                        continue
                else:
                    continue
                self._add_shape_to_scene(shape, label)
        except Exception as e:
            print(f"加载 JSON 标注失败: {e}")

    def _load_yolo(self, txt_path, img_w, img_h):
        if not os.path.exists(txt_path): return
        import math
        try:
            with open(txt_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            for line in lines:
                parts = line.strip().split()
                if not parts: continue
                class_id = int(parts[0])
                label = self.class_list[class_id] if class_id < len(self.class_list) else str(class_id)

                # 1. YOLO BBox 鏍煎紡 (甯歌鐭╁舰锛?涓弬鏁?
                if len(parts) == 5:
                    cx, cy = float(parts[1]) * img_w, float(parts[2]) * img_h
                    w, h = float(parts[3]) * img_w, float(parts[4]) * img_h
                    shape = RectShape(QRectF(cx - w / 2, cy - h / 2, w, h), label)

                # YOLO OBB 鏃嬭浆妗嗘牸寮?(9涓弬鏁帮細1 涓被鍒?+ 8 涓潗鏍?
                elif len(parts) == 9:
                    x1, y1 = float(parts[1]) * img_w, float(parts[2]) * img_h
                    x2, y2 = float(parts[3]) * img_w, float(parts[4]) * img_h
                    x3, y3 = float(parts[5]) * img_w, float(parts[6]) * img_h
                    x4, y4 = float(parts[7]) * img_w, float(parts[8]) * img_h

                    # 鍒╃敤鍥涜竟褰㈢殑椤剁偣閫嗗悜鎺ㄥ鍑哄師鐢熷睘鎬?
                    cx = (x1 + x2 + x3 + x4) / 4.0
                    cy = (y1 + y2 + y3 + y4) / 4.0
                    w = math.hypot(x2 - x1, y2 - y1)
                    h = math.hypot(x4 - x1, y4 - y1)
                    angle = math.degrees(math.atan2(y2 - y1, x2 - x1))

                    # 閲嶆柊鐢熸垚甯︽湁瀹岀編鎵嬫焺鐨?OBB 瀵硅薄
                    shape = RotatedRectShape(cx, cy, w, h, angle, label)

                elif len(parts) > 9 and len(parts) % 2 == 1:
                    qpoints = [QPointF(float(parts[i]) * img_w, float(parts[i + 1]) * img_h) for i in
                               range(1, len(parts), 2)]
                    shape = PolyShape(QPolygonF(qpoints), label)
                else:
                    continue

                self._add_shape_to_scene(shape, label)
        except Exception as e:
            print(f"加载 YOLO 标注失败: {e}")

    def _load_xml(self, xml_path):
        import xml.etree.ElementTree as ET
        if not os.path.exists(xml_path): return
        try:
            tree = ET.parse(xml_path)
            root = tree.getroot()
            for obj in root.findall("object"):
                label = obj.find("name").text
                bndbox = obj.find("bndbox")
                if bndbox is not None:
                    xmin, ymin = float(bndbox.find("xmin").text), float(bndbox.find("ymin").text)
                    xmax, ymax = float(bndbox.find("xmax").text), float(bndbox.find("ymax").text)
                    shape = RectShape(QRectF(xmin, ymin, xmax - xmin, ymax - ymin), label)
                    self._add_shape_to_scene(shape, label)
        except Exception as e:
            print(f"加载 XML 标注失败: {e}")

    def save_annotation(self, format_type):
        if not self.current_image_path or not self.scene.img_item:
            QMessageBox.warning(self, "提示", "请先打开图片")
            DialogOver(self, "请先在左侧打开图片", "操作错误", "warning")
            return
        shapes_data = Exporter.extract_shapes(self.scene)
        # if not shapes_data:
        #     DialogOver(self, "当前画布没有标注内容可保存", "为空提示", "warning")
        #     return

        img_rect = self.scene.img_item.pixmap().rect()
        base_name = os.path.splitext(self.current_image_path)[0]

        try:
            if format_type == "json":
                out_path = base_name + ".json"
                Exporter.save_json(out_path, self.current_image_path, img_rect.width(), img_rect.height(), shapes_data)
            elif format_type == "yolo":
                out_path = base_name + ".txt"
                Exporter.save_yolo(out_path, img_rect.width(), img_rect.height(), shapes_data, self.class_list)
            elif format_type == "xml":
                out_path = base_name + ".xml"
                Exporter.save_xml(out_path, self.current_image_path, img_rect.width(), img_rect.height(), shapes_data)

            self.refresh_file_item_status(self.current_image_path)
            DialogOver(self, "标注文件已保存", "保存成功", "success")
            print(f"标注文件已保存到: {out_path}")
        except Exception as e:
            DialogOver(self, f"写入失败: {str(e)}", "保存出错", "danger")

    def closeEvent(self, event):
        self.auto_save_annotation()
        self.sam_client.cleanup()
        super().closeEvent(event)

    def keyPressEvent(self, event):
        super().keyPressEvent(event)
        return
        key = event.key()
        modifiers = event.modifiers()

        if modifiers == Qt.NoModifier and Qt.Key_1 <= key <= Qt.Key_9:
            index = key - Qt.Key_1
            if index < len(self.class_list):
                self.set_active_label(self.class_list[index])
                return

        if key == Qt.Key_Z and modifiers == Qt.ControlModifier:
            # Shift + Ctrl + Z 或者是多边形画点撤回处理
            if modifiers & Qt.ShiftModifier:
                self.redo()
            elif self.scene.mode == CanvasMode.POLY and len(self.scene.poly_pts) > 0:
                pass
            else:
                self.undo()
        elif key == Qt.Key_Y and modifiers == Qt.ControlModifier:
            self.redo()

        if key == Qt.Key_D or key == Qt.Key_Right:
            current_idx = self.listFiles.currentRow()
            if current_idx < self.listFiles.count() - 1:
                self.listFiles.setCurrentRow(current_idx + 1)
        elif key == Qt.Key_A or key == Qt.Key_Left:
            current_idx = self.listFiles.currentRow()
            if current_idx > 0:
                self.listFiles.setCurrentRow(current_idx - 1)
        elif key == Qt.Key_S and modifiers == Qt.ControlModifier:
            self.save_annotation(self.current_format)
        elif key in (Qt.Key_Delete, Qt.Key_Backspace):
            selected_items = [
                item for item in self.scene.selectedItems()
                if isinstance(item, (RectShape, PolyShape, PointShape, RotatedRectShape))
            ]
            if selected_items:
                for item in selected_items:
                    self.scene.removeItem(item)
                self.scene.state_changed.emit()
                self.update_annotation_panel()
                self.auto_save_annotation()
            return
        elif key == Qt.Key_E:
            selected_items = self.scene.selectedItems()
            for item in selected_items:
                if hasattr(item, 'label'):
                    self.edit_shape_label(item)
                    break
        elif key == Qt.Key_Q:
            if self.scene.mode == CanvasMode.POINT:
                DialogOver(self, "点标注模式下不可使用 SAM 提示词提取", "提示", "warning")
            else:
                self.samSwitch.setChecked(not self.samSwitch.isChecked())
        elif key == Qt.Key_F1:
            self.show_help_dialog()
        elif key == Qt.Key_R:
            self.actionRect.trigger()
        elif key == Qt.Key_P:
            self.actionPoly.trigger()
        elif key == Qt.Key_T:
            self.actionPoint.trigger()
        elif key == Qt.Key_O:
            self.actionRBox.trigger()

        super().keyPressEvent(event)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
