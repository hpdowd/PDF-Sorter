"""Unit tests for the pure matching functions in src.matching.

These test the matcher in isolation (no Sorter, no filesystem). The engine's
end-to-end matching is covered by test_sorting.py; here we pin down the pure
semantics, including the All/Any/None model the key-derived specs don't yet use.
"""
import unittest

from src import matching


class TestNormalize(unittest.TestCase):
    def test_collapses_whitespace_and_lowercases(self):
        self.assertEqual(matching.normalize("  Statement   of\nAccount "), "statement of account")

    def test_empty(self):
        self.assertEqual(matching.normalize(""), "")


class TestResolveMatchSpec(unittest.TestCase):
    def test_single_key_becomes_any_of_one(self):
        spec = matching.resolve_match_spec("Invoice", {"dest": "X"})
        self.assertEqual(spec, {"all": [], "any": ["invoice"], "none": []})

    def test_pipe_key_becomes_any_of_alternatives_normalized(self):
        spec = matching.resolve_match_spec("Invoice | Receipt", {"dest": "X"})
        self.assertEqual(spec["any"], ["invoice", "receipt"])

    def test_blank_alternatives_dropped(self):
        spec = matching.resolve_match_spec("invoice||", {"dest": "X"})
        self.assertEqual(spec["any"], ["invoice"])

    def test_explicit_match_block_takes_precedence_over_key(self):
        rule = {"dest": "X", "match": {"all": ["Invoice"], "any": ["Acme", "Acme Corp"],
                                       "none": ["Quote"]}}
        spec = matching.resolve_match_spec("Acme invoices", rule)
        self.assertEqual(spec, {"all": ["invoice"], "any": ["acme", "acme corp"],
                                "none": ["quote"]})

    def test_empty_match_block_falls_back_to_key(self):
        # A block with no positive term must not leave the rule dead.
        rule = {"dest": "X", "match": {"none": ["draft"]}}
        spec = matching.resolve_match_spec("invoice", rule)
        self.assertEqual(spec, {"all": [], "any": ["invoice"], "none": []})

    def test_string_rule_uses_key(self):
        # Old-format rules are bare strings (dest); matching comes from the key.
        spec = matching.resolve_match_spec("receipt", "Receipts")
        self.assertEqual(spec["any"], ["receipt"])


class TestDescribeMatch(unittest.TestCase):
    def test_simple_key(self):
        self.assertEqual(matching.describe_match("invoice", {"dest": "X"}), "invoice")

    def test_pipe_key_reads_as_or(self):
        self.assertEqual(matching.describe_match("invoice|receipt", {"dest": "X"}),
                         "invoice or receipt")

    def test_full_advanced_rule(self):
        rule = {"dest": "X", "match": {"any": ["invoice", "receipt"], "all": ["acme"],
                                       "none": ["quote"]}}
        self.assertEqual(matching.describe_match("Acme", rule),
                         "invoice or receipt · and acme · not quote")

    def test_all_only_omits_leading_and(self):
        rule = {"dest": "X", "match": {"all": ["acme", "globex"]}}
        self.assertEqual(matching.describe_match("Acme", rule), "acme · and globex")


class TestDescribeMatchSegments(unittest.TestCase):
    def test_segments_join_to_describe_match(self):
        rule = {"dest": "X", "match": {"any": ["invoice", "receipt"], "all": ["acme"],
                                       "none": ["quote"]}}
        segs = matching.describe_match_segments("Acme", rule)
        self.assertEqual("".join(t for t, _ in segs), matching.describe_match("Acme", rule))

    def test_roles_are_colour_coded(self):
        rule = {"dest": "X", "match": {"any": ["invoice"], "all": ["acme"], "none": ["quote"]}}
        roles = {text.strip(): role for text, role in matching.describe_match_segments("R", rule)}
        self.assertEqual(roles["invoice"], "or")
        self.assertEqual(roles["acme"], "and")
        self.assertEqual(roles["quote"], "not")

    def test_simple_key_terms_are_or_role(self):
        segs = matching.describe_match_segments("invoice|receipt", {"dest": "X"})
        term_roles = [(t, r) for t, r in segs if t not in (" or ",)]
        self.assertEqual(term_roles, [("invoice", "or"), ("receipt", "or")])


class TestMatchRule(unittest.TestCase):
    def test_any_single_term_present(self):
        matched, which = matching.match_rule("here is an invoice", {"any": ["invoice"]})
        self.assertTrue(matched)
        self.assertEqual(which, "invoice")

    def test_any_no_term_present(self):
        matched, which = matching.match_rule("a statement", {"any": ["invoice", "receipt"]})
        self.assertFalse(matched)
        self.assertIsNone(which)

    def test_any_returns_first_present_term(self):
        # 'receipt' appears; 'invoice' does not — which_term is the one that hit.
        matched, which = matching.match_rule("your receipt", {"any": ["invoice", "receipt"]})
        self.assertTrue(matched)
        self.assertEqual(which, "receipt")

    def test_all_terms_present(self):
        matched, which = matching.match_rule("alpha and beta", {"all": ["alpha", "beta"]})
        self.assertTrue(matched)
        self.assertEqual(which, "alpha")  # first all-term, for display

    def test_all_one_term_missing(self):
        matched, _ = matching.match_rule("alpha only", {"all": ["alpha", "beta"]})
        self.assertFalse(matched)

    def test_none_excludes(self):
        spec = {"any": ["invoice"], "none": ["quote"]}
        self.assertFalse(matching.match_rule("invoice quote", spec)[0])
        self.assertTrue(matching.match_rule("invoice only", spec)[0])

    def test_combined_all_any_none(self):
        spec = {"all": ["invoice"], "any": ["acme", "acme corp"], "none": ["draft"]}
        self.assertTrue(matching.match_rule("acme invoice final", spec)[0])
        self.assertFalse(matching.match_rule("acme invoice draft", spec)[0])   # excluded
        self.assertFalse(matching.match_rule("invoice from someone", spec)[0])  # no any
        self.assertFalse(matching.match_rule("acme statement", spec)[0])        # no all

    def test_empty_spec_never_matches(self):
        self.assertEqual(matching.match_rule("anything", {}), (False, None))
        self.assertEqual(matching.match_rule("anything", {"all": [], "any": [], "none": []}),
                         (False, None))

    def test_none_only_is_not_a_catch_all(self):
        # Exclusions without any positive term must never match on their own.
        self.assertEqual(matching.match_rule("harmless text", {"none": ["secret"]}),
                         (False, None))

    def test_blank_terms_ignored(self):
        self.assertEqual(matching.match_rule("text", {"any": ["", "  "]}), (False, None))


if __name__ == "__main__":
    unittest.main()
