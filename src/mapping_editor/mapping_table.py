import tkinter as tk
from tkinter import ttk

from src import matching


class MappingTable(ttk.Treeview):
    """
    A custom Treeview widget to display and manage mapping rules.
    Handles the start of drag-and-drop operations.

    The rule's phrase key is the row's item id (iid), so callers read it from the
    selection directly. The visible middle column shows a plain-language "Matches
    when" summary rather than the raw key, so advanced (all/any/none) rules read
    clearly.
    """
    def __init__(self, master, on_item_drag, **kwargs):
        super().__init__(master, columns=("name", "matches", "destination"), show="headings", **kwargs)
        self.heading("name", text="Rule Name")
        self.heading("matches", text="Matches when")
        self.heading("destination", text="Destination Folder")
        self.column("name", width=180, stretch=tk.NO, anchor="w")
        self.column("matches", width=320, stretch=tk.YES, anchor="w")
        self.column("destination", width=220, stretch=tk.YES, anchor="w")

        self.on_item_drag = on_item_drag
        self._dragged_item = None

        self.bind("<ButtonPress-1>", self._on_drag_start)

    def _on_drag_start(self, event):
        """Identifies the item under the cursor and initiates the drag."""
        item_id = self.identify_row(event.y)
        if item_id:
            # The row's iid is the phrase key (the unique rule identifier).
            self._dragged_item = item_id
            self.on_item_drag(self._dragged_item)

    def refresh(self, mappings):
        """Clears and repopulates the table with the given mapping data."""
        # Clear all existing items from the table
        for item in self.get_children():
            self.delete(item)
        # Insert the new mapping rules, keyed by phrase (the iid).
        if mappings:
            for phrase, rule in mappings.items():
                name = rule.get("name", "") if isinstance(rule, dict) else ""
                dest = rule.get("dest", "") if isinstance(rule, dict) else (rule or "")
                summary = matching.describe_match(phrase, rule)
                self.insert("", "end", iid=phrase, values=(name, summary, dest))
