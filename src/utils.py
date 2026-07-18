import os
import sys
import json
import shutil
import logging
from logging.handlers import RotatingFileHandler
import tkinter as tk
from tkinter import messagebox

# --- Constants ---
LAST_MAPPING_KEY = "last_mapping_file"
OUTPUT_DIR_KEY = "output_dir"
DEEP_AUDIT_KEY = "deep_audit"
FIRST_PAGE_KEY = "first_page_only"

def _mappings_dir():
    """Per-user, writable mappings directory.

    Previously the mappings lived next to the code (``src/mappings``), which in a
    frozen build resolves *inside* the app's ``_internal`` folder. That folder is
    replaced on every update and removed on uninstall, so any mapping the user
    created there — and the files sorted into its template tree — were silently
    lost. Store mappings alongside settings/logs under the per-user app-data dir.
    """
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, "OCR File Sorter", "mappings")

MAPPINGS_DIR = _mappings_dir()

def _bundled_mappings_dir():
    """Read-only default mappings shipped with the app (source tree or bundle)."""
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "mappings"))

def ensure_mappings_seeded():
    """Seed the per-user mappings dir with the bundled defaults on first run.

    Only seeds when the per-user dir has no mapping files yet, so we never
    resurrect a default the user deleted or overwrite their edits. Safe to call
    repeatedly.
    """
    try:
        os.makedirs(MAPPINGS_DIR, exist_ok=True)
    except OSError:
        logging.getLogger(LOGGER_NAME).exception("Could not create mappings dir")
        return
    if any(f.endswith(".json") for f in os.listdir(MAPPINGS_DIR)):
        return  # already populated; leave the user's mappings alone
    src_dir = _bundled_mappings_dir()
    if not os.path.isdir(src_dir):
        return
    try:
        for name in os.listdir(src_dir):
            src = os.path.join(src_dir, name)
            dst = os.path.join(MAPPINGS_DIR, name)
            if os.path.isdir(src):
                shutil.copytree(src, dst, dirs_exist_ok=True)
            elif not os.path.exists(dst):
                shutil.copy2(src, dst)
    except OSError:
        logging.getLogger(LOGGER_NAME).exception("Failed to seed default mappings")

# Reserved top-level keys in a mapping file that are config, not phrase rules.
RESERVED_MAPPING_KEYS = ("_config",)

# --- Logging ---
LOGGER_NAME = "ocr_file_sorter"

def _log_path():
    """Per-user log file location (alongside settings, independent of CWD)."""
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, "OCR File Sorter", "logs", "ocr-file-sorter.log")

LOG_FILE = _log_path()

# A NullHandler on the base logger avoids the stdlib "last resort" stderr output
# when the app hasn't called setup_logging() (e.g. during tests or library use).
logging.getLogger(LOGGER_NAME).addHandler(logging.NullHandler())

def setup_logging(level=logging.INFO):
    """Attach a rotating file handler under the per-user log dir. Idempotent.

    Returns the log file path. If the log file can't be created, the app keeps
    running (logging just goes nowhere).
    """
    logger = logging.getLogger(LOGGER_NAME)
    if any(not isinstance(h, logging.NullHandler) for h in logger.handlers):
        return LOG_FILE  # already configured
    logger.setLevel(level)
    try:
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        handler = RotatingFileHandler(
            LOG_FILE, maxBytes=1_000_000, backupCount=3, encoding="utf-8"
        )
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
        )
        logger.addHandler(handler)
    except OSError:
        pass
    return LOG_FILE

def _settings_path():
    """Per-user settings location, independent of the launch directory.

    Previously this was a bare 'settings.json' resolved against the current
    working directory, so settings only persisted when launched from a specific
    folder. Store it under the user's app-data directory instead.
    """
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, "OCR File Sorter", "settings.json")

SETTINGS_FILE = _settings_path()

# --- Settings Functions ---
def load_settings():
    """Loads the application settings from the per-user settings file."""
    try:
        with open(SETTINGS_FILE, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_settings(settings):
    """Saves the application settings to the per-user settings file."""
    os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
    with open(SETTINGS_FILE, 'w') as f:
        json.dump(settings, f, indent=4)

# --- Sort manifest (for Undo, persisted so it survives a restart) ---
def _manifest_path():
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, "OCR File Sorter", "last_sort.json")

MANIFEST_FILE = _manifest_path()

def save_manifest(entries):
    """Persist the last sort's move manifest (list of {src,dest,copied})."""
    try:
        os.makedirs(os.path.dirname(MANIFEST_FILE), exist_ok=True)
        with open(MANIFEST_FILE, "w", encoding="utf-8") as f:
            json.dump({"entries": entries}, f, indent=2)
    except OSError:
        pass

def load_manifest():
    """Return the last saved manifest entries, or [] if none/unreadable."""
    try:
        with open(MANIFEST_FILE, "r", encoding="utf-8") as f:
            return json.load(f).get("entries", [])
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return []

def clear_manifest():
    """Remove the persisted manifest (after a successful undo)."""
    try:
        os.remove(MANIFEST_FILE)
    except OSError:
        pass

# --- Dialog helpers ---
# These accept either show_x(message) or show_x(title, message), so both the
# main window (single-arg) and the mapping editor (title + message) can use them.
def show_error(title, message=None, parent=None):
    """Show an error dialog."""
    if message is None:
        title, message = "Error", title
    messagebox.showerror(title, message, parent=parent)

def show_warning(title, message=None, parent=None):
    """Show a warning dialog."""
    if message is None:
        title, message = "Warning", title
    messagebox.showwarning(title, message, parent=parent)

def show_info(title, message=None, parent=None):
    """Show an informational dialog."""
    if message is None:
        title, message = "Information", title
    messagebox.showinfo(title, message, parent=parent)

class MappingUtils:
    """A utility class for handling mapping files."""

    @staticmethod
    def get_available_mappings():
        """Returns a sorted list of available .json mapping files."""
        ensure_mappings_seeded()
        return sorted([f for f in os.listdir(MAPPINGS_DIR) if f.endswith(".json")])

    @staticmethod
    def is_valid_mapping_file(file_path):
        """Checks if a file is a valid, non-empty JSON file."""
        if not file_path or not os.path.exists(file_path) or os.path.getsize(file_path) == 0:
            return False
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                json.load(f)
            return True
        except (json.JSONDecodeError, UnicodeDecodeError):
            return False

    @staticmethod
    def load_mapping(file_path):
        """Loads mapping data from a JSON file, migrating old format if necessary."""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            # Check for old format and migrate.
            # The first value in the dict will be a string in the old format,
            # and a dictionary in the new format.
            if data and isinstance(next(iter(data.values())), str):
                migrated_data = {}
                for phrase, dest in data.items():
                    # Create a default name from the phrase for backward compatibility
                    default_name = phrase.replace("_", " ").replace("-", " ").title()
                    migrated_data[phrase] = {"name": default_name, "dest": dest}
                return migrated_data
            
            return data
        except (FileNotFoundError, json.JSONDecodeError, StopIteration):
            return {}

    @staticmethod
    def save_mapping(file_path, data):
        """Saves mapping data to a JSON file."""
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)

# --- UI Helpers ---
class ToolTip:
    """
    Create a tooltip for a given widget.
    """
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tipwindow = None
        widget.bind("<Enter>", self.show_tip)
        widget.bind("<Leave>", self.hide_tip)

    def show_tip(self, event=None):
        if self.tipwindow or not self.text:
            return
        x = self.widget.winfo_pointerx() + 20
        y = self.widget.winfo_pointery() + 10
        self.tipwindow = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        label = tk.Label(
            tw, text=self.text, justify=tk.LEFT,
            background="#ffffe0", relief=tk.SOLID, borderwidth=1,
            font=("tahoma", "8", "normal")
        )
        label.pack(ipadx=1)

    def hide_tip(self, event=None):
        tw = self.tipwindow
        self.tipwindow = None
        if tw:
            tw.destroy()
