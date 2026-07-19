"""Main window: pick a mapping, an output folder, and folders to sort.

A straight port of the tkinter FileSorterGUI. Scanning and executing run on
worker threads exactly as before; UI updates cross back to the GUI thread via
Qt signals (the Qt equivalent of the old ``root.after`` calls). Folder
drag-and-drop is native Qt, replacing tkinterdnd2.
"""
import csv
import logging
import os
import threading

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QPainter
from PySide6.QtWidgets import (QComboBox, QFileDialog, QGridLayout, QGroupBox,
                               QHBoxLayout, QLabel, QLineEdit, QListWidget,
                               QMainWindow, QMessageBox, QProgressBar,
                               QPushButton, QToolButton, QVBoxLayout, QWidget)

from src import __version__, sorter, utils
from src.ui_qt import theme
from src.ui_qt.dialogs import PreferencesDialog, SortPreviewDialog
from src.ui_qt.editor import MappingEditor
from src.utils import (DEEP_AUDIT_KEY, FIRST_PAGE_KEY, HIDE_OCR_WARNING_KEY,
                       LAST_MAPPING_KEY, MAPPINGS_DIR, OUTPUT_DIR_KEY,
                       load_settings, save_settings)

logger = logging.getLogger("ocr_file_sorter.gui")


class FolderList(QListWidget):
    """The folders-to-sort list: accepts OS folder drops and paints a watermark
    while empty."""

    foldersDropped = Signal(list)

    def __init__(self):
        super().__init__()
        self.setSelectionMode(QListWidget.ExtendedSelection)
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event):
        if any(u.isLocalFile() and os.path.isdir(u.toLocalFile())
               for u in event.mimeData().urls()):
            event.acceptProposedAction()

    dragMoveEvent = dragEnterEvent

    def dropEvent(self, event):
        folders = [u.toLocalFile() for u in event.mimeData().urls()
                   if u.isLocalFile() and os.path.isdir(u.toLocalFile())]
        if folders:
            self.foldersDropped.emit(folders)
            event.acceptProposedAction()

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.count() == 0:
            painter = QPainter(self.viewport())
            font = painter.font()
            font.setPointSize(16)
            font.setBold(True)
            painter.setFont(font)
            painter.setPen(Qt.GlobalColor.lightGray)
            painter.drawText(self.viewport().rect(), Qt.AlignCenter, "OCR File Sorter")

    def paths(self):
        return [self.item(i).text() for i in range(self.count())]


class MainWindow(QMainWindow):
    # Worker-thread -> GUI-thread crossings (auto-queued by Qt).
    statusChanged = Signal(str)
    progressTicked = Signal()
    totalCounted = Signal(int)
    planReady = Signal(object, object)      # (sorter_obj, plan)
    sortFailed = Signal(str)
    executeDone = Signal(str)               # summary text
    sortCancelled = Signal()
    undoDone = Signal(int, int)             # (undone, errors)

    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"OCR File Sorter v{__version__}")
        self.resize(560, 520)
        self.setMinimumSize(400, 340)

        self.mapping_path = None
        self.settings = load_settings()
        self.output_dir = self.settings.get(OUTPUT_DIR_KEY)
        self.deep_audit = self.settings.get(DEEP_AUDIT_KEY, False)
        self.first_page_only = self.settings.get(FIRST_PAGE_KEY, True)

        self._progress_done = 0
        self.last_manifest = utils.load_manifest()  # enables Undo across restarts
        self.last_output_dir = None
        self._active_sorter = None  # the Sorter of the running scan/sort, for Cancel
        self._editor = None

        self._build_widgets()
        self._populate_mappings()
        self._refresh_undo_state()

        self.statusChanged.connect(self.status_label.setText)
        self.progressTicked.connect(self._on_progress_tick)
        self.totalCounted.connect(self._on_total_counted)
        self.planReady.connect(self._show_preview)
        self.sortFailed.connect(self._sort_error)
        self.executeDone.connect(self._after_execute)
        self.sortCancelled.connect(self._sort_cancelled)
        self.undoDone.connect(self._after_undo)

    # --- construction -----------------------------------------------------

    def _build_widgets(self):
        PAD = 8
        self._build_menubar()

        central = QWidget()
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(PAD, PAD, PAD, PAD)
        outer.setSpacing(PAD)

        # --- Mapping + Output (aligned rows) ---
        top = QGridLayout()
        top.setHorizontalSpacing(PAD)
        outer.addLayout(top)

        top.addWidget(QLabel("Mapping"), 0, 0)
        self.mapping_combo = QComboBox()
        self.mapping_combo.setToolTip("Select a mapping file to use for sorting PDFs.")
        self.mapping_combo.textActivated.connect(self._on_mapping_selected)
        top.addWidget(self.mapping_combo, 0, 1)
        edit_btn = QPushButton("Edit / Create...")
        edit_btn.setToolTip("Open the mapping editor to create or modify mapping files.")
        edit_btn.clicked.connect(self._open_mapping_editor)
        top.addWidget(edit_btn, 0, 2)

        top.addWidget(QLabel("Output"), 1, 0)
        self.output_edit = QLineEdit(self.output_dir or "")
        self.output_edit.setReadOnly(True)
        self.output_edit.setToolTip(
            "Sorted files (and their category subfolders) are placed under this folder.")
        top.addWidget(self.output_edit, 1, 1)
        choose_output_btn = QPushButton("Choose...")
        choose_output_btn.setToolTip("Pick the folder where sorted files will be placed.")
        choose_output_btn.clicked.connect(self._choose_output_dir)
        top.addWidget(choose_output_btn, 1, 2)
        top.setColumnStretch(1, 1)

        # --- Folders to sort (the main workspace) ---
        folder_group = QGroupBox("Folders to sort  (drag folders here, or use Add)")
        outer.addWidget(folder_group, 1)
        folder_lay = QHBoxLayout(folder_group)

        self.folder_list = FolderList()
        self.folder_list.foldersDropped.connect(self._add_folders)
        folder_lay.addWidget(self.folder_list, 1)

        btn_col = QVBoxLayout()
        folder_lay.addLayout(btn_col)
        add_folder_btn = QPushButton("Add Folder...")
        add_folder_btn.setToolTip("Add a folder to the list to be sorted.")
        add_folder_btn.clicked.connect(self._add_folder)
        btn_col.addWidget(add_folder_btn)
        remove_folder_btn = QPushButton("Remove Selected")
        remove_folder_btn.setToolTip("Remove selected folders from the list.")
        remove_folder_btn.clicked.connect(self._remove_selected_folders)
        btn_col.addWidget(remove_folder_btn)
        btn_col.addStretch(1)

        # --- Bottom buttons ---
        button_row = QHBoxLayout()
        outer.addLayout(button_row)
        self.sort_btn = QPushButton("Sort Files")
        self.sort_btn.setObjectName("primary")
        self.sort_btn.setToolTip("Preview the sort, then choose Move or Copy.")
        self.sort_btn.clicked.connect(self._start_sort_thread)
        button_row.addWidget(self.sort_btn)
        self.undo_btn = QPushButton("Undo Last Sort")
        self.undo_btn.setToolTip("Put the files from the last sort back where they were.")
        self.undo_btn.setEnabled(False)
        self.undo_btn.clicked.connect(self._undo_last_sort)
        button_row.addWidget(self.undo_btn)
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setToolTip("Stop the scan or sort that is currently running.")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self._cancel_running_sort)
        button_row.addWidget(self.cancel_btn)
        button_row.addStretch(1)
        settings_btn = QPushButton("Settings")
        settings_btn.setToolTip("Open Settings — scan options (deep audit, first page only).")
        settings_btn.clicked.connect(self._open_preferences)
        button_row.addWidget(settings_btn)

        # Persistent OCR warning, shown only when OCR can't run, just above the
        # status bar. Dismissable (and remembered) for users who don't want OCR.
        self.ocr_warning = QWidget()
        warn_row = QHBoxLayout(self.ocr_warning)
        warn_row.setContentsMargins(0, 0, 0, 0)
        self.ocr_warning_label = QLabel()
        self.ocr_warning_label.setProperty("warning", True)
        self.ocr_warning_label.setWordWrap(True)
        self.ocr_warning_label.setOpenExternalLinks(True)
        warn_row.addWidget(self.ocr_warning_label, 1)
        dismiss = QToolButton()
        dismiss.setText("✕")
        dismiss.setToolTip("Hide this warning (it won't be shown again).")
        dismiss.setAutoRaise(True)
        dismiss.setCursor(Qt.CursorShape.PointingHandCursor)
        dismiss.clicked.connect(self._dismiss_ocr_warning)
        warn_row.addWidget(dismiss, 0, Qt.AlignmentFlag.AlignTop)
        outer.addWidget(self.ocr_warning)
        self._update_ocr_indicator()

        # --- Status bar ---
        status_row = QHBoxLayout()
        outer.addLayout(status_row)
        self.status_label = QLabel("Ready")
        status_row.addWidget(self.status_label)
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(False)
        status_row.addWidget(self.progress_bar, 1)

    def _build_menubar(self):
        menubar = self.menuBar()
        file_menu = menubar.addMenu("File")
        settings_action = QAction("Settings...", self)
        settings_action.triggered.connect(self._open_preferences)
        file_menu.addAction(settings_action)
        file_menu.addSeparator()
        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        help_menu = menubar.addMenu("Help")
        help_action = QAction("Help", self)
        help_action.triggered.connect(self._show_help)
        help_menu.addAction(help_action)
        about_action = QAction("About", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

    # --- static dialogs ---------------------------------------------------

    def _show_help(self):
        message = (
            "OCR File Sorter Help\n\n"
            "This tool sorts PDF files into folders based on their content, using each PDF's "
            "text (with an OCR fallback for scans).\n\n"
            "Mapping File:\n"
            "- Choose the ruleset that decides where each PDF goes.\n"
            "- Use 'Edit / Create...' to open the Mapping Editor.\n\n"
            "Output Folder:\n"
            "- Sorted files are filed here, inside per-category subfolders.\n"
            "- You must choose an output folder before sorting.\n\n"
            "Folders to Sort:\n"
            "- Add one or more folders containing PDF files to be sorted.\n"
            "- You can drag and drop folders from your file manager into the list to add them quickly.\n\n"
            "Settings (the Settings button, or File > Settings):\n"
            "- Deep Audit: also scan PDFs inside subfolders (recursive).\n"
            "- Scan first page only: faster; reads just the first page of each PDF.\n\n"
            "Mapping rules:\n"
            "- A rule matches when its phrase appears in a PDF's text.\n"
            "- A rule can require any, all, or none of several words (Advanced matching).\n"
            "- Rules are checked top to bottom; the first match wins.\n\n"
            f"Mappings are stored in:\n{utils.MAPPINGS_DIR}\n\n"
            f"Logs are written to:\n{utils.LOG_FILE}\n"
        )
        QMessageBox.information(self, "Help - OCR File Sorter", message)

    def _show_about(self):
        available, detail = sorter.ocr_status()
        ocr_line = detail if available else f"unavailable — {detail}"
        QMessageBox.information(
            self, "About OCR File Sorter",
            f"OCR File Sorter\nVersion {__version__}\n\n"
            "Sorts PDFs into folders based on their text content, "
            "with an OCR fallback for scanned documents.\n\n"
            f"OCR: {ocr_line}")

    # --- mapping / output / folders ---------------------------------------

    def _populate_mappings(self):
        mappings = utils.MappingUtils.get_available_mappings()
        self.mapping_combo.clear()
        self.mapping_combo.addItems(mappings)
        last_mapping = self.settings.get(LAST_MAPPING_KEY)
        if mappings:
            if last_mapping and last_mapping in mappings:
                self.mapping_combo.setCurrentText(last_mapping)
                self.mapping_path = os.path.join(MAPPINGS_DIR, last_mapping)
            else:
                self.mapping_combo.setCurrentIndex(0)
                self.mapping_path = os.path.join(MAPPINGS_DIR, mappings[0])
        else:
            self.mapping_path = None

    def _on_mapping_selected(self, selected):
        if selected:
            self.mapping_path = os.path.join(MAPPINGS_DIR, selected)
            self.settings[LAST_MAPPING_KEY] = selected
            save_settings(self.settings)

    def _choose_output_dir(self):
        initial = self.output_dir if self.output_dir and os.path.isdir(self.output_dir) else ""
        folder = QFileDialog.getExistingDirectory(self, "Select Output Folder", initial)
        if folder:
            self.output_dir = folder
            self.output_edit.setText(folder)
            self.settings[OUTPUT_DIR_KEY] = folder
            save_settings(self.settings)

    def _open_preferences(self):
        dialog = PreferencesDialog(self, self.first_page_only, self.deep_audit)
        if dialog.exec() != PreferencesDialog.Accepted:
            return
        self.first_page_only, self.deep_audit = dialog.values()
        self.settings[FIRST_PAGE_KEY] = self.first_page_only
        self.settings[DEEP_AUDIT_KEY] = self.deep_audit
        save_settings(self.settings)

    def _add_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Folder to Sort")
        if folder:
            self._add_folders([folder])

    def _add_folders(self, folders):
        existing = set(self.folder_list.paths())
        for folder in folders:
            if os.path.isdir(folder) and folder not in existing:
                self.folder_list.addItem(folder)
                existing.add(folder)

    def _remove_selected_folders(self):
        for item in self.folder_list.selectedItems():
            self.folder_list.takeItem(self.folder_list.row(item))

    def _open_mapping_editor(self):
        # One editor at a time: two windows editing the same mapping would
        # silently lose whichever was saved first.
        if self._editor is not None:
            self._editor.raise_()
            self._editor.activateWindow()
            return

        def on_save_callback():
            selected = os.path.basename(self.mapping_path) if self.mapping_path else None
            self.settings[LAST_MAPPING_KEY] = selected
            save_settings(self.settings)
            self._populate_mappings()
            if selected:
                self.mapping_combo.setCurrentText(selected)
        self._editor = MappingEditor(self, on_save_callback=on_save_callback,
                                     mapping_path=self.mapping_path)
        self._editor.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self._editor.destroyed.connect(lambda: setattr(self, "_editor", None))
        self._editor.show()

    # --- sort flow --------------------------------------------------------

    def update_status(self, message):
        """Status callback for the Sorter (called from the worker thread)."""
        self.statusChanged.emit(message)

    def _on_progress(self):
        """Progress callback for the Sorter (called from the worker thread)."""
        self.progressTicked.emit()

    def _on_progress_tick(self):
        self._progress_done += 1
        self.progress_bar.setValue(self._progress_done)

    def _on_total_counted(self, total):
        self._progress_done = 0
        self.progress_bar.setMaximum(max(total, 1))
        self.progress_bar.setValue(0)

    def _start_sort_thread(self):
        # Validate on the main thread, then scan/plan in the background.
        mapping_path = self.mapping_path
        folders = self.folder_list.paths()
        if not mapping_path or not os.path.isfile(mapping_path):
            QMessageBox.critical(self, "Error", "Please select a valid mapping file.")
            return
        if not folders:
            QMessageBox.critical(self, "Error", "Please add at least one folder to sort.")
            return
        output_dir = self.output_dir
        if not output_dir or not os.path.isdir(output_dir):
            QMessageBox.critical(self, "Error",
                                 "Please choose an output folder for the sorted files.")
            return

        self.sort_btn.setEnabled(False)
        self.undo_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.status_label.setText("Scanning...")
        self.progress_bar.setValue(0)
        threading.Thread(
            target=self._plan_and_preview,
            args=(mapping_path, output_dir, folders, self.deep_audit, self.first_page_only),
            daemon=True,
        ).start()

    def _plan_and_preview(self, mapping_path, output_dir, folders, deep_audit, first_page_only):
        try:
            sorter_obj = sorter.Sorter(
                mapping_path,
                output_dir=output_dir,
                status_callback=self.update_status,
                progress_callback=self._on_progress,
            )
            self._active_sorter = sorter_obj
            total = sorter_obj.count_pdfs(folders, deep_audit=deep_audit)
            self.totalCounted.emit(total)
            plan = sorter_obj.plan(folders, deep_audit=deep_audit,
                                   first_page_only=first_page_only)
            if sorter_obj.cancelled:
                self.sortCancelled.emit()
                return
            self.planReady.emit(sorter_obj, plan)
        except Exception as e:
            logger.exception("Planning failed")
            self.sortFailed.emit(str(e))

    def _show_preview(self, sorter_obj, plan):
        if not plan:
            QMessageBox.information(self, "Nothing to sort",
                                    "No PDF files were found in the selected folders.")
            self._reset_after_sort()
            return
        dialog = SortPreviewDialog(self, plan, sorter_obj)
        dialog.exec()
        if not dialog.confirmed:
            self._reset_after_sort()
            self.status_label.setText("Cancelled")
            return
        copy = dialog.copy_mode
        self.status_label.setText("Copying..." if copy else "Moving...")
        threading.Thread(
            target=self._execute_plan, args=(sorter_obj, plan, copy), daemon=True
        ).start()

    def _execute_plan(self, sorter_obj, plan, copy):
        try:
            manifest, count = sorter_obj.execute(plan, copy=copy)
            utils.save_manifest(manifest)
            self.last_manifest = manifest
            self.last_output_dir = sorter_obj.template_dir
            unmatched = sum(1 for p in plan if p.status == "unmatched")
            problems = sum(1 for p in plan if p.status in ("error", "unreadable"))
            skipped = sum(1 for p in plan if p.status == "skipped")
            verb = "Copied" if copy else "Moved"
            if sorter_obj.cancelled:
                matched_total = sum(1 for p in plan if p.status == "matched")
                summary = (f"Cancelled. {verb} {count} of {matched_total} file(s) before stopping."
                           f"\nUse Undo to reverse them.")
            else:
                summary = (f"{verb} {count} file(s)."
                           f"\nUnmatched: {unmatched}    Unreadable/errors: {problems}")
                if skipped:
                    summary += f"    Skipped: {skipped}"
            self.executeDone.emit(summary)
        except Exception as e:
            logger.exception("Execute failed")
            self.sortFailed.emit(str(e))

    def _after_execute(self, summary):
        self._reset_after_sort()
        self._refresh_undo_state()
        if self.last_output_dir and QMessageBox.question(
                self, "Sort complete", summary + "\n\nOpen the destination folder?"
                ) == QMessageBox.StandardButton.Yes:
            self._open_output()

    def _sort_error(self, error):
        QMessageBox.critical(self, "Error", f"An error occurred:\n{error}")
        self._reset_after_sort()

    def _cancel_running_sort(self):
        """Ask the running Sorter to stop at the next file boundary."""
        if self._active_sorter:
            self._active_sorter.cancel()
            self.cancel_btn.setEnabled(False)
            self.status_label.setText("Cancelling...")

    def _sort_cancelled(self):
        self._reset_after_sort()
        self._refresh_undo_state()
        self.status_label.setText("Cancelled")

    def _update_ocr_indicator(self):
        """Show a persistent warning when OCR (Tesseract) can't run, hide it
        otherwise — or permanently once the user has dismissed it."""
        available, detail = sorter.ocr_status()
        if available or self.settings.get(HIDE_OCR_WARNING_KEY, False):
            self.ocr_warning.hide()
        else:
            self.ocr_warning_label.setText(
                f"⚠  OCR unavailable — scanned/image PDFs can't be read.  {detail}  "
                f'<a href="https://github.com/UB-Mannheim/tesseract/wiki">Get Tesseract</a>'
                " (choose “install just for me” — no admin needed).")
            self.ocr_warning.show()

    def _dismiss_ocr_warning(self):
        self.settings[HIDE_OCR_WARNING_KEY] = True
        save_settings(self.settings)
        self.ocr_warning.hide()

    def _reset_after_sort(self):
        self.sort_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self._active_sorter = None
        self.status_label.setText("Ready")
        self.progress_bar.setValue(0)

    def _refresh_undo_state(self):
        self.undo_btn.setEnabled(bool(self.last_manifest))

    def _open_output(self):
        path = self.last_output_dir
        if not path or not os.path.isdir(path):
            return
        try:
            if hasattr(os, "startfile"):
                os.startfile(path)  # Windows
            else:
                import subprocess
                import sys
                opener = "open" if sys.platform == "darwin" else "xdg-open"
                subprocess.Popen([opener, path])
        except Exception:
            logger.exception("Could not open output folder")

    # --- undo -------------------------------------------------------------

    def _undo_last_sort(self):
        if not self.last_manifest:
            return
        if QMessageBox.question(
                self, "Undo last sort",
                f"Put {len(self.last_manifest)} file(s) back to their original locations?"
                ) != QMessageBox.StandardButton.Yes:
            return
        self.undo_btn.setEnabled(False)
        self.status_label.setText("Undoing...")
        threading.Thread(target=self._do_undo, args=(self.last_manifest,), daemon=True).start()

    def _do_undo(self, manifest):
        undone, errors = sorter.Sorter.undo(manifest)
        utils.clear_manifest()
        self.last_manifest = []
        self.undoDone.emit(undone, errors)

    def _after_undo(self, undone, errors):
        self.status_label.setText("Ready")
        self._refresh_undo_state()
        QMessageBox.information(self, "Undo complete",
                                f"Restored {undone} file(s). Problems: {errors}.")
