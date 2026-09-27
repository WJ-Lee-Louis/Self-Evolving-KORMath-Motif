"""The replacement Omni split contains self-contained benchmark questions."""

import hashlib
import json
from pathlib import Path
import re
import unittest

from gepa.core.data_loader import ListDataLoader

from motif_gepa_ko.bilingual import as_v2_gepa_data, load_v2_split
from motif_gepa_ko.sampling import OmniStratifiedBatchSampler, batch_bin_counts


ROOT = Path(__file__).resolve().parents[1] / "data"


class CleanOmniTests(unittest.TestCase):
    def test_splits_exclude_numbered_context_and_preserve_strata(self):
        data_dir = ROOT / "omni_v2_clean"
        manifest = json.loads((data_dir / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["excluded_context_dependency_source_rows"],
                         [134, 143, 153, 154, 287, 639, 717, 930])
        expected = {"train": 1000, "val": 50, "test_id": 760}
        seen = set()
        for split, count in expected.items():
            path = data_dir / f"{split}.jsonl"
            records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(len(records), count)
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),
                             manifest["splits"][split]["sha256"])
            ids = {record["id"] for record in records}
            self.assertFalse(seen & ids)
            seen.update(ids)
            for record in records:
                self.assertIsNone(re.search(
                    r"\b(?:problem|question|exercise)\s*\(?\s*\d+\b",
                    record["question_en"], re.I,
                ))
        self.assertEqual(len(seen), 1810)
        self.assertEqual(manifest["splits"]["val"]["difficulty_bin_counts"],
                         {"middle_3_5_to_6_0": 30, "high_gt_6_0": 10, "low_lt_3_5": 10})

    def test_english_train_loads_and_sampler_keeps_one_three_one(self):
        train = load_v2_split(ROOT / "omni_v2_clean", "train", "en")
        sampler = OmniStratifiedBatchSampler(train, seed=0)
        selected = sampler.next_minibatch_ids(ListDataLoader(as_v2_gepa_data(train)),
                                               type("State", (), {"i": 0})())
        self.assertEqual(sorted(batch_bin_counts(selected, train).values()), [1, 1, 3])


if __name__ == "__main__":
    unittest.main()
