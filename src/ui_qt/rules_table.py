"""RulesTable — the mapping-rules list with an inline colour-coded summary.

Each row shows the rule name, a plain-language "Matches when" summary whose
terms are coloured by role (any=blue, all=green, none=red — Variant A), and the
destination folder. The colouring uses a rich-text item delegate, which is why
this is a plain QTreeWidget rather than the Canvas workaround tkinter needed.

Rows are keyed by the rule's phrase key and are draggable onto the template
tree to assign a destination.
"""
import html

from PySide6.QtCore import QMimeData, QSize, Qt
from PySide6.QtGui import QColor, QDrag, QTextDocument
from PySide6.QtWidgets import (QHeaderView, QStyle, QStyledItemDelegate,
                               QTreeWidget, QTreeWidgetItem)

from src import matching
from src.ui_qt import theme

RULE_MIME = "application/x-pdf-sorter-rule"
_ROW_H = 30


def segments_to_html(segments):
    """Render describe_match_segments output as a rich-text line."""
    parts = []
    for text, role in segments:
        color = theme.ROLE.get(role, theme.INK)
        parts.append(f'<span style="color:{color}">{html.escape(text)}</span>')
    return "".join(parts)


class _RichTextDelegate(QStyledItemDelegate):
    """Paints a cell's UserRole HTML so one line can mix colours."""

    def paint(self, painter, option, index):
        html_text = index.data(Qt.ItemDataRole.UserRole)
        if not html_text:
            super().paint(painter, option, index)
            return
        if option.state & QStyle.StateFlag.State_Selected:
            painter.fillRect(option.rect, QColor(theme.ACCENT_SOFT))
        doc = QTextDocument()
        doc.setDefaultFont(option.font)
        doc.setHtml(html_text)
        painter.save()
        # Left padding matches the plain columns; vertically centred.
        y = option.rect.y() + (option.rect.height() - doc.size().height()) / 2
        painter.translate(option.rect.x() + 4, y)
        painter.setClipRect(0, 0, option.rect.width() - 4, option.rect.height())
        doc.drawContents(painter)
        painter.restore()

    def sizeHint(self, option, index):
        size = super().sizeHint(option, index)
        return QSize(size.width(), max(size.height(), _ROW_H))


class RulesTable(QTreeWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setColumnCount(3)
        self.setHeaderLabels(["RULE NAME", "MATCHES WHEN", "FOLDER"])
        self.setRootIsDecorated(False)
        self.setUniformRowHeights(True)
        # Name and folder track their content; the summary takes what's left,
        # so the folder column never truncates at the default panel width.
        self.setColumnWidth(0, 150)
        header = self.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.setItemDelegateForColumn(1, _RichTextDelegate(self))
        self.setDragEnabled(True)

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
