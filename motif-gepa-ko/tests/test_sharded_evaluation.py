"""A full test split is covered once by independently resumable shards."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from motif_gepa_ko.artifacts import sha256_file
from motif_gepa_ko import bilingual
from motif_gepa_ko.settings import Settings
from motif_gepa_ko.sharded_evaluation import aggregate_shards_if_complete, evaluate_shard_run


class ShardedEvaluationTests(unittest.TestCase):
    def test_four_shards_cover_full_test_once(self):
        class FakeLM:
            def __init__(self, _settings):
                pass

            def __call__(self, prompt):
                return "FINAL_ANSWER: 1" if "EVOLVED" in prompt[0]["content"] else "FINAL_ANSWER: 0"

        with TemporaryDirectory() as directory:
            root = Path(directory)
            data_dir = root / "omni_v2_clean"
            run_dir = root / "runs" / "mock"
            data_dir.mkdir()
            run_dir.mkdir(parents=True)
            rows = [
                {"id": f"test-{idx}", "question_en": f"English {idx}",
                 "question_ko": f"Korean {idx}", "answer": "1"}
                for idx in range(8)
            ]
            (data_dir / "test_id.jsonl").write_text(
                "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
            )
            settings = Settings(api_key="fake")
            (run_dir / "run_status.json").write_text('{"phase":"complete"}', encoding="utf-8")
            (run_dir / "audit.json").write_text('{"passed":true}', encoding="utf-8")
            (run_dir / "summary.json").write_text('{"best_idx":6}', encoding="utf-8")
            (run_dir / "config.json").write_text(json.dumps({
                "dataset_version": "omni_v2_clean", "language": "ko",
                "model": settings.model, "base_url": settings.base_url,
                "temperature": settings.temperature,
                "max_output_tokens": settings.max_output_tokens,
            }), encoding="utf-8")
            (run_dir / "run_manifest.json").write_text(json.dumps({
                "code_sha256": {"motif_gepa_ko/bilingual.py": sha256_file(Path(bilingual.__file__))},
            }), encoding="utf-8")
            (run_dir / "seed_prompt.md").write_text("SEED\n", encoding="utf-8")
            (run_dir / "best_prompt.md").write_text("EVOLVED\n", encoding="utf-8")
            with patch("motif_gepa_ko.sharded_evaluation.MotifLM", FakeLM), patch(
                "motif_gepa_ko.sharded_evaluation.Settings.from_env", return_value=settings
            ):
                for index in range(4):
                    result = evaluate_shard_run(
                        data_dir=data_dir, runs_dir=root / "runs", run_id="mock",
                        language="ko", shard_index=index, shard_count=4,
                        max_api_calls=4,
                    )
                    self.assertEqual((result["selected"], result["completed"]), (2, 2))
            aggregate = aggregate_shards_if_complete(
                data_dir=data_dir, runs_dir=root / "runs", run_id="mock",
                language="ko", shard_count=4,
            )
            self.assertEqual(aggregate["completed"], 8)
            self.assertEqual((aggregate["seed_correct"], aggregate["best_correct"]), (0, 8))
            self.assertEqual(aggregate["question_ids"], [row["id"] for row in rows])
            self.assertTrue((run_dir / "heldout" / "test_id_shards_aggregate.json").exists())


if __name__ == "__main__":
    unittest.main()
