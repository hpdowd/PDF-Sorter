"""
dialogs.py

Dialog classes for FileSorter:
- NewMappingDialog: Create a new mapping, optionally importing from an existing mapping file.
- PatternDestDialog: Edit or add a pattern/destination mapping, with user-friendly layout and help.

Author: Your Name
"""

import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from src import utils, theme

class BaseDialog(tk.Toplevel):
    """A base class for creating modal dialogs using standard tkinter."""
    def __init__(self, parent, title=None):
        super().__init__(parent)
        self.configure(background=theme.BG)
        self.transient(parent)
        if title:
            self.title(title)
        
        self.parent = parent
        self.result = None
        
        self.grid_columnconfigure(0, weight=1)
        
        body_frame = ttk.Frame(self)
        self.initial_focus = self.body(body_frame)
        body_frame.grid(row=0, column=0, sticky="nsew", padx=15, pady=15)
        
        self.buttonbox()
        
        self.grab_set()
        if not self.initial_focus:
            self.initial_focus = self
            
        self.protocol("WM_DELETE_WINDOW", self.cancel)
        self.geometry(f"+{parent.winfo_rootx()+50}+{parent.winfo_rooty()+50}")
        self.initial_focus.focus_set()
        self.wait_window(self)

    def body(self, master):
        # Override to create dialog body. Return widget that should have initial focus.
        pass

    def buttonbox(self):
        box = ttk.Frame(self)
        box.grid(row=1, column=0, sticky="e", padx=15, pady=(0, 15))
        
        ok_btn = ttk.Button(box, text="OK", width=10, command=self.ok)
        ok_btn.pack(side=tk.LEFT, padx=(0, 5))
        cancel_btn = ttk.Button(box, text="Cancel", width=10, command=self.cancel)
        cancel_btn.pack(side=tk.LEFT)
        
        self.bind("<Return>", self.ok)
        self.bind("<Escape>", self.cancel)

    def ok(self, event=None):
        if not self.validate():
            self.initial_focus.focus_set()
            return
        
        self.apply()
        self.result = True
        self.destroy()

    def cancel(self, event=None):
        self.result = None
        self.parent.focus_set()
        self.destroy()

    def validate(self):
        return True

    def apply(self):
        pass

class NewMappingDialog(BaseDialog):
    """Dialog for creating a new mapping file."""
    def body(self, master):
        master.grid_columnconfigure(1, weight=1)
        ttk.Label(master, text="New Mapping Name:").grid(row=0, column=0, sticky="w", pady=2, padx=(0,10))
        self.name_entry = ttk.Entry(master, width=40)
        self.name_entry.grid(row=0, column=1, sticky="ew", pady=2)

        self.import_var = tk.BooleanVar()
        self.import_check = ttk.Checkbutton(master, text="Import from existing mapping", variable=self.import_var, command=self.toggle_import)
        self.import_check.grid(row=1, columnspan=2, sticky="w", pady=(10, 0))

        self.import_path_var = tk.StringVar()
        self.import_entry = ttk.Entry(master, textvariable=self.import_path_var, width=35, state="disabled")
        self.import_entry.grid(row=2, column=0, columnspan=2, sticky="ew", pady=2, padx=(20, 85))
        self.browse_btn = ttk.Button(master, text="...", width=5, command=self.browse_import, state="disabled")
        self.browse_btn.grid(row=2, column=1, sticky="e", pady=2)
        
        return self.name_entry

    def toggle_import(self):
        state = "normal" if self.import_var.get() else "disabled"
        self.import_entry.configure(state=state)
        self.browse_btn.configure(state=state)

    def browse_import(self):
        path = filedialog.askopenfilename(
            parent=self,
            title="Select Mapping File to Import",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            initialdir=utils.MAPPINGS_DIR
        )
        if path:
            self.import_path_var.set(path)

    def validate(self):
        self.mapping_name = self.name_entry.get().strip()
        if not self.mapping_name:
            messagebox.showerror("Invalid Name", "Mapping name cannot be empty.", parent=self)
            return False
        if self.import_var.get() and not self.import_path_var.get():
            messagebox.showerror("Invalid Path", "Please select a mapping file to import.", parent=self)
            return False
        return True

    def apply(self):
        self.import_selected = self.import_var.get()
        self.import_path = self.import_path_var.get() if self.import_selected else None

class PatternDestDialog(BaseDialog):
    """Dialog for adding or editing a mapping rule.

    The simple case is unchanged: a rule name, an *Any of these* phrase field, and
    a destination. An *Advanced matching* toggle (progressive disclosure) reveals
    optional *All of these* and *None of these* rows. Only the leading word differs
    across the three so the any/all/none distinction reads at a glance. Advanced
    options are persisted as a ``match`` block (built in :meth:`validate`); a rule
    that uses none stays exactly as short as before.
    """
    def __init__(self, parent, title, template_dir, destinations, initial_name="",
                 initial_phrase="", initial_dest="", initial_match=None):
        self.template_dir = template_dir
        self.destinations = destinations
        self.initial_name = initial_name
        self.initial_phrase = initial_phrase
        self.initial_dest = initial_dest
        self.initial_match = initial_match or {}
        self.match = None
        super().__init__(parent, title)

    @staticmethod
    def _terms(values):
        return [str(t).strip() for t in (values or []) if str(t).strip()]

    def body(self, master):
        master.grid_columnconfigure(0, weight=1)

        initial_all = self._terms(self.initial_match.get("all"))
        initial_none = self._terms(self.initial_match.get("none"))

        ttk.Label(master, text="Rule Name (for easy identification):").pack(anchor="w", pady=(0, 2))
        self.name_entry = ttk.Entry(master, width=50)
        self.name_entry.pack(fill="x", expand=True, pady=(0, 10))
        self.name_entry.insert(0, self.initial_name)

        ttk.Label(master, text="Any of these words or phrases (must be unique):").pack(anchor="w", pady=(0, 2))
        self.phrase_entry = ttk.Entry(master, width=50)
        self.phrase_entry.pack(fill="x", expand=True, pady=(0, 2))
        self.phrase_entry.insert(0, self.initial_phrase)
        ttk.Label(
            master,
            text="Separate alternatives with |  e.g. invoice|receipt  (matches if any appears)",
            style="Muted.TLabel",
        ).pack(anchor="w", pady=(0, 10))

        ttk.Label(master, text="Destination Folder:").pack(anchor="w", pady=(0, 2))
        self.dest_combo = ttk.Combobox(master, values=self.destinations, width=47)
        self.dest_combo.pack(fill="x", expand=True, pady=(0, 10))
        if self.initial_dest:
            self.dest_combo.set(self.initial_dest)

        # --- Advanced matching (progressive disclosure) ---
        self.advanced_var = tk.BooleanVar(value=bool(initial_all or initial_none))
        ttk.Checkbutton(master, text="Advanced matching", variable=self.advanced_var,
                        command=self._toggle_advanced).pack(anchor="w")

        self.adv_frame = ttk.Frame(master)
        ttk.Label(self.adv_frame, text="All of these (must also contain):").pack(anchor="w", pady=(8, 2))
        self.all_entry = ttk.Entry(self.adv_frame, width=50)
        self.all_entry.pack(fill="x", expand=True, pady=(0, 2))
        self.all_entry.insert(0, " | ".join(initial_all))
        ttk.Label(self.adv_frame, text="None of these (ignore the file if it contains):").pack(anchor="w", pady=(8, 2))
        self.none_entry = ttk.Entry(self.adv_frame, width=50)
        self.none_entry.pack(fill="x", expand=True, pady=(0, 2))
        self.none_entry.insert(0, " | ".join(initial_none))
        ttk.Label(self.adv_frame, text="Separate multiple with |", style="Muted.TLabel").pack(anchor="w")

        if self.advanced_var.get():
            self.adv_frame.pack(fill="x", expand=True, pady=(0, 4))

        return self.name_entry

    def _toggle_advanced(self):
        if self.advanced_var.get():
            self.adv_frame.pack(fill="x", expand=True, pady=(0, 4))
        else:
            self.adv_frame.pack_forget()

    def validate(self):
        self.name = self.name_entry.get().strip()
        self.phrase = self.phrase_entry.get().strip()
        self.dest = self.dest_combo.get().strip()
        if not self.name:
            messagebox.showerror("Invalid Name", "Rule Name cannot be empty.", parent=self)
            return False
        if not self.phrase:
            messagebox.showerror("Invalid Phrase", "'Any of these' cannot be empty.", parent=self)
            return False
        if not self.dest:
            messagebox.showerror("Invalid Destination", "Destination cannot be empty.", parent=self)
            return False

        # Build a match block only when advanced options are actually used, so a
        # simple rule stays as short as before. The block carries the 'any' terms
        # too (from the phrase field) since a present block fully defines matching.
        self.match = None
        if self.advanced_var.get():
            all_terms = [p.strip() for p in self.all_entry.get().split("|") if p.strip()]
            none_terms = [p.strip() for p in self.none_entry.get().split("|") if p.strip()]
            if all_terms or none_terms:
                any_terms = [p.strip() for p in self.phrase.split("|") if p.strip()]
                self.match = {"any": any_terms, "all": all_terms, "none": none_terms}
        return True

    def apply(self):
        # The result is read from the instance attributes after the dialog closes
        pass