"""MappingEditor — the window for editing file-sorting mappings.

The view and controller over the toolkit-agnostic EditorLogic model (which is
reused unchanged from the tkinter version). Everything the old editor_gui.py +
editor_actions.py pair did lives here: file selection, the rules table, the
template tree, date foldering, the filename scheme, and dirty tracking.
"""
import logging
import os
import shutil
from contextlib import contextmanager

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox, QFileDialog, QGroupBox, QHBoxLayout,
                               QInputDialog, QLabel, QLineEdit, QMenu,
                               QMessageBox, QPushButton, QSplitter,
                               QVBoxLayout, QWidget)

from src import utils
from src.mapping_editor.editor_logic import EditorLogic
from src.ui_qt.editor_dialogs import (NewMappingDialog, PatternDestDialog,
                                      SearchMappingDialog)
from src.ui_qt.rules_table import RulesTable
from src.ui_qt.template_tree import TemplateTree

logger = logging.getLogger("ocr_file_sorter.editor")

MAPPINGS_DIR = utils.MAPPINGS_DIR


def _bold_label(text):
    label = QLabel(text)
    font = label.font()
    font.setBold(True)
    label.setFont(font)
    return label


class MappingEditor(QWidget):
    # Human labels <-> stored values for the "Group by" and date-source dropdowns.
    _GROUP_LABEL_TO_VALUE = {"Year": "year", "Year and Quarter": "quarter",
                             "Year and Month": "year_month"}
    _GROUP_VALUE_TO_LABEL = {v: k for k, v in _GROUP_LABEL_TO_VALUE.items()}
    _SOURCE_LABEL_TO_VALUE = {"A date printed in the document": "content",
                              "File modified date": "file_modified",
                              "Date saved in the PDF (often wrong)": "pdf_metadata"}
    _SOURCE_VALUE_TO_LABEL = {v: k for k, v in _SOURCE_LABEL_TO_VALUE.items()}
    # Sample subfolders shown in the live preview for each grouping.
    _GROUP_SAMPLE = {"year": ["2024"], "quarter": ["2024", "Q1"], "year_month": ["2024", "03"]}

    def __init__(self, parent=None, on_save_callback=None, mapping_path=None):
        super().__init__(parent, Qt.WindowType.Window)
        self.setWindowTitle("Mapping Editor")
        self.resize(1000, 620)
        self.on_save_callback = on_save_callback

        self.logic = EditorLogic()
        # Guards dirty-tracking while the view is being (re)populated from the model.
        self._loading = False

        self._build_widgets()

        if mapping_path:
            self.logic.load_mapping_file(mapping_path)
            self.refresh_all(reload_files=True)
        else:
            self.update_mapping_file_list()

    # --- construction -----------------------------------------------------

    def _build_widgets(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 10, 10, 10)

        # --- Top row: mapping file selection ---
        file_row = QHBoxLayout()
        outer.addLayout(file_row)
        self.mapping_file_combo = QComboBox()
        self.mapping_file_combo.setToolTip("Select a mapping JSON file to edit.")
        self.mapping_file_combo.textActivated.connect(self.on_mapping_file_selected)
        file_row.addWidget(self.mapping_file_combo, 1)
        search_btn = QPushButton("Search...")
        search_btn.setToolTip("Search for a mapping JSON file by name.")
        search_btn.clicked.connect(self.on_search_mapping)
        file_row.addWidget(search_btn)
        new_btn = QPushButton("New Mapping")
        new_btn.setToolTip("Create a new mapping file.")
        new_btn.clicked.connect(self.on_new_mapping)
        file_row.addWidget(new_btn)

        # --- Main splitter: rules table | template tree ---
        splitter = QSplitter(Qt.Orientation.Horizontal)
        outer.addWidget(splitter, 1)

        left = QWidget()
        left_lay = QVBoxLayout(left)
        left_lay.setContentsMargins(0, 6, 0, 0)
        left_lay.addWidget(_bold_label("Matching rules"))
        self.rules_table = RulesTable()
        self.rules_table.setToolTip(
            "Phrases and their destination folders. Drag a phrase onto a folder to assign.")
        self.rules_table.itemDoubleClicked.connect(lambda *_: self.on_edit_rule())
        self.rules_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.rules_table.customContextMenuRequested.connect(self._show_rules_menu)
        left_lay.addWidget(self.rules_table, 1)

        rule_btns = QHBoxLayout()
        left_lay.addLayout(rule_btns)
        for text, slot in (("Add", self.on_add_rule),
                           ("Remove", self.on_remove_rule),
                           ("Move Up", lambda: self.on_move_rule("up")),
                           ("Move Down", lambda: self.on_move_rule("down"))):
            btn = QPushButton(text)
            btn.clicked.connect(slot)
            rule_btns.addWidget(btn, 1)

        test_row = QHBoxLayout()
        left_lay.addLayout(test_row)
        test_btn = QPushButton("Test a PDF against these rules…")
        test_btn.clicked.connect(self.on_test_pdf)
        test_row.addWidget(test_btn)
        test_row.addStretch(1)
        splitter.addWidget(left)

        right = QWidget()
        right_lay = QVBoxLayout(right)
        right_lay.setContentsMargins(0, 6, 0, 0)
        right_lay.addWidget(_bold_label("Template Directory Structure"))
        self.template_tree = TemplateTree(template_dir=self.logic.template_dir)
        self.template_tree.setToolTip("Visualize and manage the template directory structure.")
        self.template_tree.ruleDropped.connect(self.on_rule_dropped)
        self.template_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.template_tree.customContextMenuRequested.connect(self._show_template_menu)
        right_lay.addWidget(self.template_tree, 1)

        tmpl_btns = QHBoxLayout()
        right_lay.addLayout(tmpl_btns)
        for text, slot in (("New Folder", self.template_tree.add_folder),
                           ("Delete Folder", self.template_tree.delete_folder),
                           ("Refresh", self.refresh_template_tree),
                           ("Auto-Build Tree", self.on_autobuild_tree)):
            btn = QPushButton(text)
            btn.clicked.connect(slot)
            tmpl_btns.addWidget(btn)
        tmpl_btns.addStretch(1)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)

        # --- Subfolder foldering (date-based) ---
        self._build_foldering_panel(outer)

        # --- Optional filename scheme ---
        scheme_row = QHBoxLayout()
        outer.addLayout(scheme_row)
        scheme_row.addWidget(QLabel("Filename scheme:"))
        self.scheme_edit = QLineEdit()
        self.scheme_edit.setToolTip(
            "Optional: rename sorted files. Placeholders: {rule_name} {phrase} "
            "{original_filename} {date} {time} {ext}. "
            "e.g. {rule_name}_{date} - {original_filename}{ext}. Blank = keep names.")
        self.scheme_edit.textChanged.connect(lambda: self._touch())
        scheme_row.addWidget(self.scheme_edit, 1)

        # --- Bottom: Save/Cancel ---
        bottom = QHBoxLayout()
        outer.addLayout(bottom)
        bottom.addStretch(1)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.close)
        bottom.addWidget(cancel_btn)
        save_btn = QPushButton("Save")
        save_btn.setObjectName("primary")
        save_btn.clicked.connect(self.on_save)
        bottom.addWidget(save_btn)

    def _build_foldering_panel(self, outer):
        panel = QGroupBox("Organise into subfolders")
        outer.addWidget(panel)
        panel_lay = QVBoxLayout(panel)
        row = QHBoxLayout()
        panel_lay.addLayout(row)

        row.addWidget(QLabel("Put files into subfolders by:"))
        self.fold_by_combo = QComboBox()
        self.fold_by_combo.addItems(["Nothing", "Date"])
        row.addWidget(self.fold_by_combo)
        row.addSpacing(10)

        row.addWidget(QLabel("Group by:"))
        self.fold_group_combo = QComboBox()
        self.fold_group_combo.addItems(list(self._GROUP_LABEL_TO_VALUE))
        self.fold_group_combo.setCurrentText("Year and Month")
        row.addWidget(self.fold_group_combo)
        row.addSpacing(10)

        row.addWidget(QLabel("Use the date from:"))
        self.fold_source_combo = QComboBox()
        self.fold_source_combo.addItems(list(self._SOURCE_LABEL_TO_VALUE))
        row.addWidget(self.fold_source_combo)
        row.addStretch(1)

        self.fold_preview = QLabel()
        self.fold_preview.setProperty("muted", True)
        panel_lay.addWidget(self.fold_preview)

        for combo in (self.fold_by_combo, self.fold_group_combo, self.fold_source_combo):
            combo.currentTextChanged.connect(lambda *_: self._on_foldering_changed())
        self._update_foldering_state()

    # --- context menus ----------------------------------------------------

    def _show_rules_menu(self, pos):
        has_item = self.rules_table.itemAt(pos) is not None
        menu = QMenu(self)
        menu.addAction("Add Rule", self.on_add_rule)
        edit_action = menu.addAction("Edit Rule", self.on_edit_rule)
        remove_action = menu.addAction("Remove Rule", self.on_remove_rule)
        edit_action.setEnabled(has_item)
        remove_action.setEnabled(has_item)
        menu.exec(self.rules_table.viewport().mapToGlobal(pos))

    def _show_template_menu(self, pos):
        has_item = self.template_tree.itemAt(pos) is not None
        menu = QMenu(self)
        menu.addAction("Add Folder", self.template_tree.add_folder)
        rename_action = menu.addAction("Rename Folder", self.on_rename_template_folder)
        delete_action = menu.addAction("Delete Folder", self.template_tree.delete_folder)
        rename_action.setEnabled(has_item)
        delete_action.setEnabled(has_item)
        menu.exec(self.template_tree.viewport().mapToGlobal(pos))

    # --- foldering panel --------------------------------------------------

    @contextmanager
    def _loading_guard(self):
        """Suspend dirty-tracking while the view is populated from the model.
        Nestable: the outermost guard wins."""
        prev = self._loading
        self._loading = True
        try:
            yield
        finally:
            self._loading = prev

    def _touch(self):
        if not self._loading:
            self.set_dirty(True)

    def _on_foldering_changed(self):
        self._touch()
        self._update_foldering_state()

    def _update_foldering_state(self):
        """Enable the detail dropdowns only for Date, and refresh the preview."""
        on_date = self.fold_by_combo.currentText() == "Date"
        self.fold_group_combo.setEnabled(on_date)
        self.fold_source_combo.setEnabled(on_date)
        if not on_date:
            self.fold_preview.setText(
                "Files go straight into each rule's destination folder.")
            return
        group = self._GROUP_LABEL_TO_VALUE.get(
            self.fold_group_combo.currentText(), "year_month")
        parts = self._GROUP_SAMPLE[group]
        self.fold_preview.setText(
            "Example: a file dated 14 Mar 2024 → Statements / " + " / ".join(parts))

    def get_foldering_config(self):
        """Assemble the foldering config from the dropdowns ({} when off)."""
        if self.fold_by_combo.currentText() != "Date":
            return {}
        return {
            "by": "date",
            "group": self._GROUP_LABEL_TO_VALUE.get(
                self.fold_group_combo.currentText(), "year_month"),
            "date_source": self._SOURCE_LABEL_TO_VALUE.get(
                self.fold_source_combo.currentText(), "content"),
        }

    def _refresh_foldering_ui(self):
        """Populate the dropdowns from the loaded mapping's foldering config."""
        f = self.logic.get_foldering()
        if (f.get("by") or "none") == "date":
            self.fold_by_combo.setCurrentText("Date")
            self.fold_group_combo.setCurrentText(
                self._GROUP_VALUE_TO_LABEL.get(f.get("group") or "year_month",
                                               "Year and Month"))
            self.fold_source_combo.setCurrentText(
                self._SOURCE_VALUE_TO_LABEL.get(f.get("date_source") or "content",
                                                "A date printed in the document"))
        else:
            self.fold_by_combo.setCurrentText("Nothing")
        self._update_foldering_state()

    # --- view refresh -----------------------------------------------------

    def refresh_all(self, reload_files=False):
        """Refresh the entire view based on the current logic state."""
        with self._loading_guard():
            if reload_files:
                self.update_mapping_file_list()
            self.update_mapping_file_display(self.logic.mapping_path)
            self.refresh_mapping_table()
            self.refresh_template_tree()
            self.scheme_edit.setText(self.logic.get_naming_scheme())
            self._refresh_foldering_ui()
        self.set_dirty(self.logic.is_dirty)

    def refresh_mapping_table(self):
        self.rules_table.refresh(self.logic.mappings)

    def refresh_template_tree(self):
        self.template_tree.template_dir = self.logic.template_dir
        self.template_tree.populate()

    def set_dirty(self, is_dirty):
        """Update window title to show unsaved changes state."""
        self.setWindowTitle("Mapping Editor *" if is_dirty else "Mapping Editor")
        self.logic.is_dirty = is_dirty

    def update_mapping_file_list(self):
        with self._loading_guard():
            current = self.mapping_file_combo.currentText()
            self.mapping_file_combo.clear()
            self.mapping_file_combo.addItems(utils.MappingUtils.get_available_mappings())
            if current:
                self.mapping_file_combo.setCurrentText(current)

    def update_mapping_file_display(self, mapping_path):
        with self._loading_guard():
            self.mapping_file_combo.setCurrentText(
                os.path.basename(mapping_path) if mapping_path else "")

    # --- actions (the old EditorActions controller) -----------------------

    def on_mapping_file_selected(self, selected_file):
        if not self._check_unsaved_changes():
            self.update_mapping_file_display(self.logic.mapping_path)
            return
        if not selected_file:
            return
        self.logic.load_mapping_file(os.path.join(MAPPINGS_DIR, selected_file))
        self.refresh_all()

    def on_new_mapping(self):
        if not self._check_unsaved_changes():
            return
        dialog = NewMappingDialog(self)
        if dialog.exec() != NewMappingDialog.Accepted or not dialog.mapping_name:
            return

        mapping_path = os.path.join(MAPPINGS_DIR, dialog.mapping_name + ".json")
        if os.path.exists(mapping_path):
            QMessageBox.critical(self, "File Exists",
                                 "A mapping file with that name already exists.")
            return

        template_dir = self.logic._get_template_dir(mapping_path)
        os.makedirs(template_dir, exist_ok=True)

        if dialog.import_selected and dialog.import_path:
            shutil.copy(dialog.import_path, mapping_path)
            import_template_dir = self.logic._get_template_dir(dialog.import_path)
            if os.path.exists(import_template_dir):
                if os.path.exists(template_dir):
                    shutil.rmtree(template_dir)
                shutil.copytree(import_template_dir, template_dir)
        else:
            with open(mapping_path, "w", encoding="utf-8") as f:
                f.write("{}")

        self.logic.load_mapping_file(mapping_path)
        self.refresh_all(reload_files=True)

    def on_search_mapping(self):
        if not self._check_unsaved_changes():
            return
        dialog = SearchMappingDialog(self)
        if dialog.exec() != SearchMappingDialog.Accepted or not dialog.selected_file:
            return
        self.logic.load_mapping_file(os.path.join(MAPPINGS_DIR, dialog.selected_file))
        self.refresh_all(reload_files=True)

    def on_save(self):
        self.logic.set_naming_scheme(self.scheme_edit.text())
        self.logic.set_foldering(self.get_foldering_config())
        success, message = self.logic.save_mappings()
        if success:
            self.set_dirty(False)
            if self.on_save_callback:
                self.on_save_callback()
            QMessageBox.information(self, "Saved", message)
        else:
            QMessageBox.critical(self, "Error", message)

    def on_add_rule(self):
        destinations = self.logic.get_all_destinations()
        dialog = PatternDestDialog(self, "Add Rule", self.logic.template_dir, destinations)
        if dialog.exec() != PatternDestDialog.Accepted:
            return
        success, message = self.logic.add_rule(dialog.phrase, dialog.name,
                                               dialog.dest, dialog.match)
        if success:
            self.refresh_mapping_table()
            self.set_dirty(True)
        else:
            QMessageBox.warning(self, "Warning", message)

    def on_edit_rule(self):
        phrase = self.rules_table.selected_phrase()
        if phrase is None:
            QMessageBox.warning(self, "No Selection", "Please select a mapping to edit.")
            return
        # Read the full rule (incl. any match block) from the model rather than
        # the displayed summary.
        rule = self.logic.mappings.get(phrase, {})
        name = rule.get("name", "") if isinstance(rule, dict) else ""
        dest = rule.get("dest", "") if isinstance(rule, dict) else (rule or "")
        match = rule.get("match") if isinstance(rule, dict) else None
        destinations = self.logic.get_all_destinations()
        dialog = PatternDestDialog(self, "Edit Rule", self.logic.template_dir, destinations,
                                   initial_name=name, initial_phrase=phrase,
                                   initial_dest=dest, initial_match=match)
        if dialog.exec() != PatternDestDialog.Accepted:
            return
        success, message = self.logic.update_rule(phrase, dialog.phrase, dialog.name,
                                                  dialog.dest, dialog.match)
        if success:
            self.refresh_mapping_table()
            self.set_dirty(True)
        else:
            QMessageBox.warning(self, "Warning", message)

    def on_test_pdf(self):
        """Test a chosen PDF against the current rules and show the outcome."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose a PDF to test", "", "PDF files (*.pdf);;All files (*.*)")
        if not path:
            return
        try:
            result = self.logic.test_pdf(path)
        except Exception as e:
            QMessageBox.critical(self, "Test failed", f"Could not test this PDF:\n{e}")
            return
        QMessageBox.information(self, f"Test result — {os.path.basename(path)}", result)

    def on_remove_rule(self):
        phrase = self.rules_table.selected_phrase()
        if phrase is None:
            QMessageBox.warning(self, "No Selection", "Please select a mapping to remove.")
            return
        self.logic.remove_rule(phrase)
        self.refresh_mapping_table()
        self.set_dirty(True)

    def on_move_rule(self, direction):
        phrase = self.rules_table.selected_phrase()
        if phrase is None:
            return
        if self.logic.move_rule(phrase, direction):
            self.refresh_mapping_table()
            # Reselect the item after refresh (its key is unchanged).
            self.rules_table.select_phrase(phrase)
            self.set_dirty(True)

    def on_rename_template_folder(self):
        old_rel_path = self.template_tree.selected_rel_path()
        if not old_rel_path:
            QMessageBox.warning(self, "No Selection", "Please select a folder to rename.")
            return
        old_name = os.path.basename(old_rel_path)
        new_name, ok = QInputDialog.getText(self, "Rename Folder",
                                            f"Enter new name for '{old_name}':")
        if not ok or not new_name or new_name == old_name:
            return
        success, message = self.logic.rename_template_folder(old_rel_path, new_name)
        if success:
            self.refresh_all()
            self.set_dirty(True)
        else:
            QMessageBox.critical(self, "Error", message)

    def on_autobuild_tree(self):
        created = self.logic.autobuild_template_tree()
        self.refresh_template_tree()
        QMessageBox.information(
            self, "Done", f"Template tree updated. Folders created/ensured: {created}")

    def on_rule_dropped(self, phrase, rel_path):
        """A rule was dragged onto a template folder: assign that destination."""
        rule = self.logic.mappings.get(phrase)
        if rule is None:
            return
        if isinstance(rule, dict):
            if rule.get("dest") != rel_path:
                rule["dest"] = rel_path
                self.refresh_mapping_table()
                self.set_dirty(True)
        elif rule != rel_path:
            self.logic.mappings[phrase] = rel_path
            self.refresh_mapping_table()
            self.set_dirty(True)

    # --- closing ----------------------------------------------------------

    def _check_unsaved_changes(self):
        """Check for unsaved changes and prompt the user. True = safe to proceed."""
        if not self.logic.is_dirty:
            return True
        response = QMessageBox.question(
            self, "Unsaved Changes", "You have unsaved changes. Do you want to save them?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            | QMessageBox.StandardButton.Cancel)
        if response == QMessageBox.StandardButton.Yes:
            self.on_save()
            return not self.logic.is_dirty
        return response == QMessageBox.StandardButton.No

    def closeEvent(self, event):
        if self._check_unsaved_changes():
            event.accept()
        else:
            event.ignore()
