import os
import re
import shutil
import logging
from dataclasses import dataclass
from datetime import datetime, date
import fitz  # PyMuPDF

from src import utils
from src import matching
from src import dates

logger = logging.getLogger("ocr_file_sorter.sorter")

# Safety cap on how deep a token-expanded destination path may nest.
_MAX_DEST_DEPTH = 8

# How a "Group by" foldering choice maps to destination-path date tokens.
_GROUP_TOKENS = {
    "year": "{doc_year}",
    "quarter": "{doc_year}/{doc_quarter}",
    "year_month": "{doc_year}/{doc_month}",
}


@dataclass
class PlanItem:
    """One PDF's planned outcome from a (non-destructive) sort plan."""
    src: str                 # absolute source path
    status: str              # "matched" | "unmatched" | "unreadable" | "error" | "skipped"
    phrase: str = None       # matched phrase (when matched); "(manual)" for a preview override
    dest: str = None         # destination folder, relative to the template dir (when matched)
    dest_name: str = None    # proposed filename after any renaming (when matched)
    message: str = ""        # human-readable note (e.g. error text)

    @property
    def filename(self):
        return os.path.basename(self.src)

# Attempt to import OCR libraries. If they fail, OCR will be disabled.
try:
    from PIL import Image
    import pytesseract
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False


def ocr_status():
    """Return (available, detail): whether OCR can actually run, plus a short note.

    OCR needs both the Python libraries (Pillow/pytesseract) *and* the Tesseract
    binary on PATH. pytesseract only fails at call time when the binary is
    missing, so probe it here for a definitive answer at startup.
    """
    if not OCR_AVAILABLE:
        return False, "OCR libraries not installed (Pillow/pytesseract)."
    try:
        version = pytesseract.get_tesseract_version()
        return True, f"Tesseract {version}"
    except Exception:
        return False, "Tesseract OCR is not installed or not on PATH."

class Sorter:
    def __init__(self, mapping_path, output_dir=None, progress_callback=None, status_callback=None):
        self.mapping_path = mapping_path
        self.progress_callback = progress_callback
        self.status_callback = status_callback
        self._cancelled = False
        self.mapping_data = self.load_mapping()
        # Optional filename scheme and subfolder foldering, under "_config".
        self.naming_scheme = (self.mapping_data.get("_config") or {}).get("naming_scheme") or None
        self.foldering = (self.mapping_data.get("_config") or {}).get("foldering") or {}
        self._validate_mapping()
        # Destination root for sorted files. When the caller supplies an output
        # directory (the GUI's "Output folder" picker), sort into it. Otherwise
        # fall back to a "<mapping>_template" folder beside the mapping file
        # (legacy behaviour, kept for tests and headless callers).
        if output_dir:
            self.template_dir = os.path.abspath(output_dir)
        else:
            self.template_dir = os.path.splitext(self.mapping_path)[0] + "_template"
        if not os.path.exists(self.template_dir):
            os.makedirs(self.template_dir)

    @classmethod
    def from_mapping_data(cls, mapping_data, template_dir=None):
        """Build a Sorter around already-loaded mapping data, without any
        filesystem side effects (no mapping load, no template dir creation).

        Used to test a single PDF against the editor's current — possibly
        unsaved — rules. Reuses the exact matching/expansion the real sort uses.
        """
        s = cls.__new__(cls)
        s.status_callback = None
        s.progress_callback = None
        s.mapping_path = None
        s.template_dir = template_dir
        s.mapping_data = mapping_data or {}
        s.naming_scheme = (s.mapping_data.get("_config") or {}).get("naming_scheme") or None
        s.foldering = (s.mapping_data.get("_config") or {}).get("foldering") or {}
        s._cancelled = False
        return s

    def cancel(self):
        """Request cooperative cancellation of an in-progress plan/execute.

        The plan and execute loops check this between files, so a cancel stops at
        the next file boundary rather than mid-copy.
        """
        self._cancelled = True

    @property
    def cancelled(self):
        return self._cancelled

    def load_mapping(self):
        """
        Load mapping from the JSON file specified by mapping_path.
        """
        if self.status_callback:
            self.status_callback(f"Loading mapping from {self.mapping_path}")
        data = utils.MappingUtils.load_mapping(self.mapping_path)
        if self.status_callback:
            self.status_callback(f"Mapping loaded from {self.mapping_path}")
        return data

    def read_pdf_text(self, file_path, first_page_only=False):
        """
        Reads text from a PDF. Can be set to read only the first page.
        If that fails (e.g., for a scanned PDF), it falls back to OCR.
        """
        text = ""
        try:
            # 1. First, try direct text extraction
            with fitz.open(file_path) as doc:
                if not doc:
                    return ""
                
                if first_page_only:
                    text = doc[0].get_text().strip()
                else:
                    text = "".join(page.get_text() for page in doc).strip()
        except Exception as e:
            logger.exception("Error reading %s", os.path.basename(file_path))
            if self.status_callback:
                self.status_callback(f"Error reading {os.path.basename(file_path)}: {e}")
            return ""

        # 2. If no text was found, fall back to OCR if available
        if not text and OCR_AVAILABLE:
            logger.info("OCR fallback for %s", os.path.basename(file_path))
            if self.status_callback:
                self.status_callback(f"No text layer in {os.path.basename(file_path)}. Attempting OCR...")
            try:
                ocr_texts = []
                with fitz.open(file_path) as doc:
                    if not doc:
                        return ""
                    
                    # Determine which pages to scan based on the flag
                    pages_to_scan = [doc[0]] if first_page_only and len(doc) > 0 else doc

                    for i, page in enumerate(pages_to_scan):
                        if self.status_callback:
                            # Adjust status message for single page scan
                            page_count = len(pages_to_scan)
                            self.status_callback(f"OCR page {i + 1}/{page_count} of {os.path.basename(file_path)}...")
                        # Render page to an image (pixmap) at high DPI for better accuracy
                        pix = page.get_pixmap(dpi=300)
                        # Convert pixmap to a PIL Image (match mode to channels)
                        mode = "RGBA" if pix.alpha else "RGB"
                        img = Image.frombytes(mode, [pix.width, pix.height], pix.samples)
                        # Use Tesseract to do OCR on the image.
                        # NOTE: This requires Tesseract-OCR to be installed on your system.
                        page_text = pytesseract.image_to_string(img)
                        ocr_texts.append(page_text)
                text = "\n".join(ocr_texts)
            except pytesseract.TesseractNotFoundError:
                logger.warning("Tesseract not found; OCR unavailable")
                if self.status_callback:
                    self.status_callback("Tesseract not found. OCR unavailable. Please install Tesseract.")
                return "" # Return empty string if Tesseract is not found
            except Exception as e:
                logger.exception("OCR error for %s", os.path.basename(file_path))
                if self.status_callback:
                    self.status_callback(f"An error occurred during OCR: {e}")
                return ""
        elif not text and not OCR_AVAILABLE:
             if self.status_callback:
                self.status_callback(f"No text in {os.path.basename(file_path)}, and OCR libraries not installed.")

        return text

    def find_matching_rule(self, text):
        """Return (phrase, rule, dest) for the first matching rule with a usable
        destination, or None. Skips reserved config keys; a rule that matches but
        has no destination is warned about and skipped (so it doesn't block a
        later valid match). Search is case-insensitive + whitespace-normalized.
        """
        normalized_text = matching.normalize(text)

        for phrase, rule in self.mapping_data.items():
            if phrase in utils.RESERVED_MAPPING_KEYS:
                continue
            # Matching is delegated to the pure matcher: the rule resolves to a
            # normalized {all, any, none} spec (today derived from the key's '|'
            # alternatives as any-of, so this stays backward-compatible) which is
            # then evaluated against the text.
            matched, which_term = matching.match_rule(
                normalized_text, matching.resolve_match_spec(phrase, rule))

            if matched:
                # New-format rules are dicts ({"name", "dest"}); migrated
                # old-format rules are plain strings. Support both.
                destination = rule.get("dest") if isinstance(rule, dict) else rule
                if not destination:
                    logger.warning("Rule %r matched but has no destination; skipping", phrase)
                    continue
                if self.status_callback:
                    self.status_callback(f"Found a match for keyword: '{which_term}'")
                return phrase, rule, destination
        return None

    def find_destination(self, text):
        """Return the destination folder for the first matching rule, or None."""
        match = self.find_matching_rule(text)
        return match[2] if match else None

    def destination_folders(self):
        """Unique, sorted destination folders configured by the mapping's rules.

        This is the curated set the preview's manual-override chooser offers, so a
        user can only reassign a file to a real, already-configured destination
        (no free-text folder typing — the target group is non-technical).
        """
        dests = set()
        for phrase, rule in self.mapping_data.items():
            if phrase in utils.RESERVED_MAPPING_KEYS:
                continue
            dest = rule.get("dest") if isinstance(rule, dict) else rule
            if dest:
                dests.add(dest)
        return sorted(dests)

    def _validate_mapping(self):
        """Log (and surface) a warning for any rule that has no usable destination."""
        invalid = [phrase for phrase, rule in self.mapping_data.items()
                   if phrase not in utils.RESERVED_MAPPING_KEYS
                   and not (rule.get("dest") if isinstance(rule, dict) else rule)]
        if invalid:
            logger.warning("%d mapping rule(s) have no destination and will be skipped: %s",
                           len(invalid), ", ".join(repr(p) for p in invalid))
            if self.status_callback:
                self.status_callback(
                    f"Warning: {len(invalid)} rule(s) have no destination and will be skipped.")

    def _iter_pdfs(self, folder, deep_audit):
        """Yield PDF paths in a folder. With deep_audit, recurse into subfolders,
        but skip the mapping's own template dir so files already sorted there
        aren't picked up and moved again."""
        if deep_audit:
            template_abs = os.path.abspath(self.template_dir)
            for root, dirs, files in os.walk(folder):
                # Don't descend into the template dir (its files are already sorted).
                dirs[:] = [d for d in dirs
                           if os.path.abspath(os.path.join(root, d)) != template_abs]
                if os.path.abspath(root) == template_abs:
                    continue
                for filename in files:
                    if filename.lower().endswith('.pdf'):
                        yield os.path.join(root, filename)
        else:
            for filename in os.listdir(folder):
                file_path = os.path.join(folder, filename)
                if os.path.isfile(file_path) and filename.lower().endswith('.pdf'):
                    yield file_path

    def count_pdfs(self, folders_to_sort, deep_audit=False):
        """Count the PDFs sort_files would scan (respects deep_audit + template guard)."""
        total = 0
        for folder in folders_to_sort:
            if os.path.isdir(folder):
                total += sum(1 for _ in self._iter_pdfs(folder, deep_audit))
        return total

    @staticmethod
    def _replace_tokens(template, values):
        """Expand ``{token}`` placeholders in a template from a values dict.

        The shared placeholder core for both filename renaming (``_apply_naming``)
        and destination-path expansion (``_expand_dest``) — one place to reason
        about token substitution.
        """
        result = template
        for key, value in values.items():
            result = result.replace(key, str(value))
        return result

    @staticmethod
    def _sanitize_segment(segment):
        """Make one path segment safe: drop filesystem-illegal characters and
        stray surrounding whitespace/dots."""
        for ch in '<>:"/\\|?*':
            segment = segment.replace(ch, "")
        return segment.strip().strip(".")

    def _apply_naming(self, rule, phrase, original_path):
        """Compute the destination filename. With a configured naming scheme,
        expand its placeholders; otherwise keep the original name."""
        original_stem, ext = os.path.splitext(os.path.basename(original_path))
        if not self.naming_scheme:
            return original_stem + ext

        now = datetime.now()
        rule_name = (rule.get("name") if isinstance(rule, dict) else "") or ""
        values = {
            "{rule_name}": rule_name,
            "{phrase}": phrase,
            "{original_filename}": original_stem,
            "{date}": now.strftime("%Y%m%d"),
            "{time}": now.strftime("%H-%M-%S"),
            "{ext}": ext,
        }
        new_name = self._replace_tokens(self.naming_scheme, values)
        # Strip characters that are invalid in filenames.
        for ch in '<>:"/\\|?*':
            new_name = new_name.replace(ch, "")
        new_name = new_name.strip()
        if not new_name:
            return original_stem + ext
        # Keep an extension even if the scheme omitted {ext}.
        if not os.path.splitext(new_name)[1]:
            new_name += ext
        return new_name

    def _mtime_date(self, file_path):
        try:
            return date.fromtimestamp(os.path.getmtime(file_path))
        except OSError:
            return None

    def _pdf_metadata_date(self, file_path):
        """Date embedded in the PDF (creation, else modification). Often wrong
        after emailing/re-saving — offered but not the default."""
        try:
            with fitz.open(file_path) as doc:
                meta = doc.metadata or {}
        except Exception:
            return None
        raw = meta.get("creationDate") or meta.get("modDate") or ""
        m = re.search(r"(\d{4})(\d{2})(\d{2})", raw)
        if not m:
            return None
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None

    def _document_date(self, file_path, text, source="content"):
        """Best-effort date for a document from the chosen source, always with a
        fallback so a date-foldered file is never left without a bucket.

        Content is the default because a date printed in the document is more
        trustworthy than the file's timestamp or embedded PDF metadata (the same
        reason filename renaming derives names from content).
        """
        if source == "file_modified":
            return self._mtime_date(file_path)
        if source == "pdf_metadata":
            found = self._pdf_metadata_date(file_path)
            if found:
                return found
            # fall through to content, then mtime
        found = dates.extract_date(text) if text else None
        if found:
            return found
        return self._mtime_date(file_path)

    def _date_context(self, file_path, text, source="content"):
        """Build the date tokens available to destination expansion for one file."""
        doc_date = self._document_date(file_path, text, source)
        if not doc_date:
            return {}
        return {
            "doc_year": f"{doc_date.year:04d}",
            "doc_month": f"{doc_date.month:02d}",
            "doc_quarter": f"Q{(doc_date.month - 1) // 3 + 1}",
        }

    def _foldering_template(self):
        """The date-token subpath appended to every destination by the mapping's
        global foldering setting, or "" when foldering is off."""
        if (self.foldering.get("by") or "none") != "date":
            return ""
        return _GROUP_TOKENS.get(self.foldering.get("group") or "year_month",
                                 _GROUP_TOKENS["year_month"])

    def _resolve_dest(self, base_dest, file_path, text):
        """Resolve a rule's destination for one file: expand any per-rule date
        tokens, then append the mapping's global date-foldering subpath. Returns
        ``base_dest`` unchanged when neither applies (existing mappings)."""
        template = self._foldering_template()
        if not template and not (base_dest and "{" in base_dest):
            return base_dest
        source = self.foldering.get("date_source") or "content"
        context = self._date_context(file_path, text, source)
        dest = self._expand_dest(base_dest, context) if base_dest and "{" in base_dest else base_dest
        if template:
            suffix = self._expand_dest(template, context)
            dest = f"{dest}/{suffix}" if dest else suffix
        return dest

    def _expand_dest(self, dest, context):
        """Expand ``{tokens}`` in a rule's destination path using a per-file
        context, returning a sanitized relative folder path.

        A token with no value resolves to an ``Unknown`` bucket so a file is never
        lost. Each path segment is sanitized independently (slashes preserved),
        empty segments are dropped, and depth is capped. A dest with no tokens is
        returned unchanged, so existing mappings are unaffected.
        """
        if not dest or "{" not in dest:
            return dest
        tokens = {
            "{doc_year}": context.get("doc_year") or "Unknown",
            "{doc_month}": context.get("doc_month") or "Unknown",
            "{doc_quarter}": context.get("doc_quarter") or "Unknown",
        }
        expanded = self._replace_tokens(dest, tokens)
        segments = [self._sanitize_segment(s) for s in re.split(r"[\\/]+", expanded)]
        segments = [s for s in segments if s][:_MAX_DEST_DEPTH]
        return "/".join(segments) if segments else dest

    @staticmethod
    def _unique_path(directory, filename):
        """Return a path in `directory` that won't overwrite an existing file."""
        target = os.path.join(directory, filename)
        if not os.path.exists(target):
            return target
        stem, ext = os.path.splitext(filename)
        i = 1
        while True:
            candidate = os.path.join(directory, f"{stem} ({i}){ext}")
            if not os.path.exists(candidate):
                return candidate
            i += 1

    def plan(self, folders_to_sort, deep_audit=False, first_page_only=False):
        """Read every PDF and decide its outcome **without moving anything**.

        Returns a list of PlanItem. This is the non-destructive preview/dry-run
        the GUI shows before the user confirms.
        """
        items = []
        for folder in folders_to_sort:
            if self._cancelled:
                break
            if not os.path.isdir(folder):
                continue
            if self.status_callback:
                scope = "recursively" if deep_audit else "top-level"
                self.status_callback(f"Scanning folder ({scope}): {folder}")

            # Materialize before iterating so nothing shifts under us.
            for file_path in list(self._iter_pdfs(folder, deep_audit)):
                if self._cancelled:
                    break
                if self.progress_callback:
                    self.progress_callback()
                if self.status_callback:
                    self.status_callback(f"Scanning: {file_path}")
                try:
                    text = self.read_pdf_text(file_path, first_page_only=first_page_only)
                    if not text:
                        logger.info("Unreadable: %s", os.path.basename(file_path))
                        items.append(PlanItem(file_path, "unreadable", message="No readable text"))
                        continue
                    match = self.find_matching_rule(text)
                    if match:
                        phrase, rule, dest = match
                        # Resolve per-rule tokens + global date foldering now, so
                        # the preview shows the real folder (e.g. Statements/2024/03).
                        dest = self._resolve_dest(dest, file_path, text)
                        items.append(PlanItem(
                            file_path, "matched", phrase=phrase, dest=dest,
                            dest_name=self._apply_naming(rule, phrase, file_path)))
                    else:
                        logger.info("No match: %s", os.path.basename(file_path))
                        items.append(PlanItem(file_path, "unmatched", message="No matching rule"))
                except Exception as e:
                    logger.exception("Error planning %s", os.path.basename(file_path))
                    items.append(PlanItem(file_path, "error", message=str(e)))
        return items

    def execute(self, plan_items, copy=False):
        """Carry out a plan: copy or move each matched item into its destination.

        Returns (manifest, count). The manifest is a list of
        {"src", "dest", "copied"} entries describing what happened, suitable for
        undo. Collisions are resolved with a numbered suffix.
        """
        manifest = []
        for item in plan_items:
            if self._cancelled:
                break
            if item.status != "matched":
                continue
            dest_dir = os.path.join(self.template_dir, item.dest)
            try:
                os.makedirs(dest_dir, exist_ok=True)
                target = self._unique_path(dest_dir, item.dest_name)
                if copy:
                    shutil.copy2(item.src, target)
                else:
                    shutil.move(item.src, target)
                manifest.append({"src": item.src, "dest": target, "copied": copy})
                logger.info("%s %s -> %s", "Copied" if copy else "Moved",
                            item.filename, target)
                if self.status_callback:
                    verb = "Copied" if copy else "Moved"
                    self.status_callback(f"{verb}: {item.filename} -> {item.dest}/{os.path.basename(target)}")
            except Exception as e:
                logger.exception("Failed to place %s", item.filename)
                if self.status_callback:
                    self.status_callback(f"Error placing {item.filename}: {e}")
        logger.info("Execute complete: %s=%d", "copied" if copy else "moved", len(manifest))
        return manifest, len(manifest)

    @staticmethod
    def undo(manifest):
        """Reverse a manifest: move files back (or delete copies). Returns (undone, errors)."""
        undone = 0
        errors = 0
        for entry in reversed(manifest):
            src, dest, copied = entry["src"], entry["dest"], entry.get("copied", False)
            try:
                if not os.path.exists(dest):
                    continue
                if copied:
                    os.remove(dest)
                else:
                    os.makedirs(os.path.dirname(src), exist_ok=True)
                    # Restore to the original path; if something now occupies it,
                    # fall back to a numbered name rather than clobbering.
                    restore = src if not os.path.exists(src) else \
                        Sorter._unique_path(os.path.dirname(src), os.path.basename(src))
                    shutil.move(dest, restore)
                undone += 1
            except Exception:
                logger.exception("Undo failed for %s", dest)
                errors += 1
        logger.info("Undo complete: undone=%d errors=%d", undone, errors)
        return undone, errors

    def sort_files(self, folders_to_sort, deep_audit=False, first_page_only=False):
        """Plan then move, in one call (kept for callers that don't preview).

        Returns (scanned, moved)."""
        plan_items = self.plan(folders_to_sort, deep_audit, first_page_only)
        _manifest, moved = self.execute(plan_items, copy=False)
        scanned = len(plan_items)
        logger.info("Sort complete: scanned=%d moved=%d", scanned, moved)
        if self.status_callback:
            self.status_callback(f"Sort complete. Scanned: {scanned}, Moved: {moved}")
        return scanned, moved