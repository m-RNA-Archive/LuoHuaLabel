import os
import sys

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QToolBar, QListWidget,
    QGraphicsView, QLabel, QLineEdit, QPushButton, QToolButton, QStatusBar, QMenu,
    QSplitter, QListView, QComboBox, QAbstractItemView, QTreeWidget,
    QTabWidget, QSizePolicy
)
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QAction, QActionGroup, QPainter, QColor, QIcon, QPixmap, QPalette
from PySide6.QtSvg import QSvgRenderer


UI_RESOURCE_DIR = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class ToolbarIconSet:
    ICON_FILES = {
        "open": "folder-open.svg",
        "refresh": "refresh.svg",
        "save": "save.svg",
        "rect": "rectangle.svg",
        "poly": "pentagon.svg",
        "point": "point.svg",
        "rbox": "rotate.svg",
        "pulse": "live.svg",
        "panel_left": "panel-left.svg",
        "panel_right": "panel-right.svg",
        "undo": "undo.svg",
        "redo": "redo.svg",
        "help": "help.svg",
        "dataset": "dataset.svg",
        "visible": "eye.svg",
        "invisible": "eye-off.svg",
        "light": "sun.svg",
        "dark": "moon.svg",
        "sam": "prompt.svg",
        "send": "arrow-up.svg",
        "search": "search.svg",
        "format": "format.svg",
    }

    def __init__(self, icon_dir=None):
        self.icon_dir = icon_dir or os.path.join(UI_RESOURCE_DIR, "ui", "icons", "fluent")
        self._cache = {}

    def clear_cache(self):
        self._cache.clear()

    def _default_color(self):
        app = QApplication.instance()
        if app is None:
            return QColor("#f8fafc")
        return app.palette().color(QPalette.ButtonText)

    def icon(self, name, color=None):
        color = QColor(color) if color is not None else self._default_color()
        cache_key = (name, color.name(QColor.HexArgb))
        if cache_key not in self._cache:
            self._cache[cache_key] = self._build_icon(name, color)
        return self._cache[cache_key]

    def pixmap(self, name, size=24, color=None):
        return self.icon(name, color).pixmap(size, size)

    def _build_icon(self, name, color):
        filename = self.ICON_FILES.get(name)
        if not filename:
            return QIcon()
        path = os.path.join(self.icon_dir, filename)
        if not os.path.exists(path):
            return QIcon()
        icon = QIcon()
        for size in (20, 24, 28, 32):
            icon.addPixmap(self._render_pixmap(path, size, color), QIcon.Normal, QIcon.Off)
            disabled = QColor(color)
            disabled.setAlpha(95)
            icon.addPixmap(self._render_pixmap(path, size, disabled), QIcon.Disabled, QIcon.Off)
        return icon

    def _render_pixmap(self, path, size, color):
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.transparent)
        renderer = QSvgRenderer(path)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        renderer.render(painter)
        painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
        painter.fillRect(pixmap.rect(), color)
        painter.end()
        return pixmap


class WheelFormatButton(QPushButton):
    wheel_delta = Signal(int)

    def wheelEvent(self, event):
        self.wheel_delta.emit(event.angleDelta().y())
        event.accept()


class FormatSelectorWidget(QWidget):
    format_changed = Signal(str)
    FORMAT_ITEMS = (("JSON", "json"), ("YOLO", "yolo"), ("XML", "xml"))

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("toolbarField")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self.label = QLabel("标注格式")
        self.label.setObjectName("toolbarFieldLabel")
        self.btn = WheelFormatButton("YOLO")
        self.btn.setObjectName("toolbarSelectButton")
        self.menu = QMenu(self)
        self.act_json = QAction("JSON", self)
        self.act_yolo = QAction("YOLO", self)
        self.act_xml = QAction("XML", self)
        self.menu.addAction(self.act_json)
        self.menu.addAction(self.act_yolo)
        self.menu.addAction(self.act_xml)
        self.btn.setMenu(self.menu)
        layout.addWidget(self.label)
        layout.addWidget(self.btn)
        self.act_json.triggered.connect(lambda: self._on_format_selected("json", "JSON"))
        self.act_yolo.triggered.connect(lambda: self._on_format_selected("yolo", "YOLO"))
        self.act_xml.triggered.connect(lambda: self._on_format_selected("xml", "XML"))
        self.btn.wheel_delta.connect(self._on_wheel_delta)

    def _on_format_selected(self, fmt, text):
        self.btn.setText(text)
        self.format_changed.emit(fmt)

    def set_format(self, fmt):
        text_map = {"json": "JSON", "yolo": "YOLO", "xml": "XML"}
        self.btn.setText(text_map.get(fmt, "YOLO"))

    def wheelEvent(self, event):
        self._on_wheel_delta(event.angleDelta().y())
        event.accept()

    def _on_wheel_delta(self, delta_y):
        current_text = self.btn.text()
        current_index = next(
            (index for index, (text, _fmt) in enumerate(self.FORMAT_ITEMS) if text == current_text),
            1,
        )
        step = -1 if delta_y > 0 else 1
        next_index = (current_index + step) % len(self.FORMAT_ITEMS)
        text, fmt = self.FORMAT_ITEMS[next_index]
        self._on_format_selected(fmt, text)


class ToolbarSpring(QWidget):
    def __init__(self, width=16, parent=None):
        super().__init__(parent)
        self.setObjectName("toolbarSpring")
        self.setFixedWidth(width)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)


class ThemeSelectorWidget(QWidget):
    theme_changed = Signal(str)

    THEME_ORDER = ("light", "dark")
    THEME_TEXT = {
        "light": "\u6d45\u8272\u4e3b\u9898",
        "dark": "\u6df1\u8272\u4e3b\u9898",
    }

    def __init__(self, icons=None, parent=None):
        super().__init__(parent)
        self.icons = icons or ToolbarIconSet()
        self._theme_key = "dark"
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.btn = QToolButton()
        self.btn.setObjectName("toolbarIconButton")
        self.btn.setToolButtonStyle(Qt.ToolButtonIconOnly)
        self.btn.setAutoRaise(False)
        self.btn.setFixedSize(42, 40)
        self.btn.setIconSize(QSize(28, 28))
        layout.addWidget(self.btn)
        self.btn.clicked.connect(self._toggle_theme)
        self.set_theme(self._theme_key)

    def _toggle_theme(self):
        current_index = self.THEME_ORDER.index(self._theme_key)
        next_theme = self.THEME_ORDER[(current_index + 1) % len(self.THEME_ORDER)]
        self.theme_changed.emit(next_theme)

    def set_theme(self, theme_key):
        if theme_key not in self.THEME_ORDER:
            theme_key = "dark"
        self._theme_key = theme_key
        self.btn.setIcon(self.icons.icon(theme_key))
        self.btn.setToolTip(self.THEME_TEXT[theme_key])


class SwitchControl(QWidget):
    toggled = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(50, 26)
        self._checked = False

    def isChecked(self):
        return self._checked

    def setChecked(self, checked):
        if self._checked != checked:
            self._checked = checked
            self.toggled.emit(checked)
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.setChecked(not self._checked)
        super().mouseReleaseEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        if not self.isEnabled():
            track = QColor("#334155")
            knob = QColor("#64748b")
        else:
            track = QColor("#16a34a") if self._checked else QColor("#64748b")
            knob = QColor("#ffffff")
        painter.setBrush(track)
        painter.drawRoundedRect(self.rect(), 13, 13)
        painter.setBrush(knob)
        x = self.width() - 24 if self._checked else 2
        painter.drawEllipse(x, 2, 22, 22)


class CanvasView(QGraphicsView):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setRenderHint(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorUnderMouse)
        self.setAlignment(Qt.AlignCenter)
        self.setFocusPolicy(Qt.StrongFocus)
        self._is_panning = False
        self._pan_start_pos = None

    def wheelEvent(self, event):
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        self.scale(factor, factor)

    def mousePressEvent(self, event):
        self.setFocus()
        if event.button() == Qt.MiddleButton:
            self._is_panning = True
            self._pan_start_pos = event.position().toPoint()
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def keyPressEvent(self, event):
        scene = self.scene()
        if scene is not None:
            scene.keyPressEvent(event)
            if event.isAccepted():
                return
        super().keyPressEvent(event)

    def mouseMoveEvent(self, event):
        if self._is_panning:
            delta = event.position().toPoint() - self._pan_start_pos
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
            self._pan_start_pos = event.position().toPoint()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        scene = self.scene()
        if scene is not None and hasattr(scene, "clear_sam_hover"):
            scene.clear_sam_hover()
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MiddleButton:
            self._is_panning = False
            self.setCursor(Qt.ArrowCursor)
            event.accept()
            return
        super().mouseReleaseEvent(event)


class Ui_MainWindow(object):
    def setupUi(self, MainWindow):
        MainWindow.setWindowTitle("PromptLabel")
        MainWindow.resize(1500, 900)

        self.centralWidget = QWidget(MainWindow)
        self.centralWidget.setObjectName("workspaceRoot")
        self.mainLayout = QHBoxLayout(self.centralWidget)
        self.mainLayout.setContentsMargins(0, 0, 0, 0)
        self.mainLayout.setSpacing(0)
        MainWindow.setCentralWidget(self.centralWidget)

        self.toolBar = QToolBar("命令栏")
        self.toolBar.setObjectName("topCommandBar")
        self.toolBar.setOrientation(Qt.Horizontal)
        self.toolBar.setMovable(False)
        self.icons = ToolbarIconSet()
        self.toolBar.setIconSize(QSize(28, 28))
        self.toolBar.setToolButtonStyle(Qt.ToolButtonIconOnly)
        MainWindow.addToolBar(Qt.TopToolBarArea, self.toolBar)

        self.actionOpen = QAction("打开", MainWindow)
        self.actionOpen.setToolTip("打开图片目录")
        self.actionRefreshFiles = QAction("刷新图片队列", MainWindow)
        self.actionRefreshFiles.setToolTip("重新扫描当前图片目录并刷新左侧图片队列")
        self.actionSave = QAction("保存", MainWindow)
        self.actionSave.setToolTip("保存当前标注")
        self.actionUndo = QAction("撤销", MainWindow)
        self.actionUndo.setToolTip("撤销 (Ctrl+Z)")
        self.actionRedo = QAction("重做", MainWindow)
        self.actionRedo.setToolTip("重做 (Ctrl+Y / Ctrl+Shift+Z)")
        self.actionRect = QAction("矩形", MainWindow)
        self.actionRect.setToolTip("矩形标注 (B)")
        self.actionPoly = QAction("多边形", MainWindow)
        self.actionPoly.setToolTip("多边形标注 (P)")
        self.actionPoint = QAction("点", MainWindow)
        self.actionPoint.setToolTip("点标注 (T)")
        self.actionRBox = QAction("旋转框", MainWindow)
        self.actionRBox.setToolTip("旋转框标注 (O)")
        self.actionBreathingHighlight = QAction("呼吸高亮", MainWindow)
        self.actionBreathingHighlight.setToolTip("让当前标签的标注框填充透明度循环变化，便于在密集标注中定位目标")
        self.actionBreathingHighlight.setCheckable(True)
        self.actionBreathingHighlight.setChecked(True)
        self.actionToggleLeftPanel = QAction("隐藏左侧", MainWindow)
        self.actionToggleLeftPanel.setToolTip("显示或隐藏左侧图片队列")
        self.actionToggleLeftPanel.setCheckable(True)
        self.actionToggleLeftPanel.setChecked(True)
        self.actionToggleRightPanel = QAction("隐藏右侧", MainWindow)
        self.actionToggleRightPanel.setToolTip("显示或隐藏右侧管理面板")
        self.actionToggleRightPanel.setCheckable(True)
        self.actionToggleRightPanel.setChecked(True)

        self.modeGroup = QActionGroup(MainWindow)
        for action in [self.actionRect, self.actionPoly, self.actionPoint, self.actionRBox]:
            action.setCheckable(True)
            self.modeGroup.addAction(action)
        self.actionRect.setChecked(True)

        self.toolBar.addAction(self.actionOpen)
        self.toolBar.addAction(self.actionRefreshFiles)
        self.toolBar.addAction(self.actionSave)
        self.toolBar.addAction(self.actionUndo)
        self.toolBar.addAction(self.actionRedo)
        self.toolBar.addWidget(ToolbarSpring())
        self.toolBar.addAction(self.actionRect)
        self.toolBar.addAction(self.actionPoly)
        self.toolBar.addAction(self.actionPoint)
        self.toolBar.addAction(self.actionRBox)
        self.toolBar.addWidget(ToolbarSpring())
        self.toolbarSpacer = QWidget()
        self.toolbarSpacer.setObjectName("toolbarFlexSpacer")
        self.toolbarSpacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.toolBar.addWidget(self.toolbarSpacer)
        self.formatWidget = FormatSelectorWidget()
        self.toolBar.addWidget(self.formatWidget)
        self.btnDatasetTool = QPushButton("编辑数据集")
        self.btnDatasetTool.setObjectName("toolbarCommandButton")
        self.btnDatasetTool.setIconSize(QSize(24, 24))
        self.btnDatasetTool.setFixedSize(116, 40)
        self.toolBar.addWidget(self.btnDatasetTool)
        self.toolBar.addAction(self.actionToggleLeftPanel)
        self.toolBar.addAction(self.actionToggleRightPanel)
        self.toolBar.addAction(self.actionBreathingHighlight)
        self.themeWidget = ThemeSelectorWidget(self.icons)
        self.toolBar.addWidget(self.themeWidget)
        self.btnHelp = QToolButton()
        self.btnHelp.setObjectName("toolbarIconButton")
        self.btnHelp.setToolButtonStyle(Qt.ToolButtonIconOnly)
        self.btnHelp.setFixedSize(42, 40)
        self.btnHelp.setIconSize(QSize(28, 28))
        self.btnHelp.setToolTip("帮助")
        self.toolBar.addWidget(self.btnHelp)

        self.splitter = QSplitter(Qt.Horizontal)
        self.mainLayout.addWidget(self.splitter)

        self.leftPanel = QWidget()
        self.leftPanel.setObjectName("leftPanel")
        self.leftPanel.setMinimumWidth(148)
        self.leftLayout = QVBoxLayout(self.leftPanel)
        self.leftLayout.setContentsMargins(10, 10, 8, 10)
        self.leftLayout.setSpacing(8)
        self.fileTitle = QLabel("图片队列 (0 张)")
        self.fileTitle.setObjectName("panelTitle")
        self.leftLayout.addWidget(self.fileTitle)
        self.listFiles = QListWidget()
        self.listFiles.setObjectName("fileGrid")
        self.listFiles.setMinimumWidth(124)
        self.listFiles.setViewMode(QListView.IconMode)
        self.listFiles.setResizeMode(QListView.Adjust)
        self.listFiles.setMovement(QListView.Static)
        self.listFiles.setSelectionMode(QAbstractItemView.SingleSelection)
        self.listFiles.setWrapping(True)
        self.listFiles.setIconSize(QSize(132, 132))
        self.listFiles.setGridSize(QSize(148, 172))
        self.listFiles.setWordWrap(True)
        self.leftLayout.addWidget(self.listFiles)

        self.centerPanel = QWidget()
        self.centerPanel.setObjectName("centerPanel")
        self.centerLayout = QVBoxLayout(self.centerPanel)
        self.centerLayout.setContentsMargins(8, 10, 8, 8)
        self.centerLayout.setSpacing(8)
        self.view = CanvasView()
        self.view.setObjectName("canvasView")
        self.centerLayout.addWidget(self.view, 1)

        self.samRow = QWidget()
        self.samRow.setObjectName("samDock")
        self.samRowLayout = QHBoxLayout(self.samRow)
        self.samRowLayout.setContentsMargins(10, 8, 10, 8)
        self.samRowLayout.setSpacing(8)
        self.samSwitch = QToolButton()
        self.samSwitch.setObjectName("samToggleButton")
        self.samSwitch.setText("打开 SAM")
        self.samSwitch.setIconSize(QSize(24, 24))
        self.samSwitch.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.samSwitch.setCheckable(True)
        self.samRowLayout.addWidget(self.samSwitch)
        self.promptLabel = QLabel("提示词")
        self.promptLabel.setObjectName("fieldInlineLabel")
        self.samRowLayout.addWidget(self.promptLabel)
        self.samPromptInput = QComboBox()
        self.samPromptInput.setEditable(True)
        self.samPromptInput.setInsertPolicy(QComboBox.NoInsert)
        self.samPromptInput.lineEdit().setPlaceholderText("输入或选择提示词，如 dog")
        self.samRowLayout.addWidget(self.samPromptInput, 1)
        self.samPromptBtn = QPushButton("提交")
        self.samPromptBtn.setObjectName("primaryButton")
        self.samPromptBtn.setIconSize(QSize(20, 20))
        self.samRowLayout.addWidget(self.samPromptBtn)
        self.samRefBtn = QPushButton("参考查找")
        self.samRefBtn.setIconSize(QSize(20, 20))
        self.samRowLayout.addWidget(self.samRefBtn)
        self.centerLayout.addWidget(self.samRow)

        self.rightPanel = QWidget()
        self.rightPanel.setObjectName("rightPanel")
        self.rightLayout = QVBoxLayout(self.rightPanel)
        self.rightLayout.setContentsMargins(8, 10, 10, 10)
        self.rightLayout.setSpacing(8)
        self.annotationTitle = QLabel("管理面板")
        self.annotationTitle.setObjectName("panelTitle")
        self.activeLabelHeader = QLabel("当前标签: 未选择")
        self.activeLabelHeader.setObjectName("activeLabelHeader")
        self.activeLabelHeader.setVisible(False)

        self.rightLayout.addWidget(self.annotationTitle)

        self.labelPanel = QWidget()
        self.labelPanelLayout = QVBoxLayout(self.labelPanel)
        self.labelPanelLayout.setContentsMargins(0, 0, 0, 0)
        self.labelPanelLayout.setSpacing(6)
        self.listClasses = QTreeWidget()
        self.listClasses.setHeaderHidden(True)
        self.listClasses.setIconSize(QSize(22, 22))
        self.listClasses.setContextMenuPolicy(Qt.CustomContextMenu)
        self.labelPanelLayout.addWidget(self.listClasses)

        self.annotationPanel = QWidget()
        self.annotationPanelLayout = QVBoxLayout(self.annotationPanel)
        self.annotationPanelLayout.setContentsMargins(0, 0, 0, 0)
        self.annotationPanelLayout.setSpacing(6)
        self.annotationToolBox = QTabWidget()
        self.annotationToolBox.setObjectName("annotationTypeTabs")
        self.rectStatsList = QListWidget()
        self.polyStatsList = QListWidget()
        self.pointStatsList = QListWidget()
        self.rboxStatsList = QListWidget()
        for widget in (self.rectStatsList, self.polyStatsList, self.pointStatsList, self.rboxStatsList):
            widget.setObjectName("annotationTypeList")
            widget.setSelectionMode(QAbstractItemView.ExtendedSelection)
            widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.annotationToolBox.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.rectStatsIndex = self.annotationToolBox.addTab(self.rectStatsList, "矩形")
        self.polyStatsIndex = self.annotationToolBox.addTab(self.polyStatsList, "多边形")
        self.pointStatsIndex = self.annotationToolBox.addTab(self.pointStatsList, "点")
        self.rboxStatsIndex = self.annotationToolBox.addTab(self.rboxStatsList, "旋转框")
        self.annotationPanelLayout.addWidget(self.annotationToolBox, 1)

        self.rightTabs = QTabWidget()
        self.rightTabs.setObjectName("rightTabs")
        self.rightTabs.addTab(self.labelPanel, "类别")
        self.rightTabs.addTab(self.annotationPanel, "标注")
        self.rightLayout.addWidget(self.rightTabs, 1)

        self.splitter.addWidget(self.leftPanel)
        self.splitter.addWidget(self.centerPanel)
        self.splitter.addWidget(self.rightPanel)
        self.splitter.setCollapsible(0, True)
        self.splitter.setCollapsible(2, True)
        self.splitter.setSizes([300, 900, 300])

        self.statusBar = QStatusBar()
        MainWindow.setStatusBar(self.statusBar)
        self.annotationStatsLabel = QLabel("统计: 暂无标注")
        self.statusBar.addPermanentWidget(self.annotationStatsLabel)
        self._apply_toolbar_icons()

    def _apply_toolbar_icons(self):
        self.icons.clear_cache()
        self.actionOpen.setIcon(self.icons.icon("open"))
        self.actionSave.setIcon(self.icons.icon("save"))
        self.actionRefreshFiles.setIcon(self.icons.icon("refresh"))
        self.actionUndo.setIcon(self.icons.icon("undo"))
        self.actionRedo.setIcon(self.icons.icon("redo"))
        self.actionRect.setIcon(self.icons.icon("rect"))
        self.actionPoly.setIcon(self.icons.icon("poly"))
        self.actionPoint.setIcon(self.icons.icon("point"))
        self.actionRBox.setIcon(self.icons.icon("rbox"))
        self.actionBreathingHighlight.setIcon(self.icons.icon("pulse"))
        self.actionToggleLeftPanel.setIcon(self.icons.icon("panel_left"))
        self.actionToggleRightPanel.setIcon(self.icons.icon("panel_right"))
        self.btnDatasetTool.setIcon(self.icons.icon("dataset"))
        self.btnHelp.setIcon(self.icons.icon("help"))
        self.samSwitch.setIcon(self.icons.icon("sam"))
        self.samPromptBtn.setIcon(self.icons.icon("send"))
        self.samRefBtn.setIcon(self.icons.icon("search"))
        if hasattr(self, "themeWidget"):
            self.themeWidget.set_theme(self.themeWidget._theme_key)
