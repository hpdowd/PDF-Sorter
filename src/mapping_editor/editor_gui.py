import os
import tkinter as tk
from tkinter import ttk

from src import utils
from src.utils import ToolTip
from src.mapping_editor.dialogs import NewMappingDialog, PatternDestDialog
from src.mapping_editor.mapping_table import MappingTable
from src.mapping_editor.template_tree import TemplateTree
from src.mapping_editor.editor_logic import EditorLogic
from src.mapping_editor.editor_actions import EditorActions

MAPPINGS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../mappings"))

class MappingEditor(tk.Toplevel):
    """
    Main window for editing file sorting mappings.
    This class is the 'View' in a Model-View-Controller architecture.
    It builds the UI and delegates all logic and actions to other classes.
    """
    def __init__(self, master, on_save_callback=None, mapping_path=None):
        super().__init__(master)
        self.title("Mapping Editor")
        self.geometry("1000x600")
        self.on_save_callback = on_save_callback

        # Instantiate Logic (Model) and Actions (Controller)
        self.logic = EditorLogic()
        self.actions = EditorActions(self, self.logic)

        self._build_widgets()
        self.protocol("WM_DELETE_WINDOW", self.actions.on_close_window)
        self.bind_all("<ButtonRelease-1>", self.actions.on_drag_release)

        # Initial load if a mapping path is provided
        if mapping_path:
            self.logic.load_mapping_file(mapping_path)
            self.refresh_all(reload_files=True)

    def _build_widgets(self):
        # --- Top frame for mapping file selection ---
        file_frame = ttk.Frame(self)
        file_frame.pack(fill="x", padx=10, pady=(10, 0))

        self.mapping_file_var = tk.StringVar()
        self.mapping_file_combo = ttk.Combobox(file_frame, textvariable=self.mapping_file_var, state="readonly")
        self.mapping_file_combo.pack(side="left", fill="x", expand=True, padx=(0, 5), ipady=2, ipadx=4)
        self.mapping_file_combo.bind("<<ComboboxSelected>>", self.actions.on_mapping_file_selected)
        ToolTip(self.mapping_file_combo, "Select a mapping JSON file to edit.")

        search_btn = ttk.Button(file_frame, text="Search...", command=self.actions.on_search_mapping)
        search_btn.pack(side="left")
        ToolTip(search_btn, "Search for a mapping JSON file by name.")

        new_btn = ttk.Button(file_frame, text="New Mapping", command=self.actions.on_new_mapping)
        new_btn.pack(side="left", padx=(5, 0))
        ToolTip(new_btn, "Create a new mapping file.")

        # --- Main PanedWindow for resizable split view ---
        paned = ttk.PanedWindow(self, orient="horizontal")
        paned.pack(fill="both", expand=True, padx=10, pady=10)

        # --- Left Panel: Mapping Table ---
        self._build_left_panel(paned)

        # --- Right Panel: Template Tree ---
        self._build_right_panel(paned)

        # --- Optional filename scheme ---
        scheme_frame = ttk.Frame(self)
        scheme_frame.pack(fill="x", padx=10, pady=(0, 5))
        ttk.Label(scheme_frame, text="Filename scheme:").pack(side="left")
        self.scheme_var = tk.StringVar()
        scheme_entry = ttk.Entry(scheme_frame, textvariable=self.scheme_var)
        scheme_entry.pack(side="left", fill="x", expand=True, padx=(5, 0))
        ToolTip(scheme_entry,
                "Optional: rename sorted files. Placeholders: {rule_name} {phrase} "
                "{original_filename} {date} {time} {ext}. "
                "e.g. {rule_name}_{date} - {original_filename}{ext}. Blank = keep names.")
        self.scheme_var.trace_add("write", lambda *a: self.set_dirty(True))

        # --- Bottom frame for Save/Cancel ---
        bottom_frame = ttk.Frame(self)
        bottom_frame.pack(fill="x", padx=10, pady=(0, 10))
        save_btn = ttk.Button(bottom_frame, text="Save", command=self.actions.on_save)
        save_btn.pack(side="right", padx=(5, 0))
        cancel_btn = ttk.Button(bottom_frame, text="Cancel", command=self.actions.on_close_window)
        cancel_btn.pack(side="right")

    def _build_left_panel(self, parent):
        left_frame = ttk.Frame(parent)
        parent.add(left_frame, weight=3)
        ttk.Label(left_frame, text="Phrase / Keyword → Destination", font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=5, pady=(0, 2))
        
        self.mapping_table = MappingTable(left_frame, on_item_drag=self.actions.on_item_drag_start)
        self.mapping_table.pack(fill="both", expand=True)
        self.mapping_table.bind("<B1-Motion>", lambda e: self.actions.on_drag_motion())
        self.mapping_table.bind("<Double-Button-1>", lambda e: self.actions.on_edit_rule())
        self._build_mapping_table_menu()
        self.mapping_table.bind("<Button-3>", self._show_mapping_table_menu)
        ToolTip(self.mapping_table, "Phrases and their destination folders. Drag a phrase onto a folder to assign.")

        button_frame = ttk.Frame(left_frame)
        button_frame.pack(fill="x", pady=(8, 0))
        ttk.Button(button_frame, text="Add", command=self.actions.on_add_rule).pack(side="left", fill="x", expand=True, padx=(0, 5))
        ttk.Button(button_frame, text="Remove", command=self.actions.on_remove_rule).pack(side="left", fill="x", expand=True, padx=(0, 5))
        ttk.Button(button_frame, text="Move Up", command=lambda: self.actions.on_move_rule("up")).pack(side="left", fill="x", expand=True, padx=(0, 5))
        ttk.Button(button_frame, text="Move Down", command=lambda: self.actions.on_move_rule("down")).pack(side="left", fill="x", expand=True)

    def _build_right_panel(self, parent):
        right_frame = ttk.Frame(parent)
        parent.add(right_frame, weight=2)
        ttk.Label(right_frame, text="Template Directory Structure", font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=5, pady=(0, 2))

        self.template_tree = TemplateTree(right_frame, self.logic.template_dir)
        self.template_tree.pack(fill="both", expand=True, padx=(0, 5))
        self._build_template_tree_menu()
        self.template_tree.bind("<Button-3>", self._show_template_tree_menu)
        ToolTip(self.template_tree, "Visualize and manage the template directory structure.")

        template_btn_frame = ttk.Frame(right_frame)
        template_btn_frame.pack(fill="x", pady=(8, 0))
        ttk.Button(template_btn_frame, text="New Folder", command=self.template_tree.add_folder).pack(side="left", padx=(0, 5))
        ttk.Button(template_btn_frame, text="Delete Folder", command=self.template_tree.delete_folder).pack(side="left", padx=(0, 5))
        ttk.Button(template_btn_frame, text="Refresh", command=self.refresh_template_tree).pack(side="left")
        ttk.Button(template_btn_frame, text="Auto-Build Tree", command=self.actions.on_autobuild_tree).pack(side="left", padx=(5, 0))

    def _build_mapping_table_menu(self):
        self.mapping_table_menu = tk.Menu(self, tearoff=0)
        self.mapping_table_menu.add_command(label="Add Rule", command=self.actions.on_add_rule)
        self.mapping_table_menu.add_command(label="Edit Rule", command=self.actions.on_edit_rule)
        self.mapping_table_menu.add_command(label="Remove Rule", command=self.actions.on_remove_rule)

    def _show_mapping_table_menu(self, event):
        is_item_selected = bool(self.mapping_table.identify_row(event.y))
        if is_item_selected:
            self.mapping_table.selection_set(self.mapping_table.identify_row(event.y))
        
        self.mapping_table_menu.entryconfig("Edit Rule", state="normal" if is_item_selected else "disabled")
        self.mapping_table_menu.entryconfig("Remove Rule", state="normal" if is_item_selected else "disabled")
        self.mapping_table_menu.tk_popup(event.x_root, event.y_root)

    def _build_template_tree_menu(self):
        self.template_tree_menu = tk.Menu(self, tearoff=0)
        self.template_tree_menu.add_command(label="Add Folder", command=self.template_tree.add_folder)
        self.template_tree_menu.add_command(label="Rename Folder", command=self.actions.on_rename_template_folder)
        self.template_tree_menu.add_command(label="Delete Folder", command=self.template_tree.delete_folder)

    def _show_template_tree_menu(self, event):
        is_item_selected = bool(self.template_tree.identify_row(event.y))
        if is_item_selected:
            self.template_tree.selection_set(self.template_tree.identify_row(event.y))

        self.template_tree_menu.entryconfig("Rename Folder", state="normal" if is_item_selected else "disabled")
        self.template_tree_menu.entryconfig("Delete Folder", state="normal" if is_item_selected else "disabled")
        self.template_tree_menu.tk_popup(event.x_root, event.y_root)

    # --- UI Update Methods (called by Actions) ---

    def refresh_all(self, reload_files=False):
        """Refresh the entire view based on the current logic state."""
        if reload_files:
            self.update_mapping_file_list()
        self.update_mapping_file_display(self.logic.mapping_path)
        self.refresh_mapping_table()
        self.refresh_template_tree()
        dirty = self.logic.is_dirty
        self.scheme_var.set(self.logic.get_naming_scheme())  # trace may flip dirty
        self.set_dirty(dirty)

    def refresh_mapping_table(self):
        self.mapping_table.refresh(self.logic.mappings)

    def refresh_template_tree(self):
        self.template_tree.template_dir = self.logic.template_dir
        self.template_tree._populate_tree()

    def set_dirty(self, is_dirty):
        """Update window title to show unsaved changes state."""
        title = "Mapping Editor"
        if is_dirty:
            self.title(f"{title} *")
        else:
            self.title(title)
        self.logic.is_dirty = is_dirty

    def update_mapping_file_list(self):
        self.mapping_file_combo["values"] = utils.MappingUtils.get_available_mappings()

    def update_mapping_file_display(self, mapping_path):
        self.mapping_file_var.set(os.path.basename(mapping_path) if mapping_path else "")

    def highlight_template_tree_under_pointer(self):
        self.clear_drag_highlight()
        y = self.template_tree.winfo_pointery() - self.template_tree.winfo_rooty()
        item = self.template_tree.identify_row(y)
        if item:
            self.template_tree.tag_configure("drag_highlight", background="#a1e3f7")
            self.template_tree.item(item, tags=("drag_highlight",))

    def clear_drag_highlight(self):
        def _clear_recursive(item):
            self.template_tree.item(item, tags=())
            for child in self.template_tree.get_children(item):
                _clear_recursive(child)
        for item in self.template_tree.get_children(""):
            _clear_recursive(item)

    # --- Drag and drop logic for assigning destination folders ---

    def _on_item_drag_event(self, action, item, event=None):
        if action == "start":
            self._dragged_item = item
            self._dragging = True
        elif action == "motion":
            if self._dragging:
                self.highlight_template_tree_under_pointer()

    def _on_drag_motion_context(self, event):
        if self._dragging and self._dragged_item:
            widget = event.widget
            if widget == self.template_tree:
                self._drag_context = "template"
                self.highlight_template_tree_under_pointer()
            else:
                self._drag_context = None

    def _on_drag_release(self, event):
        if not self._dragging or not self._dragged_item:
            return
        widget = self.winfo_containing(self.winfo_pointerx(), self.winfo_pointery())
        if widget == self.template_tree:
            x = self.template_tree.winfo_pointerx() - self.template_tree.winfo_rootx()
            y = self.template_tree.winfo_pointery() - self.template_tree.winfo_rooty()
            dest_item = self.template_tree.identify_row(y)
            if dest_item:
                rel_path = self.template_tree.item(dest_item, "values")[0]
                self._highlight_drop_target(dest_item)
            else:
                rel_path = "."
            if self._dragged_item in self.logic.mappings:
                if self.logic.mappings[self._dragged_item] != rel_path:
                    self.logic.mappings[self._dragged_item] = rel_path
                    self.refresh_mapping_table()
                    self.set_dirty(True)
        self._dragged_item = None
        self._dragging = False
        self._drag_context = None

    def _highlight_drop_target(self, item):
        self.template_tree.tag_configure("drop_highlight", background="#7fe3a1")
        self.template_tree.item(item, tags=("drop_highlight",))
        self.after(350, lambda: self.template_tree.item(item, tags=()))

    # --- End drag and drop logic ---


# For testing layout only
if __name__ == "__main__":
    root = tk.Tk()
    root.withdraw()
    MappingEditor(root)
    root.mainloop()