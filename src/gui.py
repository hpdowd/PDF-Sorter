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

        self._build_widgets()
        self._populate_mappings()

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
        utils.ToolTip(self.sort_btn, "Start sorting PDF files according to the selected options.")

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

    def _start_sort_thread(self):
        self.sort_btn.config(state="disabled")
        self.status_label.config(text="Starting sort...")
        self.progress_bar['value'] = 0
        thread = threading.Thread(target=self._sort_files, daemon=True)
        thread.start()

    def _sort_files(self):
        mapping_path = self.mapping_path
        folders = self.folder_listbox.get(0, tk.END)
        if not mapping_path or not os.path.isfile(mapping_path):
            self.root.after(0, lambda: utils.show_error("Please select a valid mapping file."))
            self.root.after(0, lambda: self.sort_btn.config(state="normal"))
            return
        if not folders:
            self.root.after(0, lambda: utils.show_error("Please add at least one folder to sort."))
            self.root.after(0, lambda: self.sort_btn.config(state="normal"))
            return

        try:
            sorter_obj = sorter.Sorter(
                mapping_path,
                status_callback=self.update_status
            )
            deep_audit = self.deep_audit.get()
            first_page_only = self.first_page_only.get()
            
            self.root.after(0, lambda: self.progress_bar.config(maximum=len(folders)))
            total_scanned = 0
            total_moved = 0
            for i, folder in enumerate(folders):
                if os.path.isdir(folder):
                    self.root.after(0, lambda f=folder: self.status_label.config(text=f"Sorting {os.path.basename(f)}..."))
                    scanned, moved = sorter_obj.sort_files([folder], deep_audit=deep_audit, first_page_only=first_page_only)
                    total_scanned += scanned
                    total_moved += moved
                self.root.after(0, lambda v=i+1: self.progress_bar.config(value=v))

            summary = f"Sorted {total_moved} of {total_scanned} PDF(s) scanned."
            self.root.after(0, lambda: messagebox.showinfo("Sort complete", summary))
        except Exception as e:
            logger.exception("Sorting failed")
            self.root.after(0, lambda: utils.show_error(f"An error occurred during sorting:\n{e}"))
        finally:
            def final_update():
                self.sort_btn.config(state="normal")
                self.status_label.config(text="Ready")
                self.progress_bar['value'] = 0
            self.root.after(0, final_update)

def main():
    utils.setup_logging()
    logger.info("OCR File Sorter v%s starting", __version__)
    root = TkinterDnD.Tk()
    app = FileSorterGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()