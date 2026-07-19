import os
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk
from src.mapping_editor.dialogs import NewMappingDialog, PatternDestDialog
from src import utils

MAPPINGS_DIR = utils.MAPPINGS_DIR

class EditorActions:
    """
    Handles user actions and coordinates between the View (Editor) and Model (Logic).
    """
    def __init__(self, view, logic):
        self.view = view
        self.logic = logic
        self._dragged_item = None
        self._dragging = False

    def on_close_window(self):
        """Handle closing the window, checking for unsaved changes."""
        if self._check_unsaved_changes():
            self.view.destroy()

    def on_mapping_file_selected(self, event=None):
        """Load a new mapping file when selected from the combobox."""
        if not self._check_unsaved_changes():
            self.view.update_mapping_file_display(self.logic.mapping_path)
            return
        selected_file = self.view.mapping_file_var.get()
        if not selected_file: return
        
        file_path = os.path.join(MAPPINGS_DIR, selected_file)
        self.logic.load_mapping_file(file_path)
        self.view.refresh_all()

    def on_new_mapping(self):
        """Handle the 'New Mapping' button click."""
        if not self._check_unsaved_changes(): return
        
        dialog = NewMappingDialog(self.view, "New Mapping")
        if not dialog.mapping_name: return

        mapping_path = os.path.join(MAPPINGS_DIR, dialog.mapping_name + ".json")
        if os.path.exists(mapping_path):
            messagebox.showerror("File Exists", "A mapping file with that name already exists.", parent=self.view)
            return

        template_dir = self.logic._get_template_dir(mapping_path)
        os.makedirs(template_dir, exist_ok=True)

        if dialog.import_selected and dialog.import_path:
            import shutil
            shutil.copy(dialog.import_path, mapping_path)
            import_template_dir = self.logic._get_template_dir(dialog.import_path)
            if os.path.exists(import_template_dir):
                if os.path.exists(template_dir): shutil.rmtree(template_dir)
                shutil.copytree(import_template_dir, template_dir)
        else:
            with open(mapping_path, "w", encoding="utf-8") as f: f.write("{}")
        
        self.logic.load_mapping_file(mapping_path)
        self.view.refresh_all(reload_files=True)

    def on_search_mapping(self):
        """Show a searchable dialog to find and load a mapping file."""
        if not self._check_unsaved_changes(): return
        
        os.makedirs(MAPPINGS_DIR, exist_ok=True)
        all_files = [f for f in os.listdir(MAPPINGS_DIR) if f.endswith(".json")]
        
        dialog = tk.Toplevel(self.view)
        dialog.title("Search Mapping File")
        dialog.geometry("400x400")
        dialog.transient(self.view)
        dialog.grab_set()
        
        ttk.Label(dialog, text="Search:").pack(anchor="w", padx=10, pady=(10, 0))
        search_var = tk.StringVar()
        search_entry = ttk.Entry(dialog, textvariable=search_var)
        search_entry.pack(fill="x", padx=10, pady=(0, 5))
        search_entry.focus_set()
        
        listbox = tk.Listbox(dialog, height=15)
        listbox.pack(fill="both", expand=True, padx=10, pady=5)
        
        def update_list(*args):
            query = search_var.get().lower()
            listbox.delete(0, tk.END)
            for f in all_files:
                if query in f.lower():
                    listbox.insert(tk.END, f)
        search_var.trace_add("write", update_list)
        update_list()
        
        selected_file = {"name": None}
        def on_select(event=None):
            selection = listbox.curselection()
            if selection:
                selected_file["name"] = listbox.get(selection[0])
                dialog.destroy()
        
        listbox.bind("<Double-Button-1>", on_select)
        
        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(fill="x", padx=10, pady=(0, 10))
        ok_btn = ttk.Button(btn_frame, text="OK", command=on_select)
        ok_btn.pack(side="right")
        cancel_btn = ttk.Button(btn_frame, text="Cancel", command=dialog.destroy)
        cancel_btn.pack(side="right", padx=(0, 5))
        
        dialog.wait_window()
        
        if selected_file["name"]:
            file_path = os.path.join(MAPPINGS_DIR, selected_file["name"])
            self.logic.load_mapping_file(file_path)
            self.view.refresh_all(reload_files=True)

    def on_save(self):
        """Handle the 'Save' button click."""
        self.logic.set_naming_scheme(self.view.scheme_var.get())
        success, message = self.logic.save_mappings()
        if success:
            self.view.set_dirty(False)
            if self.view.on_save_callback:
                self.view.on_save_callback()
            messagebox.showinfo("Saved", message, parent=self.view)
        else:
            messagebox.showerror("Error", message, parent=self.view)

    def on_add_rule(self):
        """Handle adding a new mapping rule."""
        destinations = self.logic.get_all_destinations()
        dialog = PatternDestDialog(self.view, "Add Rule", self.logic.template_dir, destinations)
        if not dialog.result: return # Check if the user clicked OK

        success, message = self.logic.add_rule(dialog.phrase, dialog.name, dialog.dest, dialog.match)
        if success:
            self.view.refresh_mapping_table()
            self.view.set_dirty(True)
        else:
            messagebox.showwarning("Warning", message, parent=self.view)

    def on_edit_rule(self):
        """Handle editing an existing mapping rule."""
        selected_item = self.view.mapping_table.selection()
        if not selected_item:
            messagebox.showwarning("No Selection", "Please select a mapping to edit.", parent=self.view)
            return
        
        # The row's iid is the phrase key; read the full rule (incl. any match
        # block) from the model rather than the displayed summary.
        phrase = selected_item[0]
        rule = self.logic.mappings.get(phrase, {})
        name = rule.get("name", "") if isinstance(rule, dict) else ""
        dest = rule.get("dest", "") if isinstance(rule, dict) else (rule or "")
        match = rule.get("match") if isinstance(rule, dict) else None
        destinations = self.logic.get_all_destinations()
        dialog = PatternDestDialog(self.view, "Edit Rule", self.logic.template_dir, destinations,
                                   initial_name=name, initial_phrase=phrase, initial_dest=dest,
                                   initial_match=match)
        if not dialog.result: return # Check if the user clicked OK

        success, message = self.logic.update_rule(phrase, dialog.phrase, dialog.name, dialog.dest, dialog.match)
        if success:
            self.view.refresh_mapping_table()
            self.view.set_dirty(True)
        else:
            messagebox.showwarning("Warning", message, parent=self.view)

    def on_remove_rule(self):
        """Handle removing a mapping rule."""
        selected_item = self.view.mapping_table.selection()
        if not selected_item:
            messagebox.showwarning("No Selection", "Please select a mapping to remove.", parent=self.view)
            return
        phrase = selected_item[0]  # iid is the phrase key
        self.logic.remove_rule(phrase)
        self.view.refresh_mapping_table()
        self.view.set_dirty(True)

    def on_move_rule(self, direction):
        """Handle moving a rule up or down."""
        selected_item = self.view.mapping_table.selection()
        if not selected_item: return
        phrase = selected_item[0]  # iid is the phrase key
        if self.logic.move_rule(phrase, direction):
            self.view.refresh_mapping_table()
            # Reselect the item after refresh (its iid is unchanged).
            self.view.mapping_table.selection_set(phrase)
            self.view.mapping_table.see(phrase)
            self.view.set_dirty(True)

    def on_rename_template_folder(self):
        """Handle renaming a folder in the template tree."""
        selected_item = self.view.template_tree.selection()
        if not selected_item:
            messagebox.showwarning("No Selection", "Please select a folder to rename.", parent=self.view)
            return
        
        old_rel_path = self.view.template_tree.item(selected_item[0], "values")[0]
        old_name = os.path.basename(old_rel_path)
        new_name = simpledialog.askstring("Rename Folder", f"Enter new name for '{old_name}':", parent=self.view)
        if not new_name or new_name == old_name: return

        success, message = self.logic.rename_template_folder(old_rel_path, new_name)
        if success:
            self.view.refresh_all()
            self.view.set_dirty(True)
        else:
            messagebox.showerror("Error", message, parent=self.view)

    def on_autobuild_tree(self):
        """Handle the 'Auto-Build Tree' button click."""
        created = self.logic.autobuild_template_tree()
        self.view.refresh_template_tree()
        messagebox.showinfo("Done", f"Template tree updated. Folders created/ensured: {created}", parent=self.view)

    def on_drag_release(self, event):
        """Handle the release of a drag-and-drop operation."""
        if not self._dragging or not self._dragged_item: return
        
        widget = self.view.winfo_containing(self.view.winfo_pointerx(), self.view.winfo_pointery())
        if widget == self.view.template_tree:
            y = self.view.template_tree.winfo_pointery() - self.view.template_tree.winfo_rooty()
            dest_item = self.view.template_tree.identify_row(y)
            rel_path = self.view.template_tree.item(dest_item, "values")[0] if dest_item else "."
            
            # Update the destination in the rule's dictionary
            if self.logic.mappings[self._dragged_item]["dest"] != rel_path:
                self.logic.mappings[self._dragged_item]["dest"] = rel_path
                self.view.refresh_mapping_table()
                self.view.set_dirty(True)
        
        self._dragging = False
        self._dragged_item = None
        self.view.clear_drag_highlight()

    def on_item_drag_start(self, item):
        self._dragged_item = item
        self._dragging = True

    def on_drag_motion(self):
        if self._dragging:
            self.view.highlight_template_tree_under_pointer()

    def _check_unsaved_changes(self):
        """Check for unsaved changes and prompt user. Return True if it's safe to proceed."""
        if not self.logic.is_dirty: return True
        response = messagebox.askyesnocancel("Unsaved Changes", "You have unsaved changes. Do you want to save them?", parent=self.view)
        if response is True: # Yes
            self.on_save()
            return not self.logic.is_dirty
        elif response is False: # No
            return True
        else: # Cancel
            return False