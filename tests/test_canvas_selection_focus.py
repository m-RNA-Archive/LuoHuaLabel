import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QCursor, QPixmap
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QGraphicsPixmapItem

import main
from core.shapes import RectShape


class CanvasSelectionFocusTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        directory = self.stack.enter_context(tempfile.TemporaryDirectory())
        self.stack.enter_context(patch.object(main, 'SETTINGS_PATH', str(Path(directory) / 'test.ini')))
        for method in ('load_sam_model_or_prompt', '_schedule_startup_help_once', 'restore_last_session'):
            self.stack.enter_context(patch.object(main.MainWindow, method))
        self.stack.enter_context(patch('core.sam_client.SamInferenceWorker.start'))
        self.window = main.MainWindow()
        self.addCleanup(self.window.close)
        self.window.show()
        self.window.activateWindow()
        self.window.samPromptInput.setEnabled(True)
        self.app.processEvents()
        self.scene = self.window.scene
        self.view = self.window.view
        pixmap = QPixmap(500, 400)
        pixmap.fill(Qt.white)
        self.scene.img_item = QGraphicsPixmapItem(pixmap)
        self.scene.addItem(self.scene.img_item)
        self.scene.setSceneRect(0, 0, 500, 400)
        self.shapes = [RectShape(QRectF(50, 50, 50, 50)), RectShape(QRectF(180, 50, 50, 50))]
        for shape in self.shapes:
            self.scene.addItem(shape)
        self.window.update_annotation_panel()

    def drag_from_focus(self, focused):
        self.scene.clearSelection()
        focused.setFocus()
        start = self.view.mapFromScene(QPointF(20, 20))
        end = self.view.mapFromScene(QPointF(250, 120))
        QCursor.setPos(self.view.viewport().mapToGlobal(start))
        self.app.processEvents()
        self.assertTrue(focused.hasFocus())
        QTest.keyPress(focused, Qt.Key_G)
        self.assertTrue(self.view.hasFocus())
        QTest.mousePress(self.view.viewport(), Qt.LeftButton, Qt.NoModifier, start)
        QTest.mouseMove(self.view.viewport(), end, 30)
        self.app.processEvents()
        QTest.mouseRelease(self.view.viewport(), Qt.LeftButton, Qt.NoModifier, end)
        QTest.keyRelease(self.app.focusWidget(), Qt.Key_G)
        self.app.processEvents()
        self.assertEqual(set(self.scene.selectedItems()), set(self.shapes))
        self.assertEqual(len(self.window.rectStatsList.selectedItems()), 2)
        self.assertFalse(self.scene._g_selection_pressed)

    def test_g_from_list_and_canvas_focus(self):
        self.drag_from_focus(self.window.rectStatsList)
        self.drag_from_focus(self.view)

    def test_g_remains_text_with_sam_focus(self):
        editor = self.window.samPromptInput.input
        editor.setFocus()
        QCursor.setPos(editor.mapToGlobal(editor.rect().center()))
        self.app.processEvents()
        self.assertTrue(editor.hasFocus())
        for target in (editor.viewport(), self.view.viewport()):
            QCursor.setPos(target.mapToGlobal(target.rect().center()))
            self.app.processEvents()
            editor.clear()
            QTest.keyClicks(editor, 'g')
            self.assertEqual(editor.toPlainText(), 'g')
            self.assertTrue(editor.hasFocus())
            self.assertFalse(self.scene._g_selection_pressed)


if __name__ == '__main__':
    unittest.main()
