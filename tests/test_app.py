import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from app.server import ROOT, create_app
from app.csv_store import CsvStore, REVIEW_COLUMNS


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "04_natural.csv"
        shutil.copy2(ROOT / "input" / "04_natural.csv", self.path)
        self.original_bytes = self.path.read_bytes()
        self.original = pd.read_csv(self.path, encoding="utf-8-sig", dtype=str, keep_default_na=False)
        self.app = create_app(self.path, backup_count=2, backup_interval=0)
        self.client = self.app.test_client()
        self.store = self.app.extensions["csv_store"]
        self.id = self.original.iloc[0]["instance_id"]
        self.url = "/api/items/" + self.id

    def test_read_and_diff(self):
        with self.client.get("/") as response:
            self.assertEqual(response.status_code, 200)
        self.assertEqual(len(self.client.get("/api/items").json), len(self.original))
        item = self.client.get(self.url).json
        for side in ("original", "rewritten"):
            self.assertEqual("".join(part[side] for part in item["diff"]), item[side + "_sentence"])
        self.assertTrue(all(self.original[key].nunique(dropna=False) > 1 for key in item["reference"]))
        self.assertNotIn("rewrite_rule_id", item["reference"])
        self.assertEqual(self.path.read_bytes(), self.original_bytes)

    def test_roundtrip_preserves_every_original_cell(self):
        comment = '日本語, "引用"\n次の行 <script>alert(1)</script>'
        self.assertEqual(self.client.put(self.url + "/review", json={"meaning_preserved": "NG"}).status_code, 200)
        result = self.client.put(self.url + "/review", json={"naturalness": "OK", "review_comment": comment})
        self.assertTrue(result.json["saved"])
        self.assertEqual(result.json["item"]["meaning_preserved"], "NG")
        self.assertTrue(result.json["item"]["reviewed_at"])
        frame = pd.read_csv(self.path, encoding="utf-8-sig", dtype=str, keep_default_na=False)
        pd.testing.assert_frame_equal(frame[self.original.columns], self.original)
        self.assertEqual(list(frame.columns[-4:]), REVIEW_COLUMNS)
        self.assertTrue(self.path.read_bytes().startswith(b"\xef\xbb\xbf"))
        self.assertEqual(CsvStore(self.path).detail(self.id)["review_comment"], comment)
        progress = self.client.get("/api/progress").json
        self.assertEqual(progress["reviewed"], 1)
        self.assertEqual(progress["any_ng"], 1)
        self.client.put(self.url + "/review", json={"meaning_preserved": ""})
        self.assertEqual(self.client.get("/api/progress").json["reviewed"], 0)

    def test_backup_original_and_retention(self):
        self.store.update(self.id, {"meaning_preserved": "OK"})
        backups = sorted((self.path.parent / ".backup").glob("*.csv"))
        self.assertEqual(backups[0].read_bytes(), self.original_bytes)
        for value in ("NG", "OK", "NG"):
            self.store.update(self.id, {"meaning_preserved": value})
        self.assertEqual(len(list((self.path.parent / ".backup").glob("*.csv"))), 2)

    def test_failed_replace_keeps_disk_and_memory(self):
        before = self.store.detail(self.id)
        with patch("app.csv_store.os.replace", side_effect=PermissionError("File locked")):
            response = self.client.put(self.url + "/review", json={"meaning_preserved": "OK"})
        self.assertEqual(response.status_code, 500)
        self.assertEqual(self.path.read_bytes(), self.original_bytes)
        self.assertEqual(self.store.detail(self.id), before)
        self.assertFalse(list(self.path.parent.glob("*.tmp")))
        self.assertEqual(self.client.put(self.url + "/review", json={"meaning_preserved": "OK"}).status_code, 200)

    def test_validation(self):
        for changes in ({"meaning_preserved": "maybe"}, {"naturalness": None}, {"review_comment": 1},
                        {"original_sentence": "changed"}, [], {}, None):
            response = self.client.put(self.url + "/review", json=changes)
            self.assertIn(response.status_code, (400, 415))
        self.assertEqual(self.client.get("/api/items/missing").status_code, 404)
        self.assertEqual(self.client.put("/api/items/missing/review", json={"naturalness": "OK"}).status_code, 404)
        self.assertEqual(self.path.read_bytes(), self.original_bytes)

    def test_reference_columns_are_dynamic(self):
        frame = self.original.copy()
        frame.loc[0, "rewrite_rule_id"] = "different"
        frame["focus_surface"] = "constant"
        frame.to_csv(self.path, index=False, encoding="utf-8-sig")
        reference = CsvStore(self.path).detail(self.id)["reference"]
        self.assertIn("rewrite_rule_id", reference)
        self.assertNotIn("focus_surface", reference)

    def test_duplicate_ids_rejected(self):
        frame = self.original.copy()
        frame.loc[1, "instance_id"] = self.id
        frame.to_csv(self.path, index=False, encoding="utf-8-sig")
        with self.assertRaises(ValueError):
            CsvStore(self.path)


if __name__ == "__main__":
    unittest.main()
