"""Unit tests for the content date extractor (src.dates)."""
import unittest
from datetime import date

from src import dates


class TestExtractDate(unittest.TestCase):
    def test_iso(self):
        self.assertEqual(dates.extract_date("dated 2024-03-01 here"), date(2024, 3, 1))

    def test_numeric_dayfirst(self):
        self.assertEqual(dates.extract_date("on 01/03/2024"), date(2024, 3, 1))

    def test_numeric_monthfirst(self):
        self.assertEqual(dates.extract_date("on 01/03/2024", dayfirst=False), date(2024, 1, 3))

    def test_numeric_two_digit_year(self):
        self.assertEqual(dates.extract_date("dated 1-3-24"), date(2024, 3, 1))

    def test_day_month_year_full(self):
        self.assertEqual(dates.extract_date("issued 1 March 2024"), date(2024, 3, 1))

    def test_day_month_year_abbrev_with_ordinal(self):
        self.assertEqual(dates.extract_date("on 21st Mar 2024"), date(2024, 3, 21))

    def test_month_day_year(self):
        self.assertEqual(dates.extract_date("March 1, 2024"), date(2024, 3, 1))

    def test_month_year_defaults_to_first(self):
        self.assertEqual(dates.extract_date("statement for Mar 2024"), date(2024, 3, 1))

    def test_first_date_in_text_wins(self):
        self.assertEqual(dates.extract_date("printed 2023-12-31, due 2024-06-30"),
                         date(2023, 12, 31))

    def test_invalid_date_skipped_for_next(self):
        # 31/02 isn't a real date; the extractor moves on to the valid one.
        self.assertEqual(dates.extract_date("31/02/2024 or 05/04/2024"), date(2024, 4, 5))

    def test_no_date(self):
        self.assertIsNone(dates.extract_date("no dates here at all"))

    def test_empty(self):
        self.assertIsNone(dates.extract_date(""))

    def test_does_not_match_version_numbers(self):
        # Dotted separators must not be read as dates (avoids 1.2.3 -> a date).
        self.assertIsNone(dates.extract_date("version 1.2.3 of the app"))

    def test_march_not_shadowed_by_mar(self):
        self.assertEqual(dates.extract_date("1 March 2024"), date(2024, 3, 1))


if __name__ == "__main__":
    unittest.main()
