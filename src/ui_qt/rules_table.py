"""RulesTable — the mapping-rules list with an inline colour-coded summary.

Each row shows the rule name, a plain-language "Matches when" summary whose
terms are coloured by role (any=blue, all=green, none=red — Variant A), and the
destination folder. The colouring uses a rich-text item delegate, which is why
this is a plain QTreeWidget rather than the Canvas workaround tkinter needed.

Rows are keyed by the rule's phrase key and are draggable two ways: onto the
template tree to assign a destination, and within the table to reorder (order
is match priority — the first matching rule wins).
"""
import html

from PySide6.QtCore import QMimeData, QSize, Qt, Signal
from PySide6.QtGui import QColor, QDrag, QPainter, QPen, QTextDocument
from PySide6.QtWidgets import (QHeaderView, QStyle, QStyledItemDelegate,
                               QTreeWidget, QTreeWidgetItem)

from src import matching
from src.ui_qt import theme

RULE_MIME = "application/x-pdf-sorter-rule"
_ROW_H = 30


def segments_to_html(segments):
    """Render describe_match_segments output as rich text, one line per
    match role: the *any* terms first, then all the *and* terms together,
    then all the *not* terms. Simple rules stay a single line."""
    # The segments arrive as parts joined by " · " connectors; split them
    # back apart, then merge consecutive parts of the same role into a line.
    parts = [[]]
    for seg in segments:
        if seg == (" · ", "plain"):
            parts.append([])
        else:
            parts[-1].append(seg)

    def role_of(part):
        return next((role for _, role in reversed(part) if role != "plain"), "plain")

    grouped = []   # [(role, [part, ...])]
    for part in parts:
        role = role_of(part)
        if grouped and grouped[-1][0] == role:
            grouped[-1][1].append(part)
        else:
            grouped.append((role, [part]))

    def span(text, role):
        color = theme.ROLE.get(role, theme.INK)
        return f'<span style="color:{color}">{html.escape(text)}</span>'

    sep = f'<span style="color:{theme.MUTED}"> · </span>'
    lines = [sep.join("".join(span(t, r) for t, r in part) for part in group)
             for _, group in grouped]
    return "<br>".join(lines)


class _RichTextDelegate(QStyledItemDelegate):
    """Paints a cell's UserRole HTML so lines can mix colours; rows grow to
    fit multi-line summaries, wrapping within the column width."""

    PAD_X = 4
    PAD_Y = 5

    def _doc(self, option, index, width):
        doc = QTextDocument()
        doc.setDefaultFont(option.font)
        doc.setDocumentMargin(0)
        doc.setHtml(index.data(Qt.ItemDataRole.UserRole) or "")
        if width > 0:
            doc.setTextWidth(width)
        return doc

    def paint(self, painter, option, index):
        if not index.data(Qt.ItemDataRole.UserRole):
            super().paint(painter, option, index)
            return
        if option.state & QStyle.StateFlag.State_Selected:
            painter.fillRect(option.rect, QColor(theme.ACCENT_SOFT))
        doc = self._doc(option, index, option.rect.width() - 2 * self.PAD_X)
        painter.save()
        # Left padding matches the plain columns; vertically centred.
        y = option.rect.y() + max((option.rect.height() - doc.size().height()) / 2, 0)
        painter.translate(option.rect.x() + self.PAD_X, y)
        painter.setClipRect(0, 0, option.rect.width() - self.PAD_X,
                            option.rect.height())
        doc.drawContents(painter)
        painter.restore()

    def sizeHint(self, option, index):
        view = self.parent()
        width = view.columnWidth(index.column()) if isinstance(view, QTreeWidget) else 260
        doc = self._doc(option, index, max(width - 2 * self.PAD_X, 50))
        return QSize(int(doc.idealWidth()) + 2 * self.PAD_X,
                     max(int(doc.size().height()) + 2 * self.PAD_Y, _ROW_H))


class RulesTable(QTreeWidget):
    ruleMoved = Signal(str, int)   # phrase, drop-row index (pre-removal count)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._drop_row = None
        self.setColumnCount(3)
        self.setHeaderLabels(["RULE NAME", "MATCHES WHEN", "FOLDER"])
        self.setRootIsDecorated(False)
        # Name and folder track their content; the summary takes what's left,
        # so the folder column never truncates at the default panel width.
        self.setColumnWidth(0, 150)
        header = self.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.setItemDelegateForColumn(1, _RichTextDelegate(self))
        # Multi-line summaries mean per-row heights; recompute them when the
        # summary column changes width (e.g. the splitter or window resizes).
        header.sectionResized.connect(lambda *_: self.scheduleDelayedItemsLayout())
        self.setDragEnabled(True)
        self.setAcceptDrops(True)

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.topLevelItemCount() == 0:
            painter = QPainter(self.viewport())
            painter.setPen(QColor("#9aa4ae"))
            painter.drawText(self.viewport().rect(), Qt.AlignmentFlag.AlignCenter,
                             "No rules yet — click Add to create one")
        if self._drop_row is not None:
            if self._drop_row < self.topLevelItemCount():
                y = self.visualItemRect(self.topLevelItem(self._drop_row)).top()
            else:
                y = self.visualItemRect(
                    self.topLevelItem(self.topLevelItemCount() - 1)).bottom()
            painter = QPainter(self.viewport())
            painter.setPen(QPen(QColor(theme.ACCENT), 2))
            painter.drawLine(0, y, self.viewport().width(), y)

    # --- data -------------------------------------------------------------

    def refresh(self, mappings):
        self.clear()
        for phrase, rule in (mappings or {}).items():
            name = rule.get("name", "") if isinstance(rule, dict) else ""
            folder = rule.get("dest", "") if isinstance(rule, dict) else (rule or "")
            item = QTreeWidgetItem([name, "", folder])
            font = item.font(0)
            font.setBold(True)
            item.setFont(0, font)
            item.setForeground(2, QColor("#3a4149"))
            item.setData(0, Qt.ItemDataRole.UserRole, phrase)
            item.setData(1, Qt.ItemDataRole.UserRole, segments_to_html(
                matching.describe_match_segments(phrase, rule)))
            item.setSizeHint(0, QSize(0, _ROW_H))
            self.addTopLevelItem(item)

    def selected_phrase(self):
        """The phrase key of the selected rule, or None."""
        items = self.selectedItems()
        return items[0].data(0, Qt.ItemDataRole.UserRole) if items else None

    def select_phrase(self, phrase):
        for i in range(self.topLevelItemCount()):
            item = self.topLevelItem(i)
            if item.data(0, Qt.ItemDataRole.UserRole) == phrase:
                self.setCurrentItem(item)
                self.scrollToItem(item)
                return

    # --- drag source (assign destination by dropping onto the template tree)

    def startDrag(self, supported_actions):
        phrase = self.selected_phrase()
        if phrase is None:
            return
        mime = QMimeData()
        mime.setData(RULE_MIME, phrase.encode("utf-8"))
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.exec(Qt.DropAction.MoveAction | Qt.DropAction.CopyAction)
        # The drag may end outside the table (e.g. on the template tree).
        self._drop_row = None
        self.viewport().update()

    # --- drop target (reorder by dropping a rule back into the list)

    def _row_for_pos(self, pos):
        """The drop-row index for a viewport position: before the row under
        the cursor's top half, after it for the bottom half, end when below."""
        item = self.itemAt(pos)
        if item is None:
            return self.topLevelItemCount()
        row = self.indexOfTopLevelItem(item)
        if pos.y() > self.visualItemRect(item).center().y():
            row += 1
        return row

    def _is_own_rule_drag(self, event):
        return event.source() is self and event.mimeData().hasFormat(RULE_MIME)

    def dragEnterEvent(self, event):
        if self._is_own_rule_drag(event):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if self._is_own_rule_drag(event):
            self._drop_row = self._row_for_pos(event.position().toPoint())
            self.viewport().update()
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self._drop_row = None
        self.viewport().update()

    def dropEvent(self, event):
        if not self._is_own_rule_drag(event):
            event.ignore()
            return
        row = self._row_for_pos(event.position().toPoint())
        self._drop_row = None
        self.viewport().update()
        phrase = bytes(event.mimeData().data(RULE_MIME)).decode("utf-8")
        event.acceptProposedAction()
        self.ruleMoved.emit(phrase, row)
