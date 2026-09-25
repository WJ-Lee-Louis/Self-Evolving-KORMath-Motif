"""Check the Omni 1:3:1 sampler and its GEPA connection without API calls."""

from collections import Counter
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from gepa.core.data_loader import ListDataLoader

from motif_gepa_ko.data import as_gepa_data
from motif_gepa_ko.experiment import EvolutionLog, optimize_run
from motif_gepa_ko.sampling import BIN_QUOTAS, OmniStratifiedBatchSampler, batch_bin_counts
from motif_gepa_ko.settings import Settings


def synthetic_rows() -> list[dict]:
    rows = []
    for label, count, difficulty in (
        ("low_lt_3_5", 6, "2.0"),
        ("middle_3_5_to_6_0", 12, "5.0"),
        ("high_gt_6_0", 4, "8.0"),
    ):
        start = len(rows)
        rows.extend({
            "id": f"omni-{start + index}",
            "source_subset": "OMNI-MATH",
            "question": f"{label} question {index}",
            "answer": "1",
            "difficulty": difficulty,
            "difficulty_bin": label,
        } for index in range(count))
    return rows


class OmniSamplingTests(unittest.TestCase):
    def test_every_batch_has_1_3_1_and_restarts_from_saved_iteration(self):
        rows = synthetic_rows()
        loader = ListDataLoader(as_gepa_data(rows))
        sampler = OmniStratifiedBatchSampler(rows, seed=17)
        batches = [sampler.next_minibatch_ids(loader, SimpleNamespace(i=i)) for i in range(4)]
        for batch in batches:
            self.assertEqual(batch_bin_counts(batch, rows), BIN_QUOTAS)
            self.assertEqual(len(set(batch)), 5)
        for label in BIN_QUOTAS:
            seen = [index for batch in batches for index in batch if rows[index]["difficulty_bin"] == label]
            self.assertEqual(len(seen), len(set(seen)))
        resumed = OmniStratifiedBatchSampler(rows, seed=17)
        self.assertEqual(
            resumed.next_minibatch_ids(loader, SimpleNamespace(i=3)),
            batches[3],
        )

    def test_optimize_uses_custom_sampler_and_archives_its_settings(self):
        rows = synthetic_rows()
        with TemporaryDirectory() as directory:
            root = Path(directory)
            data_dir, prompts_dir, runs_dir = root / "omni_v1", root / "prompts", root / "runs"
            for path in (data_dir, prompts_dir, runs_dir):
                path.mkdir()
            for name, records in (("train", rows), ("val", [{**rows[0], "id": "val-0"}])):
                (data_dir / f"{name}.jsonl").write_text(
                    "".join(json.dumps(record) + "\n" for record in records), encoding="utf-8"
                )
            (prompts_dir / "seed_ko.md").write_text("초기 프롬프트", encoding="utf-8")
            (prompts_dir / "reflection_ko.md").write_text("<curr_param> <side_info>", encoding="utf-8")

            class StopBeforeApi(Exception):
                pass

            with patch("motif_gepa_ko.experiment.Settings.from_env", return_value=Settings(api_key="fake")), patch(
                "motif_gepa_ko.experiment.gepa.optimize", side_effect=StopBeforeApi
            ) as optimize:
                with self.assertRaises(StopBeforeApi):
                    optimize_run(
                        data_dir=data_dir, prompts_dir=prompts_dir, runs_dir=runs_dir,
                        run_id="omni-sampler-test", max_metric_calls=2, max_api_calls=10,
                        minibatch_size=5, seed=17,
                    )
            kwargs = optimize.call_args.kwargs
            self.assertIsInstance(kwargs["batch_sampler"], OmniStratifiedBatchSampler)
            self.assertNotIn("reflection_minibatch_size", kwargs)
            config = json.loads((runs_dir / "omni-sampler-test" / "config.json").read_text(encoding="utf-8"))
            self.assertEqual(config["batch_sampling"]["quotas"], BIN_QUOTAS)
            manifest = json.loads((runs_dir / "omni-sampler-test" / "run_manifest.json").read_text(encoding="utf-8"))
            self.assertIn("motif_gepa_ko/sampling.py", manifest["code_sha256"])

    def test_minibatch_log_retains_question_difficulties(self):
        rows = synthetic_rows()
        with TemporaryDirectory() as directory:
            log = EvolutionLog(
                Path(directory), [row["id"] for row in rows], ["val-0"],
                train_difficulty_bins={row["id"]: row["difficulty_bin"] for row in rows},
            )
            ids = OmniStratifiedBatchSampler(rows, 0).next_minibatch_ids(
                ListDataLoader(as_gepa_data(rows)), SimpleNamespace(i=0)
            )
            log.on_minibatch_sampled({"iteration": 1, "minibatch_ids": ids})
            record = json.loads((Path(directory) / "events.jsonl").read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(
                dict(Counter(record["difficulty_bins_by_question_id"].values())),
                BIN_QUOTAS,
            )

    def test_gepa_runs_with_stratified_batches_and_fake_model(self):
        class FakeLM:
            def __init__(self, _settings):
                pass

            def __call__(self, prompt):
                if isinstance(prompt, str):
                    return "```\nIMPROVED\n```"
                system = next((message["content"] for message in prompt if message["role"] == "system"), "")
                return "정답: 1" if "IMPROVED" in system else "정답: 0"

        rows = synthetic_rows()
        with TemporaryDirectory() as directory:
            root = Path(directory)
            data_dir, prompts_dir, runs_dir = root / "omni_v1", root / "prompts", root / "runs"
            for path in (data_dir, prompts_dir, runs_dir):
                path.mkdir()
            val = [{**row, "id": f"val-{index}", "question": f"val question {index}"}
                   for index, row in enumerate(rows[:2])]
            for name, records in (("train", rows), ("val", val)):
                (data_dir / f"{name}.jsonl").write_text(
                    "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
                    encoding="utf-8",
                )
            (prompts_dir / "seed_ko.md").write_text("SEED", encoding="utf-8")
            (prompts_dir / "reflection_ko.md").write_text("<curr_param> <side_info>", encoding="utf-8")
            with patch("motif_gepa_ko.experiment.MotifLM", FakeLM), patch(
                "motif_gepa_ko.experiment.Settings.from_env", return_value=Settings(api_key="fake")
            ):
                summary = optimize_run(
                    data_dir=data_dir, prompts_dir=prompts_dir, runs_dir=runs_dir,
                    run_id="omni-fake-run", max_metric_calls=16, max_api_calls=30,
                    minibatch_size=5, seed=0,
                )
            events = [json.loads(line) for line in
                      (runs_dir / "omni-fake-run" / "events.jsonl").read_text(encoding="utf-8").splitlines()]
            minibatches = [event for event in events if event["event"] == "minibatch"]
            self.assertTrue(minibatches)
            for event in minibatches:
                self.assertEqual(
                    dict(Counter(event["difficulty_bins_by_question_id"].values())),
                    BIN_QUOTAS,
                )
            self.assertGreaterEqual(summary["best_val_accuracy"], summary["seed_val_accuracy"])


if __name__ == "__main__":
    unittest.main()
