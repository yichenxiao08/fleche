"""The shipping report must preserve the owner's existing ratings and archives."""

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location(
    "shipping_review", SCRIPTS / "run_fewshot_v7_ship_review.py"
)
shipping = importlib.util.module_from_spec(spec)
spec.loader.exec_module(shipping)


class ShippingRatingAppendTests(unittest.TestCase):
    def test_new_replies_preserve_ratings_archive_and_contiguous_table(self):
        original = (
            "# Frozen fewshot-v7 rating sheet\n\n## Groq\n\n"
            "| Chain | Turn | Athlete | Coach | Acceptable | Reason | Invented |\n"
            "|---|---|---|---|---|---|---|\n"
            "| C01 | 1 | first | saved reply | Y | good | N |\n"
            "| C01 | 2 | second |  |  |  |  |\n\n"
            "## Gemini\n\n"
            "| Chain | Turn | Athlete | Coach | Acceptable | Reason | Invented |\n"
            "|---|---|---|---|---|---|---|\n\n"
            "# v6 comparison (archived)\n\nKeep this | exactly.\n"
        )
        saved = [
            {
                "id": "C01",
                "turns": [
                    {"turn": 1, "question": "first", "answer": "do not overwrite"},
                    {"turn": 2, "question": "second", "answer": "new | reply\nline two"},
                    {"turn": 3, "question": "third", "answer": "another reply"},
                ],
            }
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "docs").mkdir()
            path = root / "docs/rating_sheet.md"
            path.write_text(original, encoding="utf-8")
            with (
                patch.object(shipping.review, "ROOT", root),
                patch.object(
                    shipping.review, "rows", side_effect=lambda p: saved if p == "groq" else []
                ),
            ):
                shipping.append_new_replies()
                first = path.read_text(encoding="utf-8")
                shipping.append_new_replies()
                self.assertEqual(first, path.read_text(encoding="utf-8"))
        self.assertIn("| C01 | 1 | first | saved reply | Y | good | N |", first)
        self.assertIn("new \\| reply<br>line two", first)
        self.assertIn("| C01 | 3 | third | another reply |  |  |  |\n\n## Gemini", first)
        self.assertNotIn("| C01 | 4 |", first)
        self.assertEqual(
            original.split("\n# v6 comparison", 1)[1], first.split("\n# v6 comparison", 1)[1]
        )


if __name__ == "__main__":
    unittest.main()
