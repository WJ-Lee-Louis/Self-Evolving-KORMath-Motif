"""Audit the callback records without making model calls."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from motif_gepa_ko.artifacts import audit_saved_run
from motif_gepa_ko.experiment import EvolutionLog, optimize_run
from motif_gepa_ko.settings import Settings


class EvolutionLogTests(unittest.TestCase):
    def test_error_during_proposal_is_not_recorded_as_rejection(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            log = EvolutionLog(root, ["train-a"], ["val-a"])
            log.iteration_ids[1] = "interrupted-trial"
            log.on_proposal_end({
                "iteration": 1, "new_instructions": {"system_prompt": "새 지침"},
                "prompts": {}, "raw_lm_outputs": {},
            })
            log.on_error({"iteration": 1, "exception": TimeoutError("timeout"), "will_continue": False})
            log.on_iteration_end({
                "iteration": 1, "proposal_accepted": False,
                "state": SimpleNamespace(
                    full_program_trace=[{"iteration_id": "interrupted-trial", "selected_program_candidate": 0}],
                    total_num_evals=1, program_candidates=[{"system_prompt": "초기"}],
                    parent_program_for_candidate=[[None]], iteration_ids_by_candidate_idx=["seed"],
                    prog_candidate_val_subscores=[{0: 1.0}],
                    get_program_average_val_subset=lambda _idx: (1.0, 1),
                ),
            })
            attempt = json.loads((root / "iterations" / "interrupted-trial" / "attempt.json").read_text(encoding="utf-8"))
            self.assertEqual(attempt["decision"], "interrupted")
            self.assertEqual(attempt["error_type"], "TimeoutError")
            self.assertEqual(attempt["proposals"][0]["decision"], "evaluation_incomplete")

    def test_validation_and_rejection_are_distinct(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            checkpoints = []
            log = EvolutionLog(root, ["train-a", "train-b"], ["val-a", "val-b"], lambda: checkpoints.append(1))
            log.on_valset_evaluated({
                "iteration": 0, "candidate_idx": 0, "candidate": {"system_prompt": "초기"},
                "scores_by_val_id": {0: 1.0, 1: 0.0}, "average_score": 0.5,
                "num_examples_evaluated": 2, "total_valset_size": 2,
                "parent_ids": [], "is_best_program": True, "outputs_by_val_id": None,
            })
            log.on_minibatch_sampled({"iteration": 1, "minibatch_ids": [1], "trainset_size": 2})
            log.on_proposal_end({"iteration": 1, "new_instructions": {"system_prompt": "새 지침"},
                                 "prompts": {"system_prompt": "반성 입력"},
                                 "raw_lm_outputs": {"system_prompt": "새 지침"}})
            log.on_candidate_rejected({"iteration": 1, "old_score": 1.0, "new_score": 0.0,
                                       "reason": "worse minibatch score"})
            log.on_iteration_end({"iteration": 1, "proposal_accepted": False,
                                  "state": SimpleNamespace(full_program_trace=[{
                                      "iteration_id": "trial-1", "proposal_accepted": False,
                                  }], total_num_evals=3,
                                  program_candidates=[{"system_prompt": "초기"}],
                                  parent_program_for_candidate=[[None]],
                                  iteration_ids_by_candidate_idx=["seed"],
                                  prog_candidate_val_subscores=[{0: 1.0, 1: 0.0}],
                                  get_program_average_val_subset=lambda _idx: (0.5, 2))})
            log.on_state_saved({"iteration": 2, "run_dir": str(root)})

            validations = [json.loads(line) for line in (root / "validation.jsonl").read_text(encoding="utf-8").splitlines()]
            events = [json.loads(line) for line in (root / "events.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertEqual(validations[0]["scores_by_question_id"], {"val-a": 1.0, "val-b": 0.0})
            self.assertEqual([e["event"] for e in events], ["validation", "minibatch", "proposal", "rejected", "iteration_end", "state_saved"])
            self.assertEqual(events[1]["train_ids"], ["train-b"])
            self.assertEqual(events[2]["prompts"]["system_prompt"], "반성 입력")
            self.assertEqual(checkpoints, [1, 1])
            self.assertTrue((root / "iterations" / "trial-1" / "trace.json").exists())

    def test_gepa_run_records_accepted_candidate_and_val_scores(self):
        class FakeLM:
            def __init__(self, _settings):
                pass

            def __call__(self, prompt):
                if isinstance(prompt, str):
                    return "```\nIMPROVED\n```"
                system = next((message["content"] for message in prompt if message["role"] == "system"), "")
                return "\uc815\ub2f5: 1" if "IMPROVED" in system else "\uc815\ub2f5: 0"

        with TemporaryDirectory() as directory:
            root = Path(directory)
            data_dir, prompts_dir, runs_dir = root / "data", root / "prompts", root / "runs"
            for path in (data_dir, prompts_dir, runs_dir):
                path.mkdir()
            for split, size in (("train", 3), ("val", 2)):
                rows = [{"id": f"{split}-{i}", "question": f"{split} question {i}", "answer": "1"}
                        for i in range(size)]
                (data_dir / f"{split}.jsonl").write_text(
                    "\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
            (prompts_dir / "seed_ko.md").write_text("SEED", encoding="utf-8")
            (prompts_dir / "reflection_ko.md").write_text("<curr_param>\n<side_info>", encoding="utf-8")

            with patch("motif_gepa_ko.experiment.MotifLM", FakeLM), patch(
                "motif_gepa_ko.experiment.Settings.from_env", return_value=Settings(api_key="fake")
            ):
                summary = optimize_run(data_dir=data_dir, prompts_dir=prompts_dir,
                                       runs_dir=runs_dir, run_id="mock", max_metric_calls=6,
                                       max_api_calls=20, minibatch_size=1)
                resumed = optimize_run(data_dir=data_dir, prompts_dir=prompts_dir,
                                       runs_dir=runs_dir, run_id="mock", max_metric_calls=6,
                                       max_api_calls=20, minibatch_size=1)

            run_dir = runs_dir / "mock"
            self.assertEqual(resumed["best_val_accuracy"], summary["best_val_accuracy"])
            validations = [json.loads(line) for line in (run_dir / "validation.jsonl").read_text(encoding="utf-8").splitlines()]
            events = [json.loads(line) for line in (run_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertEqual(summary["seed_val_accuracy"], 0)
            self.assertEqual(summary["best_val_accuracy"], 1)
            self.assertEqual({row["candidate_idx"] for row in validations}, {0, 1})
            self.assertEqual(set(validations[1]["scores_by_question_id"]), {"val-0", "val-1"})
            self.assertIn("proposal", {event["event"] for event in events})
            self.assertIn("accepted", {event["event"] for event in events})
            self.assertTrue((run_dir / "iterations" / "seed" / "val_scores.json").exists())
            accepted_dirs = [path for path in (run_dir / "iterations").iterdir() if path.name != "seed"]
            self.assertEqual(len(accepted_dirs), 1)
            self.assertTrue((accepted_dirs[0] / "trace.json").exists())
            self.assertTrue((accepted_dirs[0] / "val_scores.json").exists())
            self.assertTrue((accepted_dirs[0] / "reflective_dataset.json").exists(),
                            f"files={list(accepted_dirs[0].iterdir())}; all={list(run_dir.rglob('reflective_dataset.json'))}")
            self.assertTrue((run_dir / "evolution.md").exists())
            manifest = json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))
            lineage = json.loads((run_dir / "lineage.json").read_text(encoding="utf-8"))
            attempt = json.loads((accepted_dirs[0] / "attempt.json").read_text(encoding="utf-8"))
            audit = json.loads((run_dir / "audit.json").read_text(encoding="utf-8"))
            self.assertEqual(lineage["nodes"][1]["parent_candidate_indices"], [0])
            self.assertEqual(lineage["edges"], [{"parent_candidate_idx": 0, "child_candidate_idx": 1}])
            self.assertEqual(lineage["proposal_nodes"][0]["child_candidate_idx"], 1)
            self.assertEqual({edge["relationship"] for edge in lineage["proposal_edges"]},
                             {"parent_proposed", "accepted_as"})
            self.assertEqual(attempt["selected_parent_candidate_idx"], 0)
            self.assertEqual(attempt["proposals"][0]["decision"], "accepted")
            self.assertEqual(attempt["proposals"][0]["val_accuracy"], 1)
            self.assertEqual(attempt["train_tasks"][0]["train_question_ids"], ["train-2"])
            self.assertTrue(audit["passed"])
            self.assertTrue(audit_saved_run(run_dir)["passed"])
            self.assertEqual(set(manifest["inputs"]), {"train", "val", "seed_prompt", "reflection_template"})
            self.assertIn("motif_gepa_ko/experiment.py", manifest["code_snapshots"])
            self.assertTrue((run_dir / manifest["code_snapshots"]["gepa/core/engine.py"]["path"]).exists())
            self.assertNotIn("fake", json.dumps(manifest))
            self.assertTrue((run_dir / "attempt_timeline.md").exists())
            self.assertTrue((run_dir / "candidates.csv").exists())
            self.assertIn("C0 --> P0", (run_dir / "proposal_graph.md").read_text(encoding="utf-8"))
            api_requests = [json.loads(line) for line in (run_dir / "api_requests.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertEqual(len(api_requests), summary["logical_api_calls_this_process"])
            self.assertEqual({row["role"] for row in api_requests}, {"task", "reflection"})
            self.assertTrue(all(row["status"] == "success" for row in api_requests))
            task_requests = [row for row in api_requests if row["role"] == "task"]
            self.assertTrue(all(row["question_matches"] for row in task_requests))
            self.assertTrue(all(row["system_prompt_sha256"] for row in task_requests))
            tampered = validations[:]
            tampered[1] = {**tampered[1], "average_score": 0.25}
            (run_dir / "validation.jsonl").write_text(
                "\n".join(json.dumps(row) for row in tampered) + "\n", encoding="utf-8")
            failed_audit = audit_saved_run(run_dir)
            self.assertFalse(failed_audit["passed"])
            self.assertTrue(any("검증 평균" in issue for issue in failed_audit["issues"]))

    def test_rejected_proposal_keeps_trace_without_validation(self):
        class FakeLM:
            def __init__(self, _settings):
                pass

            def __call__(self, prompt):
                if isinstance(prompt, str):
                    return "```\nWORSE\n```"
                system = next((message["content"] for message in prompt if message["role"] == "system"), "")
                return "\uc815\ub2f5: 2" if "WORSE" in system else "\uc815\ub2f5: 1"

        with TemporaryDirectory() as directory:
            root = Path(directory)
            data_dir, prompts_dir, runs_dir = root / "data", root / "prompts", root / "runs"
            for path in (data_dir, prompts_dir, runs_dir):
                path.mkdir()
            for split, size in (("train", 3), ("val", 2)):
                rows = [{"id": f"{split}-{i}", "question": f"{split} question {i}",
                         "answer": "0" if split == "train" and i == 2 else "1"}
                        for i in range(size)]
                (data_dir / f"{split}.jsonl").write_text(
                    "\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
            (prompts_dir / "seed_ko.md").write_text("SEED", encoding="utf-8")
            (prompts_dir / "reflection_ko.md").write_text("<curr_param>\n<side_info>", encoding="utf-8")

            with patch("motif_gepa_ko.experiment.MotifLM", FakeLM), patch(
                "motif_gepa_ko.experiment.Settings.from_env", return_value=Settings(api_key="fake")
            ):
                summary = optimize_run(data_dir=data_dir, prompts_dir=prompts_dir,
                                       runs_dir=runs_dir, run_id="rejected", max_metric_calls=8,
                                       max_api_calls=20, minibatch_size=3)

            run_dir = runs_dir / "rejected"
            validations = [json.loads(line) for line in (run_dir / "validation.jsonl").read_text(encoding="utf-8").splitlines()]
            events = [json.loads(line) for line in (run_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertEqual(summary["num_candidates"], 1)
            self.assertEqual([row["candidate_idx"] for row in validations], [0])
            self.assertIn("rejected", {event["event"] for event in events})
            proposal_dirs = [path for path in (run_dir / "iterations").iterdir() if path.name != "seed"]
            self.assertEqual(len(proposal_dirs), 1)
            self.assertEqual(json.loads((proposal_dirs[0] / "meta.json").read_text(encoding="utf-8"))["accepted"], False)
            self.assertTrue((proposal_dirs[0] / "trace.json").exists(),
                            f"files={list(proposal_dirs[0].iterdir())}; events={events}")
            self.assertFalse((proposal_dirs[0] / "val_scores.json").exists())
            attempt = json.loads((proposal_dirs[0] / "attempt.json").read_text(encoding="utf-8"))
            self.assertEqual(attempt["decision"], "rejected")
            self.assertEqual(attempt["proposals"][0]["parent_candidate_idx"], 0)
            self.assertIsNone(attempt["proposals"][0]["val_accuracy"])
            self.assertEqual(attempt["train_tasks"][0]["train_question_ids"], ["train-2", "train-0", "train-1"])
            self.assertTrue(attempt["rejections"])
            lineage = json.loads((run_dir / "lineage.json").read_text(encoding="utf-8"))
            self.assertEqual(lineage["proposal_nodes"][0]["parent_candidate_idx"], 0)
            self.assertIsNone(lineage["proposal_nodes"][0]["child_candidate_idx"])
            self.assertEqual([edge["relationship"] for edge in lineage["proposal_edges"]], ["parent_proposed"])
            self.assertIn("거절", (run_dir / "proposal_graph.md").read_text(encoding="utf-8"))
            self.assertIn("WORSE", (run_dir / "attempt_timeline.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
