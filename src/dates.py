"""Extract a date printed in a document's text, dependency-free.

Date foldering (Feature B) defaults to a date found *in the document's content*
rather than the embedded PDF metadata: metadata (creation date/author) is
routinely wrong once a file has been emailed or re-saved, which is the same reason
filename renaming derives names from content. So this extractor is the load-bearing
path for foldering, and it uses only the stdlib — no dateparser/dateutil dependency
to keep the Windows build small.

Scope is deliberately a small set of common formats, first (earliest in the text)
valid date wins:

* ISO            ``2024-03-01``
* numeric        ``01/03/2024`` / ``1-3-24``  (day/month order by ``dayfirst``)
* day month year ``1 March 2024`` / ``1 Mar 2024``
* month day year ``March 1, 2024`` / ``Mar 1 2024``
* month year     ``Mar 2024``  (day defaults to the 1st)

Ambiguity: purely numeric dates like ``03/04/2024`` can't be disambiguated from the
text alone, so the day/month order follows the ``dayfirst`` flag (default ``True``,
i.e. day-first / European). A locale/preference wires into this later.
"""
import re
from datetime import date

_MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9, "oct": 10,
    "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}
# Longest names first so 'march' isn't shadowed by 'mar' in the alternation.
_MONTH_ALT = "|".join(sorted(_MONTHS, key=len, reverse=True))

_ISO = re.compile(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b")
# Only '/' and '-' as separators (never '.', to avoid matching version numbers
# like 1.2.3). The 1-2 digit first group keeps this from colliding with ISO.
_NUMERIC = re.compile(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})\b")
_DMY = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(" + _MONTH_ALT + r")\.?,?\s+(\d{4})\b", re.I)
_MDY = re.compile(r"\b(" + _MONTH_ALT + r")\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})\b", re.I)
_MY = re.compile(r"\b(" + _MONTH_ALT + r")\.?,?\s+(\d{4})\b", re.I)


def extract_date(text, dayfirst=True):
    """Return the first valid date found in ``text`` as a ``datetime.date``, or
    ``None`` if no recognizable date is present.

    "First" means earliest position in the text; a candidate whose numbers don't
    form a real calendar date (e.g. ``31/02``) is skipped in favour of the next.
    """
    if not text:
        return None

    candidates = []  # (start_index, year, month, day)

    for m in _ISO.finditer(text):
        candidates.append((m.start(), int(m.group(1)), int(m.group(2)), int(m.group(3))))

    for m in _NUMERIC.finditer(text):
        first, second, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if year < 100:
            year += 2000
        day, month = (first, second) if dayfirst else (second, first)
        candidates.append((m.start(), year, month, day))

    for m in _DMY.finditer(text):
        candidates.append((m.start(), int(m.group(3)), _MONTHS[m.group(2).lower()], int(m.group(1))))

    for m in _MDY.finditer(text):
        candidates.append((m.start(), int(m.group(3)), _MONTHS[m.group(1).lower()], int(m.group(2))))

    for m in _MY.finditer(text):
        candidates.append((m.start(), int(m.group(2)), _MONTHS[m.group(1).lower()], 1))

    for _start, year, month, day in sorted(candidates, key=lambda c: c[0]):
        try:
            return date(year, month, day)
        except ValueError:
            continue
    return None
