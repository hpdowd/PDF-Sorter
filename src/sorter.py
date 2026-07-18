import os
import shutil
import logging
import fitz  # PyMuPDF

from src import utils

logger = logging.getLogger("ocr_file_sorter.sorter")

# Attempt to import OCR libraries. If they fail, OCR will be disabled.
try:
    from PIL import Image
    import pytesseract
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False

class Sorter:
    def __init__(self, mapping_path, progress_callback=None, status_callback=None):
        self.mapping_path = mapping_path
        self.progress_callback = progress_callback
        self.status_callback = status_callback
        self.mapping_data = self.load_mapping()
        # The template directory is named after the mapping file (without .json) + "_template"
        self.template_dir = os.path.splitext(self.mapping_path)[0] + "_template"
        if not os.path.exists(self.template_dir):
            os.makedirs(self.template_dir)

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

    def find_destination(self, text):
        """
        Finds the destination folder by checking for keywords in the text.
        The search is case-insensitive and normalized to handle OCR quirks.
        """
        # Normalize the text from the PDF: replace newlines/tabs with spaces,
        # collapse multiple spaces, and convert to lowercase.
        normalized_text = ' '.join(text.split()).lower()

        for phrase, rule in self.mapping_data.items():
            # Normalize the mapping phrase in the same way.
            normalized_phrase = ' '.join(phrase.split()).lower()
            
            if normalized_phrase in normalized_text:
                # New-format rules are dicts ({"name", "dest"}); migrated
                # old-format rules are plain strings. Support both.
                destination = rule.get("dest") if isinstance(rule, dict) else rule
                if self.status_callback:
                    # Add a debug message to show exactly what matched.
                    self.status_callback(f"Found a match for keyword: '{normalized_phrase}'")
                return destination
        return None

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

    def sort_files(self, folders_to_sort, deep_audit=False, first_page_only=False):
        total_files_sorted = 0
        total_files_scanned = 0

        for folder in folders_to_sort:
            if not os.path.isdir(folder):
                continue

            if self.status_callback:
                scope = "recursively" if deep_audit else "top-level"
                self.status_callback(f"Sorting folder ({scope}): {folder}")

            # Materialize the list before moving so files relocated during the
            # sort don't disturb the os.walk in deep-audit mode.
            for file_path in list(self._iter_pdfs(folder, deep_audit)):
                filename = os.path.basename(file_path)
                total_files_scanned += 1
                if self.status_callback:
                    self.status_callback(f"Scanning: {file_path}")

                text = self.read_pdf_text(file_path, first_page_only=first_page_only)
                if not text:
                    continue

                try:
                    destination_folder = self.find_destination(text)

                    if destination_folder:
                        destination_path = os.path.join(self.template_dir, destination_folder)
                        os.makedirs(destination_path, exist_ok=True)
                        target = self._unique_path(destination_path, filename)
                        shutil.move(file_path, target)
                        total_files_sorted += 1
                        logger.info("Moved %s -> %s", filename, destination_folder)
                        if self.status_callback:
                            self.status_callback(f"Moved: {filename} -> {destination_folder}")
                    else:
                        logger.info("No match: %s", filename)
                        if self.status_callback:
                            self.status_callback(f"No match found for: {filename}")
                            # Print the NORMALIZED text for easier debugging
                            debug_text = ' '.join(text.split()).lower()
                            if len(debug_text) > 1000:
                                debug_text = debug_text[:1000] + "..."
                            self.status_callback(f"--- Normalized Text Read from {filename} ---\n{debug_text}\n---------------------------------")
                except Exception as e:
                    logger.exception("Error processing %s", filename)
                    if self.status_callback:
                        self.status_callback(f"Error processing {filename}: {e}")

        logger.info("Sort complete: scanned=%d moved=%d", total_files_scanned, total_files_sorted)
        if self.status_callback:
            self.status_callback(f"Sort complete. Scanned: {total_files_scanned}, Moved: {total_files_sorted}")

        return total_files_scanned, total_files_sorted