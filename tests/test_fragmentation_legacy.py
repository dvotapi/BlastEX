"""Старые модели после переноса в legacy/ считают ровно как до PR 2."""
import json
import unittest
from pathlib import Path

from simulation.fragmentation.legacy import kuznetsov, kuzram, swebrec
from simulation.fragmentation.models import Calibration
from tests.test_fragmentation_kuzram import _inputs

GOLDEN = Path(__file__).parent / "fixtures" / "fragmentation_legacy_golden.json"
PREDICTORS = {
    "kuznetsov": kuznetsov.predict_kuznetsov,
    "kuzram": kuzram.predict_kuzram,
    "swebrec": swebrec.predict_swebrec,
}


class LegacyGoldenTests(unittest.TestCase):
    def test_numbers_match_pre_move_snapshot(self):
        data = json.loads(GOLDEN.read_text(encoding="utf-8"))
        for row in data["rows"]:
            with self.subTest(model=row["model"], case=row["case"], calibration=row["calibration"]):
                calibration = Calibration.from_dict(data["calibrations"][row["calibration"]])
                payload = PREDICTORS[row["model"]](_inputs(**data["cases"][row["case"]]), calibration).to_dict()
                for key in ("x20_mm", "x50_mm", "x80_mm", "oversize_pct", "curve"):
                    self.assertEqual(payload[key], row[key])
                self.assertEqual(payload["provenance"]["parameters"], row["parameters"])

    def test_ids_and_versions(self):
        self.assertEqual(
            (kuznetsov.MODEL_ID, kuzram.MODEL_ID, swebrec.MODEL_ID),
            ("kuznetsov_legacy", "kuzram_legacy", "swebrec_legacy"),
        )
        self.assertEqual({kuznetsov.MODEL_VERSION, kuzram.MODEL_VERSION, swebrec.MODEL_VERSION}, {"1.0.0"})


if __name__ == "__main__":
    unittest.main()
