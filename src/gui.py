import os
import json
import logging
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinterdnd2 import DND_FILES, TkinterDnD
import threading

from src import sorter, utils, __version__

logger = logging.getLogger("ocr_file_sorter.gui")
from src.mapping_editor.editor_gui import MappingEditor
from src.utils import (
    load_settings, save_settings,
    LAST_MAPPING_KEY, MAPPINGS_DIR
)

class FileSorterGUI:
    def __init__(self, root):
        self.root = root
        self.root.title(f"OCR File Sorter v{__version__}")
        self.root.geometry("500x500")
        
        self.mapping_path = None
        self.settings = load_settings()
        self.deep_audit = tk.BooleanVar()
        self.first_page_only = tk.BooleanVar(value=True) # Default to True for speed
        self.root.minsize(300, 220)

        self._progress_done = 0
        self.last_manifest = utils.load_manifest()  # enables Undo across restarts
        self.last_output_dir = None

        self._build_widgets()
        self._populate_mappings()
        self._refresh_undo_state()

    def _show_help(self):
        message = (
            "OCR File Sorter Help\n\n"
            "This tool sorts PDF files into folders based on their content using OCR technology.\n\n"
            "Folders to Sort:\n"
            "- Add one or more folders containing PDF files to be sorted.\n"
            "- You can drag and drop folders from Explorer into the list below to add them quickly.\n\n"
            "Deep Audit:\n"
            "When enabled, the tool will recursively scan all subdirectories for PDF files to sort.\n\n"
            "First Page Only:\n"
            "When enabled, only scans the first page of each PDF for faster processing.\n\n"
            "Use the Mapping Editor to create or modify sorting rules based on PDF content.\n\n"
            f"Logs are written to:\n{utils.LOG_FILE}\n"
        )
        messagebox.showinfo("Help - OCR File Sorter", message)

    def _build_widgets(self):
        # --- Mapping Selection ---
        mapping_frame = ttk.LabelFrame(self.root, text="Mapping File")
        mapping_frame.pack(fill="x", padx=10, pady=5)

        self.mapping_combo = ttk.Combobox(mapping_frame, state="readonly")
        self.mapping_combo.pack(side="left", fill="x", expand=True, padx=5, pady=5)
        self.mapping_combo.bind("<<ComboboxSelected>>", self._on_mapping_selected)
        utils.ToolTip(self.mapping_combo, "Select a mapping file to use for sorting PDFs.")

        edit_btn = ttk.Button(mapping_frame, text="Edit/Create Mapping", command=self._open_mapping_editor)
        edit_btn.pack(side="left", padx=5)
        utils.ToolTip(edit_btn, "Open the mapping editor to create or modify mapping files.")

        # --- Folder List ---
        folder_frame = ttk.LabelFrame(self.root, text="Folders to Sort (Drag folders here or use Add Folder...)")
        folder_frame.pack(fill="both", expand=True, padx=10, pady=5)

        listbox_frame = ttk.Frame(folder_frame)
        listbox_frame.pack(side="left", fill="both", expand=True, padx=(5, 0), pady=5)

        self.folder_listbox = tk.Listbox(listbox_frame, selectmode=tk.EXTENDED, bg="#ffffff")
        self.folder_listbox.place(relx=0, rely=0, relwidth=1, relheight=1)
        self.folder_listbox.drop_target_register(DND_FILES)
        self.folder_listbox.dnd_bind('<<Drop>>', self._on_drop_folders)

        self.watermark_label = tk.Label(
            self.folder_listbox, text="OCR File Sorter", font=("Arial", 16, "bold"), fg="#cccccc", bg="#ffffff"
        )
        self._update_watermark()

        listbox_frame.rowconfigure(0, weight=1)
        listbox_frame.columnconfigure(0, weight=1)
        self.folder_listbox.lift()

        button_frame = ttk.Frame(folder_frame)
        button_frame.pack(side="left", fill="y", padx=5, pady=5)

        add_folder_btn = ttk.Button(button_frame, text="Add Folder...", command=self._add_folder)
        add_folder_btn.pack(fill="x", pady=(0, 5))
        utils.ToolTip(add_folder_btn, "Add a folder to the list to be sorted.")

        remove_folder_btn = ttk.Button(button_frame, text="Remove Selected", command=self._remove_selected_folders)
        remove_folder_btn.pack(fill="x")
        utils.ToolTip(remove_folder_btn, "Remove selected folders from the list.")

        self.root.rowconfigure(2, weight=1)
        self.root.columnconfigure(0, weight=1)
        folder_frame.rowconfigure(0, weight=1)
        folder_frame.columnconfigure(0, weight=1)

        # --- Options ---
        options_frame = ttk.Frame(self.root)
        options_frame.pack(fill="x", padx=10, pady=5)

        deep_audit_check = ttk.Checkbutton(
            options_frame, text="Deep Audit", variable=self.deep_audit
        )
        deep_audit_check.pack(side="left", padx=5)
        utils.ToolTip(deep_audit_check, "If checked, also scan PDFs inside subfolders (recursive).")

        first_page_check = ttk.Checkbutton(
            options_frame, text="Scan first page only (faster)", variable=self.first_page_only
        )
        first_page_check.pack(side="left", padx=5)
        utils.ToolTip(first_page_check, "Speeds up sorting by only reading the first page of each PDF.")

        # --- Bottom Buttons ---
        button_row = ttk.Frame(self.root)
        button_row.pack(fill="x", padx=10, pady=5)

        self.sort_btn = ttk.Button(button_row, text="Sort Files", command=self._start_sort_thread)
        self.sort_btn.pack(side="left")
        utils.ToolTip(self.sort_btn, "Preview the sort, then choose Move or Copy.")

        self.undo_btn = ttk.Button(button_row, text="Undo Last Sort", command=self._undo_last_sort, state="disabled")
        self.undo_btn.pack(side="left", padx=(5, 0))
        utils.ToolTip(self.undo_btn, "Put the files from the last sort back where they were.")

        help_btn = ttk.Button(button_row, text="Help", command=self._show_help)
        help_btn.pack(side="right")
        utils.ToolTip(help_btn, "Show help and usage instructions.")

        # --- Status Bar ---
        status_frame = ttk.Frame(self.root)
        status_frame.pack(side="bottom", fill="x", padx=10, pady=5)
        self.status_label = ttk.Label(status_frame, text="Ready")
        self.status_label.pack(side="left")
        self.progress_bar = ttk.Progressbar(status_frame, orient="horizontal", mode="determinate")
        self.progress_bar.pack(side="right", fill="x", expand=True, padx=(10, 0))

        self.folder_listbox.bind("<Configure>", lambda e: self._update_watermark())

    def _update_watermark(self):
        if self.folder_listbox.size() == 0:
            self.watermark_label.place(relx=0.5, rely=0.5, anchor="center")
        else:
            self.watermark_label.place_forget()

    def _populate_mappings(self):
        mappings = utils.MappingUtils.get_available_mappings()
        self.mapping_combo['values'] = mappings
        last_mapping = self.settings.get(LAST_MAPPING_KEY)
        if mappings:
            if last_mapping and last_mapping in mappings:
                self.mapping_combo.set(last_mapping)
                self.mapping_path = os.path.join(MAPPINGS_DIR, last_mapping)
            else:
                self.mapping_combo.current(0)
                self.mapping_path = os.path.join(MAPPINGS_DIR, mappings[0])
        else:
            self.mapping_path = None

    def _on_mapping_selected(self, event=None):
        selected = self.mapping_combo.get()
        if selected:
            self.mapping_path = os.path.join(MAPPINGS_DIR, selected)
            self.settings[LAST_MAPPING_KEY] = selected
            save_settings(self.settings)
    def _add_folder(self):
        folder = filedialog.askdirectory(mustexist=True, title="Select Folder to Sort")
        if folder and folder not in self.folder_listbox.get(0, tk.END):
            self.folder_listbox.insert(tk.END, folder)
        self._update_watermark()

    def _on_drop_folders(self, event):
        paths = self.root.tk.splitlist(event.data)
        for folder in paths:
            folder = folder.strip('"')
            if os.path.isdir(folder) and folder not in self.folder_listbox.get(0, tk.END):
                self.folder_listbox.insert(tk.END, folder)
        self._update_watermark()

    def _remove_selected_folders(self):
        for idx in reversed(self.folder_listbox.curselection()):
            self.folder_listbox.delete(idx)
        self._update_watermark()

    def _open_mapping_editor(self):
        def on_save_callback():
            selected = os.path.basename(self.mapping_path) if self.mapping_path else None
            self.settings[LAST_MAPPING_KEY] = selected
            save_settings(self.settings)
            self._populate_mappings()
            if selected:
                self.mapping_combo.set(selected)
        MappingEditor(self.root, on_save_callback=on_save_callback, mapping_path=self.mapping_path)

    def update_status(self, message):
        """Callback function to update the status label from the sorter."""
        self.root.after(0, lambda: self.status_label.config(text=message))

    def _on_progress(self):
        """Advance the progress bar by one PDF (called from the sort thread)."""
        self._progress_done = getattr(self, "_progress_done", 0) + 1
        done = self._progress_done
        self.root.after(0, lambda: self.progress_bar.config(value=done))

    def _start_sort_thread(self):
        # Validate on the main thread, then scan/plan in the background.
        mapping_path = self.mapping_path
        folders = list(self.folder_listbox.get(0, tk.END))
        if not mapping_path or not os.path.isfile(mapping_path):
            utils.show_error("Please select a valid mapping file.")
            return
        if not folders:
            utils.show_error("Please add at least one folder to sort.")
            return
        deep_audit = self.deep_audit.get()
        first_page_only = self.first_page_only.get()

        self.sort_btn.config(state="disabled")
        self.undo_btn.config(state="disabled")
        self.status_label.config(text="Scanning...")
        self.progress_bar['value'] = 0
        threading.Thread(
            target=self._plan_and_preview,
            args=(mapping_path, folders, deep_audit, first_page_only),
            daemon=True,
        ).start()

    def _plan_and_preview(self, mapping_path, folders, deep_audit, first_page_only):
        try:
            sorter_obj = sorter.Sorter(
                mapping_path,
                status_callback=self.update_status,
                progress_callback=self._on_progress,
            )
            total = sorter_obj.count_pdfs(folders, deep_audit=deep_audit)
            self._progress_done = 0
            self.root.after(0, lambda: self.progress_bar.config(maximum=max(total, 1), value=0))
            plan = sorter_obj.plan(folders, deep_audit=deep_audit, first_page_only=first_page_only)
            self.root.after(0, lambda: self._show_preview(sorter_obj, plan))
        except Exception as e:
            logger.exception("Planning failed")
            self.root.after(0, lambda: self._sort_error(e))

    def _show_preview(self, sorter_obj, plan):
        if not plan:
            messagebox.showinfo("Nothing to sort", "No PDF files were found in the selected folders.")
            self._reset_after_sort()
            return
        dialog = SortPreviewDialog(self.root, plan)
        if not dialog.confirmed:
            self.status_label.config(text="Cancelled")
            self._reset_after_sort()
            return
        copy = dialog.copy_mode
        self.status_label.config(text="Copying..." if copy else "Moving...")
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
            verb = "Copied" if copy else "Moved"
            summary = (f"{verb} {count} file(s)."
                       f"\nUnmatched: {unmatched}    Unreadable/errors: {problems}")
            self.root.after(0, lambda: self._after_execute(summary))
        except Exception as e:
            logger.exception("Execute failed")
            self.root.after(0, lambda: self._sort_error(e))

    def _after_execute(self, summary):
        self._reset_after_sort()
        self._refresh_undo_state()
        if self.last_output_dir and messagebox.askyesno(
                "Sort complete", summary + "\n\nOpen the destination folder?"):
            self._open_output()

    def _sort_error(self, error):
        utils.show_error(f"An error occurred:\n{error}")
        self._reset_after_sort()

    def _reset_after_sort(self):
        self.sort_btn.config(state="normal")
        self.status_label.config(text="Ready")
        self.progress_bar['value'] = 0

    def _refresh_undo_state(self):
        self.undo_btn.config(state="normal" if self.last_manifest else "disabled")

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

    def _undo_last_sort(self):
        if not self.last_manifest:
            return
        if not messagebox.askyesno(
                "Undo last sort",
                f"Put {len(self.last_manifest)} file(s) back to their original locations?"):
            return
        self.undo_btn.config(state="disabled")
        self.status_label.config(text="Undoing...")
        threading.Thread(target=self._do_undo, args=(self.last_manifest,), daemon=True).start()

    def _do_undo(self, manifest):
        undone, errors = sorter.Sorter.undo(manifest)
        utils.clear_manifest()
        self.last_manifest = []

        def done():
            self.status_label.config(text="Ready")
            self._refresh_undo_state()
            messagebox.showinfo("Undo complete", f"Restored {undone} file(s). Problems: {errors}.")
        self.root.after(0, done)


class SortPreviewDialog(tk.Toplevel):
    """Shows each PDF's planned outcome; the user picks Move, Copy, or Cancel."""

    STATUS_LABEL = {
        "matched": "will sort",
        "unmatched": "no match",
        "unreadable": "unreadable",
        "error": "error",
    }

    def __init__(self, master, plan):
        super().__init__(master)
        self.title("Preview sort")
        self.geometry("640x430")
        self.transient(master)
        self.confirmed = False
        self.copy_mode = False

        matched = [p for p in plan if p.status == "matched"]
        unmatched = [p for p in plan if p.status == "unmatched"]
        problems = [p for p in plan if p.status in ("unreadable", "error")]

        ttk.Label(
            self,
            text=(f"{len(matched)} to sort    ·    {len(unmatched)} no match    ·    "
                  f"{len(problems)} unreadable/error"),
            font=("Segoe UI", 10, "bold"),
        ).pack(anchor="w", padx=10, pady=(10, 5))

        frame = ttk.Frame(self)
        frame.pack(fill="both", expand=True, padx=10)
        tree = ttk.Treeview(frame, columns=("outcome", "dest"), show="tree headings")
        tree.heading("#0", text="File")
        tree.heading("outcome", text="Outcome")
        tree.heading("dest", text="Destination")
        tree.column("#0", width=240)
        tree.column("outcome", width=100, anchor="w")
        tree.column("dest", width=260, anchor="w")
        vsb = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=vsb.set)
        tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        tree.tag_configure("matched", foreground="#1a7f37")
        tree.tag_configure("unmatched", foreground="#57606a")
        tree.tag_configure("unreadable", foreground="#9a6700")
        tree.tag_configure("error", foreground="#cf222e")

        for p in matched + unmatched + problems:
            dest = f"{p.dest}/{p.dest_name}" if p.status == "matched" else p.message
            tree.insert("", "end", text=p.filename,
                        values=(self.STATUS_LABEL.get(p.status, p.status), dest),
                        tags=(p.status,))

        btns = ttk.Frame(self)
        btns.pack(fill="x", padx=10, pady=10)
        cancel_btn = ttk.Button(btns, text="Cancel", command=self._cancel)
        cancel_btn.pack(side="right")
        copy_btn = ttk.Button(btns, text="Copy", command=self._copy,
                              state=("normal" if matched else "disabled"))
        copy_btn.pack(side="right", padx=(0, 5))
        move_btn = ttk.Button(btns, text="Move", command=self._move,
                              state=("normal" if matched else "disabled"))
        move_btn.pack(side="right", padx=(0, 5))

        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.grab_set()
        (move_btn if matched else cancel_btn).focus_set()
        self.wait_window()

    def _move(self):
        self.copy_mode = False
        self.confirmed = True
        self.destroy()

    def _copy(self):
        self.copy_mode = True
        self.confirmed = True
        self.destroy()

    def _cancel(self):
        self.confirmed = False
        self.destroy()


def main():
    utils.setup_logging()
    logger.info("OCR File Sorter v%s starting", __version__)
    root = TkinterDnD.Tk()
    app = FileSorterGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()