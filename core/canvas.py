# -*- coding: utf-8 -*-
from PySide6.QtWidgets import QApplication, QGraphicsScene, QGraphicsPixmapItem, QGraphicsLineItem, QGraphicsRectItem
from PySide6.QtGui import QPixmap, QPolygonF, QPen, QColor, QBrush, QPainterPath
from PySide6.QtCore import Qt, QPointF, Signal, QRectF
from core.shapes import RectShape, PolyShape, PointShape, RotatedRectShape, HandleItem, color_for_label


class CanvasMode:
    EDIT = 0
    RECT = 1
    POLY = 2
    POINT = 3
    RBOX = 4

    @staticmethod
    def get_mode_name(mode):
        names = {1: "矩形", 2: "多边形", 3: "点", 4: "旋转框"}
        return names.get(mode, "未知")


class Canvas(QGraphicsScene):
    mouse_moved = Signal(int, int)
    shape_drawn = Signal(object)
    shape_double_clicked = Signal(object)
    state_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.mode = CanvasMode.RECT
        self.img_item = None
        self.sam_client = None
        self.sam_enabled = False

        self.drawing = False
        self.start_pt = None
        self.temp_item = None
        self.poly_pts = []
        self._selection_start = None
        self._selection_screen_start = None
        self._selection_before = set()
        self._selection_item = None

        # 智能悬停提示图层
        self.sam_hover_item = None
        self.sam_hover_active = False

        self.h_line = QGraphicsLineItem()
        self.v_line = QGraphicsLineItem()
        crosshair_pen = QPen(QColor(255, 255, 255, 200), 1, Qt.DashLine)
        self.h_line.setPen(crosshair_pen)
        self.v_line.setPen(crosshair_pen)
        self.h_line.setZValue(9999)
        self.v_line.setZValue(9999)
        self.h_line.hide()
        self.v_line.hide()
        self.addItem(self.h_line)
        self.addItem(self.v_line)

    def load_image(self, path):
        self.clear_shapes()
        pixmap = QPixmap(path)
        if self.img_item:
            self.removeItem(self.img_item)
        self.img_item = QGraphicsPixmapItem(pixmap)
        self.addItem(self.img_item)
        self.setSceneRect(pixmap.rect())
        self.h_line.show()
        self.v_line.show()

    def clear_shapes(self):
        self.cancel_drawing()
        for item in self.items():
            if isinstance(item, (RectShape, PolyShape, PointShape, RotatedRectShape)):
                self.removeItem(item)

    def set_mode(self, mode):
        self.mode = mode
        self.cancel_drawing()
        for item in self.selectedItems():
            item.setSelected(False)

    def set_sam_enabled(self, enabled):
        self.sam_enabled = enabled
        if not enabled:
            self.clear_sam_hover()

    def clear_sam_hover(self):
        self.sam_hover_active = False
        if self.sam_hover_item:
            self.removeItem(self.sam_hover_item)
            self.sam_hover_item = None

    def is_inside_image(self, pt):
        if not self.img_item: return False
        return self.sceneRect().contains(pt)

    def clamp_point(self, pt):
        rect = self.sceneRect()
        x = max(rect.left(), min(pt.x(), rect.right()))
        y = max(rect.top(), min(pt.y(), rect.bottom()))
        return QPointF(x, y)

    def update_crosshair(self, pt):
        if self.img_item:
            rect = self.sceneRect()
            x = max(rect.left(), min(pt.x(), rect.right()))
            y = max(rect.top(), min(pt.y(), rect.bottom()))
            self.h_line.setLine(rect.left(), y, rect.right(), y)
            self.v_line.setLine(x, rect.top(), x, rect.bottom())
            self.mouse_moved.emit(int(x), int(y))

    def get_active_label(self):
        parent = self.parent()
        if parent is None:
            return ""
        return getattr(parent, "active_label", "") or ""

    def get_active_color(self):
        label = self.get_active_label()
        parent = self.parent()
        if parent is not None:
            class_colors = getattr(parent, "class_colors", {})
            if label and label in class_colors:
                return QColor(class_colors[label])
        return color_for_label(label)

    def apply_preview_style(self, item):
        color = self.get_active_color()
        if isinstance(item, QGraphicsRectItem):
            item.setPen(QPen(color, 2, Qt.DashLine))
            item.setBrush(QBrush(QColor(color.red(), color.green(), color.blue(), 50)))
            return
        if hasattr(item, "setPen") and not isinstance(item, RotatedRectShape):
            item.setPen(QPen(color, 2, Qt.DashLine))
        if hasattr(item, "setBrush") and not isinstance(item, RotatedRectShape):
            item.setBrush(QBrush(QColor(color.red(), color.green(), color.blue(), 50)))
        if isinstance(item, RotatedRectShape):
            item.rect_item.setPen(QPen(color, 2, Qt.DashLine))
            item.rect_item.setBrush(QBrush(QColor(color.red(), color.green(), color.blue(), 50)))
            item.rotate_line.setPen(QPen(color, 1.5, Qt.DashLine))

    def mouseMoveEvent(self, event):
        pt = event.scenePos()
        self.update_crosshair(pt)
        if self._selection_start is not None:
            self._update_selection(event)
            event.accept()
            return
        super().mouseMoveEvent(event)
        clamped_pt = self.clamp_point(pt)

        # ---------------- SAM 智能辅助悬停 ----------------
        # 将 RBOX 加入 SAM 支持的模式列表
        if self.sam_enabled and self.is_inside_image(pt) and self.mode in [CanvasMode.RECT, CanvasMode.POLY,
                                                                           CanvasMode.RBOX]:
            self.sam_hover_active = True
            if self.sam_client:
                self.sam_client.request_inference(clamped_pt.x(), clamped_pt.y(), is_click=False)
            return
        elif self.sam_hover_item or self.sam_hover_active:
            self.clear_sam_hover()

        # ---------------- 常规绘图 ----------------
        if self.drawing and self.start_pt:
            rect = QRectF(min(self.start_pt.x(), clamped_pt.x()), min(self.start_pt.y(), clamped_pt.y()),
                          abs(clamped_pt.x() - self.start_pt.x()), abs(clamped_pt.y() - self.start_pt.y()))
            if self.temp_item: self.removeItem(self.temp_item)

            if self.mode == CanvasMode.RECT:
                self.temp_item = QGraphicsRectItem(rect)
                self.temp_item.is_temp = True
                self.apply_preview_style(self.temp_item)

            # 手动拉框时，调用全新的 RotatedRectShape 参数格式
            elif self.mode == CanvasMode.RBOX:
                cx, cy = rect.center().x(), rect.center().y()
                w, h = max(1, rect.width()), max(1, rect.height())
                self.temp_item = RotatedRectShape(cx, cy, w, h, 0, is_temp=True)
                self.apply_preview_style(self.temp_item)

            self.addItem(self.temp_item)

        elif self.mode == CanvasMode.POLY and not self.sam_enabled and len(self.poly_pts) > 0:
            self.update_temp_poly(mouse_pos=clamped_pt)

    def handle_sam_result(self, poly_pts, rect_xywh, rect_obb, score, is_click):
        """处理来自 SAM 后台的推理结果，正确区分矩形、多边形和旋转框"""
        # 支持 RBOX
        if self._selection_start is not None or not self.sam_enabled or self.mode not in [CanvasMode.RECT, CanvasMode.POLY, CanvasMode.RBOX]:
            return

        if not is_click and not self.sam_hover_active:
            return

        old_hover_active = self.sam_hover_active
        self.clear_sam_hover()
        if not is_click:
            self.sam_hover_active = old_hover_active

        if not poly_pts or not rect_xywh:
            return

        # ---- 模式判断：矩形智能框 / 多边形点选 / 旋转框 ----
        if self.mode == CanvasMode.RECT:
            x, y, w, h = rect_xywh
            rect = QRectF(x, y, w, h)

            if is_click:
                shape = RectShape(rect)
                self.shape_drawn.emit(shape)
            else:
                self.sam_hover_item = QGraphicsRectItem(rect)
                self.apply_preview_style(self.sam_hover_item)
                self.addItem(self.sam_hover_item)
                self.sam_hover_active = True

        elif self.mode == CanvasMode.POLY:
            qpts = [QPointF(p[0], p[1]) for p in poly_pts]
            if is_click:
                shape = PolyShape(QPolygonF(qpts))
                self.shape_drawn.emit(shape)
            else:
                self.sam_hover_item = PolyShape(QPolygonF(qpts), is_temp=True)
                self.apply_preview_style(self.sam_hover_item)
                self.addItem(self.sam_hover_item)
                self.sam_hover_active = True

        # SAM 的 OBB 旋转框处理分支
        elif self.mode == CanvasMode.RBOX:
            if not rect_obb or len(rect_obb) < 5: return
            cx, cy, w, h, angle = rect_obb

            if is_click:
                shape = RotatedRectShape(cx, cy, w, h, angle)
                self.shape_drawn.emit(shape)
            else:
                self.sam_hover_item = RotatedRectShape(cx, cy, w, h, angle, is_temp=True)
                self.apply_preview_style(self.sam_hover_item)
                self.addItem(self.sam_hover_item)
                self.sam_hover_active = True

    def mousePressEvent(self, event):
        pt = event.scenePos()
        clamped_pt = self.clamp_point(pt)
        if event.button() == Qt.LeftButton and event.modifiers() & (Qt.ControlModifier | Qt.AltModifier):
            self.cancel_drawing()
            if self.img_item is not None:
                self._selection_start = QPointF(pt)
                self._selection_screen_start = event.screenPos()
                self._selection_before = set(self.selectedItems())
            event.accept()
            return
        if self._selection_start is not None:
            event.accept()
            return

        # ---------------- SAM 确认生成 ----------------
        # 支持 RBOX
        if self.sam_enabled and event.button() == Qt.LeftButton and self.mode in [CanvasMode.RECT, CanvasMode.POLY,
                                                                                  CanvasMode.RBOX]:
            if self.is_inside_image(pt) and self.sam_client:
                self.sam_client.request_inference(clamped_pt.x(), clamped_pt.y(), is_click=True)
            return

        items = self.items(clamped_pt)
        clicked_item = None
        for item in items:
            if isinstance(item, HandleItem) and item.isVisible():
                if not getattr(item.parentItem(), 'is_temp', False):
                    clicked_item = item
                    break
        if not clicked_item:
            for item in items:
                if isinstance(item, (PolyShape, RectShape, PointShape, RotatedRectShape)):
                    if not getattr(item, 'is_temp', False):
                        clicked_item = item
                        break

        if clicked_item and not self.sam_enabled:
            super().mousePressEvent(event)
            if event.button() == Qt.LeftButton:
                if not (event.modifiers() & (Qt.ControlModifier | Qt.ShiftModifier)):
                    for item in self.selectedItems():
                        if item != clicked_item and item != clicked_item.parentItem():
                            item.setSelected(False)
                    if isinstance(clicked_item, HandleItem):
                        clicked_item.parentItem().setSelected(True)
                    else:
                        clicked_item.setSelected(True)
            return

        # ---------------- 常规绘图起点 ----------------
        if not self.is_inside_image(pt) and not self.drawing: return
        if event.button() == Qt.LeftButton:
            if self.mode in [CanvasMode.RECT, CanvasMode.RBOX]:
                self.drawing = True
                self.start_pt = clamped_pt
            elif self.mode == CanvasMode.POLY:
                if len(self.poly_pts) > 2:
                    dist = ((clamped_pt.x() - self.poly_pts[0].x()) ** 2 + (
                            clamped_pt.y() - self.poly_pts[0].y()) ** 2) ** 0.5
                    if dist < 10:
                        self.finish_poly_shape()
                        return
                self.poly_pts.append(clamped_pt)
                self.update_temp_poly()
            elif self.mode == CanvasMode.POINT:
                shape = PointShape(clamped_pt)
                self.shape_drawn.emit(shape)
        elif event.button() == Qt.RightButton:
            if self.mode == CanvasMode.POLY and len(self.poly_pts) > 2:
                self.finish_poly_shape()

    def mouseReleaseEvent(self, event):
        if self._selection_start is not None:
            if event.button() == Qt.LeftButton:
                self._update_selection(event)
                if self._selection_item is None:
                    for item in self.items(self._selection_start):
                        while item is not None and not self._is_annotation(item):
                            item = item.parentItem()
                        if item is not None:
                            item.setSelected(not item.isSelected())
                            break
                self._finish_selection()
            event.accept()
            return
        super().mouseReleaseEvent(event)
        if self.sam_enabled: return

        if event.button() == Qt.LeftButton and self.drawing:
            self.drawing = False
            if self.temp_item:
                pt = self.clamp_point(event.scenePos())
                rect = QRectF(min(self.start_pt.x(), pt.x()), min(self.start_pt.y(), pt.y()),
                              abs(pt.x() - self.start_pt.x()), abs(pt.y() - self.start_pt.y()))
                self.removeItem(self.temp_item)
                self.temp_item = None

                if rect.width() > 5 and rect.height() > 5:
                    if self.mode == CanvasMode.RECT:
                        self.shape_drawn.emit(RectShape(rect))

                    # 手动松开鼠标完成绘制时，实例化新的 RotatedRectShape
                    elif self.mode == CanvasMode.RBOX:
                        cx, cy = rect.center().x(), rect.center().y()
                        w, h = rect.width(), rect.height()
                        self.shape_drawn.emit(RotatedRectShape(cx, cy, w, h, 0))

        self.state_changed.emit()

    def mouseDoubleClickEvent(self, event):
        if self._selection_start is not None or event.modifiers() & (Qt.ControlModifier | Qt.AltModifier):
            self.mousePressEvent(event)
            return
        pt = event.scenePos()
        if not self.is_inside_image(pt): return

        for item in self.items(pt):
            if isinstance(item, (HandleItem, PolyShape, RectShape, PointShape, RotatedRectShape)) and not getattr(item,
                                                                                                                  'is_temp',
                                                                                                                  False):
                shape_item = item.parentItem() if isinstance(item, HandleItem) else item
                self.shape_double_clicked.emit(shape_item)
                return

        if event.button() == Qt.LeftButton and self.mode == CanvasMode.POLY and not self.sam_enabled and len(
                self.poly_pts) > 2:
            self.finish_poly_shape()
        else:
            super().mouseDoubleClickEvent(event)

    def update_temp_poly(self, mouse_pos=None):
        display_pts = self.poly_pts.copy()
        if mouse_pos is not None: display_pts.append(mouse_pos)
        if len(display_pts) < 2:
            if self.temp_item: self.removeItem(self.temp_item); self.temp_item = None
            return
        if self.temp_item and isinstance(self.temp_item, PolyShape):
            self.temp_item.setPolygon(QPolygonF(display_pts))
        else:
            if self.temp_item: self.removeItem(self.temp_item)
            self.temp_item = PolyShape(QPolygonF(display_pts), is_temp=True)
            self.apply_preview_style(self.temp_item)
            self.addItem(self.temp_item)

    def finish_poly_shape(self):
        shape = PolyShape(QPolygonF(self.poly_pts))
        self.poly_pts.clear()
        if self.temp_item:
            self.removeItem(self.temp_item)
            self.temp_item = None
        self.shape_drawn.emit(shape)

    @staticmethod
    def _is_annotation(item):
        return isinstance(item, (RectShape, PolyShape, PointShape, RotatedRectShape)) and not getattr(item, 'is_temp', False)

    def _update_selection(self, event):
        if self._selection_item is None:
            if (event.screenPos() - self._selection_screen_start).manhattanLength() < QApplication.startDragDistance():
                return
            self._selection_item = QGraphicsRectItem()
            pen = QPen(QColor(28, 126, 214), 1, Qt.DashLine)
            pen.setCosmetic(True)
            self._selection_item.setPen(pen)
            self._selection_item.setBrush(QColor(28, 126, 214, 30))
            self._selection_item.setAcceptedMouseButtons(Qt.NoButton)
            self._selection_item.setZValue(10000)
            self.addItem(self._selection_item)
        rect = QRectF(self._selection_start, event.scenePos()).normalized()
        self._selection_item.setRect(rect)
        hits = set(self.items(rect, Qt.IntersectsItemShape))
        selection_path = QPainterPath()
        selection_path.addRect(rect)
        for item in self.items():
            if self._is_annotation(item):
                hit = item in hits
                if isinstance(item, RotatedRectShape):
                    hit = selection_path.intersects(item.rect_item.mapToScene(item.rect_item.shape()))
                item.setSelected(item in self._selection_before or hit)

    def _finish_selection(self, restore=False):
        if self._selection_start is None:
            return
        if restore:
            for item in self.items():
                if self._is_annotation(item):
                    item.setSelected(item in self._selection_before)
        if self._selection_item is not None:
            self.removeItem(self._selection_item)
        self._selection_item = None
        self._selection_start = None
        self._selection_screen_start = None
        self._selection_before.clear()

    def cancel_drawing(self):
        self._finish_selection(restore=True)
        self.drawing = False
        self.poly_pts.clear()
        if self.temp_item:
            self.removeItem(self.temp_item)
            self.temp_item = None
        self.clear_sam_hover()

    def keyPressEvent(self, event):
        key = event.key()
        modifiers = event.modifiers()
        if self._selection_start is not None:
            if key == Qt.Key_Escape:
                self.cancel_drawing()
            event.accept()
            return

        if key == Qt.Key_Backspace or key == Qt.Key_Delete:
            for item in self.selectedItems():
                self.removeItem(item)
            self.state_changed.emit()
        elif key == Qt.Key_Z and modifiers == Qt.ControlModifier:
            if self.mode == CanvasMode.POLY and not self.sam_enabled and len(self.poly_pts) > 0:
                self.poly_pts.pop()
                self.update_temp_poly()
        elif key == Qt.Key_Return or key == Qt.Key_Enter:
            if self.mode == CanvasMode.POLY and len(self.poly_pts) > 2:
                self.finish_poly_shape()
        elif key == Qt.Key_Escape:
            self.cancel_drawing()
        elif key in [Qt.Key_Z, Qt.Key_X, Qt.Key_C, Qt.Key_V]:
            items = self.selectedItems()
            if items and isinstance(items[0], RotatedRectShape):
                delta = 0
                if key == Qt.Key_Z:
                    delta = -5
                elif key == Qt.Key_X:
                    delta = -1
                elif key == Qt.Key_C:
                    delta = 1
                elif key == Qt.Key_V:
                    delta = 5
                if delta != 0:
                    item = items[0]
                    item.setRotation(item.rotation() + delta)
                    self.state_changed.emit()

        super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        super().keyReleaseEvent(event)

    def focusOutEvent(self, event):
        self._finish_selection(restore=True)
        super().focusOutEvent(event)
