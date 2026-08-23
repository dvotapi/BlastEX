import unittest

from intelligence.datasets.builder import build_sample
from intelligence.datasets.validation import is_closed_blast
from tests.dataset_fixtures import closed_design


class DatasetValidationTests(unittest.TestCase):
    def test_closed_complete_sample_is_accepted(self):
        design = closed_design()
        closed, reasons = is_closed_blast(design)
        self.assertTrue(closed, reasons)
        sample = build_sample(design, site_id="quarry-1")
        self.assertTrue(sample.validation.ok, sample.validation.reasons)
        self.assertIn("FRAGMENTATION", sample.validation.complete_target_groups)
        self.assertEqual(sample.provenance["source_blast_id"], "blast-closed")
        self.assertEqual(sample.provenance["site_id"], "quarry-1")
        self.assertEqual(sample.provenance["feature_schema_version"], sample.feature_schema_version)

    def test_missing_result_is_rejected(self):
        design = closed_design()
        design.blast_result = None
        closed, reasons = is_closed_blast(design)
        self.assertFalse(closed)
        self.assertTrue(any("BlastResult" in item for item in reasons))
        self.assertFalse(build_sample(design, site_id="quarry-1").validation.ok)

    def test_missing_execution_is_rejected(self):
        design = closed_design()
        design.as_drilled_holes = []
        design.as_charged_holes = []
        design.as_fired_holes = []
        closed, reasons = is_closed_blast(design)
        self.assertFalse(closed)
        self.assertTrue(any("исполнения" in item for item in reasons))

    def test_empty_provenance_is_rejected(self):
        design = closed_design()
        design.blast_result.provenance.source = ""
        design.blast_result.provenance.method = ""
        design.blast_result.provenance.timestamp = ""
        closed, reasons = is_closed_blast(design)
        self.assertFalse(closed)
        self.assertTrue(any("происхождение" in item for item in reasons))

    def test_empty_site_id_is_rejected(self):
        sample = build_sample(closed_design(), site_id="")
        self.assertFalse(sample.validation.ok)
        self.assertTrue(any("site_id" in item for item in sample.validation.reasons))


if __name__ == "__main__":
    unittest.main()
