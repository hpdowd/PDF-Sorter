import os
import csv
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
    LAST_MAPPING_KEY, OUTPUT_DIR_KEY, MAPPINGS_DIR,
    DEEP_AUDIT_KEY, FIRST_PAGE_KEY,
)

class FileSorterGUI:
    def __init__(self, root):
        self.root = root
        self.root.title(f"OCR File Sorter v{__version__}")
        self.root.geometry("500x500")
        
        self.mapping_path = None
        self.settings = load_settings()
        self.output_dir = self.settings.get(OUTPUT_DIR_KEY)
        self.deep_audit = tk.BooleanVar(value=self.settings.get(DEEP_AUDIT_KEY, False))
        self.first_page_only = tk.BooleanVar(value=self.settings.get(FIRST_PAGE_KEY, True))
        self.root.minsize(360, 300)

        self._progress_done = 0
        self.last_manifest = utils.load_manifest()  # enables Undo across restarts
        self.last_output_dir = None
        self._active_sorter = None  # the Sorter of the running scan/sort, for Cancel

        self._build_widgets()
        self._populate_mappings()
        self._refresh_undo_state()

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
            "- You can drag and drop folders from Explorer into the list to add them quickly.\n\n"
            "Settings (the Settings button, or File > Settings):\n"
            "- Deep Audit: also scan PDFs inside subfolders (recursive).\n"
            "- Scan first page only: faster; reads just the first page of each PDF.\n\n"
            "Mapping rules:\n"
            "- A rule matches when its phrase appears in a PDF's text.\n"
            "- Separate alternatives with | (e.g. invoice|receipt) to match any of them.\n"
            "- Rules are checked top to bottom; the first match wins.\n\n"
            f"Mappings are stored in:\n{utils.MAPPINGS_DIR}\n\n"
            f"Logs are written to:\n{utils.LOG_FILE}\n"
        )
        messagebox.showinfo("Help - OCR File Sorter", message)

    def _show_about(self):
        available, detail = sorter.ocr_status()
        ocr_line = detail if available else f"unavailable — {detail}"
        messagebox.showinfo(
            "About OCR File Sorter",
            f"OCR File Sorter\nVersion {__version__}\n\n"
            "Sorts PDFs into folders based on their text content, "
            "with an OCR fallback for scanned documents.\n\n"
            f"OCR: {ocr_line}",
        )

    def _build_widgets(self):
        PAD = 8
        self._setup_styles()
        self._build_menubar()

        # --- Mapping + Output (aligned rows, no heavy group borders) ---
        top = ttk.Frame(self.root)
        top.pack(fill="x", padx=PAD, pady=(PAD, 0))
        top.columnconfigure(1, weight=1)

        ttk.Label(top, text="Mapping").grid(row=0, column=0, sticky="w", padx=(0, PAD), pady=4)
        self.mapping_combo = ttk.Combobox(top, state="readonly")
        self.mapping_combo.grid(row=0, column=1, sticky="ew", pady=4)
        self.mapping_combo.bind("<<ComboboxSelected>>", self._on_mapping_selected)
        utils.ToolTip(self.mapping_combo, "Select a mapping file to use for sorting PDFs.")
        edit_btn = ttk.Button(top, text="Edit / Create...", command=self._open_mapping_editor)
        edit_btn.grid(row=0, column=2, sticky="e", padx=(PAD, 0), pady=4)
        utils.ToolTip(edit_btn, "Open the mapping editor to create or modify mapping files.")

        ttk.Label(top, text="Output").grid(row=1, column=0, sticky="w", padx=(0, PAD), pady=4)
        self.output_var = tk.StringVar(value=self.output_dir or "")
        output_entry = ttk.Entry(top, textvariable=self.output_var, state="readonly")
        output_entry.grid(row=1, column=1, sticky="ew", pady=4)
        utils.ToolTip(output_entry, "Sorted files (and their category subfolders) are placed under this folder.")
        choose_output_btn = ttk.Button(top, text="Choose...", command=self._choose_output_dir)
        choose_output_btn.grid(row=1, column=2, sticky="e", padx=(PAD, 0), pady=4)
        utils.ToolTip(choose_output_btn, "Pick the folder where sorted files will be placed.")

        # --- Folders to sort (the main workspace) ---
        folder_frame = ttk.LabelFrame(self.root, text="Folders to sort  (drag folders here, or use Add)")
        folder_frame.pack(fill="both", expand=True, padx=PAD, pady=PAD)

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

        # --- Bottom buttons ---
        button_row = ttk.Frame(self.root)
        button_row.pack(fill="x", padx=PAD, pady=(0, PAD))

        self.sort_btn = ttk.Button(button_row, text="Sort Files", style="Primary.TButton",
                                   command=self._start_sort_thread)
        self.sort_btn.pack(side="left")
        utils.ToolTip(self.sort_btn, "Preview the sort, then choose Move or Copy.")

        self.undo_btn = ttk.Button(button_row, text="Undo Last Sort", command=self._undo_last_sort, state="disabled")
        self.undo_btn.pack(side="left", padx=(PAD, 0))
        utils.ToolTip(self.undo_btn, "Put the files from the last sort back where they were.")

        self.cancel_btn = ttk.Button(button_row, text="Cancel", command=self._cancel_running_sort,
                                     state="disabled")
        self.cancel_btn.pack(side="left", padx=(PAD, 0))
        utils.ToolTip(self.cancel_btn, "Stop the scan or sort that is currently running.")

        self.settings_btn = ttk.Button(button_row, text="Settings", command=self._open_preferences)
        self.settings_btn.pack(side="right")
        utils.ToolTip(self.settings_btn, "Open Settings — scan options (deep audit, first page only).")

        # --- Status Bar ---
        status_frame = ttk.Frame(self.root)
        status_frame.pack(side="bottom", fill="x", padx=PAD, pady=(0, PAD))
        self.status_label = ttk.Label(status_frame, text="Ready")
        self.status_label.pack(side="left")
        self.progress_bar = ttk.Progressbar(status_frame, orient="horizontal", mode="determinate")
        self.progress_bar.pack(side="right", fill="x", expand=True, padx=(PAD, 0))

        # Persistent OCR warning, shown only when OCR can't run. Packed after the
        # status bar (side=bottom) so it sits just above it when visible.
        self.ocr_warning = ttk.Label(self.root, foreground="#9a6700", anchor="w")
        self._update_ocr_indicator()

        self.folder_listbox.bind("<Configure>", lambda e: self._update_watermark())

    def _setup_styles(self):
        # Emphasize the primary action by weight/size. Native (vista) themed buttons
        # don't reliably honor a background color, so we lean on font + padding.
        style = ttk.Style()
        style.configure("Primary.TButton", font=("Segoe UI", 10, "bold"), padding=(14, 8))

    def _build_menubar(self):
        menubar = tk.Menu(self.root)

        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Settings...", command=self._open_preferences)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.root.destroy)
        menubar.add_cascade(label="File", menu=file_menu)

        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="Help", command=self._show_help)
        help_menu.add_command(label="About", command=self._show_about)
        menubar.add_cascade(label="Help", menu=help_menu)

        self.root.config(menu=menubar)

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

    def _choose_output_dir(self):
        initial = self.output_dir if self.output_dir and os.path.isdir(self.output_dir) else ""
        folder = filedialog.askdirectory(
            mustexist=True, title="Select Output Folder", initialdir=initial)
        if folder:
            self.output_dir = folder
            self.output_var.set(folder)
            self.settings[OUTPUT_DIR_KEY] = folder
            save_settings(self.settings)

    def _open_preferences(self):
        dialog = PreferencesDialog(self.root, self.first_page_only.get(), self.deep_audit.get())
        if dialog.result is None:
            return
        first_page, deep = dialog.result
        self.first_page_only.set(first_page)
        self.deep_audit.set(deep)
        self.settings[FIRST_PAGE_KEY] = first_page
        self.settings[DEEP_AUDIT_KEY] = deep
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
        output_dir = self.output_dir
        if not output_dir or not os.path.isdir(output_dir):
            utils.show_error("Please choose an output folder for the sorted files.")
            return
        deep_audit = self.deep_audit.get()
        first_page_only = self.first_page_only.get()

        self.sort_btn.config(state="disabled")
        self.undo_btn.config(state="disabled")
        self.cancel_btn.config(state="normal")
        self.status_label.config(text="Scanning...")
        self.progress_bar['value'] = 0
        threading.Thread(
            target=self._plan_and_preview,
            args=(mapping_path, output_dir, folders, deep_audit, first_page_only),
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
            self._progress_done = 0
            self.root.after(0, lambda: self.progress_bar.config(maximum=max(total, 1), value=0))
            plan = sorter_obj.plan(folders, deep_audit=deep_audit, first_page_only=first_page_only)
            if sorter_obj.cancelled:
                self.root.after(0, self._sort_cancelled)
                return
            self.root.after(0, lambda: self._show_preview(sorter_obj, plan))
        except Exception as e:
            logger.exception("Planning failed")
            self.root.after(0, lambda err=e: self._sort_error(err))

    def _show_preview(self, sorter_obj, plan):
        if not plan:
            messagebox.showinfo("Nothing to sort", "No PDF files were found in the selected folders.")
            self._reset_after_sort()
            return
        dialog = SortPreviewDialog(self.root, plan, sorter_obj)
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
            self.root.after(0, lambda: self._after_execute(summary))
        except Exception as e:
            logger.exception("Execute failed")
            self.root.after(0, lambda err=e: self._sort_error(err))

    def _after_execute(self, summary):
        self._reset_after_sort()
        self._refresh_undo_state()
        if self.last_output_dir and messagebox.askyesno(
                "Sort complete", summary + "\n\nOpen the destination folder?"):
            self._open_output()

    def _sort_error(self, error):
        utils.show_error(f"An error occurred:\n{error}")
        self._reset_after_sort()

    def _cancel_running_sort(self):
        """Ask the running Sorter to stop at the next file boundary."""
        if self._active_sorter:
            self._active_sorter.cancel()
            self.cancel_btn.config(state="disabled")
            self.status_label.config(text="Cancelling...")

    def _sort_cancelled(self):
        self._reset_after_sort()
        self._refresh_undo_state()
        self.status_label.config(text="Cancelled")

    def _update_ocr_indicator(self):
        """Show a persistent warning when OCR (Tesseract) can't run, hide it otherwise."""
        available, detail = sorter.ocr_status()
        if available:
            self.ocr_warning.pack_forget()
        else:
            self.ocr_warning.config(
                text=f"  ⚠  OCR unavailable — scanned/image PDFs can't be read.  {detail}")
            self.ocr_warning.pack(side="bottom", fill="x")

    def _reset_after_sort(self):
        self.sort_btn.config(state="normal")
        self.cancel_btn.config(state="disabled")
        self._active_sorter = None
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


class PreferencesDialog(tk.Toplevel):
    """Remembered scan defaults: first-page-only and deep audit.

    result is None on cancel, or a (first_page_only, deep_audit) tuple on OK.
    """

    def __init__(self, master, first_page_only, deep_audit):
        super().__init__(master)
        self.title("Settings")
        self.transient(master)
        self.resizable(False, False)
        self.result = None

        self.first_page_var = tk.BooleanVar(value=first_page_only)
        self.deep_audit_var = tk.BooleanVar(value=deep_audit)

        frame = ttk.Frame(self)
        frame.pack(fill="both", expand=True, padx=16, pady=16)

        ttk.Label(frame, text="Scanning", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(0, 6))
        ttk.Checkbutton(
            frame, text="Scan first page only (faster)", variable=self.first_page_var
        ).pack(anchor="w")
        ttk.Checkbutton(
            frame, text="Deep audit — also scan PDFs inside subfolders", variable=self.deep_audit_var
        ).pack(anchor="w", pady=(4, 0))

        btns = ttk.Frame(frame)
        btns.pack(fill="x", pady=(16, 0))
        ttk.Button(btns, text="OK", command=self._ok).pack(side="right")
        ttk.Button(btns, text="Cancel", command=self._cancel).pack(side="right", padx=(0, 6))

        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.bind("<Return>", lambda e: self._ok())
        self.bind("<Escape>", lambda e: self._cancel())
        self.grab_set()
        self.wait_window()

    def _ok(self):
        self.result = (self.first_page_var.get(), self.deep_audit_var.get())
        self.destroy()

    def _cancel(self):
        self.result = None
        self.destroy()


class SortPreviewDialog(tk.Toplevel):
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

    def __init__(self, master, plan, sorter_obj):
        super().__init__(master)
        self.title("Preview sort")
        self.geometry("720x470")
        self.transient(master)
        self.confirmed = False
        self.copy_mode = False
        self._sorter = sorter_obj
        self._folders = sorter_obj.destination_folders()

        matched = [p for p in plan if p.status == "matched"]
        unmatched = [p for p in plan if p.status == "unmatched"]
        problems = [p for p in plan if p.status in ("unreadable", "error")]

        self.summary_label = ttk.Label(self, font=("Segoe UI", 10, "bold"))
        self.summary_label.pack(anchor="w", padx=10, pady=(10, 2))
        ttk.Label(
            self, foreground="#57606a",
            text="Double-click a file to change where it goes, or mark it not to be sorted.",
        ).pack(anchor="w", padx=10, pady=(0, 5))

        frame = ttk.Frame(self)
        frame.pack(fill="both", expand=True, padx=10)
        self.tree = tree = ttk.Treeview(frame, columns=("outcome", "matched", "dest"),
                                        show="tree headings")
        tree.heading("#0", text="File")
        tree.heading("outcome", text="Outcome")
        tree.heading("matched", text="Matched phrase")
        tree.heading("dest", text="Destination")
        tree.column("#0", width=190)
        tree.column("outcome", width=85, anchor="w")
        tree.column("matched", width=125, anchor="w")
        tree.column("dest", width=210, anchor="w")
        vsb = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=vsb.set)
        tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        tree.tag_configure("matched", foreground="#1a7f37")
        tree.tag_configure("unmatched", foreground="#57606a")
        tree.tag_configure("unreadable", foreground="#9a6700")
        tree.tag_configure("error", foreground="#cf222e")
        tree.tag_configure("skipped", foreground="#57606a")

        # Keep insertion order stable across edits, and map each row to its PlanItem.
        self._rows = matched + unmatched + problems
        self._item_by_iid = {}
        for p in self._rows:
            iid = tree.insert("", "end", text=p.filename,
                              values=self._row_values(p), tags=(p.status,))
            self._item_by_iid[iid] = p
        tree.bind("<Double-1>", self._on_double_click)

        btns = ttk.Frame(self)
        btns.pack(fill="x", padx=10, pady=10)
        export_btn = ttk.Button(btns, text="Export...", command=self._export_csv)
        export_btn.pack(side="left")
        utils.ToolTip(export_btn, "Save this preview (each file and where it would go) to a CSV.")
        change_btn = ttk.Button(btns, text="Change destination...", command=self._edit_selected)
        change_btn.pack(side="left", padx=(5, 0))
        utils.ToolTip(change_btn, "Send the selected file to a different folder, or don't sort it.")
        self.cancel_btn = ttk.Button(btns, text="Cancel", command=self._cancel)
        self.cancel_btn.pack(side="right")
        self.copy_btn = ttk.Button(btns, text="Copy", command=self._copy)
        self.copy_btn.pack(side="right", padx=(0, 5))
        self.move_btn = ttk.Button(btns, text="Move", command=self._move)
        self.move_btn.pack(side="right", padx=(0, 5))

        self._refresh_actions()
        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.grab_set()
        (self.move_btn if matched else self.cancel_btn).focus_set()
        self.wait_window()

    def _row_values(self, p):
        """The (outcome, phrase, destination) cells shown for one PlanItem."""
        if p.status == "matched":
            return (self.STATUS_LABEL["matched"], p.phrase or "", f"{p.dest}/{p.dest_name}")
        if p.status == "skipped":
            return (self.STATUS_LABEL["skipped"], "", "(won't be sorted)")
        return (self.STATUS_LABEL.get(p.status, p.status), "", p.message)

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
        self.summary_label.config(text="    ·    ".join(parts))
        state = "normal" if matched else "disabled"
        self.move_btn.config(state=state)
        self.copy_btn.config(state=state)

    def _on_double_click(self, event):
        iid = self.tree.identify_row(event.y)
        if iid:
            self._edit_item(iid)

    def _edit_selected(self):
        sel = self.tree.selection()
        if sel:
            self._edit_item(sel[0])
        else:
            messagebox.showinfo("Change destination",
                                "Select a file first, then choose its destination.", parent=self)

    def _edit_item(self, iid):
        p = self._item_by_iid[iid]
        current = p.dest if p.status == "matched" else None
        chooser = DestinationChooser(self, p.filename, self._folders, current)
        if not chooser.result:
            return
        action, folder = chooser.result
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
        self.tree.item(iid, values=self._row_values(p), tags=(p.status,))
        self._refresh_actions()

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

    def _export_csv(self):
        path = filedialog.asksaveasfilename(
            parent=self, title="Export preview to CSV",
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")])
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["File", "Outcome", "Matched phrase", "Destination"])
                for p in self._rows:
                    outcome, phrase, dest = self._row_values(p)
                    writer.writerow([p.filename, outcome, phrase, dest])
        except OSError as e:
            messagebox.showerror("Export failed", str(e), parent=self)


class DestinationChooser(tk.Toplevel):
    """Pick a destination folder for one file, or mark it not to be sorted.

    result is None if cancelled, ("dest", folder) to file into `folder`, or
    ("skip", None) to leave the file where it is.
    """

    def __init__(self, master, filename, folders, current=None):
        super().__init__(master)
        self.title("Change destination")
        self.transient(master)
        self.resizable(False, False)
        self.result = None
        self._folders = folders

        frame = ttk.Frame(self)
        frame.pack(fill="both", expand=True, padx=16, pady=16)
        ttk.Label(frame, text="File:").grid(row=0, column=0, sticky="w")
        ttk.Label(frame, text=filename, font=("Segoe UI", 9, "bold")).grid(
            row=0, column=1, sticky="w", padx=(6, 0))
        ttk.Label(frame, text="Send to:").grid(row=1, column=0, sticky="w", pady=(12, 0))
        self.var = tk.StringVar(value=current or (folders[0] if folders else ""))
        combo = ttk.Combobox(frame, textvariable=self.var, values=folders,
                             state="readonly", width=34)
        combo.grid(row=1, column=1, sticky="we", padx=(6, 0), pady=(12, 0))

        btns = ttk.Frame(frame)
        btns.grid(row=2, column=0, columnspan=2, sticky="e", pady=(18, 0))
        assign_btn = ttk.Button(btns, text="Assign", command=self._assign,
                                state=("normal" if folders else "disabled"))
        assign_btn.pack(side="left")
        ttk.Button(btns, text="Don't sort this file", command=self._skip).pack(
            side="left", padx=(6, 0))
        ttk.Button(btns, text="Cancel", command=self._cancel).pack(side="left", padx=(6, 0))

        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.bind("<Escape>", lambda e: self._cancel())
        self.grab_set()
        (combo if folders else assign_btn).focus_set()
        self.wait_window()

    def _assign(self):
        folder = self.var.get()
        if folder:
            self.result = ("dest", folder)
        self.destroy()

    def _skip(self):
        self.result = ("skip", None)
        self.destroy()

    def _cancel(self):
        self.result = None
        self.destroy()


def main():
    utils.setup_logging()
    logger.info("OCR File Sorter v%s starting", __version__)
    utils.ensure_mappings_seeded()
    root = TkinterDnD.Tk()
    app = FileSorterGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()