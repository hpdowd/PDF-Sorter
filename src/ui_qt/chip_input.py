"""ChipInput — a native, rounded term editor built from Qt widgets.

Each chip is a real ``QFrame`` styled with QSS ``border-radius`` (crisp native
text, correct DPI — no images), colour-coded by kind: any=neutral, all=green,
none=red. A "+ add word" chip opens an inline editor; chips flow and wrap.
"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QLineEdit, QToolButton,
                               QWidget)

from src.ui_qt.flow_layout import FlowLayout


class _Chip(QFrame):
    removed = Signal(str)

    def __init__(self, text, kind):
        super().__init__()
        self.text_value = text
        self.setObjectName("chip")
        self.setProperty("kind", kind)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 3, 6, 3)
        lay.setSpacing(5)
        lay.addWidget(QLabel(text))
        close = QToolButton()
        close.setObjectName("chipX")
        close.setText("✕")
        close.setCursor(Qt.PointingHandCursor)
        close.clicked.connect(lambda: self.removed.emit(self.text_value))
        lay.addWidget(close)


class _AddChip(QFrame):
    clicked = Signal()

    def __init__(self):
        super().__init__()
        self.setObjectName("addChip")
        self.setCursor(Qt.PointingHandCursor)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(11, 3, 11, 3)
        lay.addWidget(QLabel("+ add word"))

    def mousePressEvent(self, event):
        self.clicked.emit()


class ChipInput(QWidget):
    changed = Signal()

    def __init__(self, kind="any", terms=None, parent=None):
        super().__init__(parent)
        self.kind = kind
        self._terms = [t.strip() for t in (terms or []) if t and t.strip()]
        self._editing = False
        self._committing = False
        self._layout = FlowLayout(self, margin=2, hspacing=6, vspacing=6)
        self._rebuild()

    # --- public API ---
    def get_terms(self):
        return list(self._terms)

    def set_terms(self, terms):
        self._terms = [t.strip() for t in (terms or []) if t and t.strip()]
        self._editing = False
        self._rebuild()

    def commit_pending(self):
        if self._editing:
            for i in range(self._layout.count()):
                w = self._layout.itemAt(i).widget()
                if isinstance(w, QLineEdit):
                    self._commit(w)
                    break

    # --- internals ---
    def _clear(self):
        while self._layout.count():
            item = self._layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    def _rebuild(self):
        self._clear()
        for term in self._terms:
            chip = _Chip(term, self.kind)
            chip.removed.connect(self._remove)
            self._layout.addWidget(chip)
        if self._editing:
            self._committing = False
            edit = QLineEdit()
            edit.setObjectName("addEdit")
            edit.setFixedWidth(130)
            edit.returnPressed.connect(lambda: self._commit(edit))
            edit.editingFinished.connect(lambda: self._commit(edit))
            self._layout.addWidget(edit)
            edit.setFocus()
        else:
            add = _AddChip()
            add.clicked.connect(self._begin_add)
            self._layout.addWidget(add)
        self.updateGeometry()

    def _begin_add(self):
        self._editing = True
        self._rebuild()

    def _commit(self, edit):
        if self._committing:
            return
        self._committing = True
        value = edit.text().strip()
        self._editing = False
        if value and value not in self._terms:
            self._terms.append(value)
            self.changed.emit()
        self._rebuild()

    def _remove(self, term):
        if term in self._terms:
            self._terms.remove(term)
            self.changed.emit()
        self._rebuild()
