import os
import sys
import tempfile
import unittest

# Ensure src is in sys.path
src_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if src_path not in sys.path:
    sys.path.insert(0, src_path)

from token_diet.baseline import (
    extract_total_tokens,
    load_baseline,
    compare_tokens,
    check_budget,
)


class TestExtractTotalTokens(unittest.TestCase):
    def test_bare_int(self):
        self.assertEqual(extract_total_tokens(500), 500)
        self.assertEqual(extract_total_tokens(0), 0)

    def test_bare_float(self):
        self.assertEqual(extract_total_tokens(500.8), 500)
        self.assertEqual(extract_total_tokens(0.0), 0)

    def test_dict_total_tokens(self):
        self.assertEqual(extract_total_tokens({"total_tokens": 1200}), 1200)

    def test_dict_summary_total_tokens(self):
        self.assertEqual(extract_total_tokens({"summary": {"total_tokens": 850}}), 850)

    def test_none(self):
        self.assertIsNone(extract_total_tokens(None))

    def test_string(self):
        self.assertIsNone(extract_total_tokens("1200"))
        self.assertIsNone(extract_total_tokens(""))

    def test_negative_int(self):
        self.assertIsNone(extract_total_tokens(-1))
        self.assertIsNone(extract_total_tokens(-500))

    def test_nested_dict_non_numeric(self):
        self.assertIsNone(extract_total_tokens({"summary": {"total_tokens": "invalid"}}))
        self.assertIsNone(extract_total_tokens({"total_tokens": [1, 2, 3]}))

    def test_bool_rejected(self):
        self.assertIsNone(extract_total_tokens(True))
        self.assertIsNone(extract_total_tokens(False))
        self.assertIsNone(extract_total_tokens({"total_tokens": True}))
        self.assertIsNone(extract_total_tokens({"summary": {"total_tokens": False}}))


class TestLoadBaseline(unittest.TestCase):
    def test_valid_file(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = os.path.join(tmp_dir, "baseline.json")
            with open(path, "w", encoding="utf-8") as f:
                f.write('{"summary": {"total_tokens": 1500}}')
            res = load_baseline(path)
            self.assertEqual(
                res,
                {
                    "ok": True,
                    "tokens": 1500,
                    "path": path,
                    "error": None,
                },
            )

    def test_missing_file(self):
        path = "/path/to/definitely/non_existent_baseline_report.json"
        res = load_baseline(path)
        self.assertEqual(
            res,
            {
                "ok": False,
                "tokens": None,
                "path": path,
                "error": f"Baseline file not found: {path}",
            },
        )

    def test_invalid_json(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = os.path.join(tmp_dir, "broken.json")
            with open(path, "w", encoding="utf-8") as f:
                f.write('{"summary": {not valid json}')
            res = load_baseline(path)
            self.assertFalse(res["ok"])
            self.assertIsNone(res["tokens"])
            self.assertEqual(res["path"], path)
            self.assertIsInstance(res["error"], str)
            self.assertTrue(len(res["error"]) > 0)

    def test_valid_json_without_token_field(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = os.path.join(tmp_dir, "no_tokens.json")
            with open(path, "w", encoding="utf-8") as f:
                f.write('{"files": ["a", "b"], "status": "OK"}')
            res = load_baseline(path)
            self.assertFalse(res["ok"])
            self.assertIsNone(res["tokens"])
            self.assertEqual(res["path"], path)
            self.assertIsInstance(res["error"], str)
            self.assertTrue(len(res["error"]) > 0)


class TestCompareTokens(unittest.TestCase):
    def test_increase(self):
        res = compare_tokens(1100, 1000)
        self.assertEqual(
            res,
            {
                "baseline_tokens": 1000,
                "current_tokens": 1100,
                "delta_tokens": 100,
                "delta_percent": 10.0,
                "direction": "increase",
            },
        )

    def test_decrease(self):
        res = compare_tokens(900, 1000)
        self.assertEqual(
            res,
            {
                "baseline_tokens": 1000,
                "current_tokens": 900,
                "delta_tokens": -100,
                "delta_percent": -10.0,
                "direction": "decrease",
            },
        )

    def test_unchanged(self):
        res = compare_tokens(1000, 1000)
        self.assertEqual(
            res,
            {
                "baseline_tokens": 1000,
                "current_tokens": 1000,
                "delta_tokens": 0,
                "delta_percent": 0.0,
                "direction": "unchanged",
            },
        )

    def test_zero_baseline(self):
        res = compare_tokens(500, 0)
        self.assertEqual(
            res,
            {
                "baseline_tokens": 0,
                "current_tokens": 500,
                "delta_tokens": 500,
                "delta_percent": 0.0,
                "direction": "increase",
            },
        )

    def test_rounding_two_decimals(self):
        res = compare_tokens(301, 300)
        self.assertEqual(res["delta_tokens"], 1)
        self.assertEqual(res["delta_percent"], 0.33)
        self.assertEqual(res["direction"], "increase")


class TestCheckBudget(unittest.TestCase):
    def test_over_budget(self):
        res = check_budget(1100, 1000, 5.0)
        self.assertTrue(res["exceeded"])
        self.assertEqual(res["max_delta_percent"], 5.0)
        self.assertEqual(res["direction"], "increase")
        self.assertEqual(res["delta_percent"], 10.0)

    def test_exactly_at_budget(self):
        res = check_budget(1050, 1000, 5.0)
        self.assertFalse(res["exceeded"])
        self.assertEqual(res["max_delta_percent"], 5.0)
        self.assertEqual(res["direction"], "increase")
        self.assertEqual(res["delta_percent"], 5.0)

    def test_decrease_not_exceeded(self):
        res1 = check_budget(800, 1000, 5.0)
        self.assertFalse(res1["exceeded"])
        self.assertEqual(res1["direction"], "decrease")

        # Even with a negative budget, decrease passes
        res2 = check_budget(800, 1000, -25.0)
        self.assertFalse(res2["exceeded"])
        self.assertEqual(res2["direction"], "decrease")

    def test_zero_baseline_with_growth(self):
        res = check_budget(100, 0, 5.0)
        self.assertFalse(res["exceeded"])
        self.assertEqual(res["direction"], "increase")
        self.assertEqual(res["delta_percent"], 0.0)

    def test_negative_budget_with_any_increase(self):
        # Normal baseline with growth under negative budget fails
        res1 = check_budget(1001, 1000, -1.0)
        self.assertTrue(res1["exceeded"])

        # Zero baseline with growth under negative budget fails
        res2 = check_budget(100, 0, -1.0)
        self.assertTrue(res2["exceeded"])


if __name__ == "__main__":
    unittest.main()
