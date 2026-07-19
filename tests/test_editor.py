"""Tests for the mapping editor logic and the Remove/Move actions.

on_remove_rule / on_move_rule previously unpacked a 3-column table row into two
variables (phrase, _), raising ValueError and silently failing in the no-console
release build. These tests guard that regression.
"""
import os
import json
import shutil
import tempfile
import unittest
from unittest.mock import patch

from src.mapping_editor.editor_logic import EditorLogic
from src.mapping_editor.editor_actions import EditorActions


BASE = {
    "invoice": {"name": "Inv", "dest": "Invoices"},
    "receipt": {"name": "Rec", "dest": "Receipts"},
    "report": {"name": "Rep", "dest": "Reports"},
}


class FakeTable:
    """Minimal stand-in for the MappingTable Treeview. The row iid is the phrase
    key, mirroring the real widget; selection() yields that key."""
    def __init__(self):
        self._rows = {}
        self._order = []
        self._sel = ()

    def set_rows(self, mappings):
        self._order = list(mappings.keys())
        self._rows = {p: (r["name"], p, r["dest"]) for p, r in mappings.items()}

    def selection(self):
        return (self._sel[0],) if self._sel else ()

    def item(self, item_id, what):
        return self._rows[item_id]

    def get_children(self):
        return tuple(self._order)

    def selection_set(self, item_id):
        self._sel = (item_id,)

    def see(self, item_id):
        pass


class FakeView:
    def __init__(self, logic):
        self.logic = logic
        self.mapping_table = FakeTable()
        self.dirty = None
        self._rebuild()

    def _rebuild(self):
        self.mapping_table.set_rows(self.logic.mappings)

    def refresh_mapping_table(self):
        self._rebuild()

    def set_dirty(self, value):
        self.dirty = value


def make(mappings):
    logic = EditorLogic()
    logic.mappings = dict(mappings)
    view = FakeView(logic)
    return logic, view, EditorActions(view, logic)


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
    def test_remove_rule(self):
        logic, view, actions = make(BASE)
        view.mapping_table._sel = ("invoice",)
        actions.on_remove_rule()
        self.assertEqual(list(logic.mappings), ["receipt", "report"])
        self.assertTrue(view.dirty)

    def test_move_up(self):
        logic, view, actions = make(BASE)
        view.mapping_table._sel = ("report",)
        actions.on_move_rule("up")
        self.assertEqual(list(logic.mappings), ["invoice", "report", "receipt"])

    def test_move_down(self):
        logic, view, actions = make(BASE)
        view.mapping_table._sel = ("invoice",)
        actions.on_move_rule("down")
        self.assertEqual(list(logic.mappings), ["receipt", "invoice", "report"])


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
