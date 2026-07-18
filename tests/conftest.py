"""Shared test setup.

Allows the suite to import `src.sorter` (which does `import fitz`) even when
PyMuPDF isn't installed in the local dev environment. On CI the real package is
present, so `setdefault` leaves it untouched and tests run against real PyMuPDF.
Tests that exercise PDF reading mock `fitz.open` explicitly, so the stub is only
a shim to make the import resolve.
"""
import sys
from unittest.mock import MagicMock

sys.modules.setdefault("fitz", MagicMock())
