import os
import sys
import json
import logging
from logging.handlers import RotatingFileHandler
import tkinter as tk
from tkinter import messagebox

# --- Constants ---
LAST_MAPPING_KEY = "last_mapping_file"
MAPPINGS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "mappings"))

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
        os.makedirs(MAPPINGS_DIR, exist_ok=True)
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
