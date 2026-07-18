import os
import logging
import shutil
import tempfile
import unittest

from src import utils


class TestLogging(unittest.TestCase):
    def setUp(self):
        self._orig_log_file = utils.LOG_FILE
        self._logger = logging.getLogger(utils.LOGGER_NAME)
        self._saved_handlers = self._logger.handlers[:]
        # Start from just the NullHandler so setup_logging configures fresh.
        self._close_real_handlers()

    def tearDown(self):
        self._close_real_handlers()
        self._logger.handlers = self._saved_handlers
        utils.LOG_FILE = self._orig_log_file

    def _close_real_handlers(self):
        """Close + detach any file handlers so their file can be deleted (Windows)."""
        for h in self._logger.handlers[:]:
            if not isinstance(h, logging.NullHandler):
                h.close()
                self._logger.removeHandler(h)

    def test_log_path_is_absolute_and_under_appdata(self):
        p = utils._log_path()
        self.assertTrue(os.path.isabs(p))
        self.assertTrue(
            p.endswith(os.path.join("OCR File Sorter", "logs", "ocr-file-sorter.log"))
        )

    def test_setup_logging_writes_records(self):
        tmp = tempfile.mkdtemp()
        try:
            utils.LOG_FILE = os.path.join(tmp, "logs", "app.log")  # parent missing
            self.assertEqual(utils.setup_logging(), utils.LOG_FILE)
            logging.getLogger("ocr_file_sorter.sorter").error("hello-log-test")
            self._close_real_handlers()  # flush + release the file before reading/deleting
            self.assertTrue(os.path.exists(utils.LOG_FILE))
            with open(utils.LOG_FILE, encoding="utf-8") as f:
                self.assertIn("hello-log-test", f.read())
        finally:
            self._close_real_handlers()
            shutil.rmtree(tmp, ignore_errors=True)

    def test_setup_logging_is_idempotent(self):
        tmp = tempfile.mkdtemp()
        try:
            utils.LOG_FILE = os.path.join(tmp, "app.log")
            utils.setup_logging()
            before = [h for h in self._logger.handlers if not isinstance(h, logging.NullHandler)]
            utils.setup_logging()  # must not add a second handler
            after = [h for h in self._logger.handlers if not isinstance(h, logging.NullHandler)]
            self.assertEqual(len(before), len(after))
        finally:
            self._close_real_handlers()
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
