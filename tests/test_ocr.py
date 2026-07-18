import os
import shutil
import unittest
from unittest.mock import patch, MagicMock
from src.sorter import Sorter, OCR_AVAILABLE

# We import the specific exception to simulate it being raised
if OCR_AVAILABLE:
    from pytesseract import TesseractNotFoundError

# Helper function to create a mock for a fitz.Document (which is a context manager)
def create_mock_document_context(pages):
    """Creates a mock context manager that yields an iterable of mock pages."""
    mock_doc_context = MagicMock()
    mock_doc_context.__enter__.return_value = pages
    return mock_doc_context

@unittest.skipIf(not OCR_AVAILABLE, "Pytesseract or Pillow not installed, skipping OCR tests.")
class TestOCRFallback(unittest.TestCase):

    def setUp(self):
        """Create the dummy mapping file in the correct location for the tests."""
        self.mappings_dir = "tests/mappings"
        self.mapping_path = os.path.join(self.mappings_dir, "dummy_mapping.json")
        os.makedirs(self.mappings_dir, exist_ok=True)
        with open(self.mapping_path, "w") as f:
            f.write('{"ocr_text": "ScannedDocs"}')

    def tearDown(self):
        """Clean up the dummy mapping directory."""
        if os.path.exists(self.mappings_dir):
            shutil.rmtree(self.mappings_dir)

    @patch('src.sorter.utils.MappingUtils.load_mapping')
    @patch('src.sorter.fitz.open')
    @patch('src.sorter.Image.frombytes')
    @patch('src.sorter.pytesseract.image_to_string')
    def test_ocr_fallback_is_triggered(self, mock_image_to_string, mock_frombytes, mock_fitz_open, mock_load_mapping):
        """
        Tests that OCR is used when a PDF has no text layer.
        """
        # --- Arrange ---
        # 1. Mock the mapping so the Sorter can initialize.
        mock_load_mapping.return_value = {"ocr_text": "ScannedDocs"}

        # 2. Simulate a PDF page that has NO text layer, but does have an image (pixmap).
        mock_page = MagicMock()
        mock_page.get_text.return_value = ""  # This is key: no text is found initially.
        mock_page.get_pixmap.return_value = MagicMock() # Represents the page image.

        # 3. Set up fitz.open to return a document with our mock page.
        mock_fitz_open.return_value = create_mock_document_context([mock_page])
        
        # 4. We don't need a real image, so frombytes can just return a placeholder.
        mock_frombytes.return_value = MagicMock()

        # 5. Simulate the OCR engine successfully reading text from the image.
        expected_ocr_text = "This is some text found by OCR."
        mock_image_to_string.return_value = expected_ocr_text

        # 6. Initialize the Sorter using the dummy mapping file from the correct path.
        sorter = Sorter(self.mapping_path)

        # --- Act ---
        # Call the method we are testing.
        extracted_text = sorter.read_pdf_text('scanned_document.pdf')

        # --- Print the result for the user ---
        print(f"\n--- OCR Test: Text Found ---\n{extracted_text}\n----------------------------")

        # --- Assert ---
        # Verify that the text returned is the text from our mocked OCR.
        self.assertEqual(extracted_text, expected_ocr_text)
        # Verify that the OCR function was actually called.
        mock_image_to_string.assert_called_once()

    @patch('src.sorter.utils.MappingUtils.load_mapping')
    @patch('src.sorter.fitz.open')
    @patch('src.sorter.pytesseract.image_to_string')
    @patch('src.sorter.Image.frombytes')
    def test_tesseract_not_found_error(self, mock_frombytes, mock_image_to_string, mock_fitz_open, mock_load_mapping):
        """
        Tests that the system handles when the Tesseract executable is not installed.
        """
        # --- Arrange ---
        # 1. Mock mapping and a text-less PDF page as before.
        mock_load_mapping.return_value = {}
        mock_page = MagicMock()
        mock_page.get_text.return_value = ""
        mock_page.get_pixmap.return_value = MagicMock()
        mock_fitz_open.return_value = create_mock_document_context([mock_page])

        # 2. Give frombytes a valid return so we actually reach the OCR call,
        #    then simulate Tesseract not being found on the system.
        mock_frombytes.return_value = MagicMock()
        mock_image_to_string.side_effect = TesseractNotFoundError

        # 3. Initialize the Sorter.
        sorter = Sorter(self.mapping_path)

        # --- Act ---
        extracted_text = sorter.read_pdf_text('scanned_document.pdf')

        # --- Assert ---
        # We actually reached the OCR call (which raised TesseractNotFoundError)...
        mock_image_to_string.assert_called_once()
        # ...and the function failed gracefully, returning an empty string.
        self.assertEqual(extracted_text, "")
        print("\n--- Tesseract Not Found Test Passed ---\nSuccessfully handled missing Tesseract executable.\n-----------------------------------")

if __name__ == '__main__':
    unittest.main()