"""Main-window dialogs: Settings, the editable sort preview, and the
per-file destination chooser."""
import csv
import logging

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QFont
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QFileDialog,
                               QGridLayout, QHBoxLayout, QLabel, QMessageBox,
                               QPushButton, QTreeWidget, QTreeWidgetItem,
                               QVBoxLayout)

from src.ui_qt import theme

logger = logging.getLogger("ocr_file_sorter.gui")


class PreferencesDialog(QDialog):
    """Remembered scan defaults: first-page-only and deep audit.

    exec() returns Accepted on OK; read the choices with values().
    """

    def __init__(self, parent, first_page_only, deep_audit):
        super().__init__(parent)
        self.setWindowTitle("Settings")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 16, 16, 16)
        heading = QLabel("Scanning")
        bold = heading.font()
        bold.setBold(True)
        heading.setFont(bold)
        lay.addWidget(heading)
        self.first_page_check = QCheckBox("Scan first page only (faster)")
        self.first_page_check.setChecked(first_page_only)
        lay.addWidget(self.first_page_check)
        self.deep_audit_check = QCheckBox("Deep audit — also scan PDFs inside subfolders")
        self.deep_audit_check.setChecked(deep_audit)
        lay.addWidget(self.deep_audit_check)

        btns = QHBoxLayout()
        lay.addSpacing(10)
        lay.addLayout(btns)
        btns.addStretch(1)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btns.addWidget(cancel_btn)
        ok_btn = QPushButton("OK")
        ok_btn.setDefault(True)
        ok_btn.clicked.connect(self.accept)
        btns.addWidget(ok_btn)

    def values(self):
        return self.first_page_check.isChecked(), self.deep_audit_check.isChecked()


class SortPreviewDialog(QDialog):
    """Shows each PDF's planned outcome; the user picks Move, Copy, or Cancel.

    The plan is editable before it runs: double-click a file (or use "Change
    destination...") to send it to a different configured folder, or mark it not
    to be sorted. Edits mutate the PlanItems in place, so the same objects flow on
    to Sorter.execute — no separate override bookkeeping.
    """

    STATUS_LABEL = {
        "matched": "will sort",
        "unmatched": "no match",
        "unreadable": "unreadable",
        "error": "error",
        "skipped": "won't sort",
    }

    STATUS_COLOR = {
        "matched": theme.GOOD,
        "unmatched": theme.MUTED,
        "unreadable": theme.AMBER,
        "error": theme.RED,
        "skipped": theme.MUTED,
    }

    def __init__(self, parent, plan, sorter_obj):
        super().__init__(parent)
        self.setWindowTitle("Preview sort")
        self.resize(720, 470)
        self.confirmed = False
        self.copy_mode = False
        self._sorter = sorter_obj
        self._folders = sorter_obj.destination_folders()

        matched = [p for p in plan if p.status == "matched"]
        unmatched = [p for p in plan if p.status == "unmatched"]
        problems = [p for p in plan if p.status in ("unreadable", "error")]

        lay = QVBoxLayout(self)
        self.summary_label = QLabel()
        bold = self.summary_label.font()
        bold.setBold(True)
        self.summary_label.setFont(bold)
        lay.addWidget(self.summary_label)
        hint = QLabel("Double-click a file to change where it goes, "
                      "or mark it not to be sorted.")
        hint.setProperty("muted", True)
        lay.addWidget(hint)

        self.tree = QTreeWidget()
        self.tree.setColumnCount(4)
        self.tree.setHeaderLabels(["File", "Outcome", "Matched phrase", "Destination"])
        self.tree.setRootIsDecorated(False)
        self.tree.setAllColumnsShowFocus(True)
        self.tree.setColumnWidth(0, 190)
        self.tree.setColumnWidth(1, 85)
        self.tree.setColumnWidth(2, 125)
        self.tree.setColumnWidth(3, 210)
        self.tree.itemDoubleClicked.connect(self._on_double_click)
        lay.addWidget(self.tree, 1)

        # Keep insertion order stable across edits, and map each row to its PlanItem.
        self._rows = matched + unmatched + problems
        for p in self._rows:
            item = QTreeWidgetItem([p.filename, *self._row_values(p)])
            item.setData(0, Qt.ItemDataRole.UserRole, p)
            self.tree.addTopLevelItem(item)
            self._style_item(item, p)

        btns = QHBoxLayout()
        lay.addLayout(btns)
        export_btn = QPushButton("Export...")
        export_btn.setToolTip("Save this preview (each file and where it would go) to a CSV.")
        export_btn.clicked.connect(self._export_csv)
        btns.addWidget(export_btn)
        change_btn = QPushButton("Change destination...")
        change_btn.setToolTip("Send the selected file to a different folder, or don't sort it.")
        change_btn.clicked.connect(self._edit_selected)
        btns.addWidget(change_btn)
        btns.addStretch(1)
        self.move_btn = QPushButton("Move")
        self.move_btn.setObjectName("primary")
        self.move_btn.clicked.connect(self._move)
        btns.addWidget(self.move_btn)
        self.copy_btn = QPushButton("Copy")
        self.copy_btn.clicked.connect(self._copy)
        btns.addWidget(self.copy_btn)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btns.addWidget(cancel_btn)

        self._refresh_actions()
        (self.move_btn if matched else cancel_btn).setFocus()

    def _row_values(self, p):
        """The (outcome, phrase, destination) cells shown for one PlanItem."""
        if p.status == "matched":
            return (self.STATUS_LABEL["matched"], p.phrase or "", f"{p.dest}/{p.dest_name}")
        if p.status == "skipped":
            return (self.STATUS_LABEL["skipped"], "", "(won't be sorted)")
        return (self.STATUS_LABEL.get(p.status, p.status), "", p.message)

    def _style_item(self, item, p):
        brush = QBrush(QColor(self.STATUS_COLOR.get(p.status, theme.INK)))
        for col in range(1, 4):
            item.setForeground(col, brush)

    def _refresh_actions(self):
        """Enable Move/Copy only while at least one file is set to sort, and keep
        the running tally in the header current."""
        counts = {}
        for p in self._rows:
            counts[p.status] = counts.get(p.status, 0) + 1
        matched = counts.get("matched", 0)
        parts = [f"{matched} to sort",
                 f"{counts.get('unmatched', 0)} no match",
                 f"{counts.get('unreadable', 0) + counts.get('error', 0)} unreadable/error"]
        if counts.get("skipped"):
            parts.append(f"{counts['skipped']} won't sort")
        self.summary_label.setText("    ·    ".join(parts))
        self.move_btn.setEnabled(bool(matched))
        self.copy_btn.setEnabled(bool(matched))

    def _on_double_click(self, item, column):
        self._edit_item(item)

    def _edit_selected(self):
        items = self.tree.selectedItems()
        if items:
            self._edit_item(items[0])
        else:
            QMessageBox.information(self, "Change destination",
                                    "Select a file first, then choose its destination.")

    def _edit_item(self, item):
        p = item.data(0, Qt.ItemDataRole.UserRole)
        current = p.dest if p.status == "matched" else None
        chooser = DestinationChooser(self, p.filename, self._folders, current)
        chooser.exec()
        if chooser.result:
            self._apply_choice(item, *chooser.result)

    def _apply_choice(self, item, action, folder):
        p = item.data(0, Qt.ItemDataRole.UserRole)
        if action == "skip":
            p.status = "skipped"
        else:  # "dest"
            # Reassigning only changes the target folder; the proposed filename
            # (any naming-scheme rename) is preserved. A file that had no match
            # keeps its original name and is tagged "(manual)" so the audit trail
            # shows it was placed by hand rather than by a rule.
            if p.status != "matched":
                p.dest_name = p.filename
                p.phrase = "(manual)"
            p.dest = folder
            p.status = "matched"
        for col, value in enumerate(self._row_values(p), start=1):
            item.setText(col, value)
        self._style_item(item, p)
        self._refresh_actions()

    def _move(self):
        self.copy_mode = False
        self.confirmed = True
        self.accept()

    def _copy(self):
        self.copy_mode = True
        self.confirmed = True
        self.accept()

    def _export_csv(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Export preview to CSV", "",
            "CSV files (*.csv);;All files (*.*)")
        if not path:
            return
        if not path.lower().endswith(".csv"):
            path += ".csv"
        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["File", "Outcome", "Matched phrase", "Destination"])
                for p in self._rows:
                    outcome, phrase, dest = self._row_values(p)
                    writer.writerow([p.filename, outcome, phrase, dest])
        except OSError as e:
            QMessageBox.critical(self, "Export failed", str(e))


class DestinationChooser(QDialog):
    """Pick a destination folder for one file, or mark it not to be sorted.

    result is None if cancelled, ("dest", folder) to file into `folder`, or
    ("skip", None) to leave the file where it is.
    """

    def __init__(self, parent, filename, folders, current=None):
        super().__init__(parent)
        self.setWindowTitle("Change destination")
        self.result = None

        lay = QGridLayout(self)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.addWidget(QLabel("File:"), 0, 0)
        name_label = QLabel(filename)
        bold = name_label.font()
        bold.setBold(True)
        name_label.setFont(bold)
        lay.addWidget(name_label, 0, 1)
        lay.addWidget(QLabel("Send to:"), 1, 0)
        self.combo = QComboBox()
        self.combo.addItems(folders)
        if current:
            self.combo.setCurrentText(current)
        self.combo.setMinimumWidth(280)
        lay.addWidget(self.combo, 1, 1)

        btns = QHBoxLayout()
        lay.addLayout(btns, 2, 0, 1, 2)
        btns.addStretch(1)
        assign_btn = QPushButton("Assign")
        assign_btn.setEnabled(bool(folders))
        assign_btn.setDefault(True)
        assign_btn.clicked.connect(self._assign)
        btns.addWidget(assign_btn)
        skip_btn = QPushButton("Don't sort this file")
        skip_btn.clicked.connect(self._skip)
        btns.addWidget(skip_btn)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btns.addWidget(cancel_btn)

        (self.combo if folders else cancel_btn).setFocus()

    def _assign(self):
        folder = self.combo.currentText()
        if folder:
            self.result = ("dest", folder)
        self.accept()

    def _skip(self):
        self.result = ("skip", None)
        self.accept()
