import json
import os
import tempfile
from datetime import date, timedelta
from decimal import Decimal


def series(*closes, start=date(2026, 9, 1)):
    """Build a sorted series of consecutive days from plain numbers."""
    return [(start + timedelta(days=i), Decimal(str(c))) for i, c in enumerate(closes)]


def day(n, start=date(2026, 9, 1)):
    """The n-th day (0-based) of a series built by `series`."""
    return start + timedelta(days=n)


class TempFiles:
    """Mixin for unittest.TestCase: write throwaway input files."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)

    def write(self, name, content, encoding="utf-8"):
        path = os.path.join(self._tmp.name, name)
        if not isinstance(content, str):
            content = json.dumps(content)
        with open(path, "w", encoding=encoding, newline="") as f:
            f.write(content)
        return path
