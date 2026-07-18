"""Tests for per-user settings persistence (independent of the launch directory)."""
import os
import tempfile
import shutil
import unittest

from src import utils


class TestSettings(unittest.TestCase):
    def test_settings_path_is_absolute_and_not_cwd_relative(self):
        p = utils._settings_path()
        self.assertTrue(os.path.isabs(p))
        self.assertTrue(p.endswith(os.path.join("OCR File Sorter", "settings.json")))
        self.assertNotEqual(p, "settings.json")

    def test_save_load_roundtrip_creates_parent_dir(self):
        tmp = tempfile.mkdtemp()
        path = os.path.join(tmp, "nested", "settings.json")  # parent doesn't exist yet
        original = utils.SETTINGS_FILE
        utils.SETTINGS_FILE = path
        try:
            utils.save_settings({"last_mapping_file": "example.json"})
            self.assertTrue(os.path.exists(path))
            self.assertEqual(utils.load_settings(), {"last_mapping_file": "example.json"})
        finally:
            utils.SETTINGS_FILE = original
            shutil.rmtree(tmp)

    def test_load_missing_returns_empty(self):
        original = utils.SETTINGS_FILE
        utils.SETTINGS_FILE = os.path.join(tempfile.gettempdir(), "definitely-missing-xyz", "settings.json")
        try:
            self.assertEqual(utils.load_settings(), {})
        finally:
            utils.SETTINGS_FILE = original


if __name__ == "__main__":
    unittest.main()
