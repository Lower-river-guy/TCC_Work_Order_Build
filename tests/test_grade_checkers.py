import unittest

from app.builder import build_work_orders
from app.grade_checkers import get_grade_checker
from pathlib import Path
import tempfile


class GradeCheckerTests(unittest.TestCase):
    def test_ryan_kolt_maps_dk_to_rk(self):
        checker = get_grade_checker("ryan-kolt")
        self.assertEqual(checker.label, "Ryan Kolt")
        self.assertEqual(checker.prefix, "RK-")
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            (root / "DK-Topo").mkdir()
            (root / "DK-Topo" / "notes.txt").write_text("x", encoding="utf-8")
            _payload, report = build_work_orders(root, checker.search, checker.replace)
        self.assertEqual(report.work_orders, ["RK-Topo"])

    def test_unknown_checker_rejected(self):
        with self.assertRaises(ValueError):
            get_grade_checker("missing")


if __name__ == "__main__":
    unittest.main()
