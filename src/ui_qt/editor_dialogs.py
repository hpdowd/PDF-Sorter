"""Mapping-editor dialogs: create a mapping, search for one, and the rule
editor (Variant A: chip inputs with progressive-disclosure advanced matching).
"""
import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QFileDialog,
                               QGridLayout, QHBoxLayout, QLabel, QLineEdit,
                               QListWidget, QMessageBox, QPushButton,
                               QVBoxLayout, QWidget)

from src import utils
from src.ui_qt.chip_input import ChipInput


def _button_row(dialog, ok_text="OK"):
    """A right-aligned OK/Cancel row wired to accept/reject."""
    row = QHBoxLayout()
    row.addStretch(1)
    ok_btn = QPushButton(ok_text)
    ok_btn.setDefault(True)
    ok_btn.clicked.connect(dialog.accept)
    row.addWidget(ok_btn)
    cancel_btn = QPushButton("Cancel")
    cancel_btn.clicked.connect(dialog.reject)
    row.addWidget(cancel_btn)
    return row


class NewMappingDialog(QDialog):
    """Create a new mapping, optionally importing from an existing mapping file.

    On Accepted: mapping_name, import_selected, import_path.
    """

    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("New Mapping")
        self.mapping_name = None
        self.import_selected = False
        self.import_path = None

        lay = QGridLayout(self)
        lay.setContentsMargins(15, 15, 15, 15)
        lay.addWidget(QLabel("New Mapping Name:"), 0, 0)
        self.name_edit = QLineEdit()
        self.name_edit.setMinimumWidth(280)
        lay.addWidget(self.name_edit, 0, 1)

        self.import_check = QCheckBox("Import from existing mapping")
        self.import_check.toggled.connect(self._toggle_import)
        lay.addWidget(self.import_check, 1, 0, 1, 2)

        import_row = QHBoxLayout()
        lay.addLayout(import_row, 2, 0, 1, 2)
        self.import_edit = QLineEdit()
        self.import_edit.setEnabled(False)
        import_row.addWidget(self.import_edit, 1)
        self.browse_btn = QPushButton("...")
        self.browse_btn.setEnabled(False)
        self.browse_btn.setMaximumWidth(40)
        self.browse_btn.clicked.connect(self._browse_import)
        import_row.addWidget(self.browse_btn)

        lay.addLayout(_button_row(self), 3, 0, 1, 2)
        self.name_edit.setFocus()

    def _toggle_import(self, checked):
        self.import_edit.setEnabled(checked)
        self.browse_btn.setEnabled(checked)

    def _browse_import(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Mapping File to Import", utils.MAPPINGS_DIR,
            "JSON files (*.json);;All files (*.*)")
        if path:
            self.import_edit.setText(path)

    def accept(self):
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.critical(self, "Invalid Name", "Mapping name cannot be empty.")
            return
        if self.import_check.isChecked() and not self.import_edit.text():
            QMessageBox.critical(self, "Invalid Path",
                                 "Please select a mapping file to import.")
            return
        self.mapping_name = name
        self.import_selected = self.import_check.isChecked()
        self.import_path = self.import_edit.text() if self.import_selected else None
        super().accept()


class SearchMappingDialog(QDialog):
    """Find a mapping file by name. On Accepted: selected_file."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("Search Mapping File")
        self.resize(400, 400)
        self.selected_file = None

        os.makedirs(utils.MAPPINGS_DIR, exist_ok=True)
        self._all_files = [f for f in os.listdir(utils.MAPPINGS_DIR)
                           if f.endswith(".json")]

        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Search:"))
        self.search_edit = QLineEdit()
        self.search_edit.textChanged.connect(self._update_list)
        lay.addWidget(self.search_edit)
        self.listbox = QListWidget()
        self.listbox.itemDoubleClicked.connect(lambda item: self.accept())
        lay.addWidget(self.listbox, 1)
        lay.addLayout(_button_row(self))

        self._update_list()
        self.search_edit.setFocus()

    def _update_list(self):
        query = self.search_edit.text().lower()
        self.listbox.clear()
        for f in self._all_files:
            if query in f.lower():
                self.listbox.addItem(f)

    def accept(self):
        items = self.listbox.selectedItems() or (
            [self.listbox.item(0)] if self.listbox.count() == 1 else [])
        if not items:
            return
        self.selected_file = items[0].text()
        super().accept()


class PatternDestDialog(QDialog):
    """Add or edit a mapping rule.

    The simple case is unchanged: a rule name, an *Any of these* chip field, and
    a destination. An *Advanced matching* toggle (progressive disclosure) reveals
    optional *All of these* and *None of these* rows. Advanced options are
    persisted as a ``match`` block (built in :meth:`accept`); a rule that uses
    none stays exactly as short as before.

    On Accepted: name, phrase, dest, match (None for a simple rule).
    """

    def __init__(self, parent, title, template_dir, destinations, initial_name="",
                 initial_phrase="", initial_dest="", initial_match=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(470)
        initial_match = initial_match or {}
        self.name = None
        self.phrase = None
        self.dest = None
        self.match = None

        initial_any = self._terms(initial_phrase.split("|"))
        initial_all = self._terms(initial_match.get("all"))
        initial_none = self._terms(initial_match.get("none"))

        lay = QVBoxLayout(self)
        lay.setContentsMargins(15, 15, 15, 15)

        lay.addWidget(QLabel("Rule name (for easy identification):"))
        self.name_edit = QLineEdit(initial_name)
        lay.addWidget(self.name_edit)
        lay.addSpacing(8)

        lay.addWidget(QLabel("Any of these"))
        self.any_chips = ChipInput(kind="any", terms=initial_any)
        lay.addWidget(self.any_chips)
        any_hint = QLabel("Matches if the file has at least one of these.")
        any_hint.setProperty("muted", True)
        lay.addWidget(any_hint)
        lay.addSpacing(6)

        # --- Advanced matching (progressive disclosure, triangle) ---
        self._advanced_open = bool(initial_all or initial_none)
        self.adv_toggle = QLabel()
        self.adv_toggle.setObjectName("discloseToggle")
        self.adv_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.adv_toggle.mousePressEvent = lambda e: self._toggle_advanced()
        lay.addWidget(self.adv_toggle)

        self.adv_frame = QWidget()
        adv_lay = QVBoxLayout(self.adv_frame)
        adv_lay.setContentsMargins(0, 8, 0, 0)
        adv_lay.addWidget(QLabel("All of these  (must also contain)"))
        self.all_chips = ChipInput(kind="all", terms=initial_all)
        adv_lay.addWidget(self.all_chips)
        adv_lay.addSpacing(8)
        adv_lay.addWidget(QLabel("None of these  (ignore the file if it contains)"))
        self.none_chips = ChipInput(kind="none", terms=initial_none)
        adv_lay.addWidget(self.none_chips)
        lay.addWidget(self.adv_frame)

        lay.addSpacing(10)
        lay.addWidget(QLabel("Send to folder:"))
        self.dest_combo = QComboBox()
        self.dest_combo.setEditable(True)
        self.dest_combo.addItems(destinations)
        self.dest_combo.setCurrentText(initial_dest or "")
        lay.addWidget(self.dest_combo)

        lay.addSpacing(10)
        lay.addLayout(_button_row(self))

        self._render_adv_toggle()
        self.adv_frame.setVisible(self._advanced_open)
        self.name_edit.setFocus()

    @staticmethod
    def _terms(values):
        return [str(t).strip() for t in (values or []) if str(t).strip()]

    def _render_adv_toggle(self):
        triangle = "▾" if self._advanced_open else "▸"
        self.adv_toggle.setText(f"{triangle} Advanced matching")

    def _toggle_advanced(self):
        self._advanced_open = not self._advanced_open
        self.adv_frame.setVisible(self._advanced_open)
        self._render_adv_toggle()
        self.adjustSize()

    def accept(self):
        for chips in (self.any_chips, self.all_chips, self.none_chips):
            chips.commit_pending()
        name = self.name_edit.text().strip()
        any_terms = self.any_chips.get_terms()
        all_terms = self.all_chips.get_terms()
        none_terms = self.none_chips.get_terms()
        dest = self.dest_combo.currentText().strip()

        if not name:
            QMessageBox.critical(self, "Invalid name", "Rule name cannot be empty.")
            return
        if not any_terms:
            QMessageBox.critical(self, "No words", "Add at least one word to 'Any of these'.")
            return
        if not dest:
            QMessageBox.critical(self, "Invalid destination", "Destination cannot be empty.")
            return

        self.name = name
        self.dest = dest
        # The phrase key is the any-of terms; a match block is written only when
        # advanced (all/none) terms exist, so a simple rule stays as short as before.
        self.phrase = "|".join(any_terms)
        self.match = None
        if all_terms or none_terms:
            self.match = {"any": any_terms, "all": all_terms, "none": none_terms}
        super().accept()
