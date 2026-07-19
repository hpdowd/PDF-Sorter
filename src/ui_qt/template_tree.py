"""TemplateTree — displays and manages the template directory structure.

Supports adding/renaming/deleting folders, drag-and-drop of folders from the
OS (copying only the folder structure, no files), and drops of rules from the
RulesTable to assign their destination (emitted as ruleDropped so the editor
owns the mapping change).
"""
import os
import shutil

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QInputDialog, QMessageBox, QTreeWidget,
                               QTreeWidgetItem)

from src.ui_qt.rules_table import RULE_MIME


class TemplateTree(QTreeWidget):
    ruleDropped = Signal(str, str)   # (phrase, rel_path)

    def __init__(self, parent=None, template_dir=None):
        super().__init__(parent)
        self.setHeaderLabels(["Template Folders"])
        self.template_dir = template_dir
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self._pre_drag_item = None   # selection to restore after a drag highlight
        self.populate()

    # --- population -------------------------------------------------------

    def populate(self):
        self.clear()
        if not self.template_dir or not os.path.isdir(self.template_dir):
            return
        root_name = os.path.basename(self.template_dir)
        root = QTreeWidgetItem([f"{root_name} (Root)"])
        root.setData(0, Qt.ItemDataRole.UserRole, ".")
        self.addTopLevelItem(root)
        self._populate_children(root, self.template_dir)
        root.setExpanded(True)

    def _populate_children(self, parent_item, parent_path):
        try:
            names = sorted(os.listdir(parent_path))
        except FileNotFoundError:
            return  # folder deleted during refresh
        for name in names:
            abs_path = os.path.join(parent_path, name)
            if os.path.isdir(abs_path):
                rel_path = os.path.relpath(abs_path, self.template_dir)
                child = QTreeWidgetItem([name])
                child.setData(0, Qt.ItemDataRole.UserRole, rel_path)
                parent_item.addChild(child)
                self._populate_children(child, abs_path)

    def selected_rel_path(self):
        """The selected folder's path relative to the template dir, or None."""
        items = self.selectedItems()
        return items[0].data(0, Qt.ItemDataRole.UserRole) if items else None

    def select_rel_path(self, rel_path):
        def search(item):
            if item.data(0, Qt.ItemDataRole.UserRole) == rel_path:
                self.setCurrentItem(item)
                self.scrollToItem(item)
                return True
            return any(search(item.child(i)) for i in range(item.childCount()))
        for i in range(self.topLevelItemCount()):
            if search(self.topLevelItem(i)):
                return

    # --- folder operations ------------------------------------------------

    def add_folder(self):
        parent_path = self.template_dir
        rel = self.selected_rel_path()
        if rel:
            parent_path = os.path.join(self.template_dir, rel)
        name, ok = QInputDialog.getText(self, "New Folder", "Enter folder name:")
        if ok and name:
            try:
                os.makedirs(os.path.join(parent_path, name))
                self.populate()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Could not create folder:\n{e}")

    def delete_folder(self):
        rel = self.selected_rel_path()
        if not rel:
            QMessageBox.warning(self, "No Selection", "Please select a folder to delete.")
            return
        if rel == ".":
            QMessageBox.warning(self, "Cannot Delete", "Cannot delete the root template folder.")
            return
        if QMessageBox.question(
                self, "Confirm Delete",
                f"Are you sure you want to delete '{rel}' and all its contents?"
                ) == QMessageBox.StandardButton.Yes:
            try:
                shutil.rmtree(os.path.join(self.template_dir, rel))
                self.populate()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Could not delete folder:\n{e}")

    # --- drops: rules (assign destination) and OS folders (structure only) --

    def _drop_kind(self, mime):
        if mime.hasFormat(RULE_MIME):
            return "rule"
        if any(u.isLocalFile() and os.path.isdir(u.toLocalFile()) for u in mime.urls()):
            return "folders"
        return None

    def dragEnterEvent(self, event):
        if self._drop_kind(event.mimeData()):
            self._pre_drag_item = self.currentItem()
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if self._drop_kind(event.mimeData()):
            # Highlight the row under the cursor so the target folder is
            # visible; the original selection is restored when the drag ends.
            item = self.itemAt(event.position().toPoint())
            self.setCurrentItem(item)
            event.acceptProposedAction()

    def dragLeaveEvent(self, event):
        self._restore_selection()
        super().dragLeaveEvent(event)

    def _restore_selection(self):
        self.setCurrentItem(self._pre_drag_item)
        self._pre_drag_item = None

    def dropEvent(self, event):
        kind = self._drop_kind(event.mimeData())
        if kind == "rule":
            phrase = bytes(event.mimeData().data(RULE_MIME)).decode("utf-8")
            item = self.itemAt(event.position().toPoint())
            rel_path = item.data(0, Qt.ItemDataRole.UserRole) if item else "."
            self._restore_selection()
            self.ruleDropped.emit(phrase, rel_path)
            event.acceptProposedAction()
        elif kind == "folders":
            for url in event.mimeData().urls():
                path = url.toLocalFile()
                if os.path.isdir(path):
                    self._copy_folder_structure_only(path, self.template_dir)
            self._pre_drag_item = None   # repopulating deletes the old items
            self.populate()
            QMessageBox.information(self, "Folders Added",
                                    "Folder structure added to template directory.")
            event.acceptProposedAction()

    def _copy_folder_structure_only(self, src, dst):
        """Copy only the folder structure (no files) from src into the template dir."""
        for root, dirs, files in os.walk(src):
            rel_path = os.path.relpath(root, src)
            if rel_path == ".":
                target_dir = os.path.join(dst, os.path.basename(src))
            else:
                target_dir = os.path.join(dst, os.path.basename(src), rel_path)
            os.makedirs(target_dir, exist_ok=True)
