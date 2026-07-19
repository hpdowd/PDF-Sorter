"""ChipInput — a rounded "pill chip" term editor drawn with Pillow.

ttk can't round corners, so each chip is rendered as an antialiased image with
``PIL.ImageDraw.rounded_rectangle`` (Pillow is already a bundled dependency) and
placed on a Canvas; the ✕ remove-button is a separate Canvas text item on top for
clean click handling. A dashed "+ add word" pill opens an inline entry.

Chips flow left-to-right and wrap; the widget colour-codes by ``kind``:
``any`` (neutral), ``all`` (green), ``none`` (red) — matching the Variant A design.
"""
import tkinter as tk
from tkinter import font as tkfont

from PIL import Image, ImageDraw, ImageFont, ImageTk

from src import theme

# Geometry (logical px). Chips are rendered supersampled then downscaled so the
# rounded edges stay crisp at 100% display scaling.
_SUPERSAMPLE = 2
_FONT_PX = 13
_CHIP_H = 24
_PAD_X = 11          # text inset from the pill's left/right
_X_GAP = 7           # gap between the word and the ✕
_X_W = 12            # reserved width for the ✕ glyph
_HGAP = 6            # gap between chips
_VGAP = 6            # gap between wrapped rows
_MARGIN = 4          # canvas outer margin

# (fill, outline, text) per kind — hex from the Variant A artifact.
_KIND = {
    "any":  ("#eef2f6", "#d5dbe1", "#1b1b1b"),
    "all":  ("#eef7f1", "#cfe6d7", "#1b1b1b"),
    "none": ("#fbeef0", "#f0cdd2", "#1b1b1b"),
}
_ADD_OUTLINE = "#a9cdee"
_ADD_TEXT = "#0067c0"
_ADD_LABEL = "+ add word"


def _load_pil_font(px):
    """Best-effort truetype at the given pixel size (Segoe UI on Windows, a
    common sans on Linux), falling back to Pillow's default bitmap font."""
    for name in ("segoeui.ttf", "Segoe UI",
                 "/usr/share/fonts/TTF/DejaVuSans.ttf",
                 "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                 "DejaVuSans.ttf", "Arial.ttf"):
        try:
            return ImageFont.truetype(name, px)
        except Exception:
            continue
    return ImageFont.load_default()


class ChipInput(tk.Frame):
    def __init__(self, master, kind="any", terms=None, on_change=None, **kw):
        super().__init__(master, background=theme.BG, **kw)
        self.kind = kind if kind in _KIND else "any"
        self.on_change = on_change
        self._terms = [str(t).strip() for t in (terms or []) if str(t).strip()]
        self._img_cache = {}          # (kind, text) -> PhotoImage (keep refs alive)
        self._entry = None
        self._entry_win = None
        self._add_xy = (_MARGIN, _MARGIN)

        self._pil_font = _load_pil_font(_FONT_PX * _SUPERSAMPLE)
        self._x_font = tkfont.Font(family="Segoe UI", size=9)
        self._entry_font = tkfont.Font(family="Segoe UI", size=10)

        self.canvas = tk.Canvas(self, highlightthickness=0, bg=theme.BG,
                                height=_CHIP_H + 2 * _MARGIN)
        self.canvas.pack(fill="x", expand=True)
        self.canvas.bind("<Configure>", lambda e: self._relayout())
        self._relayout()

    # --- public API ------------------------------------------------------
    def get_terms(self):
        return list(self._terms)

    def set_terms(self, terms):
        self._terms = [str(t).strip() for t in (terms or []) if str(t).strip()]
        self._relayout()

    def commit_pending(self):
        """Fold any half-typed word in the open add-entry into the terms. Called
        before reading terms (e.g. when the dialog's OK is clicked)."""
        if self._entry:
            self._commit_add()

    # --- term mutation ---------------------------------------------------
    def _add(self, term):
        term = term.strip()
        if term and term not in self._terms:
            self._terms.append(term)
            if self.on_change:
                self.on_change()

    def _remove(self, term):
        if term in self._terms:
            self._terms.remove(term)
            if self.on_change:
                self.on_change()
        self._relayout()

    # --- rendering -------------------------------------------------------
    def _pill_image(self, text, kind):
        key = (kind, text)
        cached = self._img_cache.get(key)
        if cached is not None:
            return cached
        ss = _SUPERSAMPLE
        f = self._pil_font
        tw = int(f.getlength(text))
        closable = kind != "add"
        extra = (_X_GAP + _X_W) if closable else 0
        w = (_PAD_X + tw + extra + _PAD_X) * ss
        h = _CHIP_H * ss
        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        r = (_CHIP_H // 2) * ss
        if kind == "add":
            d.rounded_rectangle([ss, ss, w - ss, h - ss], radius=r,
                                outline=_ADD_OUTLINE, width=ss)
            text_fill = _ADD_TEXT
            # centre the label for the add pill
            tx = (w - tw) // 2
        else:
            fill, outline, text_fill = _KIND[kind]
            d.rounded_rectangle([0, 0, w - 1, h - 1], radius=r,
                                fill=fill, outline=outline, width=ss)
            tx = _PAD_X * ss
        top, bottom = f.getbbox(text)[1], f.getbbox(text)[3]
        ty = (h - (bottom - top)) // 2 - top
        d.text((tx, ty), text, font=f, fill=text_fill)
        photo = ImageTk.PhotoImage(img.resize((w // ss, h // ss), Image.LANCZOS))
        self._img_cache[key] = photo
        return photo

    def _relayout(self):
        c = self.canvas
        if self._entry:            # don't reflow out from under an open editor
            return
        c.delete("all")
        width = max(c.winfo_width(), 60)
        x = y = _MARGIN

        for term in self._terms:
            img = self._pill_image(term, self.kind)
            w = img.width()
            if x + w > width - _MARGIN and x > _MARGIN:
                x, y = _MARGIN, y + _CHIP_H + _VGAP
            c.create_image(x, y, anchor="nw", image=img)
            xb = x + w - _PAD_X - _X_W / 2
            xid = c.create_text(xb, y + _CHIP_H / 2, text="✕",
                                font=self._x_font, fill=theme.MUTED)
            c.tag_bind(xid, "<Button-1>", lambda e, t=term: self._remove(t))
            c.tag_bind(xid, "<Enter>", lambda e: c.config(cursor="hand2"))
            c.tag_bind(xid, "<Leave>", lambda e: c.config(cursor=""))
            x += w + _HGAP

        add_img = self._pill_image(_ADD_LABEL, "add")
        w = add_img.width()
        if x + w > width - _MARGIN and x > _MARGIN:
            x, y = _MARGIN, y + _CHIP_H + _VGAP
        c.create_image(x, y, anchor="nw", image=add_img, tags=("add",))
        self._add_xy = (x, y)
        c.tag_bind("add", "<Button-1>", lambda e: self._begin_add())
        c.tag_bind("add", "<Enter>", lambda e: c.config(cursor="hand2"))
        c.tag_bind("add", "<Leave>", lambda e: c.config(cursor=""))

        c.configure(height=y + _CHIP_H + _MARGIN)

    # --- inline add entry ------------------------------------------------
    def _begin_add(self):
        if self._entry:
            return
        x, y = self._add_xy
        self._entry = tk.Entry(self.canvas, font=self._entry_font,
                               relief="solid", borderwidth=1)
        self._entry_win = self.canvas.create_window(
            x, y, anchor="nw", window=self._entry, width=120, height=_CHIP_H)
        self._entry.focus_set()
        self._entry.bind("<Return>", self._commit_add)
        self._entry.bind("<Escape>", lambda e: self._cancel_add())
        self._entry.bind("<FocusOut>", self._commit_add)

    def _commit_add(self, event=None):
        if not self._entry:
            return
        value = self._entry.get().strip()
        self._destroy_entry()
        if value:
            self._add(value)
        self._relayout()

    def _cancel_add(self):
        self._destroy_entry()
        self._relayout()

    def _destroy_entry(self):
        if self._entry_win is not None:
            self.canvas.delete(self._entry_win)
            self._entry_win = None
        if self._entry is not None:
            self._entry.destroy()
            self._entry = None
