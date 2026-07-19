# Design notes — candidate features

Forward-looking design for features that are wanted but not yet built. This is a
menu of **implementation approaches with trade-offs**, not a committed plan. It
exists so the eventual build starts from a considered design rather than a cold
start.

Grounding facts about the current engine (verify before building):
- A rule is `{"<phrase key>": {"name": ..., "dest": ...}}`. The phrase key may hold
  `a|b|c` alternatives; a rule matches if **any** alternative is a substring of the
  PDF's normalized (whitespace-collapsed, lowercased) text. First rule in insertion
  order wins. See `Sorter.find_matching_rule`.
- `_config` is a reserved key (`utils.RESERVED_MAPPING_KEYS`) already used for the
  filename `naming_scheme`. New global options belong here; it's skipped by matching
  and validation and hidden from the editor's rules table.
- `_apply_naming(rule, phrase, path)` expands `{rule_name} {phrase} {original_filename}
  {date} {time} {ext}` placeholders to rename files on move. This is the proven
  pattern to reuse for anything token-based.
- Flow is preview-first: `plan()` (non-destructive) → editable preview → `execute()`.
  `execute` only touches items with `status == "matched"`, using `item.dest` /
  `item.dest_name`, and already `os.makedirs`es nested destination paths.
- **Target users are non-technical.** Raw regex is off-putting and is a last resort.

## UI principles (the priority)

The data model is the easy part; the **UI is what makes or breaks this**. The current
matching is intentionally simple *because* that keeps it readable, and that bar must
not drop. Every option below is judged first on how it reads, not what it can express.

1. **The simple case stays simple.** Typing a word or two must work exactly as today.
   Anything more lives behind an *Advanced* expander most users never open
   (progressive disclosure).
2. **Plain language, never syntax.** No regex, no operators, no `{codes}` typed by the
   user. Build rules from "any of / and also / but not" and dropdowns.
3. **Always show the outcome.** A one-line "Matches when" summary in the rules list, and
   a live preview of the actual folder path. The user sees the result, not the mechanism.

Rendered mockups of all of this (drawn as the real Windows dialogs) exist as an artifact
titled "Matching & foldering — UI concepts" — see that before building.

---

## A. Advanced matching (without exposing regex)

Today matching is "any of these phrases appears anywhere." The wanted expressiveness
is mostly **AND / NOT / scope / tie-breaking** — reachable without regex.

Refactor prerequisite (all methods): pull matching out of `find_matching_rule` into a
pure, unit-tested function `match_rule(normalized_text, rule) -> (matched: bool,
which_term: str|None)`. Keeps the engine clean and testable, matching existing test
discipline.

### Method 1 — Plain-language condition builder (AND / ANY / NONE) — *recommended core*
Extend a rule from a bare phrase key to an optional structured condition:
```json
"Acme invoices": {
  "name": "Acme invoices",
  "dest": "Billing/Acme",
  "match": { "all": ["invoice"], "any": ["acme", "acme corp"], "none": ["quote", "estimate"] }
}
```
Matches when *every* `all` term is present AND (*some* `any` term is present, if `any`
is non-empty) AND *no* `none` term is present. Terms normalized exactly like today.
- **UI:** three simple add/remove lists — "Must contain all of", "And any of", "But
  none of". Reads like English; no syntax.
- **Back-compat:** keep the `phrase|phrase` key as sugar; on load a plain key becomes
  `{"any": [parts]}` (auto-migrate, like the old→new format migration already in
  `MappingUtils`). Old mappings keep working untouched.
- **Why first:** covers the large majority of real needs (AND/OR/NOT) with zero regex
  and a clean, pure-function matcher.

### Method 2 — Wildcards + "smart tokens" instead of regex — *defer unless needed*
Allow `*` (any run) / `?` (one char) inside terms, plus a tiny library of named tokens
that compile to safe internal patterns the user never sees: `{number}` (digits),
`{date}`, `{amount}`. e.g. `invoice no {number}`. Glob→regex is a small, safe
translation; tokens map to fixed sub-patterns. Pairs with Method 1 (tokens live inside
the term lists). Risk: this is the closest to "pattern syntax creep" — keep the token
set tiny and clearly labeled, and only add if Method 1 proves insufficient.

### Method 3 — Scope + tie-breaking — *cheap, orthogonal, do alongside Method 1*
Optional per-rule fields:
- `"where": "first_page" | "anywhere"` — per-rule override of the global "first page
  only" scan option.
- `"priority": N` and a global "warn when more than one rule matches" preference.
  When several match, take highest priority then insertion order, and surface the
  conflict in the preview (it already shows the matched phrase — add "also matched: X").

Low cost, high disambiguation value; complements 1 and 2.

### Method 4 — "Test against a sample PDF" in the editor — *companion UX, build with Method 1*
A button in the mapping editor that runs the current ruleset against a chosen PDF and
shows which rule matched and on which term. Reuses `Sorter.plan` on a single file. Not
a matching mechanism, but it's what makes advanced rules trustworthy for a non-technical
user building them — de-risks everything above.

**Recommended path:** Method 1 as the core model + Method 3 folded in + Method 4 as the
companion. Hold Method 2 wildcards/tokens until there's a concrete need.

**Recommended UI — progressive disclosure (Variant A). CHOSEN.** The Edit Rule dialog
stays identical to today until the user opens one *Advanced matching* line; inside, the
same word-chips gain optional **All of these** and **None of these** rows plus a
"Look in: whole document / first page only" choice. The three labels are deliberately
**Any of these / All of these / None of these** — only the leading word changes, so the
any-vs-all-vs-none distinction reads at a glance (settled with Henry). The rules list
renders each rule as one plain line ("invoice or receipt · and acme · not quote") so a
rule with no advanced options is as short as today. Alternatives considered:
always-visible sentence (Variant B, more expressive but heavier for the common case) and
exclusions-only (Variant C, smallest step — adds just an "ignore if it also contains"
field). Chips are square (ttk can't round corners without a dependency) and colour-coded
neutral / green / red.

---

## B. Metadata / date-based sorting

Two capabilities: (1) route into folders by a value found in/about the file; (2) the
very common special case of **date foldering** (`Statements/2024/03/...`).

### Method 1 — Date/metadata tokens in `dest`, reusing the naming engine — *recommended spine*
The app already expands placeholders to rename files. Reuse the exact same idea for the
**destination path**:
```json
"Bank statements": { "name": "Statements", "dest": "Statements/{doc_year}/{doc_month}" }
```
- Add `_expand_dest(dest, context)` mirroring `_apply_naming`; refactor both to share a
  placeholder-expansion core plus a per-file **context** dict. One place to add tokens.
- `execute` already `makedirs`es nested `dest`, so nested paths need no engine change.
- Build the context during `plan()` so the **preview shows the real resolved path**
  (`Statements/2024/03`) before sorting — fits the preview-first flow and the new
  editable preview.
- Unifies date/metadata foldering with the renaming mental model users already know.

**Where the date comes from** — a per-mapping (or per-rule) **date source**, tried in
order with a guaranteed fallback so a folder is always produced:
- `pdf_created` (`doc.metadata["creationDate"]`), `pdf_modified`, `file_modified`
  (filesystem mtime), or `content` (first date found in the text).
- Non-technical framing: a dropdown — "Use the date from: [Document created / File
  modified / Text in the document]". Default to a sensible chain ending at file mtime.

### Method 2 — Metadata-driven destinations — *natural extension of Method 1*
Same `_expand_dest` mechanism, tokens pulling PDF metadata: `Invoices/{author}`,
`{title}` (sanitized like filenames). Powerful, but metadata is often empty/garbage in
scans — so emphasize a **fallback bucket** (`.../Unknown`) when a value is missing so
no file is lost. Present as secondary to dates.

### Method 3 — Content date extraction — *the genuinely hard part*
Extracting "the document's date" from arbitrary text, by effort:
- **In-house (default, no new dependency):** a small regex set for common formats (ISO
  `2024-03-01`, `01/03/2024`, `1 March 2024`, `Mar 2024`); first match wins; resolve
  DD/MM vs MM/DD via a locale setting; document the ambiguity handling.
- **Library upgrade:** add `dateparser`/`python-dateutil` for robust natural-language
  dates — better accuracy at the cost of a dependency and a larger Windows build. Weigh
  against packaging constraints.
- Shares an extractor with Method 2's `{date}` token in matching — **build the date
  extractor once, use it for both matching and foldering.**

### Method 4 — Date-range → bucket rules — *not recommended*
Rules carry date conditions ("created in 2024 → 2024 folder"). More complex data model,
less flexible than token expansion. Noted for completeness only.

**Recommended path:** Method 1 (dest-path tokens) as the spine + the date-source
dropdown; Method 2 metadata tokens as a same-mechanism extension; Method 3 content dates
via the in-house regex set by default, library as an optional upgrade. Reuses the proven
naming engine, leaves `execute` unchanged, stays dependency-light. Guards: sanitize each
path segment, cap depth, always provide a fallback bucket.

**Recommended UI — a picker, not tokens.** The user never types `{doc_year}`. An
"Organise into subfolders" panel offers: *Put files into subfolders by* [Nothing / Date /
Document author]; when Date, *Group by* [Year / Quarter / Year-Month] *then* [Month /
nothing], and *Use the date from* [A date printed in the document / File modified / Date
saved in the PDF]. The dropdowns generate the destination-path tokens under the hood, and
a **live path preview** ("A file dated 14 Mar 2024 → Statements / 2024 / 03") shows the
result as choices change. See the mockup's "Metadata & date foldering" panel.

**Reliability (settled with Henry): default to content, not metadata.** The date/author
saved *inside* a PDF is frequently wrong once a file has been emailed or re-saved — this
is the very reason filename **renaming** was built (derive names from content, not
metadata). So the date source defaults to "a date printed in the document"; the embedded
PDF date is offered but flagged "(often wrong)". This makes Method 3 (content-date
extraction) the load-bearing path, not a nice-to-have — build the in-house extractor
first.

---

## C. Watch-folder (auto-sort) — deferred, almost a separate tool

Captured so a future effort starts informed. **Decision: keep out of the GUI app.**

- **Why separate:** the current app is interactive and human-in-the-loop (plan → review
  → confirm → undo). Watch-folder is unattended automation — no preview, no per-file
  confirmation, runs continuously/headless, needs an error/conflict policy without a
  human, plus logging/alerting and probably a tray or service presence. Different UX and
  lifecycle from a desktop dialog app.
- **What it reuses:** the `Sorter` engine is already headless (`plan`/`execute`) — that's
  the shared core. A watch tool wraps it with a filesystem watcher (`watchdog`) or a poll
  loop, auto-executes matched items, and applies a policy for unmatched/unreadable
  (leave in place, or move to a "needs review" folder).
- **Shape options:** (a) a headless mode/CLI of the same codebase
  (`--watch <folder> --mapping <m>`) — cheapest first step, reuses everything; (b) a tray
  app; (c) a Windows service / scheduled task.
- **Decisions to settle later:** debounce partially-written files (wait for size to
  stabilize before processing); don't re-process the output tree (the template-dir guard
  in `_iter_pdfs` already helps); auto-move is destructive with no human to undo —
  consider **copy-by-default** or a quarantine; concurrency if the GUI runs too.
- **Recommendation when picked up:** start as a headless `--watch` entry point over the
  existing `Sorter`, copy-by-default, with a "needs review" bucket for non-matches.

---

## D. Visual restyle — done as a foundation

`src/theme.py` (`apply_theme`) restyles the whole app via `ttk.Style` on the built-in
**clam** theme: a considered light palette, a Windows-accent blue, flat inputs, and a
filled primary button (`Primary.TButton` / `Accent.TButton`). **Zero third-party
dependencies** — this was the stated bar. clam honours button backgrounds, which the old
native (vista) theme did not, so the accent button is finally filled rather than just
bold. Wired into the main window and the editor/dialog Toplevels.

What clam *can't* do cheaply: rounded corners, drop shadows, and pill-shaped chips. So
the real app is a flatter approximation of the HTML mockup — chips are square, colour-
coded neutral/green/red. Rendered proof exists (main window + Edit Rule dialog
screenshots). Going further (rounded/modern controls) would mean a dependency like
`ttkbootstrap` — explicitly out of scope.

---

## Release framing

Editable preview + Any/All/None matching + date foldering + the restyle together are a
**major version (v3.0.0)**: the mapping JSON grows a `match` block and date/metadata
tokens in `dest` (both auto-migrated, so arguably still minor by the letter of the
policy), but the coordinated UI overhaul and format growth are best shipped and
communicated as one major step. Confirm the bump at release-cut time per
`docs/VERSIONING.md`.
