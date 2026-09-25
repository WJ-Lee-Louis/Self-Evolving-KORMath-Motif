"""Previously saved API responses can be replayed after a Modal retry."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from motif_gepa_ko.experiment import CountedLM, optimize_run
from motif_gepa_ko.settings import Settings


class RuntimeResumeTests(unittest.TestCase):
    def test_completed_calls_are_replayed_after_restart(self):
        class FakeModel:
            def __init__(self, fail=False):
                self.calls = 0
                self.fail = fail

            def __call__(self, _prompt):
                self.calls += 1
                if self.fail:
                    raise AssertionError("The provider must not be called for a saved response")
                return "정답: 1"

        prompt = [{"role": "system", "content": "풀이"}, {"role": "user", "content": "문제"}]
        with TemporaryDirectory() as directory:
            path = Path(directory) / "api_requests.jsonl"
            checkpoints = []
            first_model = FakeModel()
            first = CountedLM(
                first_model, 10, log_path=path, session_id="first",
                checkpoint_hook=lambda: checkpoints.append(1),
            )
            for _ in range(5):
                self.assertEqual(first(prompt), "정답: 1")
            self.assertEqual(first_model.calls, 5)
            self.assertEqual(len(checkpoints), 1)

            second_model = FakeModel(fail=True)
            resumed = CountedLM(second_model, 10, log_path=path, session_id="second")
            self.assertEqual(resumed(prompt), "정답: 1")
            self.assertEqual(second_model.calls, 0)
            self.assertEqual((resumed.provider_calls, resumed.replayed_calls), (0, 1))
            records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
            self.assertTrue(records[-1]["served_from_prior_session"])
            self.assertEqual(records[-1]["session_id"], "second")

    def test_seed_validation_continues_after_interrupted_process(self):
        class FakeModel:
            def __init__(self, interrupt=False):
                self.calls = 0
                self.interrupt = interrupt

            def __call__(self, prompt):
                if isinstance(prompt, str):
                    return "```\n새 프롬프트\n```"
                self.calls += 1
                if self.interrupt and self.calls == 2:
                    raise KeyboardInterrupt()
                return "정답: 1"

        with TemporaryDirectory() as directory:
            root = Path(directory)
            data_dir, prompts_dir, runs_dir = root / "omni_v1", root / "prompts", root / "runs"
            for path in (data_dir, prompts_dir, runs_dir):
                path.mkdir()
            train = [
                {"id": f"train-{i}", "source_subset": "OMNI-MATH", "question": f"train {i}",
                 "answer": "1", "difficulty": difficulty, "difficulty_bin": difficulty_bin}
                for i, (difficulty, difficulty_bin) in enumerate((
                    ("2.0", "low_lt_3_5"), ("5.0", "middle_3_5_to_6_0"),
                    ("5.0", "middle_3_5_to_6_0"), ("5.0", "middle_3_5_to_6_0"),
                    ("8.0", "high_gt_6_0"),
                ))
            ]
            val = [{"id": f"val-{i}", "question": f"val {i}", "answer": "1"}
                   for i in range(2)]
            for name, records in (("train", train), ("val", val)):
                (data_dir / f"{name}.jsonl").write_text(
                    "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
                    encoding="utf-8",
                )
            (prompts_dir / "seed_ko.md").write_text("initial prompt", encoding="utf-8")
            (prompts_dir / "reflection_ko.md").write_text("<curr_param> <side_info>", encoding="utf-8")
            kwargs = dict(
                data_dir=data_dir, prompts_dir=prompts_dir, runs_dir=runs_dir,
                run_id="resume-seed", max_metric_calls=2, max_api_calls=10,
                minibatch_size=5, seed=0,
            )
            first_model = FakeModel(interrupt=True)
            with patch("motif_gepa_ko.experiment.MotifLM", return_value=first_model), patch(
                "motif_gepa_ko.experiment.Settings.from_env", return_value=Settings(api_key="fake")
            ):
                with self.assertRaises(KeyboardInterrupt):
                    optimize_run(**kwargs)
            second_model = FakeModel()
            with patch("motif_gepa_ko.experiment.MotifLM", return_value=second_model), patch(
                "motif_gepa_ko.experiment.Settings.from_env", return_value=Settings(api_key="fake")
            ):
                summary = optimize_run(**kwargs)
            self.assertEqual(summary["seed_val_accuracy"], 1)
            self.assertEqual(second_model.calls, 1)
            records = [json.loads(line) for line in
                       (runs_dir / "resume-seed" / "api_requests.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertEqual(sum(row.get("served_from_prior_session", False) for row in records), 1)


if __name__ == "__main__":
    unittest.main()
