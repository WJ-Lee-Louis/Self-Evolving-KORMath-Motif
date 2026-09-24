"""Held-out comparisons retain enough context to audit each paired answer."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from motif_gepa_ko.artifacts import sha256_file
from motif_gepa_ko.experiment import evaluate_run
from motif_gepa_ko import scoring
from motif_gepa_ko.settings import Settings


class EvaluationArtifactTests(unittest.TestCase):
    def test_paired_rows_metadata_and_resume(self):
        class FakeLM:
            def __init__(self, _settings):
                pass

            def __call__(self, prompt):
                return "\uc815\ub2f5: 1" if "IMPROVED" in prompt[0]["content"] else "\uc815\ub2f5: 0"

        with TemporaryDirectory() as directory:
            root = Path(directory)
            data_dir = root / "data"
            run_dir = root / "runs" / "mock"
            data_dir.mkdir()
            run_dir.mkdir(parents=True)
            settings = Settings(api_key="fake")
            (run_dir / "summary.json").write_text("{}", encoding="utf-8")
            (run_dir / "config.json").write_text(json.dumps({
                "model": settings.model, "base_url": settings.base_url,
                "temperature": settings.temperature, "max_output_tokens": settings.max_output_tokens,
            }), encoding="utf-8")
            (run_dir / "run_manifest.json").write_text(json.dumps({
                "code_sha256": {"motif_gepa_ko/scoring.py": sha256_file(Path(scoring.__file__))},
            }), encoding="utf-8")
            (run_dir / "seed_prompt.md").write_text("SEED\n", encoding="utf-8")
            (run_dir / "best_prompt.md").write_text("IMPROVED\n", encoding="utf-8")
            rows = [{"id": f"test-{idx}", "question": f"problem {idx}", "answer": "1",
                     "source_subset": "GSM8K", "source_row_index": idx} for idx in range(2)]
            (data_dir / "test_id.jsonl").write_text(
                "\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
            with patch("motif_gepa_ko.experiment.MotifLM", FakeLM), patch(
                "motif_gepa_ko.experiment.Settings.from_env", return_value=settings
            ):
                first = evaluate_run(data_dir=data_dir, runs_dir=root / "runs", run_id="mock",
                                     split="test_id", limit=1, max_api_calls=2)
                full = evaluate_run(data_dir=data_dir, runs_dir=root / "runs", run_id="mock",
                                    split="test_id", limit=0, max_api_calls=2)
            self.assertEqual((first["completed"], full["completed"]), (1, 2))
            self.assertEqual(full["question_ids"], ["test-0", "test-1"])
            self.assertEqual(full["best_accuracy"], 1)
            paired = [json.loads(line) for line in (run_dir / "test_id_paired.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertEqual(len(paired), 2)
            self.assertEqual(paired[1]["question"], "problem 1")
            self.assertEqual(paired[1]["source_row_index"], 1)
            metadata = json.loads((run_dir / "test_id_metadata.json").read_text(encoding="utf-8"))
            self.assertIn("dataset_sha256", metadata)
            self.assertNotIn("fake", json.dumps(metadata))
            sessions = [json.loads(line) for line in (run_dir / "test_id_sessions.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertEqual([item["event"] for item in sessions], ["started", "finished", "started", "finished"])
            self.assertTrue((run_dir / "inputs" / "test_id.jsonl").exists())
            requests = [json.loads(line) for line in (run_dir / "test_id_api_requests.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertEqual(len(requests), 4)
            self.assertEqual([item["prompt_variant"] for item in requests], ["seed", "best", "seed", "best"])
            self.assertEqual([item["question_id"] for item in requests], ["test-0", "test-0", "test-1", "test-1"])


if __name__ == "__main__":
    unittest.main()
