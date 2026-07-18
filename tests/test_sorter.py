import os
import shutil
import tempfile
import unittest
from unittest.mock import patch, MagicMock

from src.sorter import Sorter


def mock_document_context(pages):
    """A mock context manager whose __enter__ yields an iterable of pages."""
    ctx = MagicMock()
    ctx.__enter__.return_value = pages
    return ctx


class TestReadPdfText(unittest.TestCase):
    def setUp(self):
        # Use a temp mapping path so the Sorter's <name>_template dir is created
        # under the temp dir, not the current working directory.
        self.tmp = tempfile.mkdtemp()
        self.mapping_path = os.path.join(self.tmp, "m.json")

    def tearDown(self):
        shutil.rmtree(self.tmp)

    @patch('src.sorter.utils.MappingUtils.load_mapping')
    @patch('src.sorter.fitz.open')
    def test_concatenates_text_from_pages(self, mock_fitz_open, mock_load_mapping):
        mock_load_mapping.return_value = {"keyword": {"name": "K", "dest": "folder"}}

        page1 = MagicMock(); page1.get_text.return_value = "Text from page 1. "
        page2 = MagicMock(); page2.get_text.return_value = "Text from page 2."
        mock_fitz_open.return_value = mock_document_context([page1, page2])

        sorter = Sorter(self.mapping_path)
        self.assertEqual(sorter.read_pdf_text('dummy.pdf'),
                         "Text from page 1. Text from page 2.")


if __name__ == '__main__':
    unittest.main()
