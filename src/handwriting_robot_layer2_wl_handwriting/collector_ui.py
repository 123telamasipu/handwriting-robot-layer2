from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import QEvent, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QAction,
    QCloseEvent,
    QColor,
    QFont,
    QKeySequence,
    QMouseEvent,
    QPainter,
    QPen,
    QTabletEvent,
)
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from .charset import CharacterEntry, find_character
from .models import RecordingBuffer, StrokePoint, strokes_from_document
from .storage import SampleStore


class WriterDialog(QDialog):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("选择书写者")
        self.setMinimumWidth(360)
        self.writer_id = QLineEdit("user_01")
        self.writer_name = QLineEdit()
        self.writer_name.setPlaceholderText("例如：张三")

        form = QFormLayout()
        form.addRow("书写者编号：", self.writer_id)
        form.addRow("姓名或备注：", self.writer_name)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._accept_if_valid)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def _accept_if_valid(self) -> None:
        if not self.writer_id.text().strip():
            QMessageBox.warning(self, "缺少编号", "请输入书写者编号。")
            return
        self.accept()


class TabletCanvas(QWidget):
    changed = Signal()
    stroke_finished = Signal()
    device_changed = Signal(str)
    tablet_identified = Signal(dict)

    def __init__(
        self, parent: Optional[QWidget] = None, allow_mouse: bool = True
    ) -> None:
        super().__init__(parent)
        self.buffer = RecordingBuffer()
        self._tablet_active = False
        self._mouse_active = False
        self._show_grid = True
        self._allow_mouse = allow_mouse
        self._reported_tablet = False
        self.setMinimumSize(520, 520)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def set_show_grid(self, enabled: bool) -> None:
        self._show_grid = enabled
        self.update()

    def load_document(self, document: Optional[dict]) -> None:
        if document:
            self.buffer.replace(strokes_from_document(document))
        else:
            self.buffer.clear()
        self.update()
        self.changed.emit()

    def undo(self) -> None:
        if self.buffer.undo():
            self.update()
            self.changed.emit()

    def clear_canvas(self) -> None:
        self.buffer.clear()
        self.update()
        self.changed.emit()

    def drawing_rect(self) -> QRectF:
        margin = 18.0
        side = max(1.0, min(self.width(), self.height()) - margin * 2)
        left = (self.width() - side) / 2
        top = (self.height() - side) / 2
        return QRectF(left, top, side, side)

    def _normalized_position(self, position: QPointF) -> Optional[QPointF]:
        rect = self.drawing_rect()
        if not rect.contains(position):
            return None
        return QPointF(
            (position.x() - rect.left()) / rect.width(),
            (position.y() - rect.top()) / rect.height(),
        )

    def _point(
        self,
        position: QPointF,
        pressure: float,
        source: str,
        x_tilt: float = 0.0,
        y_tilt: float = 0.0,
        rotation: float = 0.0,
        tangential_pressure: float = 0.0,
    ) -> Optional[StrokePoint]:
        normalized = self._normalized_position(position)
        if normalized is None:
            return None
        return StrokePoint(
            x=normalized.x(),
            y=normalized.y(),
            t_ms=self.buffer.timestamp_ms(),
            pressure=pressure,
            x_tilt=x_tilt,
            y_tilt=y_tilt,
            rotation=rotation,
            tangential_pressure=tangential_pressure,
            source=source,
        )

    def tabletEvent(self, event: QTabletEvent) -> None:  # noqa: N802
        point = self._point(
            event.position(),
            event.pressure(),
            "tablet",
            event.xTilt(),
            event.yTilt(),
            event.rotation(),
            event.tangentialPressure(),
        )
        event_type = event.type()

        if event_type == QEvent.Type.TabletPress and point:
            if not self._reported_tablet:
                device = event.pointingDevice()
                self.tablet_identified.emit(
                    {
                        "qt_name": device.name(),
                        "pointer_type": str(device.pointerType()).split(".")[-1],
                        "capabilities": str(device.capabilities()),
                    }
                )
                self._reported_tablet = True
            self._tablet_active = True
            self.buffer.begin_stroke(point)
            self.device_changed.emit("数位板")
            self.changed.emit()
        elif event_type == QEvent.Type.TabletMove and self._tablet_active and point:
            if self.buffer.add_point(point):
                self.changed.emit()
        elif event_type == QEvent.Type.TabletRelease and self._tablet_active:
            self.buffer.end_stroke(point)
            self._tablet_active = False
            self.changed.emit()
            self.stroke_finished.emit()
        self.update()
        event.accept()

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if (
            not self._allow_mouse
            or self._tablet_active
            or event.button() != Qt.MouseButton.LeftButton
        ):
            return
        point = self._point(event.position(), 0.5, "mouse")
        if point:
            self._mouse_active = True
            self.buffer.begin_stroke(point)
            self.device_changed.emit("鼠标测试")
            self.changed.emit()
            self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if not self._mouse_active or self._tablet_active:
            return
        point = self._point(event.position(), 0.5, "mouse")
        if point and self.buffer.add_point(point):
            self.changed.emit()
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if not self._mouse_active or event.button() != Qt.MouseButton.LeftButton:
            return
        point = self._point(event.position(), 0.5, "mouse")
        self.buffer.end_stroke(point)
        self._mouse_active = False
        self.changed.emit()
        self.stroke_finished.emit()
        self.update()

    def paintEvent(self, event: QEvent) -> None:  # noqa: N802
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.fillRect(self.rect(), QColor("#f3f4f6"))
        rect = self.drawing_rect()
        painter.fillRect(rect, QColor("#ffffff"))

        border = QPen(QColor("#9ca3af"), 1.2)
        painter.setPen(border)
        painter.drawRect(rect)

        if self._show_grid:
            grid_pen = QPen(QColor("#e5e7eb"), 1.0, Qt.PenStyle.DashLine)
            painter.setPen(grid_pen)
            painter.drawLine(rect.left(), rect.center().y(), rect.right(), rect.center().y())
            painter.drawLine(rect.center().x(), rect.top(), rect.center().x(), rect.bottom())
            painter.drawLine(rect.topLeft(), rect.bottomRight())
            painter.drawLine(rect.topRight(), rect.bottomLeft())

        for stroke in self.buffer.all_strokes(include_active=True):
            points = stroke.points
            if len(points) == 1:
                point = points[0]
                screen = self._screen_point(point.x, point.y, rect)
                radius = 1.8 + point.pressure * 2.4
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor("#111827"))
                painter.drawEllipse(screen, radius, radius)
                continue
            for previous, current in zip(points, points[1:]):
                width = 1.7 + ((previous.pressure + current.pressure) / 2.0) * 3.4
                pen = QPen(
                    QColor("#111827"),
                    width,
                    Qt.PenStyle.SolidLine,
                    Qt.PenCapStyle.RoundCap,
                    Qt.PenJoinStyle.RoundJoin,
                )
                painter.setPen(pen)
                painter.drawLine(
                    self._screen_point(previous.x, previous.y, rect),
                    self._screen_point(current.x, current.y, rect),
                )

    @staticmethod
    def _screen_point(x: float, y: float, rect: QRectF) -> QPointF:
        return QPointF(rect.left() + x * rect.width(), rect.top() + y * rect.height())


class MainWindow(QMainWindow):
    def __init__(
        self,
        entries: list[CharacterEntry],
        store: SampleStore,
        charset_path: Path,
        capture_context: Optional[dict] = None,
        require_tablet: bool = False,
    ) -> None:
        super().__init__()
        self.entries = entries
        self.store = store
        self.charset_path = Path(charset_path)
        self.capture_context = dict(capture_context or {})
        self.require_tablet = require_tablet
        self.current_index = max(0, store.next_incomplete_index(entries, -1))
        self.current_variant = 1
        self._loading = False
        self._dirty = False

        self.setWindowTitle(f"个人笔迹采集 - {store.writer_name}")
        self.resize(1120, 760)

        self.target_label = QLabel()
        self.target_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        target_font = QFont("Microsoft YaHei", 104)
        target_font.setBold(True)
        self.target_label.setFont(target_font)
        self.target_label.setMinimumHeight(180)

        self.metadata_label = QLabel()
        self.metadata_label.setWordWrap(True)
        self.metadata_label.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.progress = QProgressBar()
        self.progress.setRange(0, len(entries))
        self.progress_label = QLabel()

        self.position_spin = QSpinBox()
        self.position_spin.setRange(1, len(entries))
        self.position_spin.valueChanged.connect(self._position_changed)

        self.search_edit = QLineEdit()
        self.search_edit.setMaxLength(1)
        self.search_edit.setPlaceholderText("输入字符后回车")
        self.search_edit.returnPressed.connect(self._search_character)

        self.variant_spin = QSpinBox()
        self.variant_spin.setRange(1, 5)
        self.variant_spin.valueChanged.connect(self._variant_changed)

        self.canvas = TabletCanvas(allow_mouse=not require_tablet)
        self.canvas.changed.connect(self._canvas_changed)
        self.canvas.stroke_finished.connect(self._save_draft)
        self.canvas.device_changed.connect(self._device_changed)
        self.canvas.tablet_identified.connect(self._tablet_identified)

        self.grid_checkbox = QCheckBox("显示米字格")
        self.grid_checkbox.setChecked(True)
        self.grid_checkbox.toggled.connect(self.canvas.set_show_grid)

        self.device_label = QLabel(
            "输入设备：数位板必需，等待输入"
            if require_tablet
            else "输入设备：等待输入"
        )
        self.sample_stats = QLabel("笔画：0　点数：0　时长：0 ms")
        self.sample_state = QLabel()

        self.autosave_timer = QTimer(self)
        self.autosave_timer.setSingleShot(True)
        self.autosave_timer.setInterval(500)
        self.autosave_timer.timeout.connect(self._save_draft)

        self._build_layout()
        self._build_actions()
        self.setStatusBar(QStatusBar())
        self._load_current()

    def _build_layout(self) -> None:
        sidebar = QFrame()
        sidebar.setFrameShape(QFrame.Shape.StyledPanel)
        sidebar.setFixedWidth(315)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.addWidget(QLabel(f"书写者：{self.store.writer_name} ({self.store.writer_id})"))
        sidebar_layout.addWidget(self.progress_label)
        sidebar_layout.addWidget(self.progress)
        sidebar_layout.addSpacing(8)
        sidebar_layout.addWidget(QLabel("当前目标字符"))
        sidebar_layout.addWidget(self.target_label)
        sidebar_layout.addWidget(self.metadata_label)

        navigation = QGridLayout()
        navigation.addWidget(QLabel("序号："), 0, 0)
        navigation.addWidget(self.position_spin, 0, 1)
        navigation.addWidget(QLabel("变体："), 1, 0)
        navigation.addWidget(self.variant_spin, 1, 1)
        navigation.addWidget(QLabel("查找："), 2, 0)
        navigation.addWidget(self.search_edit, 2, 1)
        sidebar_layout.addLayout(navigation)

        previous_button = QPushButton("上一字")
        previous_button.clicked.connect(lambda: self._move(-1))
        next_button = QPushButton("下一字")
        next_button.clicked.connect(lambda: self._move(1))
        next_missing_button = QPushButton("下一未完成")
        next_missing_button.clicked.connect(self._next_incomplete)
        nav_buttons = QHBoxLayout()
        nav_buttons.addWidget(previous_button)
        nav_buttons.addWidget(next_button)
        sidebar_layout.addLayout(nav_buttons)
        sidebar_layout.addWidget(next_missing_button)

        sidebar_layout.addSpacing(12)
        sidebar_layout.addWidget(self.sample_state)
        sidebar_layout.addWidget(self.sample_stats)
        sidebar_layout.addWidget(self.device_label)
        sidebar_layout.addWidget(self.grid_checkbox)
        sidebar_layout.addStretch(1)

        undo_button = QPushButton("撤销上一笔")
        undo_button.clicked.connect(self.canvas.undo)
        clear_button = QPushButton("清空重写")
        clear_button.clicked.connect(self._clear_current)
        save_button = QPushButton("保存")
        save_button.clicked.connect(self._commit_current)
        save_next_button = QPushButton("保存并下一未完成")
        save_next_button.setDefault(True)
        save_next_button.clicked.connect(self._commit_and_next)
        sidebar_layout.addWidget(undo_button)
        sidebar_layout.addWidget(clear_button)
        sidebar_layout.addWidget(save_button)
        sidebar_layout.addWidget(save_next_button)

        canvas_panel = QVBoxLayout()
        hint_text = "请使用数位板在方框内书写；鼠标输入已禁用。"
        if not self.require_tablet:
            hint_text = "请在方框内书写；每次落笔到抬笔记录为一个笔画。"
        hint = QLabel(hint_text)
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        canvas_panel.addWidget(hint)
        canvas_panel.addWidget(self.canvas, 1)

        central = QWidget()
        layout = QHBoxLayout(central)
        layout.addWidget(sidebar)
        layout.addLayout(canvas_panel, 1)
        self.setCentralWidget(central)

    def _build_actions(self) -> None:
        actions = [
            ("保存", QKeySequence.StandardKey.Save, self._commit_current),
            ("撤销", QKeySequence.StandardKey.Undo, self.canvas.undo),
            ("清空", QKeySequence("Ctrl+R"), self._clear_current),
            ("保存并继续", QKeySequence("Ctrl+Return"), self._commit_and_next),
            ("上一字", QKeySequence("Alt+Left"), lambda: self._move(-1)),
            ("下一字", QKeySequence("Alt+Right"), lambda: self._move(1)),
        ]
        for text, shortcut, slot in actions:
            action = QAction(text, self)
            action.setShortcut(shortcut)
            action.triggered.connect(slot)
            self.addAction(action)

    @property
    def current_entry(self) -> CharacterEntry:
        return self.entries[self.current_index]

    def _load_current(self) -> None:
        self._loading = True
        entry = self.current_entry
        variant = self.current_variant
        document, state = self.store.load_working_document(entry, variant)
        self.canvas.load_document(document)
        self.target_label.setText(entry.character)
        rank = entry.frequency_rank or "领域补充/非汉字"
        strokes = entry.stroke_count or "未知"
        self.metadata_label.setText(
            f"Unicode：{entry.unicode}\n"
            f"类别：{entry.category}\n"
            f"字频序号：{rank}\n"
            f"参考笔画数：{strokes}\n"
            f"拼音：{entry.pinyin or '-'}"
        )
        self.position_spin.blockSignals(True)
        self.position_spin.setValue(self.current_index + 1)
        self.position_spin.blockSignals(False)
        self.variant_spin.blockSignals(True)
        self.variant_spin.setValue(self.current_variant)
        self.variant_spin.blockSignals(False)
        state_text = {"draft": "草稿已恢复", "complete": "已保存，可重新录入覆盖", "missing": "尚未采集"}
        self.sample_state.setText(f"状态：{state_text[state]}　变体 {variant}")
        self._dirty = False
        self._loading = False
        self._update_stats()
        self._update_progress()
        self.canvas.setFocus()

    def _save_draft(self) -> None:
        if self._loading or not self._dirty:
            return
        if self.canvas.buffer.active:
            self.autosave_timer.start()
            return
        entry = self.current_entry
        variant = self.current_variant
        path = self.store.save_draft(
            entry,
            variant,
            self.canvas.buffer,
            capture_context=self.capture_context,
        )
        if path:
            self.sample_state.setText(f"状态：草稿已自动保存　变体 {variant}")
        self._dirty = False
        self._update_stats()

    def _commit_current(self) -> bool:
        try:
            path = self.store.commit_sample(
                self.current_entry,
                self.current_variant,
                self.canvas.buffer,
                capture_context=self.capture_context,
                required_source="tablet" if self.require_tablet else None,
            )
        except ValueError as error:
            QMessageBox.warning(self, "无法保存", str(error))
            return False
        self.sample_state.setText(
            f"状态：已保存　变体 {self.current_variant}"
        )
        self._dirty = False
        self.statusBar().showMessage(f"样本已保存：{path}", 5000)
        self._update_progress()
        return True

    def _commit_and_next(self) -> None:
        if self._commit_current():
            self._next_incomplete()

    def _move(self, delta: int) -> None:
        self._save_draft()
        self.current_index = (self.current_index + delta) % len(self.entries)
        self._load_current()

    def _next_incomplete(self) -> None:
        self._save_draft()
        index = self.store.next_incomplete_index(self.entries, self.current_index)
        if index == self.current_index and self.store.is_complete(self.current_entry):
            QMessageBox.information(self, "采集完成", "当前字符集已经全部完成。")
            return
        self.current_index = index
        self._load_current()

    def _position_changed(self, value: int) -> None:
        if self._loading:
            return
        self._save_draft()
        self.current_index = value - 1
        self._load_current()

    def _variant_changed(self, value: int) -> None:
        if self._loading:
            return
        self._save_draft()
        self.current_variant = value
        self._load_current()

    def _search_character(self) -> None:
        character = self.search_edit.text()
        index = find_character(self.entries, character)
        if index < 0:
            QMessageBox.information(self, "未找到", f"字符“{character}”不在当前目标集中。")
            return
        self._save_draft()
        self.current_index = index
        self.search_edit.clear()
        self._load_current()

    def _clear_current(self) -> None:
        self.canvas.clear_canvas()
        self.store.delete_draft(self.current_entry, self.current_variant)
        if self.store.sample_path(self.current_entry, self.current_variant).exists():
            self.sample_state.setText("状态：画布已清空；已保存样本尚未删除")
        else:
            self.sample_state.setText("状态：已清空，请重新书写")

    def _canvas_changed(self) -> None:
        if not self._loading:
            self._dirty = True
            self.autosave_timer.start()
        self._update_stats()

    def _update_stats(self) -> None:
        buffer = self.canvas.buffer
        self.sample_stats.setText(
            f"笔画：{len(buffer.strokes)}　点数：{buffer.point_count}　"
            f"时长：{buffer.duration_ms} ms"
        )

    def _update_progress(self) -> None:
        completed = self.store.completed_count()
        self.progress.setValue(completed)
        self.progress_label.setText(
            f"进度：{completed} / {len(self.entries)}　"
            f"({completed / len(self.entries) * 100:.1f}%)"
        )

    def _device_changed(self, name: str) -> None:
        self.device_label.setText(f"输入设备：{name}")

    def _tablet_identified(self, value: dict) -> None:
        device = self.capture_context.setdefault("device", {})
        device.update(value)
        session_id = self.capture_context.get("session_id")
        if session_id:
            self.store.save_session(session_id, self.capture_context)

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        self._save_draft()
        event.accept()
