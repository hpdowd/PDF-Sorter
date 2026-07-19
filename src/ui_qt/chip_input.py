"""ChipInput — a native, rounded term editor built from Qt widgets.

Each chip is a real ``QFrame`` styled with QSS ``border-radius`` (crisp native
text, correct DPI — no images), colour-coded by kind: any=neutral, all=green,
none=red. A "+ add word" chip opens an inline editor; chips flow and wrap.

Editing behaviour: Enter completes the pill and opens a fresh editor for the
next word; clicking anywhere else (or Tab) completes it too. An empty field
simply dissolves, as if it was never opened. Esc cancels the pill without
closing the surrounding dialog.
"""
from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtWidgets import (QApplication, QFrame, QHBoxLayout, QLabel,
                               QLineEdit, QToolButton, QWidget)

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
        self._edit = None
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
        if self._editing and self._edit is not None:
            self._commit(self._edit)

    # --- internals ---
    def _clear(self):
        while self._layout.count():
            item = self._layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    def _rebuild(self):
        self._clear()
        self._committing = False
        for term in self._terms:
            chip = _Chip(term, self.kind)
            chip.removed.connect(self._remove)
            self._layout.addWidget(chip)
        if self._editing:
            self._edit = edit = QLineEdit()
            edit.setObjectName("addEdit")
            edit.setFixedWidth(130)
            edit.editingFinished.connect(lambda: self._commit(edit))
            # Enter/Esc are handled in the event filter so the keys never
            # reach the dialog: QLineEdit doesn't consume Return, and letting
            # it through would fire the dialog's default (OK) button.
            # The app-level filter commits on clicks that land on
            # non-focusable widgets (labels, the dialog background), which
            # never move focus, so editingFinished alone would leave the
            # field dangling.
            edit.installEventFilter(self)
            QApplication.instance().installEventFilter(self)
            self._layout.addWidget(edit)
            edit.setFocus()
        else:
            self._edit = None
            QApplication.instance().removeEventFilter(self)
            add = _AddChip()
            add.clicked.connect(self._begin_add)
            self._layout.addWidget(add)
        self.updateGeometry()

    def eventFilter(self, obj, event):
        if obj is self._edit and event.type() == QEvent.Type.KeyPress:
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self._commit(obj, chain=True)
                return True   # swallow it so Enter doesn't hit the OK button
            if event.key() == Qt.Key.Key_Escape:
                self._editing = False
                self._rebuild()
                return True   # swallow it so Esc doesn't close the dialog
        if self._editing and event.type() == QEvent.Type.MouseButtonPress \
                and isinstance(obj, QWidget) \
                and obj is not self and not self.isAncestorOf(obj):
            self.commit_pending()
        return False

    def _begin_add(self):
        self._editing = True
        self._rebuild()

    def _commit(self, edit, chain=False):
        if self._committing:
            return
        self._committing = True
        # The stale editingFinished that follows returnPressed must not
        # re-enter after this rebuild replaces the editor.
        edit.blockSignals(True)
        value = edit.text().strip()
        if value and value not in self._terms:
            self._terms.append(value)
            self.changed.emit()
        # Enter with a word chains straight into the next one; an empty field
        # just dissolves, as if it was never opened.
        self._editing = bool(chain and value)
        self._rebuild()

    def _remove(self, term):
        if term in self._terms:
            self._terms.remove(term)
            self.changed.emit()
        self._rebuild()
