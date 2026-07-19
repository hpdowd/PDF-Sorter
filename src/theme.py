"""Central visual theme for the app.

A single place that restyles Tkinter/ttk so every window shares one clean, flat
look. Built entirely on the stock ``clam`` theme via ``ttk.Style`` — **no third-party
dependencies**. Call ``apply_theme(window)`` once on the root and on each Toplevel.

Named styles this defines, for use in widgets:
- ``Accent.TButton``  — the primary action button (filled accent).
- ``Header.TLabel``   — bold section headings.
- ``Muted.TLabel``    — secondary/hint text (the app's existing #57606a grey).
"""
import tkinter as tk
from tkinter import ttk, font as tkfont

# Palette — a cool, considered light neutral with a Windows-accent blue. The status
# colours match those already used in gui.py so nothing clashes.
BG        = "#f3f5f7"   # window background
SURFACE   = "#ffffff"   # entries, lists, tree rows
INK       = "#1b1b1b"   # primary text
MUTED     = "#57606a"   # secondary text / hints
LINE      = "#d7dce1"   # borders, separators
ACCENT    = "#0067c0"   # primary buttons, selection
ACCENT_HI = "#005ba1"   # accent, pressed
ACCENT_SOFT = "#eaf3fc" # selection background
BTN       = "#fbfbfc"   # secondary button face
BTN_HOVER = "#eef2f6"
DISABLED  = "#a7b0b8"

GOOD  = "#1a7f37"
AMBER = "#9a6700"
RED   = "#cf222e"

_BASE_FONT = "Segoe UI"   # the app's Windows target face


def _pick_font():
    """Prefer Segoe UI (Windows); fall back to whatever clean sans exists."""
    families = set(tkfont.families())
    for name in (_BASE_FONT, "Selawik", "Noto Sans", "DejaVu Sans", "Helvetica"):
        if name in families:
            return name
    return _BASE_FONT


def apply_theme(window, base_font=None):
    """Apply the shared theme to ``window`` (a Tk or Toplevel). Idempotent."""
    family = base_font or _pick_font()
    try:
        window.configure(background=BG)
    except tk.TclError:
        pass

    style = ttk.Style(window)
    style.theme_use("clam")

    style.configure(".",
                    background=BG, foreground=INK,
                    font=(family, 10), focuscolor=ACCENT)

    style.configure("TFrame", background=BG)
    style.configure("TLabelframe", background=BG, bordercolor=LINE)
    style.configure("TLabelframe.Label", background=BG, foreground=MUTED)

    style.configure("TLabel", background=BG, foreground=INK)
    style.configure("Muted.TLabel", background=BG, foreground=MUTED)
    style.configure("Header.TLabel", background=BG, foreground=INK,
                    font=(family, 10, "bold"))

    # Buttons — flat with a hairline border; accent variant filled.
    style.configure("TButton",
                    background=BTN, foreground=INK, bordercolor=LINE,
                    borderwidth=1, relief="flat", padding=(12, 6))
    style.map("TButton",
              background=[("pressed", BTN_HOVER), ("active", BTN_HOVER),
                          ("disabled", BG)],
              bordercolor=[("focus", ACCENT)],
              foreground=[("disabled", DISABLED)])

    # Accent / primary action button. "Primary.TButton" is the name gui.py already
    # uses for the Sort button; keep it, now filled (clam honors background, unlike
    # the native vista theme the app used before).
    for name in ("Accent.TButton", "Primary.TButton"):
        style.configure(name,
                        background=ACCENT, foreground="#ffffff", bordercolor=ACCENT,
                        borderwidth=1, relief="flat",
                        font=(family, 10, "bold"), padding=(14, 7))
        style.map(name,
                  background=[("pressed", ACCENT_HI), ("active", ACCENT_HI),
                              ("disabled", "#a9c9e6")],
                  foreground=[("disabled", "#eef2f6")])

    # Inputs.
    for name in ("TEntry", "TCombobox", "TSpinbox"):
        style.configure(name,
                        fieldbackground=SURFACE, background=SURFACE,
                        foreground=INK, bordercolor=LINE, lightcolor=LINE,
                        darkcolor=LINE, insertcolor=INK, arrowcolor=MUTED,
                        padding=4)
        style.map(name, bordercolor=[("focus", ACCENT)],
                  lightcolor=[("focus", ACCENT)], darkcolor=[("focus", ACCENT)])
    window.option_add("*TCombobox*Listbox.background", SURFACE)
    window.option_add("*TCombobox*Listbox.selectBackground", ACCENT_SOFT)
    window.option_add("*TCombobox*Listbox.selectForeground", INK)

    style.configure("TCheckbutton", background=BG, foreground=INK)
    style.map("TCheckbutton", background=[("active", BG)],
              indicatorcolor=[("selected", ACCENT)])

    # Lists / tables.
    style.configure("Treeview",
                    background=SURFACE, fieldbackground=SURFACE, foreground=INK,
                    bordercolor=LINE, borderwidth=1, rowheight=25)
    style.map("Treeview",
              background=[("selected", ACCENT_SOFT)],
              foreground=[("selected", INK)])
    style.configure("Treeview.Heading",
                    background="#eef1f4", foreground=MUTED, relief="flat",
                    borderwidth=0, padding=(8, 5), font=(family, 9, "bold"))
    style.map("Treeview.Heading", background=[("active", "#e3e8ee")])

    style.configure("TProgressbar", background=ACCENT, troughcolor="#e6e9ed",
                    bordercolor="#e6e9ed", lightcolor=ACCENT, darkcolor=ACCENT)

    style.configure("TScrollbar", background=BG, troughcolor=BG,
                    bordercolor=BG, arrowcolor=MUTED)

    style.configure("TPanedwindow", background=BG)
    style.configure("TSeparator", background=LINE)
    return style
