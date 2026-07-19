import tkinter as tk
from tkinter import ttk, font as tkfont

from src import theme, matching

# Colour per matching role, so a rule's "Matches when" line reads at a glance:
# any=blue, all=green, none=red (Variant A). Connectors stay ink.
_ROLE_COLOR = {
    "or": theme.ACCENT,
    "and": theme.GOOD,
    "not": theme.RED,
    "by": theme.AMBER,
    "plain": theme.INK,
}

_HEAD_H = 26
_ROW_H = 30
_PAD = 12
_NAME_W = 175
_FOLDER_W = 210


class MappingTable(tk.Frame):
    """Rules list drawn on a Canvas so the "Matches when" column can colour each
    term inline (a ttk.Treeview can only colour a whole cell).

    Presents the slice of the Treeview API the editor relies on — ``refresh``,
    ``selection``/``selection_set``, ``identify_row``, ``see`` — and keeps the
    phrase key as each row's id. Rows are selectable and drag-startable exactly
    as before.
    """
    def __init__(self, master, on_item_drag, **kwargs):
        super().__init__(master, background=theme.SURFACE)
        self.on_item_drag = on_item_drag
        self._rows = []          # [{iid, name, segs, folder, y0, y1}]
        self._selected = None

        self._font = tkfont.Font(family="Segoe UI", size=10)
        self._bold = tkfont.Font(family="Segoe UI", size=10, weight="bold")
        self._head = tkfont.Font(family="Segoe UI", size=8, weight="bold")

        self.canvas = tk.Canvas(self, background=theme.SURFACE, highlightthickness=0)
        self.vsb = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.vsb.set)
        self.vsb.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)

        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<Configure>", lambda e: self._redraw())
        self.canvas.bind("<MouseWheel>", self._on_wheel)
        self.canvas.bind("<Button-4>", lambda e: self.canvas.yview_scroll(-1, "units"))
        self.canvas.bind("<Button-5>", lambda e: self.canvas.yview_scroll(1, "units"))

    # Route event bindings (double-click, right-click, motion, tooltip Enter/Leave)
    # to the canvas, where the mouse actually is.
    def bind(self, sequence=None, func=None, add=None):
        return self.canvas.bind(sequence, func, add)

    def _on_wheel(self, event):
        self.canvas.yview_scroll(-1 if event.delta > 0 else 1, "units")

    # --- Treeview-compatible surface --------------------------------------
    def refresh(self, mappings):
        self._rows = []
        self._selected = None
        for phrase, rule in (mappings or {}).items():
            name = rule.get("name", "") if isinstance(rule, dict) else ""
            folder = rule.get("dest", "") if isinstance(rule, dict) else (rule or "")
            self._rows.append({
                "iid": phrase, "name": name, "folder": folder,
                "segs": matching.describe_match_segments(phrase, rule),
                "y0": None, "y1": None,
            })
        self._redraw()

    def selection(self):
        return (self._selected,) if self._selected else ()

    def selection_set(self, iid):
        self._selected = iid
        self._redraw()

    def identify_row(self, y):
        cy = self.canvas.canvasy(y)
        for row in self._rows:
            if row["y0"] is not None and row["y0"] <= cy < row["y1"]:
                return row["iid"]
        return ""

    def see(self, iid):
        region = self.canvas.cget("scrollregion").split()
        total = float(region[3]) if len(region) == 4 else 0
        for row in self._rows:
            if row["iid"] == iid and total > 0:
                self.canvas.yview_moveto(max(0, row["y0"] / total))
                return

    # --- interaction ------------------------------------------------------
    def _on_press(self, event):
        iid = self.identify_row(event.y)
        if iid:
            self.selection_set(iid)
            if self.on_item_drag:
                self.on_item_drag(iid)

    # --- drawing ----------------------------------------------------------
    def _redraw(self):
        c = self.canvas
        c.delete("all")
        width = max(c.winfo_width(), 200)
        matches_x = _PAD + _NAME_W
        folder_x = max(matches_x + 120, width - _FOLDER_W)

        c.create_rectangle(0, 0, width, _HEAD_H, fill="#f7f9fb", outline=theme.LINE)
        for text, x in (("RULE NAME", _PAD), ("MATCHES WHEN", matches_x), ("FOLDER", folder_x)):
            c.create_text(x, _HEAD_H / 2, text=text, anchor="w", font=self._head, fill=theme.MUTED)

        y = _HEAD_H
        for row in self._rows:
            row["y0"], row["y1"] = y, y + _ROW_H
            if row["iid"] == self._selected:
                c.create_rectangle(0, y, width, y + _ROW_H, fill=theme.ACCENT_SOFT, outline="")
            cy = y + _ROW_H / 2
            c.create_text(_PAD, cy, text=row["name"], anchor="w", font=self._bold, fill=theme.INK)
            x = matches_x
            for text, role in row["segs"]:
                c.create_text(x, cy, text=text, anchor="w", font=self._font,
                              fill=_ROLE_COLOR.get(role, theme.INK))
                x += self._font.measure(text)
            c.create_text(folder_x, cy, text=row["folder"], anchor="w",
                          font=self._font, fill="#3a4149")
            c.create_line(0, y + _ROW_H, width, y + _ROW_H, fill="#eef1f4")
            y += _ROW_H

        c.configure(scrollregion=(0, 0, width, max(y, c.winfo_height())))
