from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QToolBar, QListWidget,
    QGraphicsView, QLabel, QLineEdit, QPushButton, QStatusBar, QMenu,
    QSplitter, QListView, QToolBox, QComboBox, QAbstractItemView, QTreeWidget,
    QTabWidget
)
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QAction, QActionGroup, QPainter, QColor


class FormatSelectorWidget(QWidget):
    format_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("toolbarField")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self.label = QLabel("标注格式")
        self.label.setObjectName("toolbarFieldLabel")
        self.btn = QPushButton("YOLO")
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

    def _on_format_selected(self, fmt, text):
        self.btn.setText(text)
        self.format_changed.emit(fmt)

    def set_format(self, fmt):
        text_map = {"json": "JSON", "yolo": "YOLO", "xml": "XML"}
        self.btn.setText(text_map.get(fmt, "YOLO"))


class ThemeSelectorWidget(QWidget):
    theme_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("toolbarField")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self.label = QLabel("主题")
        self.label.setObjectName("toolbarFieldLabel")
        self.combo = QComboBox()
        self.combo.setObjectName("toolbarThemeCombo")
        self.combo.addItem("跟随系统", "system")
        self.combo.addItem("浅色", "light")
        self.combo.addItem("深色", "dark")
        layout.addWidget(self.label)
        layout.addWidget(self.combo)
        self.combo.currentIndexChanged.connect(lambda _: self.theme_changed.emit(self.combo.currentData()))

    def set_theme(self, theme_key):
        for i in range(self.combo.count()):
            if self.combo.itemData(i) == theme_key:
                self.combo.setCurrentIndex(i)
                return


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

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MiddleButton:
            self._is_panning = False
            self.setCursor(Qt.ArrowCursor)
            event.accept()
            return
        super().mouseReleaseEvent(event)


class Ui_MainWindow(object):
    def setupUi(self, MainWindow):
        MainWindow.setWindowTitle("LuoHuaLabel")
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
        self.toolBar.setIconSize(QSize(16, 16))
        self.toolBar.setToolButtonStyle(Qt.ToolButtonTextOnly)
        MainWindow.addToolBar(Qt.TopToolBarArea, self.toolBar)

        self.actionOpen = QAction("打开目录", MainWindow)
        self.actionOpen.setToolTip("打开图片目录")
        self.actionSave = QAction("保存", MainWindow)
        self.actionSave.setToolTip("保存当前标注 (Ctrl+S)")
        self.actionRect = QAction("矩形", MainWindow)
        self.actionRect.setToolTip("矩形标注 (R)")
        self.actionPoly = QAction("多边形", MainWindow)
        self.actionPoly.setToolTip("多边形标注 (P)")
        self.actionPoint = QAction("点", MainWindow)
        self.actionPoint.setToolTip("点标注 (T)")
        self.actionRBox = QAction("旋转框", MainWindow)
        self.actionRBox.setToolTip("旋转框标注 (O)")
        self.actionBreathingHighlight = QAction("呼吸高亮", MainWindow)
        self.actionBreathingHighlight.setToolTip("开关标注框内部透明度呼吸高亮")
        self.actionBreathingHighlight.setCheckable(True)
        self.actionBreathingHighlight.setChecked(True)
        self.actionToggleRightPanel = QAction("右侧面板", MainWindow)
        self.actionToggleRightPanel.setToolTip("显示或隐藏右侧管理面板")
        self.actionToggleRightPanel.setCheckable(True)
        self.actionToggleRightPanel.setChecked(True)

        self.modeGroup = QActionGroup(MainWindow)
        for action in [self.actionRect, self.actionPoly, self.actionPoint, self.actionRBox]:
            action.setCheckable(True)
            self.modeGroup.addAction(action)
        self.actionRect.setChecked(True)

        self.toolBar.addAction(self.actionOpen)
        self.toolBar.addAction(self.actionSave)
        self.toolBar.addSeparator()
        self.toolBar.addAction(self.actionRect)
        self.toolBar.addAction(self.actionPoly)
        self.toolBar.addAction(self.actionPoint)
        self.toolBar.addAction(self.actionRBox)
        self.toolBar.addAction(self.actionBreathingHighlight)
        self.toolBar.addSeparator()
        self.formatWidget = FormatSelectorWidget()
        self.toolBar.addWidget(self.formatWidget)
        self.themeWidget = ThemeSelectorWidget()
        self.toolBar.addWidget(self.themeWidget)
        self.toolBar.addSeparator()
        self.toolBar.addAction(self.actionToggleRightPanel)
        self.btnDatasetTool = QPushButton("数据集处理")
        self.btnDatasetTool.setObjectName("toolbarCommandButton")
        self.toolBar.addWidget(self.btnDatasetTool)
        self.btnHelp = QPushButton("帮助")
        self.btnHelp.setObjectName("toolbarCommandButton")
        self.toolBar.addWidget(self.btnHelp)

        self.splitter = QSplitter(Qt.Horizontal)
        self.mainLayout.addWidget(self.splitter)

        self.leftPanel = QWidget()
        self.leftPanel.setObjectName("leftPanel")
        self.leftLayout = QVBoxLayout(self.leftPanel)
        self.leftLayout.setContentsMargins(10, 10, 8, 10)
        self.leftLayout.setSpacing(8)
        self.fileTitle = QLabel("图片队列")
        self.fileTitle.setObjectName("panelTitle")
        self.fileHint = QLabel("打开目录后显示图片")
        self.fileHint.setObjectName("panelHint")
        self.leftLayout.addWidget(self.fileTitle)
        self.leftLayout.addWidget(self.fileHint)
        self.listFiles = QListWidget()
        self.listFiles.setObjectName("fileGrid")
        self.listFiles.setViewMode(QListView.IconMode)
        self.listFiles.setResizeMode(QListView.Adjust)
        self.listFiles.setMovement(QListView.Static)
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
        self.samTitle = QLabel("SAM")
        self.samTitle.setObjectName("samTitle")
        self.samRowLayout.addWidget(self.samTitle)
        self.samSwitch = SwitchControl()
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
        self.samRowLayout.addWidget(self.samPromptBtn)
        self.samRefBtn = QPushButton("参考查找")
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
        self.labelTitle = QLabel("标签")
        self.labelTitle.setObjectName("rightSectionTitle")
        self.annotationListTitle = QLabel("标注列表")
        self.annotationListTitle.setObjectName("rightSectionTitle")

        self.rightLayout.addWidget(self.annotationTitle)
        self.rightLayout.addWidget(self.activeLabelHeader)

        self.labelPanel = QWidget()
        self.labelPanelLayout = QVBoxLayout(self.labelPanel)
        self.labelPanelLayout.setContentsMargins(0, 0, 0, 0)
        self.labelPanelLayout.setSpacing(6)
        self.labelPanelLayout.addWidget(self.labelTitle)
        self.listClasses = QTreeWidget()
        self.listClasses.setHeaderHidden(True)
        self.listClasses.setContextMenuPolicy(Qt.CustomContextMenu)
        self.labelPanelLayout.addWidget(self.listClasses)

        self.annotationPanel = QWidget()
        self.annotationPanelLayout = QVBoxLayout(self.annotationPanel)
        self.annotationPanelLayout.setContentsMargins(0, 0, 0, 0)
        self.annotationPanelLayout.setSpacing(6)
        self.annotationPanelLayout.addWidget(self.annotationListTitle)
        self.annotationToolBox = QToolBox()
        self.annotationToolBox.setObjectName("annotationToolBox")
        self.rectStatsList = QListWidget()
        self.polyStatsList = QListWidget()
        self.pointStatsList = QListWidget()
        self.rboxStatsList = QListWidget()
        for widget in (self.rectStatsList, self.polyStatsList, self.pointStatsList, self.rboxStatsList):
            widget.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.rectStatsIndex = self.annotationToolBox.addItem(self.rectStatsList, "矩形标注")
        self.polyStatsIndex = self.annotationToolBox.addItem(self.polyStatsList, "多边形标注")
        self.pointStatsIndex = self.annotationToolBox.addItem(self.pointStatsList, "点标注")
        self.rboxStatsIndex = self.annotationToolBox.addItem(self.rboxStatsList, "旋转框标注")
        self.annotationPanelLayout.addWidget(self.annotationToolBox)

        self.rightTabs = QTabWidget()
        self.rightTabs.setObjectName("rightTabs")
        self.rightTabs.addTab(self.labelPanel, "类别")
        self.rightTabs.addTab(self.annotationPanel, "标注")
        self.rightLayout.addWidget(self.rightTabs, 1)

        self.splitter.addWidget(self.leftPanel)
        self.splitter.addWidget(self.centerPanel)
        self.splitter.addWidget(self.rightPanel)
        self.splitter.setCollapsible(2, True)
        self.splitter.setSizes([240, 960, 300])

        self.statusBar = QStatusBar()
        MainWindow.setStatusBar(self.statusBar)
        self.coordLabel = QLabel("坐标: X: 0, Y: 0")
        self.statusBar.addPermanentWidget(self.coordLabel)
