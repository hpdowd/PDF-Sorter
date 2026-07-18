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

from src.mapping_editor.editor_logic import EditorLogic
from src.mapping_editor.editor_actions import EditorActions


BASE = {
    "invoice": {"name": "Inv", "dest": "Invoices"},
    "receipt": {"name": "Rec", "dest": "Receipts"},
    "report": {"name": "Rep", "dest": "Reports"},
}


class FakeTable:
    """Minimal stand-in for the MappingTable Treeview (name, phrase, dest)."""
    def __init__(self):
        self._rows = []
        self._sel = ()

    def set_rows(self, rows):
        self._rows = rows

    def selection(self):
        return (str(self._sel[0]),) if self._sel else ()

    def item(self, item_id, what):
        return self._rows[int(item_id)]

    def get_children(self):
        return tuple(str(i) for i in range(len(self._rows)))

    def selection_set(self, item_id):
        self._sel = (int(item_id),)


class FakeView:
    def __init__(self, logic):
        self.logic = logic
        self.mapping_table = FakeTable()
        self.dirty = None
        self._rebuild()

    def _rebuild(self):
        self.mapping_table.set_rows(
            [(r["name"], p, r["dest"]) for p, r in self.logic.mappings.items()]
        )

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


class TestEditorActionsRegression(unittest.TestCase):
    def test_remove_rule(self):
        logic, view, actions = make(BASE)
        view.mapping_table._sel = (0,)  # invoice
        actions.on_remove_rule()
        self.assertEqual(list(logic.mappings), ["receipt", "report"])
        self.assertTrue(view.dirty)

    def test_move_up(self):
        logic, view, actions = make(BASE)
        view.mapping_table._sel = (2,)  # report
        actions.on_move_rule("up")
        self.assertEqual(list(logic.mappings), ["invoice", "report", "receipt"])

    def test_move_down(self):
        logic, view, actions = make(BASE)
        view.mapping_table._sel = (0,)  # invoice
        actions.on_move_rule("down")
        self.assertEqual(list(logic.mappings), ["receipt", "invoice", "report"])


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
