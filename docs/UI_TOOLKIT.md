# UI toolkit — matching-UI fidelity and the Qt question

A decision record for the "make the matching UI match the Variant A mockup" work.
It captures what was built, why the current look is unsatisfying, every option
weighed, and an honest evaluation of moving to Qt (the current lean). Written
2026-07-19.

## Where the feature work stands (v3.0.0 branch)

Branch `feature/v3.0.0-matching-and-foldering`. The **capability** is complete and
tested (130 tests green); only the *presentation* of the matching editor is in
question.

Engine / model (UI-agnostic, done):
- `src/matching.py` — pure `match_rule`, `resolve_match_spec` (explicit
  `all/any/none` `match` block, back-compat with the `a|b|c` key), `describe_match`
  + `describe_match_segments` (coloured summary).
- `src/dates.py` — in-house content date extractor.
- `src/sorter.py` — `_expand_dest` / `_resolve_dest` date-token foldering,
  content-first date source, `from_mapping_data`, Unknown-bucket fallback.

Editor UI (tkinter, works, but the *look* is the open question):
- Advanced Any/All/None matching in the Edit Rule dialog.
- "Test a PDF against these rules" (Method 4).
- Date-foldering picker with live path preview.
- The two contested pieces: pill **chips** (`chip_input.py`) and the **colour-coded
  rules list** (`mapping_table.py`).

The mapping format grew a `match` block and `_config.foldering` (both back-compat /
auto-migrated), which is what makes this the **v3.0.0** the design notes anticipated.

## The fidelity problem

The Variant A mockup (artifact "Matching & foldering — UI concepts") shows **rounded
pill chips**, colour-coded any=neutral / all=green / none=red, with ✕ remove and a
"+ add word" affordance, plus a rules list that colours each term inline.

Hard constraint: **native tkinter/ttk cannot draw rounded corners.** So a faithful
pill is impossible with native widgets. This was flagged from the start in
`DESIGN_NOTES.md` §D ("ttk can't round corners without a dependency").

## Approaches tried / considered

1. **Plain native fields** (first cut). Any/All/None as ttk `Entry`s with `|`
   separators. Fully native, but not the chip interface.
2. **Pillow-rendered pill chips** (built, committed, then rejected). Each chip is an
   antialiased image (`PIL.ImageDraw.rounded_rectangle`) placed on a Canvas, ✕ as a
   Canvas text item; the rules list became a Canvas with per-term coloured text.
   Rounded and colour-correct — but **raster images pasted into a native dialog look
   blurry / mismatched against the surrounding native font and DPI**. Verdict from
   Henry: *"I hate how it looks, I want it native, not the image hack."*
3. **Native square chips** (proposed, not built). Chips from classic `tk.Frame` /
   `tk.Label` with coloured backgrounds — crisp native font, correct DPI, no images.
   Keeps colour + ✕ + "+ add word". The only loss is rounded corners (square).

## Options, with trade-offs

| Option | Native look | Rounded pills | Multi-colour list | New dep | Effort |
|---|---|---|---|---|---|
| Native square tk-widget chips | ✅ crisp, matches app | ❌ square only | ✅ (Canvas or `tk.Text`) | none | ~half day |
| Plain native fields (no chips) | ✅ | ❌ n/a | ⚠️ (needs the list swap) | none | ~1–2 h |
| Keep Pillow pill chips | ❌ raster/mismatched | ✅ | ✅ | none (Pillow already bundled) | done — **rejected** |
| **customtkinter** | ❌ *not native* — CTk draws its own widgets on a Canvas; own look | ✅ | ⚠️ frame-of-labels | yes | large (must migrate the **whole** app to CTk for consistency) |
| **PySide6 / Qt** | ✅ native Win11 style **and** crisp | ✅ (QSS `border-radius`, native font/DPI) | ✅ (rich-text delegate) | yes (large runtime) | **very large — UI rewrite** |

Key correction: **customtkinter is not "native."** Every CTk widget is Canvas-drawn
(rounded rectangles faked with primitives) — the same *category* as the Pillow hack,
just CTk's engine instead of Pillow. It has a distinct non-native look, and mixing it
with the existing ttk looks worse, so adopting it means restyling the entire app.
It does **not** satisfy "I want native."

The deeper tension: **native UI has no pill-chip control.** Pills are inherently
custom-drawn. "Native *and* rounded pills" only truly coexist in **Qt**, where
`border-radius` works while text still renders with the OS font at correct DPI.

## Qt (PySide6) in depth — the current lean

If the priority is *the most native look* (and rounded pills), Qt is the only toolkit
that delivers both.

**What Qt gives**
- Native-style controls on Windows (windows11/windowsvista style): buttons, combos,
  trees, line edits render close to native Win11.
- Rounded chips that are crisp: a `QLabel`/`QFrame` tag widget with QSS
  `border-radius`, or a `QListWidget`/custom widget — native font, correct DPI, **no
  images**.
- Multi-colour rules list is easy: `QTreeView`/`QTableView` with an HTML/rich-text
  item delegate (or a `QLabel` with rich text). The artifact's CSS-like styling maps
  almost directly to QSS.
- Solid high-DPI handling (tkinter's weak spot) and native drag-and-drop (replaces
  `tkinterdnd2`).
- The Variant A design could be reproduced closely.

**What it costs**
- **A full UI-layer rewrite.** Everything under the view layer is tkinter and would be
  reimplemented in Qt:
  - Rewrite: `src/gui.py` (main window + sort/preview/undo flow, ~700 lines),
    `src/theme.py`, all of `src/mapping_editor/` view pieces (`editor_gui`,
    `dialogs`, `mapping_table`, `template_tree`, `chip_input`), and the tkinter
    dialog/tooltip helpers in `utils.py`.
  - **Reused unchanged (the saving grace):** `src/sorter.py`, `src/matching.py`,
    `src/dates.py`, and the model/IO parts of `utils.py` (mapping load/save, settings,
    manifest, logging) and much of `editor_logic.py`. The hard logic is UI-agnostic,
    so a rewrite is "new view over the same model," not from scratch.
- **Bigger distribution.** PySide6 is a large dependency; PyInstaller output grows
  well beyond the current ~53 MB, and startup/memory rise. Matters for the
  download-installer model.
- **Licensing.** Use **PySide6** (LGPLv3, official Qt for Python) — fine for dynamic
  linking. Avoid PyQt (GPL/commercial).
- **Effort & risk.** The single largest piece of work in the project's history;
  large regression surface (sort, preview, undo, OCR, settings, editor, template
  tree, foldering all need re-verifying). Realistically its own multi-session effort
  on a dedicated branch (e.g. `feature/qt-ui`).

**Recommended framing if we go Qt: decouple the feature from the toolkit.**
The matching + foldering *capability* is done and valuable; the Qt rewrite is a
separate, large undertaking. Options:
- **A (recommended): ship v3.0.0 now** with native **square** chips (or plain
  fields), and pursue Qt as a dedicated **v4.0.0 "UI modernization"** later. Don't
  hold the finished features hostage to a rewrite.
- **B: fold the Qt rewrite into v3.0.0** — one big release, but it delays the features
  significantly and bundles two large changes into one.

## Status: decided and executed — Qt, in v3.0.0

Henry chose option B: fold the Qt rewrite into v3.0.0 rather than ship the
features on compromised chips. Executed on `feature/qt-ui`:

- The whole view layer is PySide6 under `src/ui_qt/` (main window, sort preview,
  mapping editor, dialogs). The engine — `sorter.py`, `matching.py`, `dates.py`,
  `mapping_editor/editor_logic.py`, the model/IO parts of `utils.py` — was reused
  unchanged, as predicted above.
- The Variant A design is now faithful: rounded QSS chips with native text
  (`ui_qt/chip_input.py`), and the rules list colours each term inline via a
  rich-text delegate (`ui_qt/rules_table.py`).
- tkinter, tkinterdnd2, and the Pillow chip hack are gone (`gui.py`, `theme.py`,
  and the tkinter halves of `src/mapping_editor/` deleted). Folder drag-and-drop
  is native Qt. The download installer keeps its stdlib tkinter UI on purpose —
  it must stay a tiny dependency-free bootstrap exe.
- PyInstaller builds with PySide6 (QtCore/QtGui/QtWidgets only; the heavy Qt
  extras are excluded in `scripts/build_exe.py` to limit the size cost).
