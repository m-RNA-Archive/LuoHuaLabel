import sys
import os
import json
import math
import subprocess
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QFileDialog, QInputDialog, QMessageBox, QLabel,
    QListWidgetItem, QColorDialog, QMenu, QDialog, QVBoxLayout, QListWidget,
    QComboBox, QLineEdit, QTextEdit, QPlainTextEdit,
    QPushButton, QHBoxLayout, QTreeWidgetItem, QAbstractSpinBox, QSplashScreen,
    QProgressBar, QStyledItemDelegate, QStyle, QStyleOptionViewItem, QWidget,
    QFrame, QToolButton, QScrollArea, QSizePolicy
)
from PySide6.QtCore import Qt, QPointF, QRectF, QSettings, QSize, QTimer, QEvent, Signal, QItemSelectionModel
from PySide6.QtGui import (
    QPolygonF, QColor, QBrush, QPixmap, QIcon, QPalette, QCursor, QPainter, QPen,
    QShortcut, QKeySequence, QDesktopServices, QFont, QPainterPath,
    QLinearGradient, QTextCharFormat, QTextCursor, QTextFormat
)
from PySide6.QtCore import QUrl

APP_DIR = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))
RESOURCE_DIR = getattr(sys, "_MEIPASS", APP_DIR)
BASE_DIR = APP_DIR
SETTINGS_PATH = os.path.join(BASE_DIR, "PromptLabel.ini")
APP_NAME = "PromptLabel"
DEFAULT_SAM3_PATH = os.path.join(BASE_DIR, "models", "sam3.pt")
SAM3_OFFICIAL_URL = "https://huggingface.co/facebook/sam3/tree/main"
SAM3_SOURCE_URL = "https://github.com/facebookresearch/sam3"
SAM3_BAIDU_URL = "https://pan.baidu.com/s/11rKzO6W5b_i8aOFcd9xOzA?pwd=6666"
SAM3_BAIDU_CODE = "6666"
_STARTUP_APP = None
_STARTUP_SPLASH = None
_STARTUP_ICON = None
APP_UI_FONT_FAMILY = "Microsoft YaHei UI"
APP_ICON_PNG_PATH = os.path.join(RESOURCE_DIR, "assets", "promptlabel_pl.png")
APP_ICON_ICO_PATH = os.path.join(RESOURCE_DIR, "assets", "promptlabel_pl.ico")
_WINDOWS_ICON_HANDLES = []


def _set_windows_app_user_model_id():
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(f"{APP_NAME}.Desktop")
    except Exception:
        pass


def _create_fallback_icon(size=118):
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)

    rect = QRectF(2, 2, size - 4, size - 4)
    gradient = QLinearGradient(rect.topLeft(), rect.bottomRight())
    gradient.setColorAt(0.0, QColor("#f9fbff"))
    gradient.setColorAt(1.0, QColor("#e7f8f5"))

    path = QPainterPath()
    path.addRoundedRect(rect, 22, 22)
    painter.fillPath(path, gradient)
    painter.setPen(QPen(QColor("#96a8f3"), 3))
    painter.drawPath(path)

    painter.setPen(QColor("#6671dc"))
    painter.setFont(QFont("Noto Sans", 42, QFont.DemiBold))
    painter.drawText(rect, Qt.AlignCenter, "PL")
    painter.end()
    return pixmap


def _load_app_icon():
    icon = QIcon()
    if os.path.exists(APP_ICON_ICO_PATH):
        icon = QIcon(APP_ICON_ICO_PATH)
    if icon.isNull() and os.path.exists(APP_ICON_PNG_PATH):
        icon = QIcon(APP_ICON_PNG_PATH)
    if icon.isNull():
        icon = QIcon(_create_fallback_icon())
    return icon


def _apply_windows_window_icon(widget):
    if sys.platform != "win32" or not os.path.exists(APP_ICON_ICO_PATH):
        return
    try:
        import ctypes
        from ctypes import wintypes

        hwnd = int(widget.winId())
        user32 = ctypes.windll.user32
        load_image = user32.LoadImageW
        load_image.argtypes = [
            wintypes.HINSTANCE,
            wintypes.LPCWSTR,
            wintypes.UINT,
            ctypes.c_int,
            ctypes.c_int,
            wintypes.UINT,
        ]
        load_image.restype = wintypes.HANDLE
        user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        user32.SendMessageW.restype = wintypes.LPARAM
        lr_loadfromfile = 0x00000010
        image_icon = 1
        wm_seticon = 0x0080
        icon_small = 0
        icon_big = 1

        small_icon = load_image(None, APP_ICON_ICO_PATH, image_icon, 16, 16, lr_loadfromfile)
        big_icon = load_image(None, APP_ICON_ICO_PATH, image_icon, 32, 32, lr_loadfromfile)
        if small_icon:
            user32.SendMessageW(hwnd, wm_seticon, icon_small, small_icon)
            _WINDOWS_ICON_HANDLES.append(small_icon)
        if big_icon:
            user32.SendMessageW(hwnd, wm_seticon, icon_big, big_icon)
            _WINDOWS_ICON_HANDLES.append(big_icon)
    except Exception:
        pass


def _read_startup_theme_key():
    settings = QSettings(SETTINGS_PATH, QSettings.IniFormat)
    theme_key = settings.value("theme", "dark", str)
    return theme_key if theme_key in ("light", "dark") else "dark"


def _resolved_startup_theme(theme_key):
    return theme_key if theme_key in ("light", "dark") else "dark"


def _create_startup_splash_pixmap(resolved_theme=None):
    resolved_theme = resolved_theme or _resolved_startup_theme(_read_startup_theme_key())
    width, height = 520, 320
    pixmap = QPixmap(width, height)
    pixmap.fill(Qt.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)

    frame = QRectF(8, 8, width - 16, height - 16)
    gradient = QLinearGradient(frame.topLeft(), frame.bottomRight())
    if resolved_theme == "dark":
        gradient.setColorAt(0.0, QColor("#101525"))
        gradient.setColorAt(0.56, QColor("#151b32"))
        gradient.setColorAt(1.0, QColor("#102b2d"))
        border_color = QColor("#3d4772")
        title_color = QColor("#eef2ff")
        hint_color = QColor("#aab5cf")
    else:
        gradient.setColorAt(0.0, QColor("#fbfdff"))
        gradient.setColorAt(0.58, QColor("#f4f8ff"))
        gradient.setColorAt(1.0, QColor("#e4f7f4"))
        border_color = QColor("#c5d0f7")
        title_color = QColor("#4450b8")
        hint_color = QColor("#6b7280")

    frame_path = QPainterPath()
    frame_path.addRoundedRect(frame, 30, 30)
    painter.fillPath(frame_path, gradient)
    painter.setPen(QPen(border_color, 1))
    painter.drawPath(frame_path)

    icon_pixmap = QPixmap(APP_ICON_PNG_PATH) if os.path.exists(APP_ICON_PNG_PATH) else _create_fallback_icon()
    icon_size = 120
    icon_pixmap = icon_pixmap.scaled(icon_size, icon_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    icon_x = (width - icon_pixmap.width()) // 2
    painter.drawPixmap(icon_x, 58, icon_pixmap)

    painter.setPen(title_color)
    painter.setFont(QFont(APP_UI_FONT_FAMILY, 25, QFont.DemiBold))
    painter.drawText(QRectF(0, 190, width, 42), Qt.AlignCenter, APP_NAME)

    painter.setPen(hint_color)
    painter.setFont(QFont(APP_UI_FONT_FAMILY, 12))
    painter.drawText(QRectF(0, 237, width, 28), Qt.AlignCenter, "\u52a0\u8f7d\u4e2d...")
    painter.end()
    return pixmap


def _finish_startup_splash(window=None):
    global _STARTUP_SPLASH
    splash = _STARTUP_SPLASH
    if splash is None:
        return
    try:
        if window is not None:
            splash.finish(window)
        else:
            splash.close()
    except RuntimeError:
        pass
    _STARTUP_SPLASH = None


def _show_startup_splash():
    global _STARTUP_APP, _STARTUP_SPLASH, _STARTUP_ICON

    _set_windows_app_user_model_id()
    _STARTUP_APP = QApplication(sys.argv)
    _STARTUP_APP.setApplicationName(APP_NAME)
    _STARTUP_ICON = _load_app_icon()
    if not _STARTUP_ICON.isNull():
        _STARTUP_APP.setWindowIcon(_STARTUP_ICON)

    resolved_theme = _resolved_startup_theme(_read_startup_theme_key())
    _STARTUP_SPLASH = QSplashScreen(_create_startup_splash_pixmap(resolved_theme))
    if not _STARTUP_ICON.isNull():
        _STARTUP_SPLASH.setWindowIcon(_STARTUP_ICON)
    _STARTUP_SPLASH.setWindowFlag(Qt.WindowStaysOnTopHint, True)
    _apply_windows_window_icon(_STARTUP_SPLASH)
    _STARTUP_SPLASH.show()
    _apply_windows_window_icon(_STARTUP_SPLASH)
    _STARTUP_APP.processEvents()


if __name__ == "__main__":
    _show_startup_splash()


from main_dataset_tool import DatasetToolWindow
from ui.main_window import ToolbarIconSet, Ui_MainWindow
from core.canvas import Canvas, CanvasMode
from core.sam_client import SAMClient
from core.exporter import Exporter
from core.shapes import BaseShape, RectShape, PolyShape, PointShape, RotatedRectShape, color_for_label


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
        self.combo.setFocus(Qt.OtherFocusReason)

    def accept_selection(self):
        self.selected_label = self.combo.currentText().strip()
        if self.selected_label:
            self.accept()

    def selected_index(self):
        return self.combo.currentIndex()

    def showEvent(self, event):
        super().showEvent(event)
        self.combo.setFocus(Qt.OtherFocusReason)
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


class FileQueueItemDelegate(QStyledItemDelegate):
    @staticmethod
    def _is_checked_state(state):
        if state == Qt.Checked:
            return True
        try:
            if state == Qt.CheckState.Checked:
                return True
        except AttributeError:
            pass
        try:
            return int(state) == int(Qt.Checked)
        except (TypeError, ValueError):
            return state == 2

    def _thumbnail_rect(self, option):
        widget = option.widget
        icon_size = widget.iconSize() if widget else option.decorationSize
        icon_width = max(1, icon_size.width())
        icon_height = max(1, icon_size.height())
        x = option.rect.left() + max(0, (option.rect.width() - icon_width) // 2)
        y = option.rect.top() + 6
        return QRectF(x, y, icon_width, icon_height)

    def checkbox_rect(self, option):
        thumb_rect = self._thumbnail_rect(option)
        size = 22
        return QRectF(thumb_rect.left() + 7, thumb_rect.top() + 7, size, size)

    def paint(self, painter, option, index):
        painter.save()
        rect = QRectF(option.rect).adjusted(2, 2, -2, -2)
        checked = self._is_checked_state(index.data(Qt.CheckStateRole))
        selected = bool(option.state & QStyle.State_Selected)
        is_light = option.palette.window().color().lightness() > 128

        if checked or selected:
            bg_color = QColor("#dcfce7") if is_light else QColor("#123524")
            border_color = QColor("#16a34a") if is_light else QColor("#22c55e")
            painter.setRenderHint(QPainter.Antialiasing, True)
            painter.setPen(QPen(border_color, 1.5))
            painter.setBrush(QBrush(bg_color))
            painter.drawRoundedRect(rect, 6, 6)

        thumb_rect = self._thumbnail_rect(option)
        icon = index.data(Qt.DecorationRole)
        if isinstance(icon, QIcon) and not icon.isNull():
            pixmap = icon.pixmap(int(thumb_rect.width()), int(thumb_rect.height()))
            painter.drawPixmap(thumb_rect.toRect(), pixmap)

        check_rect = self.checkbox_rect(option)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(QPen(QColor("#ffffff"), 1.5))
        painter.setBrush(QBrush(QColor(17, 24, 39, 185)))
        painter.drawRoundedRect(check_rect, 4, 4)
        if checked:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(QColor("#16a34a") if is_light else QColor("#22c55e")))
            painter.drawRoundedRect(check_rect.adjusted(2, 2, -2, -2), 3, 3)
            painter.setPen(QPen(QColor("#ffffff") if is_light else QColor("#052e16"), 2.2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            x = check_rect.left()
            y = check_rect.top()
            painter.drawLine(QPointF(x + 6, y + 12), QPointF(x + 10, y + 16))
            painter.drawLine(QPointF(x + 10, y + 16), QPointF(x + 17, y + 7))

        text = index.data(Qt.DisplayRole) or ""
        text_rect = QRectF(
            option.rect.left() + 4,
            thumb_rect.bottom() + 6,
            option.rect.width() - 8,
            option.rect.bottom() - thumb_rect.bottom() - 6,
        )
        if checked or selected:
            painter.setPen(QColor("#052e16") if is_light else QColor("#ffffff"))
        else:
            painter.setPen(option.palette.text().color())
        metrics = painter.fontMetrics()
        line = metrics.elidedText(text, Qt.ElideMiddle, int(text_rect.width()))
        painter.drawText(text_rect, Qt.AlignHCenter | Qt.AlignTop, line)
        painter.restore()

    def sizeHint(self, option, index):
        widget = option.widget
        if widget:
            return widget.gridSize()
        return super().sizeHint(option, index)


class LabelVisibilityItemDelegate(QStyledItemDelegate):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.icons = ToolbarIconSet()

    def paint(self, painter, option, index):
        if index.data(Qt.CheckStateRole) is None:
            super().paint(painter, option, index)
            return

        item_option = QStyleOptionViewItem(option)
        self.initStyleOption(item_option, index)
        widget = option.widget
        style = widget.style() if widget else QApplication.style()
        style.drawPrimitive(QStyle.PE_PanelItemViewItem, item_option, painter, widget)

        check_rect = style.subElementRect(QStyle.SE_ItemViewItemCheckIndicator, item_option, widget)
        content_option = QStyleOptionViewItem(item_option)
        content_option.features &= ~QStyleOptionViewItem.HasCheckIndicator
        content_option.rect.setLeft(check_rect.right() + 7)
        style.drawControl(QStyle.CE_ItemViewItem, content_option, painter, widget)

        visible = item_option.checkState == Qt.Checked
        color = item_option.palette.text().color()
        pixmap = self.icons.pixmap("visible" if visible else "invisible", 22, color)
        icon_rect = QRectF(
            check_rect.center().x() - 11,
            check_rect.center().y() - 11,
            22,
            22,
        )
        painter.drawPixmap(icon_rect.toRect(), pixmap)

    def sizeHint(self, option, index):
        size = super().sizeHint(option, index)
        size.setHeight(max(size.height(), 30))
        return size


class PromptOptionRow(QFrame):
    toggled = Signal(dict, bool)

    def __init__(self, entry, selected=False, parent=None):
        super().__init__(parent)
        self.entry = dict(entry)
        self.selected = bool(selected)
        self.setObjectName("promptPickerOptionRow")
        self.setProperty("selected", self.selected)
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(34)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 4, 10, 4)
        layout.setSpacing(8)

        color = QColor(self.entry.get("color") or "#22c55e")
        ring = QColor("#64748b") if self._is_light_color(color) else color.darker(145)
        self.color_dot = QLabel()
        self.color_dot.setObjectName("promptPickerColorDot")
        self.color_dot.setFixedSize(16, 16)
        self.color_dot.setStyleSheet(
            "QLabel#promptPickerColorDot {"
            f"background-color: {color.name()};"
            f"border: 2px solid {ring.name()};"
            "border-radius: 8px;"
            "}"
        )
        layout.addWidget(self.color_dot)

        self.prompt_label = QLabel(self.entry.get("prompt", ""))
        self.prompt_label.setObjectName("promptPickerPromptText")
        self.prompt_label.setWordWrap(False)
        layout.addWidget(self.prompt_label, 1)

        self.class_label = QLabel(self.entry.get("label", ""))
        self.class_label.setObjectName("promptPickerClassText")
        self.class_label.setWordWrap(False)
        layout.addWidget(self.class_label)

        self.check_label = QLabel("✓" if self.selected else "")
        self.check_label.setObjectName("promptPickerCheck")
        self.check_label.setAlignment(Qt.AlignCenter)
        self.check_label.setFixedWidth(22)
        layout.addWidget(self.check_label)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.selected = not self.selected
            self.setProperty("selected", self.selected)
            self.check_label.setText("✓" if self.selected else "")
            self.style().unpolish(self)
            self.style().polish(self)
            self.toggled.emit(dict(self.entry), self.selected)
            event.accept()
            return
        super().mousePressEvent(event)

    def _is_light_color(self, color):
        return (color.red() * 0.299 + color.green() * 0.587 + color.blue() * 0.114) > 210


PROMPT_TOKEN_KEY_PROPERTY = QTextFormat.UserProperty + 31
PROMPT_TOKEN_LABEL_PROPERTY = QTextFormat.UserProperty + 32
PROMPT_TOKEN_PROMPT_PROPERTY = QTextFormat.UserProperty + 33
PROMPT_TOKEN_COLOR_PROPERTY = QTextFormat.UserProperty + 34
PROMPT_TOKEN_MARK = "\u25cf"


class PromptInlineEdit(QTextEdit):
    returnPressed = Signal()
    tokensChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._syncing = False
        self.setAcceptRichText(False)
        self.setFrameShape(QFrame.NoFrame)
        self.setLineWrapMode(QTextEdit.WidgetWidth)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setTabChangesFocus(True)
        self.document().setDocumentMargin(0)
        self.document().contentsChanged.connect(self._emit_tokens_changed)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter) and not (event.modifiers() & Qt.ShiftModifier):
            self.returnPressed.emit()
            event.accept()
            return
        if event.key() in (Qt.Key_Backspace, Qt.Key_Delete) and not self.textCursor().hasSelection():
            position = self.textCursor().position()
            lookup = position - 1 if event.key() == Qt.Key_Backspace else position
            if self._remove_token_at(lookup):
                event.accept()
                return
        if event.text():
            self.setCurrentCharFormat(QTextCharFormat())
        super().keyPressEvent(event)

    def inputMethodEvent(self, event):
        self.setCurrentCharFormat(QTextCharFormat())
        super().inputMethodEvent(event)

    def insertFromMimeData(self, source):
        self.setCurrentCharFormat(QTextCharFormat())
        super().insertFromMimeData(source)

    def insertPlainText(self, text):
        self.setCurrentCharFormat(QTextCharFormat())
        super().insertPlainText(text)

    def sizeHint(self):
        return QSize(420, 24)

    def minimumSizeHint(self):
        return QSize(260, 24)

    def free_text(self):
        text = self.toPlainText()
        for start, end, _key in reversed(self._token_ranges()):
            text = text[:start] + text[end:]
        return text.strip()

    def token_keys(self):
        keys = []
        for _start, _end, key in self._token_ranges():
            keys.append(key)
        return keys

    def set_tokens_and_text(self, entries, text=""):
        self._syncing = True
        try:
            self.clear()
            cursor = self.textCursor()
            cursor.beginEditBlock()
            for entry in entries:
                self._insert_token(cursor, entry)
            if text:
                if entries:
                    cursor.insertText(" ")
                cursor.insertText(text)
            cursor.endEditBlock()
            self.setTextCursor(cursor)
            self.setCurrentCharFormat(QTextCharFormat())
        finally:
            self._syncing = False
        self.tokensChanged.emit()

    def insert_prompt_token(self, entry):
        cursor = self.textCursor()
        cursor.beginEditBlock()
        self._insert_token(cursor, entry)
        cursor.endEditBlock()
        self.setTextCursor(cursor)
        self.setCurrentCharFormat(QTextCharFormat())

    def remove_prompt_token(self, key):
        for start, end, token_key in self._token_ranges():
            if token_key == key:
                cursor = self.textCursor()
                cursor.setPosition(start)
                cursor.setPosition(end, QTextCursor.KeepAnchor)
                cursor.removeSelectedText()
                self.setTextCursor(cursor)
                return True
        return False

    def _insert_token(self, cursor, entry):
        label = (entry.get("label") or "").strip()
        prompt = (entry.get("prompt") or "").strip()
        key = f"{label}\0{prompt}"
        color = QColor(entry.get("color") or "#22c55e")

        icon_format = self._token_format(key, label, prompt, color)
        icon_format.setForeground(QBrush(color))
        cursor.insertText(PROMPT_TOKEN_MARK, icon_format)

        text_format = self._token_format(key, label, prompt, color)
        text_format.setForeground(QBrush(self.palette().text().color()))
        text_format.setFontWeight(QFont.DemiBold)
        cursor.insertText(f" {prompt}  ", text_format)
        cursor.setCharFormat(QTextCharFormat())

    def _token_format(self, key, label, prompt, color):
        fmt = QTextCharFormat()
        fmt.setProperty(PROMPT_TOKEN_KEY_PROPERTY, key)
        fmt.setProperty(PROMPT_TOKEN_LABEL_PROPERTY, label)
        fmt.setProperty(PROMPT_TOKEN_PROMPT_PROPERTY, prompt)
        fmt.setProperty(PROMPT_TOKEN_COLOR_PROPERTY, color.name())
        return fmt

    def _token_ranges(self):
        ranges = []
        current_key = None
        current_start = -1
        current_end = -1
        block = self.document().begin()
        while block.isValid():
            fragment = block.begin()
            while not fragment.atEnd():
                text_fragment = fragment.fragment()
                if text_fragment.isValid():
                    fmt = text_fragment.charFormat()
                    key = str(fmt.property(PROMPT_TOKEN_KEY_PROPERTY) or "")
                    start = text_fragment.position()
                    end = start + text_fragment.length()
                    if key and key == current_key and start == current_end:
                        current_end = end
                    else:
                        if current_key:
                            ranges.append((current_start, current_end, current_key))
                        current_key = key or None
                        current_start = start if key else -1
                        current_end = end if key else -1
                fragment += 1
            block = block.next()
        if current_key:
            ranges.append((current_start, current_end, current_key))
        return ranges

    def _token_range_at(self, position):
        if position < 0:
            return None
        for start, end, key in self._token_ranges():
            if start <= position < end:
                return start, end, key
        return None

    def _remove_token_at(self, position):
        token_range = self._token_range_at(position)
        if token_range is None:
            return False
        start, end, _key = token_range
        cursor = self.textCursor()
        cursor.setPosition(start)
        cursor.setPosition(end, QTextCursor.KeepAnchor)
        cursor.removeSelectedText()
        self.setTextCursor(cursor)
        return True

    def _emit_tokens_changed(self):
        if not self._syncing:
            self.tokensChanged.emit()


class PromptChipSelector(QWidget):
    selection_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("promptChipSelector")
        self._options = []
        self._selected = []
        self._label_order = {}
        self._current_label = ""
        self._default_placeholder = "输入或选择提示词，如 dog"
        self._popup = None
        self._popup_scroll = None
        self._options_host = None
        self._max_visible_rows = 10
        self._row_height = 24
        self._action_height = 28

        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Minimum)
        self.setMinimumWidth(260)
        self.setMinimumHeight(64)
        self.outer_layout = QVBoxLayout(self)
        self.outer_layout.setContentsMargins(10, 6, 8, 6)
        self.outer_layout.setSpacing(4)

        self.add_button = QToolButton()
        self.add_button.setObjectName("promptAddButton")
        self.add_button.setText("+")
        self.add_button.setAutoRaise(True)
        self.add_button.setToolTip("添加提示词")
        self.add_button.clicked.connect(self.show_prompt_popup)

        self.input = PromptInlineEdit()
        self.input.setObjectName("promptChipInput")
        self.input.setMinimumWidth(190)
        self.input.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.input.setPlaceholderText("输入或选择提示词，如 dog")
        self.input.textChanged.connect(self._rebuild_popup_options)
        self.input.tokensChanged.connect(self._sync_selected_from_editor)
        self.input.returnPressed.connect(self._commit_typed_prompt)
        self.outer_layout.addWidget(self.input, 1)
        self.mode_button = None
        self.submit_button = None
        self.reference_button = None

        self.action_bar = QWidget()
        self.action_bar.setObjectName("promptActionBar")
        self.action_bar.setFixedHeight(self._action_height)
        self.action_layout = QHBoxLayout(self.action_bar)
        self.action_layout.setContentsMargins(0, 0, 0, 0)
        self.action_layout.setSpacing(6)
        self.action_layout.addWidget(self.add_button)
        self.action_layout.addStretch(1)
        self.outer_layout.addWidget(self.action_bar)

        self.installEventFilter(self)
        self.input.installEventFilter(self)
        self.input.viewport().installEventFilter(self)
        self._update_content_height()

    def eventFilter(self, watched, event):
        watched_targets = (self, self.input, self.input.viewport())
        if watched in watched_targets and event.type() == QEvent.MouseButtonPress:
            if event.button() == Qt.LeftButton:
                QTimer.singleShot(0, self.show_prompt_popup)
        return super().eventFilter(watched, event)

    def lineEdit(self):
        return self.input

    def sizeHint(self):
        return QSize(420, self.minimumHeight())

    def minimumSizeHint(self):
        return QSize(260, self.minimumHeight())

    def attach_submit_button(self, button):
        self.submit_button = button
        button.setParent(self)
        button.setObjectName("promptSubmitButton")
        button.setMinimumWidth(44)
        button.setMaximumWidth(88)
        button.setMinimumHeight(28)
        button.setMaximumHeight(28)
        self.action_layout.addWidget(button)
        self._update_content_height()

    def attach_mode_button(self, button):
        self.mode_button = button
        button.setParent(self)
        button.setObjectName("promptModeButton")
        button.setAutoRaise(False)
        button.setMinimumHeight(28)
        button.setMaximumHeight(28)
        button.setMinimumWidth(74)
        button.setMaximumWidth(132)
        button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.action_layout.insertWidget(1, button)
        self._update_content_height()

    def attach_reference_button(self, button):
        self.reference_button = button
        button.setParent(self)
        button.setObjectName("promptReferenceButton")
        button.setMinimumHeight(28)
        button.setMaximumHeight(28)
        button.setMinimumWidth(88)
        button.setMaximumWidth(118)
        self.action_layout.addWidget(button)
        self._update_content_height()

    def currentText(self):
        return self.input.free_text()

    def setEditText(self, text):
        self.input.set_tokens_and_text(self._selected_sorted(), text or "")

    def setPlaceholderText(self, text):
        self._default_placeholder = text or ""
        if not self._selected:
            self.input.setPlaceholderText(self._default_placeholder)

    def clear(self):
        self._selected = []
        self.input.clear()
        self._update_content_height()
        self.selection_changed.emit()

    def set_current_label(self, label):
        self._current_label = (label or "").strip()

    def set_prompt_options(self, options):
        selected_keys = [self._entry_key(entry) for entry in self._selected]
        self._options = []
        self._label_order = {}
        seen = set()
        for option in options:
            label = (option.get("label") or "").strip()
            prompt = (option.get("prompt") or "").strip()
            if not label or not prompt:
                continue
            if label not in self._label_order:
                self._label_order[label] = len(self._label_order)
            key = self._make_key(label, prompt)
            if key in seen:
                continue
            seen.add(key)
            self._options.append({
                "label": label,
                "prompt": prompt,
                "color": option.get("color") or "#22c55e",
            })
        option_by_key = {self._entry_key(option): option for option in self._options}
        self._selected = [option_by_key[key] for key in selected_keys if key in option_by_key]
        self._render_chips()
        if self._popup and self._popup.isVisible():
            self._rebuild_popup_options()

    def selected_prompts(self):
        return [dict(entry) for entry in self._selected_sorted()]

    def set_single_prompt(self, label, prompt):
        label = (label or "").strip()
        prompt = (prompt or "").strip()
        if not label or not prompt:
            return
        self._selected = [self._entry_for(label, prompt)]
        self._render_chips("")
        self.selection_changed.emit()

    def add_prompt(self, label, prompt):
        label = (label or self._current_label or "").strip()
        prompt = (prompt or "").strip()
        if not label or not prompt:
            return False
        key = self._make_key(label, prompt)
        if key in {self._entry_key(entry) for entry in self._selected}:
            self.input.set_tokens_and_text(self._selected_sorted(), "")
            return False
        self._selected.append(self._entry_for(label, prompt))
        self._render_chips("")
        self.selection_changed.emit()
        return True

    def _commit_typed_prompt(self):
        text = self.currentText()
        if text and self._current_label:
            self.add_prompt(self._current_label, text)

    def _entry_for(self, label, prompt):
        for option in self._options:
            if option["label"] == label and option["prompt"] == prompt:
                return dict(option)
        return {
            "label": label,
            "prompt": prompt,
            "color": "#22c55e",
        }

    def _make_key(self, label, prompt):
        return f"{label}\0{prompt}"

    def _entry_key(self, entry):
        return self._make_key(entry.get("label", ""), entry.get("prompt", ""))

    def _selected_sorted(self):
        return sorted(
            self._selected,
            key=lambda entry: (
                self._label_order.get(entry.get("label", ""), 10_000),
                entry.get("label", "").lower(),
                entry.get("prompt", "").lower(),
            ),
        )

    def _render_chips(self, free_text=None):
        if free_text is None:
            free_text = self.input.free_text()
        self.input.set_tokens_and_text(self._selected_sorted(), free_text)
        self.input.setPlaceholderText("输入提示词并回车" if self._selected else self._default_placeholder)
        self._update_content_height()

    def _is_light_color(self, color):
        return (color.red() * 0.299 + color.green() * 0.587 + color.blue() * 0.114) > 210

    def _sync_selected_from_editor(self):
        keys = []
        seen = set()
        for key in self.input.token_keys():
            if key not in seen:
                seen.add(key)
                keys.append(key)

        by_key = {self._entry_key(entry): entry for entry in self._selected}
        for option in self._options:
            by_key[self._entry_key(option)] = option
        next_selected = [dict(by_key[key]) for key in keys if key in by_key]
        if [self._entry_key(entry) for entry in next_selected] == [self._entry_key(entry) for entry in self._selected]:
            self._update_content_height()
            return
        self._selected = next_selected
        if self._popup and self._popup.isVisible():
            self._rebuild_popup_options()
        self._update_content_height()
        self.selection_changed.emit()

    def _update_content_height(self):
        if not hasattr(self, "input"):
            return
        doc_height = int(math.ceil(self.input.document().size().height()))
        content_height = max(self._row_height, doc_height + 2)
        max_height = self._row_height * self._max_visible_rows + 4 * (self._max_visible_rows - 1)
        visible_height = min(content_height, max_height)
        self.input.setFixedHeight(visible_height)
        margins = self.outer_layout.contentsMargins()
        total_height = visible_height + self._action_height + self.outer_layout.spacing() + margins.top() + margins.bottom()
        self.setMinimumHeight(total_height)
        self.setMaximumHeight(total_height)
        self.updateGeometry()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_content_height()

    def _remove_prompt_key(self, key):
        if self.input.remove_prompt_token(key):
            return
        self._selected = [entry for entry in self._selected if self._entry_key(entry) != key]
        self._render_chips()
        self.selection_changed.emit()

    def show_prompt_popup(self):
        if self._popup is None:
            self._popup = QFrame(self, Qt.Popup)
            self._popup.setObjectName("promptPickerPopup")
            popup_layout = QVBoxLayout(self._popup)
            popup_layout.setContentsMargins(8, 8, 8, 8)
            popup_layout.setSpacing(0)

            scroll = QScrollArea()
            scroll.setObjectName("promptPickerScroll")
            scroll.setWidgetResizable(True)
            scroll.setMinimumHeight(120)
            self._options_host = QWidget()
            self._options_host.setObjectName("promptPickerOptions")
            scroll.setWidget(self._options_host)
            self._popup_scroll = scroll
            popup_layout.addWidget(scroll)

        self._rebuild_popup_options()
        self._position_prompt_popup()
        self._popup.show()
        self.input.setFocus(Qt.PopupFocusReason)

    def _position_prompt_popup(self):
        if self._popup is None:
            return
        anchor_top_left = self.mapToGlobal(self.rect().topLeft())
        anchor_bottom_left = self.mapToGlobal(self.rect().bottomLeft())
        window = self.window()
        if window is not None:
            bounds = window.frameGeometry()
            left_bound = bounds.left() + 10
            top_bound = bounds.top() + 10
            right_bound = bounds.right() - 10
            bottom_bound = bounds.bottom() - 10
        else:
            available = QApplication.primaryScreen().availableGeometry()
            left_bound = available.left() + 10
            top_bound = available.top() + 10
            right_bound = available.right() - 10
            bottom_bound = available.bottom() - 10

        popup_width = min(max(420, self.width()), max(320, right_bound - left_bound))
        desired_height = min(320, max(150, self._popup.sizeHint().height()))
        space_above = anchor_top_left.y() - top_bound - 8
        space_below = bottom_bound - anchor_bottom_left.y() - 8
        open_above = space_above >= min(desired_height, 180) or space_above >= space_below
        max_height = max(120, min(desired_height, space_above if open_above else space_below))
        if self._popup_scroll is not None:
            self._popup_scroll.setMaximumHeight(max_height)
        self._popup.resize(popup_width, max_height + 16)

        x = min(max(anchor_top_left.x(), left_bound), right_bound - popup_width)
        if open_above:
            y = max(top_bound, anchor_top_left.y() - self._popup.height() - 6)
        else:
            y = min(anchor_bottom_left.y() + 6, bottom_bound - self._popup.height())
        self._popup.move(x, y)

    def _rebuild_popup_options(self):
        if self._options_host is None:
            return
        old_layout = self._options_host.layout()
        if old_layout is not None:
            while old_layout.count():
                item = old_layout.takeAt(0)
                widget = item.widget()
                if widget is not None:
                    widget.deleteLater()
            QWidget().setLayout(old_layout)

        layout = QVBoxLayout(self._options_host)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        query = self.currentText().lower()
        selected_keys = {self._entry_key(entry) for entry in self._selected}
        grouped = {}
        for option in self._options:
            haystack = f"{option['label']} {option['prompt']}".lower()
            if query and query not in haystack:
                continue
            grouped.setdefault(option["label"], []).append(option)

        if not grouped:
            empty = QLabel("暂无可选提示词")
            empty.setObjectName("promptPickerEmpty")
            layout.addWidget(empty)
            layout.addStretch(1)
            return

        sorted_labels = sorted(grouped, key=lambda text: (self._label_order.get(text, 10_000), text.lower()))
        for label in sorted_labels:
            for option in sorted(grouped[label], key=lambda entry: entry["prompt"].lower()):
                row = PromptOptionRow(option, self._entry_key(option) in selected_keys)
                row.setToolTip(f"{option['label']} -> {option['prompt']}")
                row.toggled.connect(self._toggle_prompt_option)
                layout.addWidget(row)
        layout.addStretch(1)

    def _toggle_prompt_option(self, entry, checked):
        key = self._entry_key(entry)
        selected_keys = {self._entry_key(item) for item in self._selected}
        if checked and key not in selected_keys:
            self._selected.append(dict(entry))
        elif not checked and key in selected_keys:
            self._selected = [item for item in self._selected if self._entry_key(item) != key]
        self._render_chips()
        self.selection_changed.emit()


class MainWindow(QMainWindow, Ui_MainWindow):
    def __init__(self):
        super().__init__()
        self.setupUi(self)
        self._install_prompt_chip_selector()

        self.scene = Canvas(self)
        self.view.setScene(self.scene)
        self.fileQueueDelegate = FileQueueItemDelegate(self.listFiles)
        self.listFiles.setItemDelegate(self.fileQueueDelegate)
        self.labelVisibilityDelegate = LabelVisibilityItemDelegate(self.listClasses)
        self.listClasses.setItemDelegate(self.labelVisibilityDelegate)

        self.current_image_path = None
        self.current_dir = None
        self.class_list = []
        self.class_colors = {}
        self.class_visibility = {}
        self.prompt_aliases = {}
        self.pending_prompt_targets = {}
        self.batch_prompt_queue = []
        self.active_batch_prompt_task = None
        self.batch_prompt_total = 0
        self.batch_prompt_completed = 0
        self.batch_prompt_added = 0
        self.batch_prompt_failed = 0
        self._file_queue_check_anchor_row = -1
        self._file_queue_preserve_multi_selection_once = False
        self.settings = QSettings(SETTINGS_PATH, QSettings.IniFormat)
        self.current_format = self.settings.value("last_format", "yolo", str)
        if self.current_format not in ("json", "yolo", "xml"):
            self.current_format = "yolo"
        self._format_changed_by_user = False
        self.current_theme = self.settings.value("theme", "dark", str)
        if self.current_theme not in ("light", "dark"):
            self.current_theme = "dark"
        self.breathing_highlight_enabled = self._settings_bool("breathing_highlight", True)
        self.active_label = self.settings.value("active_label", "", str)
        self.last_edit_label_index = self.settings.value("last_edit_label_index", 0, int)
        self.annotation_item_syncing = False
        self.shape_to_item = {}
        self._default_palette = QApplication.instance().palette()
        self._last_left_panel_width = 300
        self._last_right_panel_width = 320
        self._file_grid_icon_size = QSize()
        self._file_grid_item_size = QSize()
        self.sam_model_available = False
        self.sam_model_loading = False
        self._default_sam_enabled_applied = False
        self._annotation_panel_updates_suspended = False

        self.modeLabel = QLabel("模式: 矩形标注")
        self.statusBar.addWidget(self.modeLabel)

        self.helpLabel = QLabel("状态: 正在初始化")
        self.statusBar.addWidget(self.helpLabel)
        self.activeLabelIndicator = QLabel("当前标签: 未选择")
        self.statusBar.addPermanentWidget(self.activeLabelIndicator)

        self.batchPromptProgress = QProgressBar()
        self.batchPromptProgress.setObjectName("batchPromptProgress")
        self.batchPromptProgress.setMinimumWidth(360)
        self.batchPromptProgress.setMaximumWidth(720)
        self.batchPromptProgress.setTextVisible(True)
        self.batchPromptProgress.setVisible(False)
        self.statusBar.addWidget(self.batchPromptProgress, 1)

        self.sam_client = SAMClient(self)
        self.sam_client.inference_result.connect(self.scene.handle_sam_result)
        self.sam_client.text_result_ready.connect(self.handle_text_results)
        self.sam_client.model_status_changed.connect(self.update_model_status)
        self.scene.sam_client = self.sam_client

        # 撤销/重做数据栈
        self.undo_stack = []
        self.redo_stack = []
        self.max_history_steps = 20
        self.history_suspended = False
        self.scene.state_changed.connect(self.push_state)
        self._breathing_cycle_elapsed = 0
        self._breathing_label_active_ms = 2200
        self._breathing_timer = QTimer(self)
        self._breathing_timer.setInterval(50)
        self._breathing_timer.timeout.connect(self._tick_breathing_highlight)
        self.sam_analysis_delay_ms = 450
        self._sam_analysis_timer = QTimer(self)
        self._sam_analysis_timer.setSingleShot(True)
        self._sam_analysis_timer.timeout.connect(self._analyze_current_image_for_sam)

        self._connect_signals()
        self._update_window_title()
        self._update_file_grid_metrics()
        QTimer.singleShot(0, self._update_file_grid_metrics)
        self._setup_shortcuts()
        QApplication.instance().installEventFilter(self)
        self.formatWidget.set_format(self.current_format)
        self.themeWidget.set_theme(self.current_theme)
        self.actionBreathingHighlight.setChecked(self.breathing_highlight_enabled)
        self.set_breathing_highlight_enabled(self.breathing_highlight_enabled, persist=False)
        self._update_panel_toggle_actions()
        self._update_history_actions()
        self._update_sam_switch_text()
        self._set_mode(CanvasMode.RECT)
        self.apply_theme(self.current_theme)
        self.update_active_label_indicator()
        self.load_sam_model_or_prompt()
        self._schedule_startup_help_once()
        self.restore_last_session()

    def _install_prompt_chip_selector(self):
        old_prompt_input = self.samPromptInput
        index = self.samRowLayout.indexOf(old_prompt_input)
        self.samRowLayout.removeWidget(old_prompt_input)
        old_prompt_input.deleteLater()
        self.samPromptInput = PromptChipSelector(self.samRow)
        if index >= 0:
            self.samRowLayout.insertWidget(index, self.samPromptInput, 1)
        else:
            self.samRowLayout.addWidget(self.samPromptInput, 1)
        self.samRowLayout.removeWidget(self.samSwitch)
        self.samPromptInput.attach_mode_button(self.samSwitch)
        self._setup_sam_mode_menu()
        self.samRowLayout.removeWidget(self.samRefBtn)
        self.samPromptInput.attach_reference_button(self.samRefBtn)
        self.samRowLayout.removeWidget(self.samPromptBtn)
        self.samPromptInput.attach_submit_button(self.samPromptBtn)

    def _setup_sam_mode_menu(self):
        menu = QMenu(self.samSwitch)
        self.samModeAction = menu.addAction("SAM 智能辅助")
        self.samModeAction.setCheckable(True)
        self.samModeAction.triggered.connect(lambda checked=False: self.samSwitch.setChecked(True))
        self.samOffAction = menu.addAction("关闭")
        self.samOffAction.setCheckable(True)
        self.samOffAction.triggered.connect(lambda checked=False: self.samSwitch.setChecked(False))
        self.samSwitch.setMenu(menu)
        self.samSwitch.setPopupMode(QToolButton.InstantPopup)

    def _connect_signals(self):
        self.actionOpen.triggered.connect(self.open_dir)
        self.actionSave.triggered.connect(lambda checked=False: self.save_annotation(self.current_format))
        self.actionRefreshFiles.triggered.connect(self.refresh_file_queue)
        self.actionUndo.triggered.connect(self.undo)
        self.actionRedo.triggered.connect(self.redo)
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
        self.actionToggleLeftPanel.toggled.connect(self.set_left_panel_visible)
        self.actionToggleRightPanel.toggled.connect(self.set_right_panel_visible)

        self.samSwitch.toggled.connect(self.on_sam_toggled)

        self.samPromptBtn.clicked.connect(self.trigger_sam_prompt)
        self.samRefBtn.clicked.connect(self.trigger_reference_search)
        self.samPromptInput.lineEdit().returnPressed.connect(self.trigger_sam_prompt)

        self.listFiles.currentItemChanged.connect(self.on_file_selected)
        self.listFiles.itemChanged.connect(self.on_file_queue_item_changed)
        self.listFiles.setContextMenuPolicy(Qt.CustomContextMenu)
        self.listFiles.customContextMenuRequested.connect(self.show_file_list_context_menu)
        self.splitter.splitterMoved.connect(lambda _pos, _index: self._on_splitter_moved())
        self.view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.view.customContextMenuRequested.connect(self.show_canvas_label_menu)
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
            self._reset_breathing_highlight()
            if not self._breathing_timer.isActive():
                self._breathing_timer.start()
        else:
            self._breathing_timer.stop()
            BaseShape.breathing_alpha = BaseShape.fill_alpha
            BaseShape.breathing_active_label = None
            self._refresh_breathing_highlight()
        if persist:
            self.settings.setValue("breathing_highlight", self.breathing_highlight_enabled)
        self._update_breathing_action_text()

    def _update_window_title(self):
        if self.current_image_path:
            self.setWindowTitle(f"PromptLabel - {self.current_image_path}")
        else:
            self.setWindowTitle("PromptLabel")

    def _update_breathing_action_text(self):
        self.actionBreathingHighlight.setText("呼吸高亮")
        detail = "呼吸高亮会让当前标签的标注框填充透明度循环变化，便于在密集标注中快速定位目标。"
        self.actionBreathingHighlight.setToolTip(
            f"{detail}\n当前已启用，点击关闭。" if self.breathing_highlight_enabled else f"{detail}\n当前已关闭，点击启用。"
        )

    def _update_history_actions(self):
        if hasattr(self, "actionUndo"):
            self.actionUndo.setEnabled(len(self.undo_stack) > 1)
        if hasattr(self, "actionRedo"):
            self.actionRedo.setEnabled(bool(self.redo_stack))

    def _update_panel_toggle_actions(self):
        sizes = self.splitter.sizes()
        if len(sizes) >= 3:
            left_visible = sizes[0] > 0
            right_visible = sizes[2] > 0
        else:
            left_visible = not self.leftPanel.isHidden()
            right_visible = not self.rightPanel.isHidden()
        self.actionToggleLeftPanel.blockSignals(True)
        self.actionToggleRightPanel.blockSignals(True)
        self.actionToggleLeftPanel.setChecked(left_visible)
        self.actionToggleRightPanel.setChecked(right_visible)
        self.actionToggleLeftPanel.blockSignals(False)
        self.actionToggleRightPanel.blockSignals(False)
        self.actionToggleLeftPanel.setText("隐藏左侧" if left_visible else "显示左侧")
        self.actionToggleLeftPanel.setToolTip("隐藏左侧图片队列" if left_visible else "显示左侧图片队列")
        self.actionToggleRightPanel.setText("隐藏右侧" if right_visible else "显示右侧")
        self.actionToggleRightPanel.setToolTip("隐藏右侧管理面板" if right_visible else "显示右侧管理面板")

    def _update_sam_switch_text(self):
        if not self.samSwitch.isEnabled():
            self.samSwitch.setText("不可用")
            self.samSwitch.setToolTip("SAM3 模型不可用或当前模式不支持 SAM")
        elif self.samSwitch.isChecked():
            self.samSwitch.setText("SAM")
            self.samSwitch.setToolTip("当前模式: SAM 智能辅助")
        else:
            self.samSwitch.setText("关闭")
            self.samSwitch.setToolTip("当前未启用 SAM，点击选择辅助模型")
        if hasattr(self, "samModeAction"):
            sam_available = self.samSwitch.isEnabled()
            self.samModeAction.setEnabled(sam_available)
            self.samModeAction.setChecked(sam_available and self.samSwitch.isChecked())
            self.samOffAction.setChecked(not self.samSwitch.isChecked())

    def _tick_breathing_highlight(self):
        self._breathing_cycle_elapsed = (
            self._breathing_cycle_elapsed + self._breathing_timer.interval()
        ) % self._breathing_label_active_ms
        self._update_breathing_active_label()
        if not BaseShape.breathing_active_label:
            self._refresh_breathing_highlight()
            return
        progress = self._breathing_cycle_elapsed / self._breathing_label_active_ms
        wave = (1.0 - math.cos(progress * math.pi * 2)) / 2.0
        BaseShape.breathing_alpha = int(wave * 125)
        self._refresh_breathing_highlight()

    def _reset_breathing_highlight(self):
        self._breathing_cycle_elapsed = 0
        BaseShape.breathing_alpha = 0
        self._update_breathing_active_label()
        self._refresh_breathing_highlight()

    def _update_breathing_active_label(self):
        BaseShape.breathing_active_label = self.active_label if self.active_label else None

    def _refresh_breathing_highlight(self):
        if not hasattr(self, "scene") or self.scene is None:
            return
        for item in self.scene.items():
            if isinstance(item, (RectShape, PolyShape, RotatedRectShape)):
                item.refresh_breathing_brush()

    def _setup_shortcuts(self):
        self._shortcuts = []
        shortcut_map = [
            ("Ctrl+Z", self.undo, True),
            ("Ctrl+Y", self.redo, True),
            ("Ctrl+Shift+Z", self.redo, True),
            ("Ctrl+A", self.select_all_by_focus, False),
            ("A", self.previous_image, False),
            ("Left", self.previous_image, False),
            ("D", self.next_image, False),
            ("Right", self.next_image, False),
            ("Up", lambda: self.select_adjacent_annotation(-1), False),
            ("W", lambda: self.select_adjacent_annotation(-1), False),
            ("Down", lambda: self.select_adjacent_annotation(1), False),
            ("S", lambda: self.select_adjacent_annotation(1), False),
            ("Delete", self.delete_selected_shapes, False),
            ("Backspace", self.delete_selected_shapes, False),
            ("0", self.delete_selected_shapes, False),
            ("F", self.delete_selected_shapes, False),
            ("E", self.edit_selected_shape_label, False),
            ("F1", self.show_help_dialog, True),
            ("R", self.trigger_sam_prompt, False),
            ("B", lambda: self._set_mode(CanvasMode.RECT), False),
            ("P", lambda: self._set_mode(CanvasMode.POLY), False),
            ("T", lambda: self._set_mode(CanvasMode.POINT), False),
            ("O", lambda: self._set_mode(CanvasMode.RBOX), False),
            ("Q", self.toggle_active_label_visibility, False),
            ("Space", self.toggle_sam_shortcut, False),
            ("Tab", self.cycle_active_label, False),
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
        while widget is not None:
            if isinstance(widget, (QLineEdit, QTextEdit, QPlainTextEdit, QAbstractSpinBox)):
                return True
            if isinstance(widget, QComboBox) and widget.isEditable():
                return True
            widget = widget.parentWidget()
        return False

    def _file_queue_has_focus(self):
        focused = QApplication.focusWidget()
        return focused in (self.listFiles, self.listFiles.viewport())

    def _class_item_icon_rect(self, item):
        rect = self.listClasses.visualItemRect(item)
        if not rect.isValid():
            return QRectF()
        depth = 0
        parent = item.parent()
        while parent is not None:
            depth += 1
            parent = parent.parent()
        x = rect.left() + 4 + depth * self.listClasses.indentation()
        if item.childCount() > 0:
            x += self.listClasses.indentation()
        return QRectF(x, rect.center().y() - 11, 22, 22)

    def _handle_class_tree_double_click(self, event):
        item = self.listClasses.itemAt(event.position().toPoint())
        if item is None or item.data(0, Qt.UserRole + 1) != "class":
            return False
        if not self._class_item_icon_rect(item).contains(event.position()):
            return False
        self.change_class_color(item)
        return True

    def select_all_by_focus(self):
        if self._file_queue_has_focus():
            self.select_all_file_queue_items()
            return
        self.select_all_current_annotation_group()

    def eventFilter(self, watched, event):
        if watched is self.listFiles.viewport() and event.type() == QEvent.MouseButtonPress:
            if self._handle_file_queue_mouse_press(event):
                return True
        if watched is self.listClasses.viewport() and event.type() == QEvent.MouseButtonDblClick:
            if self._handle_class_tree_double_click(event):
                return True
        if event.type() == QEvent.KeyPress and self._handle_file_queue_key_press(event):
            return True
        if event.type() in (QEvent.ShortcutOverride, QEvent.KeyPress) and self._handle_global_shortcut_event(event):
            return True
        if event.type() == QEvent.KeyPress and self._handle_history_shortcut_event(event):
            return True
        return super().eventFilter(watched, event)

    def _handle_canvas_selection_key(self, event):
        if event.key() != Qt.Key_G:
            return False
        if event.type() == QEvent.KeyRelease:
            if self.scene._g_selection_pressed:
                self.scene.keyReleaseEvent(event)
                return True
            return False
        if QApplication.activeWindow() is not self or QApplication.activePopupWidget() is not None:
            return False
        if event.modifiers() & (Qt.ControlModifier | Qt.AltModifier | Qt.MetaModifier):
            return False
        if self._text_input_has_focus():
            return False
        event.accept()
        if event.type() == QEvent.KeyPress:
            self.view.setFocus(Qt.ShortcutFocusReason)
            self.scene.keyPressEvent(event)
        return True

    def _handle_global_shortcut_event(self, event):
        if QApplication.activeWindow() is not self:
            return False
        if self._text_input_has_focus():
            if event.type() == QEvent.ShortcutOverride and event.key() == Qt.Key_Q:
                event.accept()
                return True
            return False

        modifiers = event.modifiers()
        key = event.key()
        callback = None

        if modifiers == Qt.NoModifier:
            shortcut_map = {
                Qt.Key_A: self.previous_image,
                Qt.Key_Left: self.previous_image,
                Qt.Key_D: self.next_image,
                Qt.Key_Right: self.next_image,
                Qt.Key_W: lambda: self.select_adjacent_annotation(-1),
                Qt.Key_Up: lambda: self.select_adjacent_annotation(-1),
                Qt.Key_S: lambda: self.select_adjacent_annotation(1),
                Qt.Key_Down: lambda: self.select_adjacent_annotation(1),
                Qt.Key_Delete: self.delete_selected_shapes,
                Qt.Key_Backspace: self.delete_selected_shapes,
                Qt.Key_0: self.delete_selected_shapes,
                Qt.Key_F: self.delete_selected_shapes,
                Qt.Key_E: self.edit_selected_shape_label,
                Qt.Key_R: self.trigger_sam_prompt,
                Qt.Key_B: lambda: self._set_mode(CanvasMode.RECT),
                Qt.Key_P: lambda: self._set_mode(CanvasMode.POLY),
                Qt.Key_T: lambda: self._set_mode(CanvasMode.POINT),
                Qt.Key_O: lambda: self._set_mode(CanvasMode.RBOX),
                Qt.Key_Q: self.toggle_active_label_visibility,
                Qt.Key_Space: self.toggle_sam_shortcut,
                Qt.Key_Tab: self.cycle_active_label,
                Qt.Key_F1: self.show_help_dialog,
            }
            callback = shortcut_map.get(key)
            if callback is None and Qt.Key_1 <= key <= Qt.Key_9:
                index = key - Qt.Key_1
                callback = lambda idx=index: self.set_label_by_index(idx)

        if callback is None:
            return False

        event.accept()
        if event.type() == QEvent.KeyPress and not (key == Qt.Key_Q and event.isAutoRepeat()):
            callback()
        return True

    def _handle_history_shortcut_event(self, event):
        active_window = QApplication.activeWindow()
        if active_window is not self:
            return False

        modifiers = event.modifiers()
        if not (modifiers & Qt.ControlModifier):
            return False

        key = event.key()
        if key == Qt.Key_Z:
            if modifiers & Qt.ShiftModifier:
                self.redo()
            elif self.scene.mode == CanvasMode.POLY and not self.scene.sam_enabled and len(self.scene.poly_pts) > 0:
                self.scene.poly_pts.pop()
                self.scene.update_temp_poly()
            else:
                self.undo()
            event.accept()
            return True

        if key == Qt.Key_Y:
            self.redo()
            event.accept()
            return True

        return False

    def set_label_by_index(self, index):
        if 0 <= index < len(self.class_list):
            self.set_active_label(self.class_list[index])

    def cycle_active_label(self):
        if not self.class_list:
            return
        if self.active_label in self.class_list:
            next_index = (self.class_list.index(self.active_label) + 1) % len(self.class_list)
        else:
            next_index = 0
        self.set_active_label(self.class_list[next_index])

    def previous_image(self):
        current_idx = self.listFiles.currentRow()
        if current_idx > 0:
            self.listFiles.setCurrentRow(current_idx - 1)

    def next_image(self):
        current_idx = self.listFiles.currentRow()
        if current_idx < self.listFiles.count() - 1:
            self.listFiles.setCurrentRow(current_idx + 1)

    def _annotation_navigation_items(self):
        items = []
        for _key, (widget, toolbox_index, _mode, _title) in self._annotation_group_config().items():
            for row in range(widget.count()):
                item = widget.item(row)
                shape = item.data(Qt.UserRole) if item is not None else None
                if shape is not None:
                    items.append((shape, widget, item, toolbox_index))
        return items

    def select_adjacent_annotation(self, step):
        nav_items = self._annotation_navigation_items()
        if not nav_items:
            return
        selected_ids = {id(item) for item in self.scene.selectedItems()}
        current_index = -1
        for index, (shape, _widget, _item, _toolbox_index) in enumerate(nav_items):
            if id(shape) in selected_ids:
                current_index = index
                break
        if current_index < 0:
            focused_widget = QApplication.focusWidget()
            for index, (_shape, widget, item, _toolbox_index) in enumerate(nav_items):
                if focused_widget is widget and item.isSelected():
                    current_index = index
                    break
        if current_index < 0:
            next_index = 0 if step > 0 else len(nav_items) - 1
        else:
            next_index = current_index + step
            if not 0 <= next_index < len(nav_items):
                return
        shape, widget, item, toolbox_index = nav_items[next_index]
        self.annotation_item_syncing = True
        try:
            for list_widget in self.annotation_list_widgets():
                list_widget.clearSelection()
            self.annotationToolBox.setCurrentIndex(toolbox_index)
            item.setSelected(True)
            widget.setCurrentItem(item)
            widget.scrollToItem(item)
            self._select_shapes_on_canvas([shape], focus_view=True)
        finally:
            self.annotation_item_syncing = False

    def select_all_current_annotation_group(self):
        current_widget = self.annotationToolBox.currentWidget()
        if current_widget not in self.annotation_list_widgets():
            return
        shapes = []
        previous_sync_state = self.annotation_item_syncing
        self.annotation_item_syncing = True
        current_widget.blockSignals(True)
        try:
            current_widget.clearSelection()
            for row in range(current_widget.count()):
                item = current_widget.item(row)
                shape = item.data(Qt.UserRole) if item is not None else None
                if shape is None:
                    continue
                item.setSelected(True)
                shapes.append(shape)
            if shapes:
                current_widget.setCurrentItem(current_widget.item(0))
                self._select_shapes_on_canvas(shapes, focus_view=True)
        finally:
            current_widget.blockSignals(False)
            self.annotation_item_syncing = previous_sync_state

    def _on_splitter_moved(self):
        self._update_file_grid_metrics()
        sizes = self.splitter.sizes()
        if len(sizes) >= 3:
            if sizes[0] > 0:
                self._last_left_panel_width = sizes[0]
            if sizes[2] > 0:
                self._last_right_panel_width = sizes[2]
        self._update_panel_toggle_actions()

    def set_left_panel_visible(self, visible):
        sizes = self.splitter.sizes()
        if len(sizes) < 3:
            self.leftPanel.setVisible(visible)
            self._update_panel_toggle_actions()
            return
        if visible:
            left_width = self._last_left_panel_width or 300
            remaining = max(1, sizes[1] - left_width)
            self.leftPanel.setVisible(True)
            self.splitter.setSizes([left_width, remaining, sizes[2]])
            self._update_file_grid_metrics()
            self._update_panel_toggle_actions()
            return
        if sizes[0] > 0:
            self._last_left_panel_width = sizes[0]
        self.splitter.setSizes([0, sizes[0] + sizes[1], sizes[2]])
        self.leftPanel.setVisible(False)
        self._update_panel_toggle_actions()

    def set_right_panel_visible(self, visible):
        sizes = self.splitter.sizes()
        if len(sizes) < 3:
            self.rightPanel.setVisible(visible)
            self._update_panel_toggle_actions()
            return
        if visible:
            right_width = self._last_right_panel_width or 320
            remaining = max(1, sizes[1] - right_width)
            self.rightPanel.setVisible(True)
            self.splitter.setSizes([sizes[0], remaining, right_width])
            self._update_panel_toggle_actions()
            return
        if sizes[2] > 0:
            self._last_right_panel_width = sizes[2]
        self.splitter.setSizes([sizes[0], sizes[1] + sizes[2], 0])
        self.rightPanel.setVisible(False)
        self._update_panel_toggle_actions()

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
            self._notify("点标注模式下不可使用 SAM 提示词提取", "warning")
            return
        self.samSwitch.setChecked(not self.samSwitch.isChecked())

    def _update_file_grid_metrics(self):
        viewport_width = self.listFiles.viewport().width() or self.listFiles.width() or self.leftPanel.width() or 292
        content_width = max(1, viewport_width - 14)
        min_item_width = 104
        item_gap = 8
        columns = max(1, (content_width + item_gap) // (min_item_width + item_gap))
        item_width = max(min_item_width, (content_width - (columns - 1) * item_gap) // columns)
        icon_width = max(82, item_width - 16)
        icon_height = max(60, int(icon_width * 0.72))
        icon_size = QSize(icon_width, icon_height)
        item_size = QSize(item_width, icon_height + 38)
        if icon_size == self._file_grid_icon_size and item_size == self._file_grid_item_size:
            return
        self._file_grid_icon_size = icon_size
        self._file_grid_item_size = item_size
        self.listFiles.setIconSize(icon_size)
        self.listFiles.setGridSize(item_size)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_file_grid_metrics()

    def _make_color_icon(self, color_value):
        pixmap = QPixmap(22, 22)
        pixmap.fill(Qt.transparent)
        color = QColor(color_value)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(QPen(QColor(90, 90, 90), 1))
        painter.setBrush(QBrush(color))
        painter.drawRoundedRect(QRectF(3, 3, 16, 16), 4, 4)
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

    def toggle_active_label_visibility(self):
        item = self._find_class_item(self.active_label)
        if item is not None:
            item.setCheckState(0, Qt.Unchecked if item.checkState(0) == Qt.Checked else Qt.Checked)

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
                item.setText(file_name)
                break

    def checked_file_paths(self):
        paths = []
        for index in range(self.listFiles.count()):
            item = self.listFiles.item(index)
            if self._is_file_item_checked(item):
                path = item.data(Qt.UserRole)
                if path:
                    paths.append(os.path.abspath(path))
        return paths

    def checked_file_items(self):
        return [
            self.listFiles.item(index)
            for index in range(self.listFiles.count())
            if self._is_file_item_checked(self.listFiles.item(index))
        ]

    def _is_file_item_checked(self, item):
        if not item:
            return False
        state = item.checkState()
        if state == Qt.Checked:
            return True
        try:
            if state == Qt.CheckState.Checked:
                return True
        except AttributeError:
            pass
        try:
            return int(state) == int(Qt.Checked)
        except (TypeError, ValueError):
            return state == 2

    def _file_item_path(self, item):
        return item.data(Qt.UserRole) if item else ""

    def _file_item_name(self, item):
        image_path = self._file_item_path(item)
        return item.data(Qt.UserRole + 1) or os.path.basename(image_path)

    def _context_file_items_for_item(self, item):
        checked_items = self.checked_file_items()
        item_path = os.path.abspath(self._file_item_path(item))
        checked_paths = {os.path.abspath(self._file_item_path(checked_item)) for checked_item in checked_items}
        if item_path in checked_paths:
            return checked_items
        self._set_single_checked_file_item(item)
        return [item]

    def open_image_location_selected(self, image_path):
        if not image_path:
            return
        normalized_path = os.path.abspath(image_path)
        try:
            if sys.platform == "win32":
                subprocess.Popen(["explorer.exe", f"/select,{normalized_path}"])
            else:
                QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(normalized_path)))
        except Exception as e:
            self._notify(f"打开所在位置失败: {e}", "danger")

    def _file_queue_event_pos(self, event):
        if hasattr(event, "position"):
            return event.position().toPoint()
        return event.pos()

    def _file_queue_checkbox_rect_for_item(self, item):
        item_rect = self.listFiles.visualItemRect(item)
        icon_size = self.listFiles.iconSize()
        icon_x = item_rect.left() + max(0, (item_rect.width() - icon_size.width()) // 2)
        icon_y = item_rect.top() + 6
        return QRectF(icon_x + 7, icon_y + 7, 22, 22)

    def _set_file_item_checked(self, item, checked):
        if not item:
            return
        item.setCheckState(Qt.Checked if checked else Qt.Unchecked)
        self.listFiles.viewport().update(self.listFiles.visualItemRect(item))

    def _set_single_checked_file_item(self, target_item):
        if not target_item:
            return
        target_row = self.listFiles.row(target_item)
        if target_row < 0:
            return
        self.listFiles.blockSignals(True)
        try:
            for row in range(self.listFiles.count()):
                item = self.listFiles.item(row)
                item.setCheckState(Qt.Checked if row == target_row else Qt.Unchecked)
        finally:
            self.listFiles.blockSignals(False)
        self.update_file_queue_title()
        self.listFiles.viewport().update()

    def _set_file_range_checked(self, start_row, end_row, checked):
        if self.listFiles.count() == 0:
            return
        first = max(0, min(start_row, end_row))
        last = min(self.listFiles.count() - 1, max(start_row, end_row))
        self.listFiles.blockSignals(True)
        try:
            for row in range(first, last + 1):
                self._set_file_item_checked(self.listFiles.item(row), checked)
        finally:
            self.listFiles.blockSignals(False)
        self.update_file_queue_title()
        self.listFiles.viewport().update()

    def select_all_file_queue_items(self):
        if self.listFiles.count() == 0:
            return
        current_row = self.listFiles.currentRow()
        if current_row < 0:
            current_row = 0
            self.listFiles.setCurrentRow(current_row)
        self._set_file_range_checked(0, self.listFiles.count() - 1, True)
        self._file_queue_check_anchor_row = current_row

    def _handle_file_queue_mouse_press(self, event):
        pos = self._file_queue_event_pos(event)
        item = self.listFiles.itemAt(pos)
        if not item:
            return False

        if event.button() == Qt.RightButton:
            if self._is_file_item_checked(item):
                self._file_queue_preserve_multi_selection_once = True
            return False

        if event.button() != Qt.LeftButton:
            return False

        row = self.listFiles.row(item)
        modifiers = event.modifiers()
        checkbox_hit = self._file_queue_checkbox_rect_for_item(item).contains(QPointF(pos))

        if modifiers & Qt.ShiftModifier:
            anchor = self._file_queue_check_anchor_row
            if anchor < 0 or anchor >= self.listFiles.count():
                anchor = self.listFiles.currentRow() if self.listFiles.currentRow() >= 0 else row
            should_check = item.checkState() != Qt.Checked
            self._set_file_range_checked(anchor, row, should_check)
            self._file_queue_check_anchor_row = anchor
            return True

        if (modifiers & Qt.ControlModifier) or checkbox_hit:
            self._set_file_item_checked(item, item.checkState() != Qt.Checked)
            self._file_queue_check_anchor_row = row
            self.update_file_queue_title()
            return True

        self._set_single_checked_file_item(item)
        self._file_queue_check_anchor_row = row
        return False

    def _handle_file_queue_key_press(self, event):
        focused = QApplication.focusWidget()
        if focused not in (self.listFiles, self.listFiles.viewport()):
            return False
        if self.listFiles.count() == 0:
            return False

        key = event.key()
        modifiers = event.modifiers()
        current_row = self.listFiles.currentRow()
        if current_row < 0:
            current_row = 0
            self.listFiles.setCurrentRow(current_row)

        if key == Qt.Key_A and modifiers == Qt.ControlModifier:
            self.select_all_file_queue_items()
            return True

        if key == Qt.Key_Space and (modifiers == Qt.NoModifier or modifiers == Qt.ControlModifier):
            item = self.listFiles.item(current_row)
            self._set_file_item_checked(item, item.checkState() != Qt.Checked)
            self._file_queue_check_anchor_row = current_row
            self.update_file_queue_title()
            return True

        if modifiers == Qt.ShiftModifier and key in (Qt.Key_Up, Qt.Key_Down, Qt.Key_Left, Qt.Key_Right):
            step = -1 if key in (Qt.Key_Up, Qt.Key_Left) else 1
            target_row = max(0, min(self.listFiles.count() - 1, current_row + step))
            anchor = self._file_queue_check_anchor_row
            if anchor < 0 or anchor >= self.listFiles.count():
                anchor = current_row
            self._file_queue_preserve_multi_selection_once = True
            self.listFiles.setCurrentRow(target_row)
            self._set_file_range_checked(anchor, target_row, True)
            self._file_queue_check_anchor_row = anchor
            return True

        return False

    def on_file_queue_item_changed(self, item):
        self.update_file_queue_title()
        self.listFiles.viewport().update(self.listFiles.visualItemRect(item))

    def update_file_queue_title(self):
        if not hasattr(self, "fileTitle"):
            return
        checked_count = len(self.checked_file_paths())
        if checked_count:
            self.fileTitle.setText(f"图片队列 ({self.listFiles.count()} 张，已选 {checked_count} 张)")
        else:
            self.fileTitle.setText(f"图片队列 ({self.listFiles.count()} 张)")

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
            self.refresh_prompt_combo()
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
            "rectangle": (self.rectStatsList, self.rectStatsIndex, CanvasMode.RECT, "矩形"),
            "polygon": (self.polyStatsList, self.polyStatsIndex, CanvasMode.POLY, "多边形"),
            "point": (self.pointStatsList, self.pointStatsIndex, CanvasMode.POINT, "点"),
            "rbox": (self.rboxStatsList, self.rboxStatsIndex, CanvasMode.RBOX, "旋转框"),
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
                return 0

            for index, shape in enumerate(visible_shapes, 1):
                label = getattr(shape, "label", "").strip() or "未命名"
                item = QListWidgetItem(f"{index}. {label}")
                item.setData(Qt.UserRole, shape)
                color = QColor(self.class_colors.get(label, color_for_label(label).name()))
                item.setIcon(self._make_color_icon(color))
                item.setToolTip(label)
                widget.addItem(item)
                self.shape_to_item[id(shape)] = (widget, item)
            return len(visible_shapes)
        finally:
            widget.blockSignals(False)

    def _set_status(self, text, color=None):
        self.helpLabel.setText(text)
        color_map = {
            "success": "#16a34a",
            "info": "#2563eb",
            "warning": "#d97706",
            "danger": "#dc2626",
            "red": "#dc2626",
            "green": "#16a34a",
            "orange": "#d97706",
        }
        if color in color_map:
            self.helpLabel.setStyleSheet(f"color: {color_map[color]}; font-weight: 600;")
        else:
            self.helpLabel.setStyleSheet("")

    def _notify(self, text, status="info"):
        self._set_status(text, status)

    def load_sam_model_or_prompt(self):
        model_path = self.resolve_sam_model_path()
        if model_path:
            self.load_sam_model_path(model_path)
            return
        self.sam_model_available = False
        self.apply_sam_control_availability()
        self._set_status("未找到 models/sam3.pt，SAM 智能辅助暂不可用", "warning")
        QTimer.singleShot(350, self.show_missing_model_dialog)

    def resolve_sam_model_path(self):
        if os.path.exists(DEFAULT_SAM3_PATH):
            return DEFAULT_SAM3_PATH
        saved_path = self.settings.value("sam3_path", "", str)
        if saved_path and os.path.exists(saved_path):
            return saved_path
        return ""

    def load_sam_model_path(self, model_path):
        self.sam_model_available = True
        self.sam_model_loading = True
        self.apply_sam_control_availability()
        self.settings.setValue("sam3_path", model_path)
        self._set_status("正在后台加载 SAM3 模型，请稍候...", "info")
        self.sam_client.load_model_async(model_path)

    def apply_sam_control_availability(self):
        enabled = bool(self.sam_model_available and self.scene.mode != CanvasMode.POINT)
        if not enabled and self.samSwitch.isChecked():
            self.samSwitch.setChecked(False)
        self.samSwitch.setEnabled(enabled)
        if enabled and not self._default_sam_enabled_applied:
            self._default_sam_enabled_applied = True
            self.samSwitch.setChecked(True)
        self.samPromptInput.setEnabled(enabled)
        self.samPromptBtn.setEnabled(enabled)
        self.samRefBtn.setEnabled(enabled)
        self._update_sam_switch_text()

    def _cancel_pending_sam_analysis(self):
        if self._sam_analysis_timer.isActive():
            self._sam_analysis_timer.stop()

    def _schedule_current_image_sam_analysis(self, delay_ms=None):
        if not self.current_image_path:
            self._cancel_pending_sam_analysis()
            return
        if self._is_batch_prompt_running():
            self._cancel_pending_sam_analysis()
            return
        if not self.sam_client.model or not self.samSwitch.isChecked() or not self.samSwitch.isEnabled():
            self._cancel_pending_sam_analysis()
            return
        self._sam_analysis_timer.start(self.sam_analysis_delay_ms if delay_ms is None else delay_ms)

    def _analyze_current_image_for_sam(self):
        if self._is_batch_prompt_running():
            return
        image_path = os.path.abspath(self.current_image_path) if self.current_image_path else ""
        if not image_path:
            return
        if not self.sam_client.model or not self.samSwitch.isChecked() or not self.samSwitch.isEnabled():
            return
        if self.sam_client.is_image_ready(image_path):
            self._set_status("当前图片 SAM 特征已就绪", "green")
            return
        self._set_status("正在分析当前图片智能特征...", "orange")
        QApplication.processEvents()
        self.sam_client.set_image(image_path)
        if self.current_image_path and os.path.abspath(self.current_image_path) == image_path:
            self._set_status("分析完成，可以开始智能标注", "green")

    def show_missing_model_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("缺少 SAM3 模型")
        dialog.setModal(True)
        dialog.resize(460, 190)

        layout = QVBoxLayout(dialog)
        title = QLabel("未找到 models/sam3.pt")
        title.setObjectName("dialogTitle")
        desc = QLabel("SAM 智能辅助暂不可用。手动标注和数据集处理可以继续使用。")
        desc.setWordWrap(True)
        tip = QLabel("可以选择已下载的 sam3.pt，也可以前往官网下载；选择后会记住路径，无需手动拷贝。")
        tip.setObjectName("mutedText")
        tip.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(desc)
        layout.addWidget(tip)

        button_row = QHBoxLayout()
        downloaded_btn = QPushButton("我已下载")
        official_btn = QPushButton("前往官网下载")
        baidu_btn = QPushButton("网盘下载")
        continue_btn = QPushButton("继续")
        continue_btn.setObjectName("DefaultBtn")
        button_row.addWidget(downloaded_btn)
        button_row.addStretch()
        button_row.addWidget(official_btn)
        button_row.addWidget(baidu_btn)
        button_row.addWidget(continue_btn)
        layout.addLayout(button_row)

        result = {"action": "continue"}

        def choose(action):
            result["action"] = action
            dialog.accept()

        downloaded_btn.clicked.connect(lambda: choose("local"))
        official_btn.clicked.connect(lambda: choose("official"))
        baidu_btn.clicked.connect(lambda: choose("baidu"))
        continue_btn.clicked.connect(lambda: choose("continue"))
        dialog.exec()

        if result["action"] == "local":
            self.select_existing_sam_model()
        elif result["action"] == "official":
            QDesktopServices.openUrl(QUrl(SAM3_OFFICIAL_URL))
        elif result["action"] == "baidu":
            QDesktopServices.openUrl(QUrl(SAM3_BAIDU_URL))
            QApplication.clipboard().setText(SAM3_BAIDU_CODE)
            self._notify("已打开备用网盘并复制提取码", "info")

    def select_existing_sam_model(self):
        saved_path = self.settings.value("sam3_path", "", str)
        start_dir = os.path.dirname(saved_path) if saved_path else BASE_DIR
        model_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择 sam3.pt",
            start_dir,
            "PyTorch checkpoint (*.pt);;All files (*.*)"
        )
        if not model_path:
            return
        self.load_sam_model_path(model_path)
        self._set_status(f"正在加载 SAM3 模型: {os.path.basename(model_path)}", "info")

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
        qss_path = os.path.join(RESOURCE_DIR, "ui", filename)
        try:
            with open(qss_path, "r", encoding="utf-8") as f:
                qss = f.read()
        except OSError:
            return ""
        ui_resource_dir = os.path.join(RESOURCE_DIR, "ui").replace("\\", "/")
        return qss.replace("url(ui/", f"url({ui_resource_dir}/")

    def apply_theme(self, theme_key, persist=True):
        if theme_key not in ("light", "dark"):
            theme_key = "dark"
        self.current_theme = theme_key
        app = QApplication.instance()
        resolved = theme_key
        if resolved == "dark":
            app.setPalette(self._build_dark_palette())
            app.setStyleSheet(self._load_theme_stylesheet("dark"))
        else:
            app.setPalette(self._build_light_palette())
            app.setStyleSheet(self._load_theme_stylesheet("light"))
        self.themeWidget.set_theme(theme_key)
        if hasattr(self, "_apply_toolbar_icons"):
            self._apply_toolbar_icons()
        if hasattr(self, "listClasses"):
            self.listClasses.viewport().update()
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
        if self.breathing_highlight_enabled:
            self._reset_breathing_highlight()

    def ensure_prompt_label(self):
        label = (self.active_label or "").strip()
        if not label:
            return self.ensure_active_label()
        if label not in self.class_list:
            self.add_class_to_list(label)
            self.save_classes()
        self.set_active_label(label)
        return label

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
        if not hasattr(self, "samPromptInput"):
            return
        self.samPromptInput.set_current_label(self.active_label)
        self.samPromptInput.set_prompt_options(self._prompt_selector_options())

    def _prompt_selector_options(self):
        options = []
        for label in self.class_list:
            color = self.class_colors.get(label, color_for_label(label).name())
            for prompt in self.prompt_aliases_for_label(label):
                options.append({
                    "label": label,
                    "prompt": prompt,
                    "color": color,
                })
        return options

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

    def _annotation_shape_from_item(self, item):
        current = item
        while current is not None:
            if isinstance(current, (RectShape, PolyShape, PointShape, RotatedRectShape)):
                return current
            current = current.parentItem()
        return None

    def _selected_annotation_shapes(self):
        return [
            item for item in self.scene.selectedItems()
            if isinstance(item, (RectShape, PolyShape, PointShape, RotatedRectShape))
        ]

    def show_canvas_label_menu(self, pos):
        menu = QMenu(self)
        sam_action_text = "关闭 SAM" if self.samSwitch.isChecked() else "打开 SAM"
        sam_action = menu.addAction(sam_action_text if self.samSwitch.isEnabled() else "SAM 不可用")
        sam_action.setEnabled(self.samSwitch.isEnabled())
        submit_prompt_action = menu.addAction("提交 SAM 提示词 (R)")
        submit_prompt_action.setEnabled(self.samPromptBtn.isEnabled() and self.scene.mode != CanvasMode.POINT)
        menu.addSeparator()

        selected_shapes = self._selected_annotation_shapes()
        scene_pos = self.view.mapToScene(pos)
        hovered_selected_shape = None
        selected_ids = {id(shape) for shape in selected_shapes}
        for item in self.scene.items(scene_pos):
            shape = self._annotation_shape_from_item(item)
            if shape is not None and id(shape) in selected_ids:
                hovered_selected_shape = shape
                break

        edit_selected_action = menu.addAction(
            f"修改 {len(selected_shapes)} 个选中标注类别" if selected_shapes else "修改选中标注类别"
        )
        edit_selected_action.setEnabled(bool(selected_shapes and hovered_selected_shape is not None))
        menu.addSeparator()
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
        if chosen == sam_action:
            self.samSwitch.setChecked(not self.samSwitch.isChecked())
            return
        if chosen == submit_prompt_action:
            self.trigger_sam_prompt()
            return
        if chosen == edit_selected_action:
            self.edit_shapes_label(selected_shapes)
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
        edit_action = menu.addAction(f"修改 {len(selected_shapes)} 个标注类别")
        delete_action = menu.addAction(f"删除 {len(selected_shapes)} 个标注")
        action = menu.exec(widget.mapToGlobal(pos))
        if action == edit_action and selected_shapes:
            self.edit_shapes_label(selected_shapes)
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
            self._notify(f"已复制文件名：{file_name}", "success")
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
            self._notify(f"删除失败: {e}", "danger")
            return

        current_row = self.listFiles.row(item)
        self.listFiles.takeItem(current_row)
        self.update_file_queue_title()
        if self.listFiles.count() > 0:
            self.listFiles.setCurrentRow(min(current_row, self.listFiles.count() - 1))
        else:
            self.current_image_path = None
            self._update_window_title()
            self.scene.clear_shapes()
            if self.scene.img_item:
                self.scene.removeItem(self.scene.img_item)
                self.scene.img_item = None
            self.update_annotation_panel()
        self._notify(f"已删除图片：{file_name}", "success")

    def show_file_list_context_menu(self, pos):
        item = self.listFiles.itemAt(pos)
        if not item:
            return

        target_items = self._context_file_items_for_item(item)
        target_count = len(target_items)
        self._file_queue_preserve_multi_selection_once = True
        self.listFiles.setCurrentItem(item)
        self._file_queue_preserve_multi_selection_once = False

        image_path = self._file_item_path(item)
        file_name = self._file_item_name(item)

        menu = QMenu(self)
        copy_action = menu.addAction("复制文件名" if target_count == 1 else f"复制 {target_count} 个文件名")
        open_location_action = menu.addAction("打开所在位置并选中图片")
        delete_action = menu.addAction("删除图片" if target_count == 1 else f"删除 {target_count} 张图片")
        action = menu.exec(self.listFiles.mapToGlobal(pos))

        if action == copy_action:
            file_names = [self._file_item_name(target_item) for target_item in target_items]
            QApplication.clipboard().setText("\n".join(file_names))
            if len(file_names) == 1:
                self._notify(f"已复制文件名：{file_name}", "success")
            else:
                self._notify(f"已复制 {len(file_names)} 个文件名", "success")
        elif action == open_location_action:
            self.open_image_location_selected(image_path)
        elif action == delete_action:
            self.delete_image_items(target_items)

    def delete_image_item(self, item):
        self.delete_image_items([item])

    def delete_image_items(self, items):
        valid_items = []
        seen_paths = set()
        for item in items:
            image_path = self._file_item_path(item)
            if not image_path:
                continue
            normalized_path = os.path.abspath(image_path)
            if normalized_path in seen_paths:
                continue
            seen_paths.add(normalized_path)
            valid_items.append(item)

        if not valid_items:
            return

        annotation_paths = []
        for item in valid_items:
            annotation_paths.extend(self.annotation_paths_for_image(self._file_item_path(item)))

        if len(valid_items) == 1:
            file_name = self._file_item_name(valid_items[0])
            message = f"确定删除图片“{file_name}”吗？"
            if annotation_paths:
                message += "\n将同时删除同名标注文件。"
        else:
            message = f"确定删除 {len(valid_items)} 张图片吗？"
            if annotation_paths:
                message += f"\n将同时删除 {len(annotation_paths)} 个同名标注文件。"

        reply = QMessageBox.question(
            self,
            "确认删除",
            message,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        current_path = os.path.abspath(self.current_image_path) if self.current_image_path else ""
        current_image_removed = False
        deleted_rows = []
        deleted_count = 0
        failed_count = 0

        for item in valid_items:
            image_path = self._file_item_path(item)
            normalized_path = os.path.abspath(image_path)
            try:
                if current_path and current_path == normalized_path:
                    self.auto_save_annotation()
                    current_image_removed = True
                if os.path.exists(image_path):
                    os.remove(image_path)
                for path in self.annotation_paths_for_image(image_path):
                    if os.path.exists(path):
                        os.remove(path)
                row = self.listFiles.row(item)
                if row >= 0:
                    deleted_rows.append(row)
                deleted_count += 1
            except Exception as e:
                failed_count += 1
                print(f"删除图片失败: {image_path}: {e}")

        for row in sorted(deleted_rows, reverse=True):
            self.listFiles.takeItem(row)

        self.update_file_queue_title()
        self._file_queue_preserve_multi_selection_once = False
        if current_image_removed:
            self._select_file_after_delete(min(deleted_rows) if deleted_rows else 0)
        elif self.listFiles.currentItem():
            self._set_single_checked_file_item(self.listFiles.currentItem())
        elif self.listFiles.count() > 0:
            self.listFiles.setCurrentRow(0)
        else:
            self._clear_current_image_view()

        if failed_count:
            self._notify(f"已删除 {deleted_count} 张图片，{failed_count} 张删除失败", "warning")
        elif deleted_count == 1:
            self._notify("已删除图片", "success")
        else:
            self._notify(f"已删除 {deleted_count} 张图片", "success")

    def _select_file_after_delete(self, preferred_row):
        if self.listFiles.count() > 0:
            next_row = min(max(0, preferred_row), self.listFiles.count() - 1)
            self.listFiles.setCurrentRow(next_row)
        else:
            self._clear_current_image_view()

    def _clear_current_image_view(self):
        self.current_image_path = None
        self._update_window_title()
        self.scene.clear_shapes()
        if self.scene.img_item:
            self.scene.removeItem(self.scene.img_item)
            self.scene.img_item = None
        self.update_annotation_panel()

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

            current_mode_index = None
            for key, (widget, toolbox_index, _mode, title) in self._annotation_group_config().items():
                rendered_count = self._render_annotation_group(widget, grouped_shapes[key])
                self.annotationToolBox.setTabText(toolbox_index, f"{title} ({rendered_count})")
                if _mode == self.scene.mode:
                    current_mode_index = toolbox_index
            if current_mode_index is not None and self.annotationToolBox.currentIndex() != current_mode_index:
                self.annotationToolBox.blockSignals(True)
                try:
                    self.annotationToolBox.setCurrentIndex(current_mode_index)
                finally:
                    self.annotationToolBox.blockSignals(False)
        finally:
            self.annotation_item_syncing = previous_sync_state

        self.sync_annotation_selection_from_scene()
        self.update_annotation_stats_status()

    def update_annotation_stats_status(self):
        if not hasattr(self, "annotationStatsLabel"):
            return

        current_mode = self.scene.mode
        current_key = None
        current_title = CanvasMode.get_mode_name(current_mode)
        for key, (_widget, _toolbox_index, mode, title) in self._annotation_group_config().items():
            if mode == current_mode:
                current_key = key
                current_title = title
                break

        counts = {}
        for shape in self.scene.items():
            if self._shape_group_name(shape) != current_key:
                continue
            label = getattr(shape, "label", "").strip() or "未命名"
            counts[label] = counts.get(label, 0) + 1

        ordered_labels = [label for label in self.class_list if counts.get(label, 0) > 0]
        ordered_labels.extend(label for label in sorted(counts) if label not in ordered_labels)
        if ordered_labels:
            stats = "，".join(f"{label}: {counts[label]}" for label in ordered_labels)
        else:
            stats = "暂无标注"
        total_count = sum(counts.values())
        self.annotationStatsLabel.setText(f"统计: {current_title} | 总数: {total_count} | {stats}")

    def push_state(self):
        # ??????????
        if self.history_suspended:
            return
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
        self._update_history_actions()

    def undo(self):
        """撤销 (Ctrl+Z)"""
        if len(self.undo_stack) > 1:
            # 把现在的状态拿出来，放到重做栈里去
            current_state = self.undo_stack.pop()
            self.redo_stack.append(current_state)
            # 获取上一步的状态并还原
            previous_state = self.undo_stack[-1]
            self.history_suspended = True
            try:
                self.restore_state(previous_state)
            finally:
                self.history_suspended = False
        self._update_history_actions()

    def redo(self):
        """重做/前进 (Ctrl+Y 或 Ctrl+Shift+Z)"""
        if self.redo_stack:
            # 从重做栈里拿出来，塞回撤销栈
            next_state = self.redo_stack.pop()
            self.undo_stack.append(next_state)
            # 还原该状态
            self.history_suspended = True
            try:
                self.restore_state(next_state)
            finally:
                self.history_suspended = False
        self._update_history_actions()

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
                resolved = self.current_theme if self.current_theme in ("light", "dark") else "dark"
                self.dataset_window = DatasetToolWindow(resolved)
            # 显示窗口
            self.dataset_window.show()
            # 把窗口强制拉到最前面
            self.dataset_window.raise_()
            self.dataset_window.activateWindow()

        except Exception as e:
            self._notify(f"启动失败: {e}", "danger")

    def _is_batch_prompt_running(self):
        return bool(self.active_batch_prompt_task or self.batch_prompt_queue)

    def _pending_prompt_target_label(self, entry):
        if isinstance(entry, dict):
            return entry.get("label", "")
        return entry

    def _normalize_pending_prompt_target(self, entry):
        if isinstance(entry, dict):
            return {
                "label": entry.get("label", ""),
                "mode": entry.get("mode", self.scene.mode),
                "format": entry.get("format", self.current_format),
                "batch": bool(entry.get("batch", False)),
            }
        return {
            "label": entry,
            "mode": self.scene.mode,
            "format": self.current_format,
            "batch": False,
        }

    def _prompt_result_shapes(self, results, target_label, mode):
        def result_sort_key(res):
            x, y, _w, _h = res.get("rect", [0, 0, 0, 0])
            return (float(x), float(y))

        shapes_data = []
        for res in sorted(results, key=result_sort_key):
            if mode == CanvasMode.RECT:
                x, y, w, h = res.get("rect", [0, 0, 0, 0])
                if w <= 0 or h <= 0:
                    continue
                shapes_data.append({
                    "label": target_label,
                    "type": "rectangle",
                    "points": [[float(x), float(y)], [float(x + w), float(y + h)]],
                })
            else:
                pts = res.get("poly_pts", [])
                if len(pts) < 3:
                    continue
                shapes_data.append({
                    "label": target_label,
                    "type": "polygon",
                    "points": [[float(p[0]), float(p[1])] for p in pts],
                })
        return shapes_data

    def _shape_item_from_data(self, shape_data):
        label = shape_data.get("label", "")
        shape_type = shape_data.get("type", "rectangle")
        points = shape_data.get("points", [])
        if shape_type == "rectangle" and len(points) == 2:
            return RectShape(
                QRectF(
                    points[0][0],
                    points[0][1],
                    points[1][0] - points[0][0],
                    points[1][1] - points[0][1],
                ),
                label,
            )
        if shape_type == "polygon" and len(points) >= 3:
            return PolyShape(QPolygonF([QPointF(p[0], p[1]) for p in points]), label)
        if shape_type == "point" and len(points) == 1:
            return PointShape(QPointF(points[0][0], points[0][1]), label)
        if shape_type == "obb":
            rect_data = shape_data.get("rect", [])
            if len(rect_data) == 4:
                return RotatedRectShape(rect_data[0], rect_data[1], rect_data[2], rect_data[3], shape_data.get("angle", 0), label)
        return None

    def _add_shape_data_to_scene(self, shapes_data):
        added = 0
        for shape_data in shapes_data:
            label = shape_data.get("label", "")
            shape = self._shape_item_from_data(shape_data)
            if not shape:
                continue
            self.scene.addItem(shape)
            self._apply_shape_label_style(shape, label)
            if hasattr(shape, 'update_label_text'):
                shape.update_label_text(label)
            if hasattr(shape, 'update_label_position'):
                shape.update_label_position(shape)
            if hasattr(shape, 'update_label_visibility'):
                shape.update_label_visibility(shape, is_selected=False, is_hovered=False)
            added += 1
        return added

    def _read_json_annotation_shapes(self, json_path):
        if not os.path.exists(json_path):
            return []
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return []

        shapes_data = []
        for shape_data in data.get("shapes", []):
            label = shape_data.get("label", "")
            shape_type = shape_data.get("shape_type", "rectangle")
            points = shape_data.get("points", [])
            if shape_type in ("rectangle", "polygon", "point"):
                shapes_data.append({"label": label, "type": shape_type, "points": points})
            elif shape_type == "obb":
                shapes_data.append({
                    "label": label,
                    "type": "obb",
                    "points": points,
                    "rect": shape_data.get("rect", [0, 0, 0, 0]),
                    "angle": shape_data.get("angle", 0),
                })
        return shapes_data

    def _read_xml_annotation_shapes(self, xml_path):
        if not os.path.exists(xml_path):
            return []
        import xml.etree.ElementTree as ET
        shapes_data = []
        try:
            tree = ET.parse(xml_path)
            root = tree.getroot()
            for obj in root.findall("object"):
                name_node = obj.find("name")
                bndbox = obj.find("bndbox")
                if name_node is None or bndbox is None:
                    continue
                xmin = float(bndbox.find("xmin").text)
                ymin = float(bndbox.find("ymin").text)
                xmax = float(bndbox.find("xmax").text)
                ymax = float(bndbox.find("ymax").text)
                shapes_data.append({
                    "label": name_node.text or "",
                    "type": "rectangle",
                    "points": [[xmin, ymin], [xmax, ymax]],
                })
        except Exception:
            return []
        return shapes_data

    def _yolo_lines_for_shapes(self, shapes_data, image_width, image_height):
        lines = []
        for shape_data in shapes_data:
            label = shape_data.get("label", "")
            if label not in self.class_list:
                continue
            class_id = self.class_list.index(label)
            shape_type = shape_data.get("type", "")
            points = shape_data.get("points", [])
            if shape_type == "rectangle" and len(points) == 2:
                x1, y1 = points[0]
                x2, y2 = points[1]
                cx = ((x1 + x2) / 2.0) / image_width
                cy = ((y1 + y2) / 2.0) / image_height
                w = abs(x2 - x1) / image_width
                h = abs(y2 - y1) / image_height
                lines.append(f"{class_id} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}")
            elif shape_type in ("polygon", "obb") and len(points) >= 3:
                flat_pts = []
                for pt in points:
                    flat_pts.append(f"{pt[0] / image_width:.6f} {pt[1] / image_height:.6f}")
                lines.append(f"{class_id} " + " ".join(flat_pts))
            elif shape_type == "point" and len(points) == 1:
                cx = points[0][0] / image_width
                cy = points[0][1] / image_height
                pw, ph = 0.02, 0.02
                cx = max(pw / 2, min(1.0 - pw / 2, cx))
                cy = max(ph / 2, min(1.0 - ph / 2, cy))
                lines.append(f"{class_id} {cx:.6f} {cy:.6f} {pw:.6f} {ph:.6f}")
        return lines

    def _append_shape_data_to_annotation_file(self, image_path, new_shapes, format_type):
        if not new_shapes:
            return 0
        pixmap = QPixmap(image_path)
        if pixmap.isNull():
            return 0
        image_width = pixmap.width()
        image_height = pixmap.height()
        base_path = os.path.splitext(image_path)[0]

        if format_type == "json":
            out_path = base_path + ".json"
            shapes_data = self._read_json_annotation_shapes(out_path) + new_shapes
            Exporter.save_json(out_path, image_path, image_width, image_height, shapes_data)
        elif format_type == "xml":
            out_path = base_path + ".xml"
            shapes_data = self._read_xml_annotation_shapes(out_path) + new_shapes
            Exporter.save_xml(out_path, image_path, image_width, image_height, shapes_data)
        else:
            out_path = base_path + ".txt"
            lines = self._yolo_lines_for_shapes(new_shapes, image_width, image_height)
            if not lines:
                return 0
            prefix = ""
            if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
                with open(out_path, "rb") as f:
                    f.seek(-1, os.SEEK_END)
                    if f.read(1) != b"\n":
                        prefix = "\n"
            with open(out_path, "a", encoding="utf-8") as f:
                f.write(prefix + "\n".join(lines))

        self.refresh_file_item_status(image_path)
        return len(new_shapes)

    def _start_batch_prompt_annotation(self, image_paths, prompt_entries):
        if self._is_batch_prompt_running():
            self._notify("批量智能标注正在进行，请等待当前任务完成", "warning")
            return
        if not self.sam_client.model:
            self._notify("SAM 模型尚未就绪，无法批量智能标注", "warning")
            return

        deduped_paths = []
        seen = set()
        for image_path in image_paths:
            normalized = os.path.abspath(image_path)
            if normalized in seen:
                continue
            seen.add(normalized)
            deduped_paths.append(normalized)
        valid_entries = []
        seen_entries = set()
        for entry in prompt_entries:
            label = (entry.get("label") or "").strip()
            prompt = (entry.get("prompt") or "").strip()
            if not label or not prompt:
                continue
            key = (label, prompt)
            if key in seen_entries:
                continue
            seen_entries.add(key)
            valid_entries.append({"label": label, "prompt": prompt})
        if not deduped_paths or not valid_entries:
            return

        self.batch_prompt_queue = [
            {
                "image_path": image_path,
                "prompt": entry["prompt"],
                "label": entry["label"],
                "mode": self.scene.mode,
                "format": self.current_format,
            }
            for image_path in deduped_paths
            for entry in valid_entries
        ]
        self.active_batch_prompt_task = None
        self.batch_prompt_total = len(self.batch_prompt_queue)
        self.batch_prompt_completed = 0
        self.batch_prompt_added = 0
        self.batch_prompt_failed = 0
        self._cancel_pending_sam_analysis()
        self._update_batch_prompt_progress(0)
        if len(deduped_paths) > 1:
            self._set_status(f"批量智能标注中：{len(deduped_paths)} 张图片 × {len(valid_entries)} 个提示词", "orange")
        else:
            self._set_status(f"正在按 {len(valid_entries)} 个提示词标注当前图片", "orange")
        self.samPromptBtn.setEnabled(False)
        self.samSwitch.setChecked(True)
        self._process_next_batch_prompt_task()

    def _update_batch_prompt_progress(self, value=None):
        if not hasattr(self, "batchPromptProgress"):
            return
        total = max(0, self.batch_prompt_total)
        if total <= 0:
            self.batchPromptProgress.setVisible(False)
            return
        current = self.batch_prompt_completed if value is None else value
        current = max(0, min(total, current))
        self.batchPromptProgress.setRange(0, total)
        self.batchPromptProgress.setValue(current)
        self.batchPromptProgress.setFormat(f"批量 {current}/{total}")
        self.batchPromptProgress.setVisible(True)

    def _process_next_batch_prompt_task(self):
        if not self.batch_prompt_queue:
            total = self.batch_prompt_total
            added = self.batch_prompt_added
            failed = self.batch_prompt_failed
            self._update_batch_prompt_progress(total)
            self.active_batch_prompt_task = None
            self.batch_prompt_total = 0
            self.batch_prompt_completed = 0
            self.batch_prompt_added = 0
            self.batch_prompt_failed = 0
            self.apply_sam_control_availability()
            self._set_status(f"智能标注完成：{total} 个任务，新增 {added} 个标注，失败 {failed} 个", "green" if failed == 0 else "orange")
            QTimer.singleShot(2400, self._update_batch_prompt_progress)
            if self.current_image_path:
                self._schedule_current_image_sam_analysis(delay_ms=0)
            return

        task = self.batch_prompt_queue.pop(0)
        self.active_batch_prompt_task = task
        image_path = task["image_path"]
        self._update_batch_prompt_progress(self.batch_prompt_completed)
        QApplication.processEvents()

        if not os.path.exists(image_path):
            self._finish_batch_prompt_task(0, failed=True)
            return

        self.sam_client.set_image(image_path)
        if not self.sam_client.is_image_ready(image_path):
            self._finish_batch_prompt_task(0, failed=True)
            return

        pending_key = (task["prompt"], image_path)
        self.pending_prompt_targets[pending_key] = {
            "label": task["label"],
            "mode": task["mode"],
            "format": task["format"],
            "batch": True,
        }
        if not self.sam_client.request_text_inference(task["prompt"], image_path):
            self.pending_prompt_targets.pop(pending_key, None)
            self._finish_batch_prompt_task(0, failed=True)

    def _finish_batch_prompt_task(self, added_count, failed=False):
        self.batch_prompt_completed += 1
        if failed:
            self.batch_prompt_failed += 1
        else:
            self.batch_prompt_added += added_count
        self._update_batch_prompt_progress(self.batch_prompt_completed)
        self.active_batch_prompt_task = None
        QTimer.singleShot(0, self._process_next_batch_prompt_task)

    def trigger_sam_prompt(self):
        if self.scene.mode == CanvasMode.POINT:
            self._notify("点标注模式下不可使用 SAM 提示词提取", "warning")
            return
        if self._is_batch_prompt_running():
            self._notify("批量智能标注正在进行，请等待当前任务完成", "warning")
            return

        typed_prompt = self.samPromptInput.currentText().strip()
        if typed_prompt:
            label = self.ensure_prompt_label()
            if not label:
                self._notify("请先选择或创建一个标签", "warning")
                return
            self.add_prompt_alias(label, typed_prompt)
            self.samPromptInput.add_prompt(label, typed_prompt)

        prompt_entries = self.samPromptInput.selected_prompts()
        if not prompt_entries:
            self._notify("请先输入或选择至少一个提示词", "warning")
            return

        for entry in prompt_entries:
            label = entry.get("label", "")
            prompt = entry.get("prompt", "")
            if label not in self.class_list:
                self.add_class_to_list(label)
                self.save_classes()
            self.add_prompt_alias(label, prompt)

        checked_paths = self.checked_file_paths()
        image_paths = checked_paths if len(checked_paths) > 1 else []
        if not image_paths:
            image_path = os.path.abspath(self.current_image_path) if self.current_image_path else ""
            if not image_path:
                self._notify("请先打开图片", "warning")
                return
            image_paths = [image_path]

        self._start_batch_prompt_annotation(image_paths, prompt_entries)

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
            self._notify("请先打开图片", "warning")
            return

        selected_shapes = [
            item for item in self.scene.selectedItems()
            if isinstance(item, (RectShape, PolyShape, PointShape, RotatedRectShape))
        ]
        if len(selected_shapes) != 1:
            self._notify("请先选中一个目标作为参考样本", "warning")
            return

        ref_shape = selected_shapes[0]
        ref_rect = self._shape_scene_rect(ref_shape).normalized()
        x1 = max(0, int(ref_rect.left()))
        y1 = max(0, int(ref_rect.top()))
        x2 = int(ref_rect.right())
        y2 = int(ref_rect.bottom())
        if x2 - x1 < 8 or y2 - y1 < 8:
            self._notify("参考目标太小，无法稳定查找", "warning")
            return

        image = cv2.imread(self.current_image_path)
        if image is None:
            self._notify("读取当前图片失败", "danger")
            return

        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        template = gray[y1:y2, x1:x2]
        if template.size == 0:
            self._notify("参考区域无效", "warning")
            return

        label = self.ensure_active_label()
        if not label:
            self._notify("请先选择或创建一个标签", "warning")
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
            self._notify("未找到足够相似的目标，可换一个更标准的参考样本", "warning")
            return

        self.update_annotation_panel()
        self.auto_save_annotation()
        self.push_state()
        self._set_status(f"参考查找完成，新增 {added} 个相似目标")

    def handle_text_results(self, results, prompt_text, image_path):
        result_image_path = os.path.abspath(image_path) if image_path else ""
        current_image_path = os.path.abspath(self.current_image_path) if self.current_image_path else ""
        pending_key = (prompt_text, result_image_path)
        pending_entry = self.pending_prompt_targets.pop(pending_key, None)
        if pending_entry is None and self.active_batch_prompt_task:
            active_path = os.path.abspath(self.active_batch_prompt_task.get("image_path", ""))
            active_prompt = self.active_batch_prompt_task.get("prompt", "")
            if active_path == result_image_path and active_prompt == prompt_text:
                pending_entry = {
                    "label": self.active_batch_prompt_task.get("label", ""),
                    "mode": self.active_batch_prompt_task.get("mode", self.scene.mode),
                    "format": self.active_batch_prompt_task.get("format", self.current_format),
                    "batch": True,
                }
        target_info = self._normalize_pending_prompt_target(pending_entry)
        is_batch = target_info["batch"]
        if result_image_path != current_image_path and not is_batch:
            return

        target_label = target_info["label"] or self.active_label
        if target_label not in self.class_list:
            self._set_status(f"提示词“{prompt_text}”已有结果，但没有可用的目标标签", "red")
            self._notify("请先选择或创建一个标签，再使用提示词检索", "warning")
            if is_batch:
                self._finish_batch_prompt_task(0, failed=True)
            return

        if not results:
            self._set_status(f"提取完成：未发现与“{prompt_text}”相关的目标", "red")
            if is_batch:
                self._finish_batch_prompt_task(0, failed=False)
            return

        shapes_data = self._prompt_result_shapes(results, target_label, target_info["mode"])
        if not shapes_data:
            self._set_status(f"提示词“{prompt_text}”已有结果，但没有可写入的标注形状", "red")
            if is_batch:
                self._finish_batch_prompt_task(0, failed=False)
            return

        self.add_prompt_alias(target_label, prompt_text)
        added_count = 0
        if result_image_path == current_image_path:
            added_count = self._add_shape_data_to_scene(shapes_data)
            self.update_annotation_panel()
            self.auto_save_annotation()
            self.push_state()
        else:
            try:
                added_count = self._append_shape_data_to_annotation_file(result_image_path, shapes_data, target_info["format"])
            except Exception as e:
                self._set_status(f"批量写入标注失败：{e}", "red")
                if is_batch:
                    self._finish_batch_prompt_task(0, failed=True)
                return

        self._set_status(f"提取完成：用提示词“{prompt_text}”找到 {len(results)} 个目标，已标注为“{target_label}”", "green")
        if is_batch:
            self._finish_batch_prompt_task(added_count, failed=added_count == 0)

    def _shortcut_guide_image_path(self):
        candidates = [
            os.path.join(RESOURCE_DIR, "assets", "shortcut.jpg"),
            os.path.join(APP_DIR, "assets", "shortcut.jpg"),
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "shortcut.jpg"),
        ]
        for path in candidates:
            if os.path.exists(path):
                return path
        return candidates[0]

    def _help_project_links_html(self):
        return (
            '<div align="center" style="font-family: Microsoft YaHei UI; font-size: 14px; line-height: 1.55;">'
            '<b>项目链接：</b>'
            '<a href="https://github.com/m-RNA/PromptLabel">当前仓库</a>'
            '&nbsp;&nbsp;|&nbsp;&nbsp;'
            '<a href="https://github.com/luohuabuxiema/LabelPaw">上游 LabelPaw</a>'
            '<br><span style="color:#8a93a6;">当前仓库是在上游 LabelPaw 的基础上继续开发。</span>'
            '</div>'
        )


    def _schedule_startup_help_once(self):
        if not self._settings_bool("startup_help_seen", False):
            QTimer.singleShot(
                0,
                self._show_startup_help_once,
            )

    def _show_startup_help_once(self):
        _finish_startup_splash(self)
        self.show_shortcut_guide(mark_seen=True, help_html=self._help_project_links_html())

    def show_shortcut_guide(self, mark_seen=False, help_html=None):
        dialog = QDialog(self)
        dialog.setWindowTitle("PromptLabel")
        dialog.setModal(True)
        dialog.resize(980, 650 if help_html else 610)

        layout = QVBoxLayout(dialog)
        title = QLabel("\u5feb\u6377\u952e\u901f\u89c8")
        title.setObjectName("dialogTitle")
        layout.addWidget(title)

        image_label = QLabel()
        image_label.setAlignment(Qt.AlignCenter)
        pixmap = QPixmap(self._shortcut_guide_image_path())
        if pixmap.isNull():
            image_label.setText("assets/shortcut.jpg")
        else:
            image_label.setPixmap(pixmap.scaled(920, 460, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        layout.addWidget(image_label)

        if help_html:
            links_label = QLabel(help_html)
            links_label.setObjectName("helpLinks")
            links_font = QFont(APP_UI_FONT_FAMILY, 11)
            links_font.setHintingPreference(QFont.PreferFullHinting)
            links_label.setFont(links_font)
            links_label.setTextFormat(Qt.RichText)
            links_label.setOpenExternalLinks(True)
            links_label.setTextInteractionFlags(Qt.TextBrowserInteraction)
            links_label.setWordWrap(True)
            links_label.setAlignment(Qt.AlignCenter)
            layout.addWidget(links_label)

        button_row = QHBoxLayout()
        close_btn = QPushButton("\u5173\u95ed")
        close_btn.setMinimumWidth(150)
        close_btn.clicked.connect(dialog.accept)
        button_row.addStretch()
        button_row.addWidget(close_btn)
        button_row.addStretch()
        layout.addLayout(button_row)

        dialog.exec()
        if mark_seen:
            self.settings.setValue("startup_help_seen", True)
            self.settings.sync()

    def show_help_dialog(self):
        self.show_shortcut_guide(help_html=self._help_project_links_html())

    def on_sam_toggled(self, checked):
        self.scene.set_sam_enabled(checked)
        self._update_sam_switch_text()
        self._update_help_text(self.scene.mode)
        if checked:
            self._schedule_current_image_sam_analysis()
        else:
            self._cancel_pending_sam_analysis()

    def _set_mode(self, mode):
        self.scene.set_mode(mode)
        mode_name = CanvasMode.get_mode_name(mode)
        self.modeLabel.setText(f"模式: {mode_name}标注")
        self._update_help_text(mode)
        self.update_annotation_stats_status()

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

            self.apply_sam_control_availability()
            self.samPromptInput.setPlaceholderText("点标注模式下不可使用 SAM")
        else:
            self.apply_sam_control_availability()
            self.samPromptInput.setPlaceholderText("输入或选择提示词提取（如: dog）")

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
        add_prompt_action = search_prompt_action = rename_prompt_action = delete_prompt_action = None
        toggle_action = color_action = delete_class_action = None

        kind = item.data(0, Qt.UserRole + 1) if item else ""
        if item is not None:
            menu.addSeparator()
            if kind == "class":
                add_prompt_action = menu.addAction("新增该类提示词")
                visible = item.checkState(0) == Qt.Checked
                toggle_action = menu.addAction("隐藏该标签" if visible else "显示该标签")
                color_action = menu.addAction("修改颜色")
                delete_class_action = menu.addAction("删除标签")
            elif kind == "prompt":
                add_prompt_action = menu.addAction("新增该类提示词")
                search_prompt_action = menu.addAction("用该提示词检索")
                rename_prompt_action = menu.addAction("重命名提示词")
                delete_prompt_action = menu.addAction("删除提示词")
        action = menu.exec(self.listClasses.mapToGlobal(pos))

        if action == new_class_action:
            self.create_class_from_input()
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
                self.samPromptInput.set_single_prompt(cls_name, prompt)
                if self.breathing_highlight_enabled:
                    self._reset_breathing_highlight()
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
            key: value
            for key, value in self.pending_prompt_targets.items()
            if self._pending_prompt_target_label(value) != cls_name
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
        self._notify(f"已删除标签“{cls_name}”", "success")

    def create_prompt_alias_for_item(self, item):
        if item.data(0, Qt.UserRole + 1) == "prompt":
            label = item.data(0, Qt.UserRole + 2)
        else:
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
            self.samPromptInput.set_single_prompt(label, prompt)
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
        self.refresh_prompt_combo()
        self.update_annotation_panel()

    def on_annotation_group_changed(self, index):
        if self.annotation_item_syncing or self._annotation_panel_updates_suspended:
            return
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
                widget.setCurrentItem(item, QItemSelectionModel.NoUpdate)
        finally:
            self.annotation_item_syncing = False

    def populate_file_list(self, dir_path, restore_image_path=""):
        self.current_dir = dir_path
        self.settings.setValue("last_dir", dir_path)
        self.listFiles.clear()
        self._update_file_grid_metrics()
        self.load_classes(dir_path)
        for f in sorted(os.listdir(dir_path)):
            if f.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp')):
                full_path = os.path.join(dir_path, f)
                item = QListWidgetItem(f)
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                item.setCheckState(Qt.Unchecked)
                item.setData(Qt.UserRole, full_path)
                item.setData(Qt.UserRole + 1, f)
                item.setToolTip(full_path)
                icon = self._make_file_thumbnail_icon(full_path)
                if not icon.isNull():
                    item.setIcon(icon)
                item.setTextAlignment(Qt.AlignCenter)
                self.listFiles.addItem(item)
        self.update_file_queue_title()
        if self.listFiles.count() > 0:
            restore_row = 0
            if restore_image_path:
                target_path = os.path.normcase(os.path.abspath(restore_image_path))
                for index in range(self.listFiles.count()):
                    item_path = self._file_item_path(self.listFiles.item(index))
                    if os.path.normcase(os.path.abspath(item_path)) == target_path:
                        restore_row = index
                        break
            self.listFiles.setCurrentRow(restore_row)
            QTimer.singleShot(0, lambda: self.listFiles.scrollToItem(self.listFiles.currentItem())
                              if self.listFiles.currentItem() is not None else None)
        else:
            self.current_image_path = None
            self._update_window_title()
            self.update_annotation_panel()
        QTimer.singleShot(0, self._update_file_grid_metrics)

    def refresh_file_queue(self):
        if not self.current_dir or not os.path.isdir(self.current_dir):
            self._notify("请先打开图片目录", "warning")
            return
        current_path = os.path.abspath(self.current_image_path) if self.current_image_path else ""
        self.populate_file_list(self.current_dir)
        if current_path:
            for index in range(self.listFiles.count()):
                item = self.listFiles.item(index)
                path = os.path.abspath(item.data(Qt.UserRole) or "")
                if path == current_path:
                    self.listFiles.setCurrentRow(index)
                    break
        self._notify("图片队列已刷新", "success")

    def restore_last_session(self):
        last_dir = self.settings.value("last_dir", "", str)
        if last_dir and os.path.isdir(last_dir):
            self.populate_file_list(last_dir, self.settings.value("last_image_path", "", str))

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
        self.edit_shapes_label([shape])

    def edit_shapes_label(self, shapes):
        valid_shapes = [
            shape for shape in shapes
            if isinstance(shape, (RectShape, PolyShape, PointShape, RotatedRectShape)) and shape.scene() is self.scene
        ]
        if not valid_shapes:
            return

        selected_index = self.last_edit_label_index
        first_label = getattr(valid_shapes[0], "label", "")
        if first_label in self.class_list:
            selected_index = self.class_list.index(first_label)

        dialog = LabelEditDialog(self.class_list, selected_index=selected_index, parent=self)
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

        for shape in valid_shapes:
            shape.label = cls_name
            self._apply_shape_label_style(shape, cls_name)
            if hasattr(shape, 'update_label_text'):
                shape.update_label_text(cls_name)
            if hasattr(shape, 'update_label_position'):
                shape.update_label_position(shape)

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
                self._notify("标签名称不能为空", "warning")
                item.setText(0, old_name)
                return

            if new_name in self.class_list:
                self._notify(f"标签“{new_name}”已存在", "warning")
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
            self._notify(f"已将所有“{old_name}”批量改为“{new_name}”", "success")
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
                self._notify("提示词不能为空", "warning")
                item.setText(0, old_prompt)
                return
            aliases = self.prompt_aliases.setdefault(label, [])
            if not aliases:
                aliases.append(old_prompt)
            if new_prompt in aliases and new_prompt != old_prompt:
                self._notify(f"提示词“{new_prompt}”已存在", "warning")
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
        load_failed = False
        if success:
            self.sam_model_loading = False
            self.sam_model_available = True
        elif self.sam_model_loading and self.sam_client.load_worker is None:
            return
        else:
            load_failed = self.sam_model_loading
            self.sam_model_loading = False
            self.sam_model_available = False
        self.apply_sam_control_availability()
        if load_failed:
            self._set_status("SAM3 模型加载失败，智能辅助已禁用", "danger")
            self.show_sam_load_error_dialog(msg)
        if success and self.current_image_path:
            self._set_status("模型已就绪，稍后分析当前图片特征...")
            self._schedule_current_image_sam_analysis()

    def show_sam_load_error_dialog(self, msg):
        error_text = (msg or "未知错误").strip()
        QMessageBox.critical(
            self,
            "SAM3 模型加载失败",
            "SAM3 智能辅助加载失败，已自动禁用。\n\n"
            "错误信息：\n"
            f"{error_text}",
        )

    def on_file_selected(self, current, previous):
        if previous:
            self.auto_save_annotation()

        if current:
            path = current.data(Qt.UserRole) or current.text()
            self._file_queue_check_anchor_row = self.listFiles.row(current)
            if self._file_queue_preserve_multi_selection_once:
                self._file_queue_preserve_multi_selection_once = False
            else:
                self._set_single_checked_file_item(current)
            if self._is_batch_prompt_running():
                self.pending_prompt_targets = {
                    key: value
                    for key, value in self.pending_prompt_targets.items()
                    if isinstance(value, dict) and value.get("batch")
                }
            else:
                self.pending_prompt_targets.clear()
            self.current_image_path = path
            self._update_window_title()
            self.scene.load_image(path)
            self.view.fitInView(self.scene.sceneRect(), Qt.KeepAspectRatio)
            self.load_annotations(path)
            self.update_annotation_panel()

            self.undo_stack.clear()
            self.redo_stack.clear()
            self.push_state()

            if self.sam_client.model:
                if self.samSwitch.isChecked() and self.samSwitch.isEnabled():
                    self._set_status("已切换图片，停止切换后将分析智能特征...", "orange")
                self._schedule_current_image_sam_analysis()
            else:
                self._set_status("等待后台加载模型，稍后将自动分析图片...", "orange")
        else:
            self.current_image_path = None
            self._update_window_title()
            self._cancel_pending_sam_analysis()

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
        if format_type not in ("json", "yolo", "xml"):
            return
        self._format_changed_by_user = True
        self.current_format = format_type
        self.settings.setValue("last_format", format_type)
        self.settings.sync()
        self.formatWidget.set_format(format_type)

        if self.current_image_path:
            self.scene.clear_shapes()
            self.load_annotations(self.current_image_path, allow_format_fallback=False)
            self.update_annotation_panel()
        self._notify(f"当前读写格式已切换为 {format_type.upper()}", "info")

    def _annotation_path_for_format(self, base_path, format_type):
        ext_map = {"json": ".json", "yolo": ".txt", "xml": ".xml"}
        ext = ext_map.get(format_type)
        return base_path + ext if ext else ""

    def _detect_existing_annotation_format(self, base_path, preferred_format):
        candidates = [preferred_format, "yolo", "json", "xml"]
        seen = set()
        for format_type in candidates:
            if format_type in seen:
                continue
            seen.add(format_type)
            path = self._annotation_path_for_format(base_path, format_type)
            if path and os.path.exists(path):
                return format_type
        return preferred_format

    def _apply_annotation_format_from_existing_file(self, format_type):
        if format_type == self.current_format:
            return
        self.current_format = format_type
        self.settings.setValue("last_format", format_type)
        self.settings.sync()
        self.formatWidget.set_format(format_type)

    def load_annotations(self, image_path, allow_format_fallback=True):
        if not self.scene.img_item: return

        img_w = self.scene.img_item.pixmap().width()
        img_h = self.scene.img_item.pixmap().height()
        base_path = os.path.splitext(image_path)[0]
        format_type = self.current_format
        annotation_path = self._annotation_path_for_format(base_path, format_type)

        if allow_format_fallback and not self._format_changed_by_user and annotation_path and not os.path.exists(annotation_path):
            detected_format = self._detect_existing_annotation_format(base_path, format_type)
            if detected_format != format_type:
                self._apply_annotation_format_from_existing_file(detected_format)
                format_type = detected_format

        previous_suspend_state = self._annotation_panel_updates_suspended
        self._annotation_panel_updates_suspended = True
        try:
            if format_type == "json":
                self._load_json(base_path + ".json")
            elif format_type == "yolo":
                self._load_yolo(base_path + ".txt", img_w, img_h)
            elif format_type == "xml":
                self._load_xml(base_path + ".xml")
        finally:
            self._annotation_panel_updates_suspended = previous_suspend_state
        self.scene.update()

    def _add_shape_to_scene(self, shape, label):
        # docstring removed
        if label not in self.class_list:
            # self.class_list.append(label)
            # self.listClasses.addItem(label)
            self.add_class_to_list(label)
            self.save_classes()
        self.scene.addItem(shape)
        self._apply_shape_label_style(shape, label)
        if not self._annotation_panel_updates_suspended:
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
            self._notify("请先在左侧打开图片", "warning")
            return
        shapes_data = Exporter.extract_shapes(self.scene)

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
            self._notify("标注文件已保存", "success")
            print(f"标注文件已保存到: {out_path}")
        except Exception as e:
            self._notify(f"写入失败: {str(e)}", "danger")

    def closeEvent(self, event):
        self.auto_save_annotation()
        if self.current_image_path:
            self.settings.setValue("last_image_path", os.path.abspath(self.current_image_path))
        else:
            self.settings.remove("last_image_path")
        self.settings.sync()
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
            self.toggle_active_label_visibility()
        elif key == Qt.Key_F1:
            self.show_help_dialog()
        elif key == Qt.Key_R:
            self.trigger_sam_prompt()
        elif key == Qt.Key_B:
            self.actionRect.trigger()
        elif key == Qt.Key_P:
            self.actionPoly.trigger()
        elif key == Qt.Key_T:
            self.actionPoint.trigger()
        elif key == Qt.Key_O:
            self.actionRBox.trigger()

        super().keyPressEvent(event)


if __name__ == "__main__":
    app = _STARTUP_APP or QApplication(sys.argv)
    app_icon = _STARTUP_ICON or _load_app_icon()
    splash = _STARTUP_SPLASH
    if splash is None:
        splash = QSplashScreen(_create_startup_splash_pixmap())
        if not app_icon.isNull():
            splash.setWindowIcon(app_icon)
        splash.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        _apply_windows_window_icon(splash)
        splash.show()
        _apply_windows_window_icon(splash)
        app.processEvents()

    window = MainWindow()
    if not app_icon.isNull():
        window.setWindowIcon(app_icon)
    _apply_windows_window_icon(window)
    window.show()
    _apply_windows_window_icon(window)
    app.processEvents()
    QTimer.singleShot(260, lambda: _finish_startup_splash(window))
    sys.exit(app.exec())
