"""Tests for the mapping editor logic and the Remove/Move actions.

Remove/Move previously had a regression where a table row was mis-unpacked,
raising ValueError and silently failing in the no-console release build. The
action-layer tests guard that path, now against the real Qt editor (offscreen)
rather than a fake table.
"""
import os
import json
import shutil
import tempfile
import unittest
from unittest.mock import patch

from src.mapping_editor.editor_logic import EditorLogic


BASE = {
    "invoice": {"name": "Inv", "dest": "Invoices"},
    "receipt": {"name": "Rec", "dest": "Receipts"},
    "report": {"name": "Rep", "dest": "Reports"},
}


class TestEditorLogic(unittest.TestCase):
    def test_add_rule_stores_new_format(self):
        logic = EditorLogic()
        ok, _ = logic.add_rule("phrase", "Name", "Dest")
        self.assertTrue(ok)
        self.assertEqual(logic.mappings["phrase"], {"name": "Name", "dest": "Dest"})

    def test_duplicate_rejected(self):
        logic = EditorLogic()
        logic.add_rule("p", "N", "D")
        ok, _ = logic.add_rule("p", "N2", "D2")
        self.assertFalse(ok)

    def test_move_rule_reorders(self):
        logic = EditorLogic()
        logic.mappings = dict(BASE)
        self.assertTrue(logic.move_rule("report", "up"))
        self.assertEqual(list(logic.mappings), ["invoice", "report", "receipt"])

    def test_add_rule_without_match_stays_compact(self):
        logic = EditorLogic()
        logic.add_rule("phrase", "Name", "Dest")
        self.assertNotIn("match", logic.mappings["phrase"])

    def test_add_rule_with_match_persists_block(self):
        logic = EditorLogic()
        match = {"any": ["invoice"], "all": ["acme"], "none": ["quote"]}
        logic.add_rule("acme invoices", "Acme", "Billing", match)
        self.assertEqual(logic.mappings["acme invoices"]["match"], match)

    def test_update_rule_keeps_position_when_phrase_changes(self):
        logic = EditorLogic()
        logic.mappings = dict(BASE)
        middle = list(logic.mappings)[1]
        ok, _ = logic.update_rule(middle, "renamed", "N", "D")
        self.assertTrue(ok)
        # Order is match priority; editing must not demote the rule.
        self.assertEqual(list(logic.mappings).index("renamed"), 1)

    def test_reorder_rule_moves_to_drop_row(self):
        logic = EditorLogic()
        logic.mappings = dict(BASE)          # invoice, receipt, report
        # Drop "invoice" below "report" (drop-row 3, counted pre-removal).
        self.assertTrue(logic.reorder_rule("invoice", 3))
        self.assertEqual(list(logic.mappings), ["receipt", "report", "invoice"])
        # Drop "invoice" back to the top.
        self.assertTrue(logic.reorder_rule("invoice", 0))
        self.assertEqual(list(logic.mappings), ["invoice", "receipt", "report"])

    def test_reorder_rule_noop_drop_is_not_dirty(self):
        logic = EditorLogic()
        logic.mappings = dict(BASE)
        # Dropping a rule just above or below itself changes nothing.
        self.assertFalse(logic.reorder_rule("receipt", 1))
        self.assertFalse(logic.reorder_rule("receipt", 2))
        self.assertFalse(logic.is_dirty)
        self.assertEqual(list(logic.mappings), ["invoice", "receipt", "report"])

    def test_update_rule_can_drop_match_block(self):
        logic = EditorLogic()
        logic.add_rule("p", "N", "D", {"any": ["p"], "all": ["x"], "none": []})
        # Editing with match=None (advanced turned off) removes the block.
        logic.update_rule("p", "p", "N", "D", None)
        self.assertNotIn("match", logic.mappings["p"])

    def test_set_and_get_foldering(self):
        logic = EditorLogic()
        self.assertEqual(logic.get_foldering(), {})
        logic.set_foldering({"by": "date", "group": "year", "date_source": "content"})
        self.assertTrue(logic.is_dirty)
        self.assertEqual(logic.get_foldering()["group"], "year")

    def test_set_foldering_none_clears(self):
        logic = EditorLogic()
        logic.config["foldering"] = {"by": "date", "group": "year", "date_source": "content"}
        logic.set_foldering({})
        self.assertNotIn("foldering", logic.config)

    def test_set_foldering_no_change_keeps_clean(self):
        logic = EditorLogic()
        logic.config["foldering"] = {"by": "date"}
        logic.is_dirty = False
        logic.set_foldering({"by": "date"})
        self.assertFalse(logic.is_dirty)


class TestEditorActionsRegression(unittest.TestCase):
    """Remove/Move driven through the real Qt editor and rules table."""

    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def make(self, mappings):
        import copy
        from src.ui_qt.editor import MappingEditor
        # Keep the editor away from the real per-user mappings directory.
        with patch("src.utils.MappingUtils.get_available_mappings", return_value=[]):
            editor = MappingEditor()
        # Deep copy: actions like a rule drop mutate the nested rule dicts.
        editor.logic.mappings = copy.deepcopy(mappings)
        editor.refresh_mapping_table()
        return editor

    def test_remove_rule(self):
        editor = self.make(BASE)
        editor.rules_table.select_phrase("invoice")
        editor.on_remove_rule()
        self.assertEqual(list(editor.logic.mappings), ["receipt", "report"])
        self.assertTrue(editor.logic.is_dirty)

    def test_move_up(self):
        editor = self.make(BASE)
        editor.rules_table.select_phrase("report")
        editor.on_move_rule("up")
        self.assertEqual(list(editor.logic.mappings), ["invoice", "report", "receipt"])
        # The moved rule stays selected after the refresh.
        self.assertEqual(editor.rules_table.selected_phrase(), "report")

    def test_move_down(self):
        editor = self.make(BASE)
        editor.rules_table.select_phrase("invoice")
        editor.on_move_rule("down")
        self.assertEqual(list(editor.logic.mappings), ["receipt", "invoice", "report"])

    def test_rule_drop_assigns_destination(self):
        editor = self.make(BASE)
        editor.on_rule_dropped("invoice", "Archive/2024")
        self.assertEqual(editor.logic.mappings["invoice"]["dest"], "Archive/2024")
        self.assertTrue(editor.logic.is_dirty)

    def test_rule_drop_same_destination_keeps_clean(self):
        editor = self.make(BASE)
        editor.logic.is_dirty = False
        editor.on_rule_dropped("invoice", "Invoices")
        self.assertFalse(editor.logic.is_dirty)


class TestTestPdf(unittest.TestCase):
    """Exercises 'Test a PDF'. PDF reading is mocked (per the suite's fitz stub);
    matching, date-token resolution, and reporting are the real thing."""
    TEXT = "This is an Employee Questionnaire dated 2024-03-01"

    def _test(self, mappings, text=TEXT):
        logic = EditorLogic()
        logic.mappings = mappings
        with patch("src.sorter.Sorter.read_pdf_text", return_value=text):
            return logic.test_pdf("dummy.pdf")

    def test_reports_match_and_destination(self):
        result = self._test({"Employee Questionnaire": {"name": "Questionnaire",
                                                        "dest": "HR/Questionnaires"}})
        self.assertIn("Questionnaire", result)
        self.assertIn("HR/Questionnaires", result)

    def test_resolves_date_tokens_in_destination(self):
        result = self._test({"Employee Questionnaire": {"name": "Q", "dest": "HR/{doc_year}"}})
        self.assertIn("HR/2024", result)

    def test_reports_no_match(self):
        result = self._test({"phrase that does not appear zzz": {"name": "X", "dest": "X"}})
        self.assertIn("No rule matched", result)

    def test_reports_unreadable(self):
        result = self._test({"invoice": {"name": "I", "dest": "Inv"}}, text="")
        self.assertIn("No readable text", result)


class TestEditorConfig(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.path = os.path.join(self.tmp, "m.json")

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def _write(self, data):
        with open(self.path, "w") as f:
            json.dump(data, f)

    def test_config_separated_on_load_and_merged_on_save(self):
        self._write({"_config": {"naming_scheme": "{rule_name}{ext}"},
                     "invoice": {"name": "Inv", "dest": "Invoices"}})
        logic = EditorLogic()
        logic.load_mapping_file(self.path)
        self.assertNotIn("_config", logic.mappings)          # not shown as a rule
        self.assertEqual(logic.get_naming_scheme(), "{rule_name}{ext}")

        logic.save_mappings()
        with open(self.path) as f:
            saved = json.load(f)
        self.assertEqual(saved["_config"]["naming_scheme"], "{rule_name}{ext}")
        self.assertIn("invoice", saved)

    def test_foldering_persists_and_reloads(self):
        self._write({"invoice": {"name": "Inv", "dest": "Invoices"}})
        logic = EditorLogic()
        logic.load_mapping_file(self.path)
        logic.set_foldering({"by": "date", "group": "year_month", "date_source": "content"})
        logic.save_mappings()

        reloaded = EditorLogic()
        reloaded.load_mapping_file(self.path)
        self.assertEqual(reloaded.get_foldering(),
                         {"by": "date", "group": "year_month", "date_source": "content"})
        self.assertNotIn("_config", reloaded.mappings)  # still hidden from the rules

    def test_set_naming_scheme_marks_dirty_then_clears(self):
        self._write({"invoice": {"name": "Inv", "dest": "Invoices"}})
        logic = EditorLogic()
        logic.load_mapping_file(self.path)
        self.assertFalse(logic.is_dirty)
        logic.set_naming_scheme("{date}{ext}")
        self.assertTrue(logic.is_dirty)
        self.assertEqual(logic.get_naming_scheme(), "{date}{ext}")
        logic.set_naming_scheme("")
        self.assertEqual(logic.get_naming_scheme(), "")


if __name__ == "__main__":
    unittest.main()
