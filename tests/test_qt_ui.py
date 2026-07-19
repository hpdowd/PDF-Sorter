"""Smoke tests for the Qt view layer (offscreen — no display needed).

These cover the view-side behaviours the engine tests can't: chip editing,
the colour-coded rules table, the rule dialog's match-block assembly, the
editable sort preview, and the editor's foldering panel round-trip.
"""
import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QLineEdit

app = QApplication.instance() or QApplication([])

from src.sorter import PlanItem
from src.ui_qt import theme
from src.ui_qt.chip_input import ChipInput
from src.ui_qt.dialogs import SortPreviewDialog
from src.ui_qt.editor import MappingEditor
from src.ui_qt.editor_dialogs import PatternDestDialog
from src.ui_qt.rules_table import RulesTable, segments_to_html


def make_editor(mappings=None):
    # Keep the editor away from the real per-user mappings directory.
    with patch("src.utils.MappingUtils.get_available_mappings", return_value=[]):
        editor = MappingEditor()
    if mappings is not None:
        editor.logic.mappings = dict(mappings)
        editor.refresh_mapping_table()
    return editor


class TestChipInput(unittest.TestCase):
    def test_set_and_get_terms(self):
        chips = ChipInput(kind="any", terms=["invoice", "  receipt ", ""])
        self.assertEqual(chips.get_terms(), ["invoice", "receipt"])

    def test_add_via_inline_editor(self):
        chips = ChipInput(kind="all")
        chips._begin_add()
        edit = next(chips._layout.itemAt(i).widget()
                    for i in range(chips._layout.count())
                    if isinstance(chips._layout.itemAt(i).widget(), QLineEdit))
        edit.setText("acme")
        chips.commit_pending()
        self.assertEqual(chips.get_terms(), ["acme"])

    def test_duplicate_not_added(self):
        chips = ChipInput(kind="any", terms=["invoice"])
        chips._begin_add()
        edit = next(chips._layout.itemAt(i).widget()
                    for i in range(chips._layout.count())
                    if isinstance(chips._layout.itemAt(i).widget(), QLineEdit))
        edit.setText("invoice")
        chips.commit_pending()
        self.assertEqual(chips.get_terms(), ["invoice"])

    def test_remove(self):
        chips = ChipInput(kind="none", terms=["a", "b"])
        chips._remove("a")
        self.assertEqual(chips.get_terms(), ["b"])

    def test_enter_chains_into_next_word(self):
        from PySide6.QtCore import QEvent, Qt as QtNS
        from PySide6.QtGui import QKeyEvent
        chips = ChipInput(kind="any")
        chips._begin_add()
        chips._edit.setText("invoice")
        event = QKeyEvent(QEvent.Type.KeyPress, QtNS.Key.Key_Return,
                          QtNS.KeyboardModifier.NoModifier)
        swallowed = chips.eventFilter(chips._edit, event)
        # Enter must be swallowed: QLineEdit doesn't consume Return, so a
        # propagated keypress would fire the dialog's default (OK) button.
        self.assertTrue(swallowed)
        self.assertEqual(chips.get_terms(), ["invoice"])
        self.assertIsNotNone(chips._edit)         # editor reopened for the next word

    def test_empty_field_dissolves(self):
        chips = ChipInput(kind="any", terms=["invoice"])
        chips._begin_add()
        chips.commit_pending()                    # empty: as if never opened
        self.assertEqual(chips.get_terms(), ["invoice"])
        self.assertIsNone(chips._edit)

    def test_escape_cancels_without_adding(self):
        from PySide6.QtCore import QEvent, Qt as QtNS
        from PySide6.QtGui import QKeyEvent
        chips = ChipInput(kind="any")
        chips._begin_add()
        chips._edit.setText("half-typed")
        event = QKeyEvent(QEvent.Type.KeyPress, QtNS.Key.Key_Escape,
                          QtNS.KeyboardModifier.NoModifier)
        swallowed = chips.eventFilter(chips._edit, event)
        self.assertTrue(swallowed)                # Esc must not reach the dialog
        self.assertEqual(chips.get_terms(), [])
        self.assertIsNone(chips._edit)

    def test_outside_click_commits(self):
        from PySide6.QtWidgets import QLabel
        chips = ChipInput(kind="any")
        outside = QLabel("elsewhere")
        chips._begin_add()
        chips._edit.setText("receipt")
        from PySide6.QtCore import QEvent
        class _Press(QEvent):
            def __init__(self):
                super().__init__(QEvent.Type.MouseButtonPress)
        chips.eventFilter(outside, _Press())      # app-filter path
        self.assertEqual(chips.get_terms(), ["receipt"])
        self.assertIsNone(chips._edit)


class TestRulesTable(unittest.TestCase):
    MAPPINGS = {
        "invoice|receipt": {"name": "Billing", "dest": "Invoices"},
        "contract": {"name": "Legal", "dest": "Contracts",
                     "match": {"any": ["contract"], "all": ["signed"], "none": ["draft"]}},
    }

    def test_refresh_and_selection(self):
        table = RulesTable()
        table.refresh(self.MAPPINGS)
        self.assertEqual(table.topLevelItemCount(), 2)
        self.assertIsNone(table.selected_phrase())
        table.select_phrase("contract")
        self.assertEqual(table.selected_phrase(), "contract")

    def test_segments_render_role_colours(self):
        from src import matching
        html = segments_to_html(matching.describe_match_segments(
            "contract", self.MAPPINGS["contract"]))
        self.assertIn(theme.ROLE["or"], html)    # any term coloured blue
        self.assertIn(theme.ROLE["and"], html)   # all term coloured green
        self.assertIn(theme.ROLE["not"], html)   # none term coloured red
        self.assertIn("signed", html)
        self.assertIn("draft", html)

    def test_segments_html_escapes_terms(self):
        html = segments_to_html([("<b>x</b>", "or")])
        self.assertIn("&lt;b&gt;x&lt;/b&gt;", html)


class TestPatternDestDialog(unittest.TestCase):
    def test_simple_rule_builds_phrase_only(self):
        dialog = PatternDestDialog(None, "Add Rule", None, ["Invoices"],
                                   initial_name="Inv", initial_phrase="invoice|receipt",
                                   initial_dest="Invoices")
        dialog.accept()
        self.assertEqual(dialog.phrase, "invoice|receipt")
        self.assertEqual(dialog.dest, "Invoices")
        self.assertIsNone(dialog.match)

    def test_advanced_rule_builds_match_block(self):
        dialog = PatternDestDialog(None, "Edit Rule", None, ["Billing"],
                                   initial_name="Acme", initial_phrase="invoice",
                                   initial_dest="Billing",
                                   initial_match={"any": ["invoice"], "all": ["acme"],
                                                  "none": ["quote"]})
        self.assertTrue(dialog._advanced_open)   # opens disclosed when advanced terms exist
        dialog.accept()
        self.assertEqual(dialog.match, {"any": ["invoice"], "all": ["acme"],
                                        "none": ["quote"]})

    def test_uncommitted_chip_text_is_committed_on_accept(self):
        dialog = PatternDestDialog(None, "Add Rule", None, ["Inbox"],
                                   initial_name="R", initial_phrase="invoice",
                                   initial_dest="Inbox")
        dialog.any_chips._begin_add()
        edit = next(dialog.any_chips._layout.itemAt(i).widget()
                    for i in range(dialog.any_chips._layout.count())
                    if isinstance(dialog.any_chips._layout.itemAt(i).widget(), QLineEdit))
        edit.setText("receipt")
        dialog.accept()
        self.assertEqual(dialog.phrase, "invoice|receipt")


class _FakeSorter:
    def destination_folders(self):
        return ["Invoices", "Receipts"]


def make_preview():
    plan = [
        PlanItem("/in/inv.pdf", "matched", phrase="invoice", dest="Invoices",
                 dest_name="inv.pdf"),
        PlanItem("/in/mystery.pdf", "unmatched", message="No matching rule"),
        PlanItem("/in/scan.pdf", "unreadable", message="No readable text"),
    ]
    return SortPreviewDialog(None, plan, _FakeSorter()), plan


class TestSortPreviewDialog(unittest.TestCase):
    def test_summary_counts(self):
        dialog, _ = make_preview()
        self.assertIn("1 to sort", dialog.summary_label.text())
        self.assertIn("1 no match", dialog.summary_label.text())
        self.assertIn("1 unreadable/error", dialog.summary_label.text())
        self.assertTrue(dialog.move_btn.isEnabled())

    def test_reassign_unmatched_marks_manual(self):
        dialog, plan = make_preview()
        item = dialog.tree.topLevelItem(1)  # the unmatched file
        dialog._apply_choice(item, "dest", "Receipts")
        p = plan[1]
        self.assertEqual(p.status, "matched")
        self.assertEqual(p.dest, "Receipts")
        self.assertEqual(p.phrase, "(manual)")
        self.assertEqual(p.dest_name, "mystery.pdf")  # keeps its original name
        self.assertIn("2 to sort", dialog.summary_label.text())

    def test_skip_last_matched_disables_move(self):
        dialog, plan = make_preview()
        dialog._apply_choice(dialog.tree.topLevelItem(0), "skip", None)
        self.assertEqual(plan[0].status, "skipped")
        self.assertFalse(dialog.move_btn.isEnabled())
        self.assertFalse(dialog.copy_btn.isEnabled())
        self.assertIn("won't sort", dialog.summary_label.text())

    def test_reassign_matched_keeps_renamed_name(self):
        dialog, plan = make_preview()
        plan[0].dest_name = "Billing_20240314 - inv.pdf"  # naming-scheme rename
        dialog._apply_choice(dialog.tree.topLevelItem(0), "dest", "Receipts")
        self.assertEqual(plan[0].dest, "Receipts")
        self.assertEqual(plan[0].dest_name, "Billing_20240314 - inv.pdf")
        self.assertEqual(plan[0].phrase, "invoice")  # still credited to its rule


class TestEditorFolderingPanel(unittest.TestCase):
    def test_off_by_default(self):
        editor = make_editor()
        self.assertEqual(editor.get_foldering_config(), {})
        self.assertFalse(editor.fold_group_combo.isEnabled())

    def test_config_assembled_from_dropdowns(self):
        editor = make_editor()
        editor.fold_by_combo.setCurrentText("Date")
        editor.fold_group_combo.setCurrentText("Year and Quarter")
        editor.fold_source_combo.setCurrentText("File modified date")
        self.assertEqual(editor.get_foldering_config(),
                         {"by": "date", "group": "quarter",
                          "date_source": "file_modified"})
        self.assertTrue(editor.fold_group_combo.isEnabled())
        self.assertTrue(editor.logic.is_dirty)

    def test_round_trip_from_loaded_config(self):
        editor = make_editor()
        editor.logic.config["foldering"] = {"by": "date", "group": "year",
                                            "date_source": "pdf_metadata"}
        editor.logic.is_dirty = False
        editor.refresh_all()
        self.assertEqual(editor.fold_by_combo.currentText(), "Date")
        self.assertEqual(editor.fold_group_combo.currentText(), "Year")
        self.assertEqual(editor.get_foldering_config(),
                         {"by": "date", "group": "year",
                          "date_source": "pdf_metadata"})
        # Repopulating the view is not an edit.
        self.assertFalse(editor.logic.is_dirty)


if __name__ == "__main__":
    unittest.main()
