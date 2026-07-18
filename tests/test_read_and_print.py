import os
import shutil
import tempfile
import unittest
from unittest.mock import patch

from src.sorter import Sorter


class TestPdfContentReader(unittest.TestCase):
    """Integration-style check: read a real pristine PDF end-to-end.

    On CI (real PyMuPDF) this exercises actual text extraction; locally, where
    fitz is stubbed, read_pdf_text returns "" and we just assert the type.
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp()  # keeps the _template dir out of the CWD
        self.mapping_path = os.path.join(self.tmp, "m.json")

    def tearDown(self):
        shutil.rmtree(self.tmp)

    @patch('src.sorter.Sorter.load_mapping')
    def test_scan_content_returns_string(self, mock_load_mapping):
        mock_load_mapping.return_value = {}
        pdf_path = os.path.join('tests', 'test_pdfs_pristine', 'Contract.pdf')
        if not os.path.exists(pdf_path):
            self.skipTest(f"Pristine PDF not found: {pdf_path}")

        sorter = Sorter(self.mapping_path)
        extracted_text = sorter.read_pdf_text(pdf_path)
        self.assertIsInstance(extracted_text, str)


if __name__ == '__main__':
    unittest.main()
