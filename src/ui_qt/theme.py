"""Shared Qt palette and stylesheet, mirroring the app's flat light look.

The colours are the same ones the tkinter theme used, so the app keeps its
identity while gaining native, crisply-rounded Qt controls.
"""

BG = "#f3f5f7"
SURFACE = "#ffffff"
INK = "#1b1b1b"
MUTED = "#57606a"
LINE = "#d7dce1"
ACCENT = "#0067c0"
ACCENT_HI = "#005ba1"
ACCENT_SOFT = "#eaf3fc"
BTN = "#fbfbfc"
GOOD = "#1a7f37"
AMBER = "#9a6700"
RED = "#cf222e"

# Per-kind chip colours (fill, border) — any=blue, all=green, none=red,
# matching the role colours the rules-table summary uses for the same terms.
CHIP = {
    "any":  ("#eaf3fc", "#c9def1"),
    "all":  ("#eef7f1", "#cfe6d7"),
    "none": ("#fbeef0", "#f0cdd2"),
}

# Role colours for the rules-list "Matches when" summary.
ROLE = {"or": ACCENT, "and": GOOD, "not": RED, "by": AMBER, "plain": INK}


def app_qss():
    """Application-wide stylesheet."""
    chip_rules = "\n".join(
        f'QFrame#chip[kind="{k}"] {{ background: {fill}; border: 1px solid {bd}; border-radius: 12px; }}'
        for k, (fill, bd) in CHIP.items()
    )
    return f"""
    QWidget {{ background: {BG}; color: {INK}; font-size: 10pt; }}
    QLabel {{ background: transparent; }}
    QLabel[muted="true"] {{ color: {MUTED}; }}
    QLabel[warning="true"] {{ color: {AMBER}; }}
    QLineEdit, QComboBox, QAbstractItemView, QPlainTextEdit, QTextEdit {{
        background: {SURFACE}; border: 1px solid {LINE}; border-radius: 4px; padding: 4px 6px;
    }}
    QLineEdit:focus, QComboBox:focus {{ border-color: {ACCENT}; }}
    QLineEdit:read-only {{ background: #f7f9fb; }}
    QComboBox:disabled, QLineEdit:disabled {{ color: {MUTED}; background: #f0f2f5; }}
    QComboBox::drop-down {{ border: none; width: 22px; }}
    QComboBox QAbstractItemView {{
        background: {SURFACE}; border: 1px solid {LINE};
        selection-background-color: {ACCENT_SOFT}; selection-color: {INK};
    }}
    QPushButton {{
        background: {BTN}; border: 1px solid {LINE}; border-radius: 4px; padding: 5px 14px;
    }}
    QPushButton:hover {{ background: #eef2f6; }}
    QPushButton:disabled {{ color: #9aa4ae; background: #f0f2f5; }}
    QPushButton#primary {{ background: {ACCENT}; border-color: {ACCENT}; color: #ffffff; }}
    QPushButton#primary:hover {{ background: {ACCENT_HI}; }}
    QPushButton#primary:disabled {{ background: #9cc3e5; border-color: #9cc3e5; color: #ffffff; }}

    QGroupBox {{
        border: 1px solid {LINE}; border-radius: 4px; margin-top: 9px; padding-top: 6px;
    }}
    QGroupBox::title {{
        subcontrol-origin: margin; left: 8px; padding: 0 3px; color: {MUTED};
    }}

    QListWidget, QTreeWidget, QTreeView {{ border: 1px solid {LINE}; border-radius: 4px; }}
    QTreeWidget::item, QTreeView::item {{ padding: 3px 2px; }}
    QListWidget::item {{ padding: 3px 4px; }}
    QListWidget::item:selected, QTreeWidget::item:selected, QTreeView::item:selected {{
        background: {ACCENT_SOFT}; color: {INK};
    }}
    QHeaderView::section {{
        background: #f7f9fb; color: {MUTED}; border: none;
        border-bottom: 1px solid {LINE}; border-right: 1px solid #eef1f4;
        padding: 4px 8px; font-size: 8pt; font-weight: bold;
    }}

    QProgressBar {{
        background: {SURFACE}; border: 1px solid {LINE}; border-radius: 4px;
        text-align: center; color: {MUTED}; max-height: 14px;
    }}
    QProgressBar::chunk {{ background: {ACCENT}; border-radius: 3px; }}

    QMenuBar {{ background: {BG}; }}
    QMenuBar::item {{ background: transparent; padding: 4px 10px; }}
    QMenuBar::item:selected {{ background: {ACCENT_SOFT}; border-radius: 3px; }}
    QMenu {{ background: {SURFACE}; border: 1px solid {LINE}; }}
    QMenu::item {{ padding: 4px 24px 4px 16px; }}
    QMenu::item:selected {{ background: {ACCENT_SOFT}; }}

    QSplitter::handle {{ background: {BG}; }}
    QCheckBox {{ spacing: 7px; }}
    QToolTip {{
        background: #ffffe0; color: {INK}; border: 1px solid #999;
        padding: 2px 4px; font-size: 9pt;
    }}

    {chip_rules}
    QToolButton#chipX {{ border: none; background: transparent; color: {MUTED}; padding: 0 2px; }}
    QToolButton#chipX:hover {{ color: {INK}; }}
    QFrame#addChip {{ border: 1px dashed #a9cdee; border-radius: 12px; }}
    QFrame#addChip QLabel {{ color: {ACCENT}; }}
    QLineEdit#addEdit {{ border-radius: 12px; padding: 3px 10px; }}

    QLabel#discloseToggle {{ color: {ACCENT}; }}
    """
