"""Tests for the core sorting engine (Sorter) and mapping loading."""
import os
import json
import shutil
import tempfile
import unittest
from datetime import date

from src.sorter import Sorter, ocr_status
from src import utils


def make_sorter(mapping_data, template_dir):
    """Build a Sorter without touching the filesystem or the mapping loader."""
    s = Sorter.__new__(Sorter)
    s.status_callback = None
    s.progress_callback = None
    s.mapping_path = "x.json"
    s.template_dir = template_dir
    s.mapping_data = mapping_data
    s.naming_scheme = (mapping_data.get("_config") or {}).get("naming_scheme") or None
    s._cancelled = False
    return s


class TestFindDestination(unittest.TestCase):
    def test_new_format_returns_dest(self):
        s = make_sorter({"INVOICE": {"name": "Inv", "dest": "2024 Invoices"}}, "/tmp")
        self.assertEqual(s.find_destination("this is an INVOICE for you"), "2024 Invoices")

    def test_no_match_returns_none(self):
        s = make_sorter({"INVOICE": {"name": "Inv", "dest": "X"}}, "/tmp")
        self.assertIsNone(s.find_destination("nothing relevant here"))

    def test_normalization_collapses_whitespace(self):
        s = make_sorter({"Statement of Account": {"name": "S", "dest": "Statements"}}, "/tmp")
        self.assertEqual(s.find_destination("...\n  statement   of\naccount ..."), "Statements")

    def test_old_format_string_value_still_resolves(self):
        s = make_sorter({"Receipt": "Receipts"}, "/tmp")
        self.assertEqual(s.find_destination("a receipt attached"), "Receipts")

    def test_first_match_wins_by_insertion_order(self):
        s = make_sorter({
            "alpha": {"name": "A", "dest": "DestA"},
            "beta": {"name": "B", "dest": "DestB"},
        }, "/tmp")
        self.assertEqual(s.find_destination("alpha and beta present"), "DestA")

    def test_empty_dest_rule_does_not_block_later_match(self):
        s = make_sorter({
            "invoice": {"name": "Bad", "dest": ""},          # matches but misconfigured
            "invoice number": {"name": "Good", "dest": "Invoices"},
        }, "/tmp")
        self.assertEqual(s.find_destination("invoice number 42"), "Invoices")

    def test_only_empty_dest_match_returns_none(self):
        s = make_sorter({"invoice": {"name": "Bad", "dest": ""}}, "/tmp")
        self.assertIsNone(s.find_destination("this invoice"))

    def test_multi_phrase_matches_any_alternative(self):
        # A key can hold several phrases separated by '|'; any one appearing matches.
        s = make_sorter({"invoice|receipt": {"name": "Billing", "dest": "Billing"}}, "/tmp")
        self.assertEqual(s.find_destination("your RECEIPT is attached"), "Billing")
        self.assertEqual(s.find_destination("this INVOICE is due"), "Billing")

    def test_multi_phrase_no_alternative_present_returns_none(self):
        s = make_sorter({"invoice|receipt": {"name": "Billing", "dest": "Billing"}}, "/tmp")
        self.assertIsNone(s.find_destination("a statement of account"))


class TestDestinationFolders(unittest.TestCase):
    def test_unique_sorted_and_skips_reserved_and_empty(self):
        s = make_sorter({
            "_config": {"naming_scheme": "x"},        # reserved, ignored
            "invoice": {"name": "Inv", "dest": "Billing"},
            "receipt": {"name": "Rec", "dest": "Billing"},   # duplicate dest
            "statement": {"name": "St", "dest": "Statements"},
            "broken": {"name": "B", "dest": ""},       # no dest, ignored
        }, "/tmp")
        self.assertEqual(s.destination_folders(), ["Billing", "Statements"])

    def test_old_format_string_dests_included(self):
        s = make_sorter({"Receipt": "Receipts", "Invoice": "Invoices"}, "/tmp")
        self.assertEqual(s.destination_folders(), ["Invoices", "Receipts"])

    def test_empty_mapping_returns_empty_list(self):
        s = make_sorter({}, "/tmp")
        self.assertEqual(s.destination_folders(), [])


class TestPreviewOverrides(unittest.TestCase):
    """Execute keys off status/dest/dest_name only, so the editable preview can
    mutate PlanItems directly. These lock that contract in place."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.inp = os.path.join(self.tmp, "in")
        os.makedirs(self.inp)
        self.tpl = os.path.join(self.tmp, "tpl")
        os.makedirs(self.tpl)
        for n in ("a.pdf", "b.pdf"):
            open(os.path.join(self.inp, n), "w").close()
        self.s = make_sorter({"invoice": {"name": "Inv", "dest": "Invoices"}}, self.tpl)
        self.s.read_pdf_text = lambda p, first_page_only=False: "an invoice"

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_skipped_item_is_not_moved(self):
        plan = self.s.plan([self.inp])
        plan[0].status = "skipped"                    # user unchecked this file
        _manifest, count = self.s.execute(plan)
        self.assertEqual(count, 1)                     # only the other file moved
        self.assertTrue(os.path.exists(os.path.join(self.inp, plan[0].filename)))

    def test_reassigned_destination_is_honored(self):
        plan = self.s.plan([self.inp])
        plan[0].dest = "Elsewhere"                     # user changed the folder
        self.s.execute(plan)
        self.assertTrue(os.path.exists(os.path.join(self.tpl, "Elsewhere", plan[0].filename)))


class TestMappingValidation(unittest.TestCase):
    def test_warns_on_rules_missing_dest(self):
        s = make_sorter({
            "good": {"name": "G", "dest": "D"},
            "bad": {"name": "B", "dest": ""},
        }, "/tmp")
        with self.assertLogs("ocr_file_sorter.sorter", level="WARNING") as cm:
            s._validate_mapping()
        self.assertIn("bad", " ".join(cm.output))


class TestUniquePath(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.d)

    def test_no_collision(self):
        self.assertEqual(Sorter._unique_path(self.d, "a.pdf"), os.path.join(self.d, "a.pdf"))

    def test_collision_appends_incrementing_counter(self):
        open(os.path.join(self.d, "a.pdf"), "w").close()
        self.assertEqual(Sorter._unique_path(self.d, "a.pdf"), os.path.join(self.d, "a (1).pdf"))
        open(os.path.join(self.d, "a (1).pdf"), "w").close()
        self.assertEqual(Sorter._unique_path(self.d, "a.pdf"), os.path.join(self.d, "a (2).pdf"))


class TestSortFiles(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.inp = os.path.join(self.tmp, "input")
        os.makedirs(os.path.join(self.inp, "sub"))
        self.tpl = os.path.join(self.tmp, "tpl")
        os.makedirs(self.tpl)
        for name in ("a.pdf", "b.pdf"):
            open(os.path.join(self.inp, name), "w").close()
        open(os.path.join(self.inp, "sub", "c.pdf"), "w").close()
        open(os.path.join(self.inp, "note.txt"), "w").close()  # non-pdf, must be ignored
        self.s = make_sorter({"invoice": {"name": "Inv", "dest": "Invoices"}}, self.tpl)
        self.s.read_pdf_text = lambda p, first_page_only=False: "this invoice"

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def inv(self, *p):
        return os.path.join(self.tpl, "Invoices", *p)

    def test_top_level_only_skips_subfolders_and_non_pdf(self):
        scanned, moved = self.s.sort_files([self.inp], deep_audit=False)
        self.assertEqual((scanned, moved), (2, 2))
        self.assertTrue(os.path.exists(self.inv("a.pdf")))
        self.assertTrue(os.path.exists(self.inv("b.pdf")))
        self.assertTrue(os.path.exists(os.path.join(self.inp, "sub", "c.pdf")))
        self.assertTrue(os.path.exists(os.path.join(self.inp, "note.txt")))

    def test_deep_audit_recurses_into_subfolders(self):
        _, moved = self.s.sort_files([self.inp], deep_audit=True)
        self.assertEqual(moved, 3)
        self.assertTrue(os.path.exists(self.inv("c.pdf")))

    def test_move_is_collision_safe(self):
        self.s.sort_files([self.inp], deep_audit=False)
        open(os.path.join(self.inp, "a.pdf"), "w").close()
        self.s.sort_files([self.inp], deep_audit=False)
        self.assertTrue(os.path.exists(self.inv("a (1).pdf")))

    def test_no_match_moves_nothing(self):
        self.s.read_pdf_text = lambda p, first_page_only=False: "unrelated text"
        scanned, moved = self.s.sort_files([self.inp], deep_audit=False)
        self.assertEqual((scanned, moved), (2, 0))

    def test_count_pdfs_respects_deep_audit(self):
        self.assertEqual(self.s.count_pdfs([self.inp], deep_audit=False), 2)
        self.assertEqual(self.s.count_pdfs([self.inp], deep_audit=True), 3)

    def test_progress_callback_fires_once_per_scanned_file(self):
        calls = []
        self.s.progress_callback = lambda: calls.append(1)
        scanned, _ = self.s.sort_files([self.inp], deep_audit=False)
        self.assertEqual(len(calls), scanned)
        self.assertEqual(len(calls), 2)

    def test_sort_renames_when_scheme_configured(self):
        s = make_sorter({"invoice": {"name": "Invoice", "dest": "Invoices"}}, self.tpl)
        s.naming_scheme = "{rule_name}_{original_filename}{ext}"
        s.read_pdf_text = lambda p, first_page_only=False: "invoice"
        s.sort_files([self.inp], deep_audit=False)
        self.assertTrue(os.path.exists(os.path.join(self.tpl, "Invoices", "Invoice_a.pdf")))
        self.assertTrue(os.path.exists(os.path.join(self.tpl, "Invoices", "Invoice_b.pdf")))

    def test_deep_audit_skips_own_template_dir(self):
        # Put the template dir *inside* the input folder with an already-sorted file.
        inside_tpl = os.path.join(self.inp, "Invoices_template")
        os.makedirs(os.path.join(inside_tpl, "Invoices"))
        already = os.path.join(inside_tpl, "Invoices", "already.pdf")
        open(already, "w").close()
        s = make_sorter({"invoice": {"name": "Inv", "dest": "Invoices"}}, inside_tpl)
        s.read_pdf_text = lambda p, first_page_only=False: "invoice"

        scanned, moved = s.sort_files([self.inp], deep_audit=True)
        # a.pdf, b.pdf, sub/c.pdf are scanned; already.pdf in the template is skipped.
        self.assertEqual(scanned, 3)
        self.assertTrue(os.path.exists(already))


class TestNaming(unittest.TestCase):
    def _sorter(self, scheme):
        s = make_sorter({"invoice": {"name": "Invoice", "dest": "Invoices"}}, "/tmp")
        s.naming_scheme = scheme
        return s

    def test_no_scheme_keeps_original_name(self):
        s = self._sorter(None)
        self.assertEqual(s._apply_naming({"name": "X"}, "p", "/x/orig.pdf"), "orig.pdf")

    def test_expands_placeholders(self):
        s = self._sorter("{rule_name} - {original_filename}{ext}")
        self.assertEqual(
            s._apply_naming({"name": "Invoice"}, "invoice", "/x/orig.pdf"),
            "Invoice - orig.pdf")

    def test_sanitizes_invalid_chars(self):
        s = self._sorter("{rule_name}{ext}")
        self.assertEqual(s._apply_naming({"name": 'A/B:C'}, "p", "/x/o.pdf"), "ABC.pdf")

    def test_appends_ext_if_scheme_omits_it(self):
        s = self._sorter("{rule_name}")
        self.assertEqual(s._apply_naming({"name": "Invoice"}, "p", "/x/o.pdf"), "Invoice.pdf")

    def test_date_placeholder(self):
        from datetime import datetime
        s = self._sorter("{date}{ext}")
        self.assertEqual(s._apply_naming({"name": "x"}, "p", "/x/o.pdf"),
                         datetime.now().strftime("%Y%m%d") + ".pdf")

    def test_config_key_is_not_matched_as_a_rule(self):
        s = make_sorter({"_config": {"naming_scheme": "x"},
                         "invoice": {"name": "I", "dest": "Invoices"}}, "/tmp")
        self.assertIsNone(s.find_matching_rule("mentions _config only"))
        match = s.find_matching_rule("here is an invoice")
        self.assertEqual((match[0], match[2]), ("invoice", "Invoices"))

    def test_config_key_not_flagged_by_validation(self):
        s = make_sorter({"_config": {"naming_scheme": "x"},
                         "invoice": {"name": "I", "dest": "Invoices"}}, "/tmp")
        with self.assertRaises(AssertionError):
            with self.assertLogs("ocr_file_sorter.sorter", level="WARNING"):
                s._validate_mapping()  # no warnings expected -> assertLogs raises


class TestFromMappingData(unittest.TestCase):
    def test_builds_without_filesystem_and_matches(self):
        s = Sorter.from_mapping_data({"invoice": {"name": "I", "dest": "Inv"}})
        self.assertIsNone(s.template_dir)
        self.assertEqual(s.find_destination("here is an invoice"), "Inv")

    def test_naming_scheme_read_from_config(self):
        s = Sorter.from_mapping_data({"_config": {"naming_scheme": "{date}{ext}"},
                                      "invoice": {"name": "I", "dest": "Inv"}})
        self.assertEqual(s.naming_scheme, "{date}{ext}")


class TestDestExpansion(unittest.TestCase):
    def _sorter(self):
        return make_sorter({"x": {"name": "X", "dest": "Y"}}, "/tmp")

    def test_plain_dest_unchanged(self):
        self.assertEqual(self._sorter()._expand_dest("Statements", {}), "Statements")

    def test_expands_year_and_month(self):
        ctx = {"doc_year": "2024", "doc_month": "03", "doc_quarter": "Q1"}
        self.assertEqual(
            self._sorter()._expand_dest("Statements/{doc_year}/{doc_month}", ctx),
            "Statements/2024/03")

    def test_quarter_token(self):
        ctx = {"doc_year": "2024", "doc_quarter": "Q1"}
        self.assertEqual(
            self._sorter()._expand_dest("Reports/{doc_year}/{doc_quarter}", ctx),
            "Reports/2024/Q1")

    def test_missing_value_becomes_unknown_bucket(self):
        self.assertEqual(self._sorter()._expand_dest("Statements/{doc_year}", {}),
                         "Statements/Unknown")

    def test_backslashes_normalized(self):
        self.assertEqual(self._sorter()._expand_dest(r"A\{doc_year}", {"doc_year": "2024"}),
                         "A/2024")

    def test_depth_capped(self):
        deep = "/".join(["a"] * 20) + "/{doc_year}"
        result = self._sorter()._expand_dest(deep, {"doc_year": "2024"})
        self.assertLessEqual(len(result.split("/")), 8)

    def test_date_context_prefers_content(self):
        ctx = self._sorter()._date_context("/does/not/exist.pdf", "invoice dated 2024-03-01")
        self.assertEqual((ctx["doc_year"], ctx["doc_month"], ctx["doc_quarter"]),
                         ("2024", "03", "Q1"))

    def test_document_date_falls_back_to_mtime(self):
        s = self._sorter()
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            path = f.name
        try:
            os.utime(path, (0, 0))
            self.assertEqual(s._document_date(path, "no date here"), date.fromtimestamp(0))
        finally:
            os.remove(path)


class TestMappingLoading(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def _write(self, data):
        p = os.path.join(self.tmp, "m.json")
        with open(p, "w") as f:
            json.dump(data, f)
        return p

    def test_migrates_old_flat_format(self):
        data = utils.MappingUtils.load_mapping(self._write({"IBAN": "01 Pay"}))
        self.assertEqual(data["IBAN"]["dest"], "01 Pay")
        self.assertIn("name", data["IBAN"])

    def test_keeps_new_dict_format(self):
        data = utils.MappingUtils.load_mapping(self._write({"IBAN": {"name": "Iban", "dest": "01 Pay"}}))
        self.assertEqual(data["IBAN"]["dest"], "01 Pay")

    def test_missing_file_returns_empty(self):
        self.assertEqual(utils.MappingUtils.load_mapping("/no/such/file.json"), {})


class TestPlanExecuteUndo(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.inp = os.path.join(self.tmp, "in")
        os.makedirs(self.inp)
        self.tpl = os.path.join(self.tmp, "tpl")
        os.makedirs(self.tpl)
        for n in ("a.pdf", "b.pdf", "nomatch.pdf"):
            open(os.path.join(self.inp, n), "w").close()
        self.s = make_sorter({"invoice": {"name": "Inv", "dest": "Invoices"}}, self.tpl)
        self.s.read_pdf_text = lambda p, first_page_only=False: (
            "unrelated" if os.path.basename(p) == "nomatch.pdf" else "an invoice")

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def inv(self, name):
        return os.path.join(self.tpl, "Invoices", name)

    def test_plan_is_non_destructive_and_classifies(self):
        plan = self.s.plan([self.inp], deep_audit=False)
        status = {i.filename: i.status for i in plan}
        self.assertEqual(status["a.pdf"], "matched")
        self.assertEqual(status["nomatch.pdf"], "unmatched")
        # Nothing moved by planning.
        self.assertTrue(os.path.exists(os.path.join(self.inp, "a.pdf")))
        self.assertFalse(os.path.exists(self.inv("a.pdf")))

    def test_execute_move_and_manifest(self):
        manifest, count = self.s.execute(self.s.plan([self.inp]), copy=False)
        self.assertEqual(count, 2)
        self.assertTrue(os.path.exists(self.inv("a.pdf")))
        self.assertFalse(os.path.exists(os.path.join(self.inp, "a.pdf")))
        self.assertEqual(len(manifest), 2)
        self.assertFalse(any(e["copied"] for e in manifest))

    def test_execute_copy_keeps_original(self):
        manifest, count = self.s.execute(self.s.plan([self.inp]), copy=True)
        self.assertEqual(count, 2)
        self.assertTrue(os.path.exists(os.path.join(self.inp, "a.pdf")))  # original stays
        self.assertTrue(os.path.exists(self.inv("a.pdf")))
        self.assertTrue(all(e["copied"] for e in manifest))

    def test_undo_move_restores_originals(self):
        manifest, _ = self.s.execute(self.s.plan([self.inp]), copy=False)
        undone, errors = Sorter.undo(manifest)
        self.assertEqual((undone, errors), (2, 0))
        self.assertTrue(os.path.exists(os.path.join(self.inp, "a.pdf")))
        self.assertFalse(os.path.exists(self.inv("a.pdf")))

    def test_undo_copy_deletes_copies(self):
        manifest, _ = self.s.execute(self.s.plan([self.inp]), copy=True)
        Sorter.undo(manifest)
        self.assertFalse(os.path.exists(self.inv("a.pdf")))
        self.assertTrue(os.path.exists(os.path.join(self.inp, "a.pdf")))


class TestCancellation(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.inp = os.path.join(self.tmp, "input")
        os.makedirs(self.inp)
        self.tpl = os.path.join(self.tmp, "tpl")
        os.makedirs(self.tpl)
        for name in ("a.pdf", "b.pdf", "c.pdf"):
            open(os.path.join(self.inp, name), "w").close()
        self.s = make_sorter({"invoice": {"name": "Inv", "dest": "Invoices"}}, self.tpl)
        self.s.read_pdf_text = lambda p, first_page_only=False: "this invoice"

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_cancel_sets_flag(self):
        self.assertFalse(self.s.cancelled)
        self.s.cancel()
        self.assertTrue(self.s.cancelled)

    def test_cancel_before_plan_yields_nothing(self):
        self.s.cancel()
        self.assertEqual(self.s.plan([self.inp]), [])

    def test_cancel_midway_stops_plan_early(self):
        # progress_callback fires per file *after* the cancel check; cancelling in
        # it means the first file completes but the next is skipped.
        self.s.progress_callback = self.s.cancel
        plan = self.s.plan([self.inp])
        self.assertEqual(len(plan), 1)

    def test_cancel_before_execute_moves_nothing(self):
        plan = self.s.plan([self.inp])
        self.assertEqual(len(plan), 3)
        self.s.cancel()
        manifest, count = self.s.execute(plan)
        self.assertEqual((count, manifest), (0, []))


class TestOcrStatus(unittest.TestCase):
    def test_returns_bool_and_nonempty_detail(self):
        available, detail = ocr_status()
        self.assertIsInstance(available, bool)
        self.assertIsInstance(detail, str)
        self.assertTrue(detail)


if __name__ == "__main__":
    unittest.main()
