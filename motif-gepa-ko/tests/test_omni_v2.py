"""Verify paired bilingual splits and train-only reference feedback."""

from collections import Counter
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from motif_gepa_ko.bilingual import (
    BilingualMathEvaluator, as_v2_gepa_data, load_v2_split, score_v2,
)
from motif_gepa_ko.translation import (
    _translate_plain_chunks, _translate_prose_segments, mask_math,
    quality_flags, restore_math,
)
from motif_gepa_ko.experiment import optimize_run
from motif_gepa_ko.settings import Settings
from scripts.review_omni_v2 import current_flags


DATA = Path(__file__).resolve().parents[1] / "data" / "omni_v2"
CURATED_DATA = Path(__file__).resolve().parents[1] / "data" / "omni_v2_clean_curated"


class OmniV2Tests(unittest.TestCase):
    def test_split_counts_and_no_duplicate_ids(self):
        expected = {
            "train": (1000, (243, 682, 75)),
            "val": (50, (10, 30, 10)),
            "test_id": (768, (190, 527, 51)),
        }
        all_ids = []
        for split, (size, bins) in expected.items():
            records = [json.loads(line) for line in (DATA / f"{split}.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertEqual(len(records), size)
            self.assertEqual(tuple(Counter(row["difficulty_bin"] for row in records)[key]
                                   for key in ("low_lt_3_5", "middle_3_5_to_6_0", "high_gt_6_0")), bins)
            self.assertTrue(all(row["question_ko"] and row["question_en"] and row["answer"] for row in records))
            all_ids.extend(row["id"] for row in records)
        self.assertEqual(len(all_ids), len(set(all_ids)))

    def test_ambiguous_source_rows_are_only_in_test(self):
        manifest = json.loads((DATA / "manifest.json").read_text(encoding="utf-8"))
        forced = set(manifest["forced_test_multi_match_source_rows"])
        self.assertEqual(len(forced), 16)
        for split in ("train", "val"):
            records = [json.loads(line) for line in (DATA / f"{split}.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertFalse(forced & {row["source_row_index"] for row in records})

    def test_reference_solution_is_feedback_only(self):
        train = load_v2_split(DATA, "train", "en")[:1]
        val = load_v2_split(DATA, "val", "en")[:1]
        train_data = as_v2_gepa_data(train)[0]
        val_data = as_v2_gepa_data(val)[0]
        self.assertEqual(train_data["input"], train[0]["question_en"])
        self.assertNotIn(train[0]["solution_en"], train_data["input"])
        self.assertEqual(train_data["additional_context"]["gold_solution"], train[0]["solution_en"])
        self.assertNotIn("gold_solution", val_data["additional_context"])
        feedback = BilingualMathEvaluator("en")(
            {"answer": "4", "additional_context": {"gold_solution": "Add 2 and 2."}},
            "Work shown.\nFINAL_ANSWER: 3",
        ).feedback
        self.assertIn("Add 2 and 2.", feedback)

    def test_korean_train_requires_matching_reviewed_solution(self):
        with TemporaryDirectory() as directory:
            data_dir = Path(directory) / "omni_v2"
            data_dir.mkdir()
            record = {"id": "example", "question_ko": "질문", "question_en": "Question",
                      "answer": "4", "solution_en": "Add two and two."}
            (data_dir / "train.jsonl").write_text(json.dumps(record, ensure_ascii=False) + "\n", encoding="utf-8")
            solution = {"id": "example", "solution_ko": "둘과 둘을 더한다.",
                        "source_solution_sha256": hashlib.sha256(record["solution_en"].encode()).hexdigest(),
                        "quality_flags": ["fallback_translation"]}
            sidecar = data_dir / "train_solutions_ko.jsonl"
            sidecar.write_text(json.dumps(solution, ensure_ascii=False) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "needs review"):
                load_v2_split(data_dir, "train", "ko")
            solution["review_status"] = "approved"
            sidecar.write_text(json.dumps(solution, ensure_ascii=False) + "\n", encoding="utf-8")
            loaded = load_v2_split(data_dir, "train", "ko")
            self.assertEqual(as_v2_gepa_data(loaded)[0]["additional_context"]["gold_solution"], "둘과 둘을 더한다.")

    def test_same_answer_format_for_both_languages(self):
        for language in ("ko", "en"):
            self.assertEqual(score_v2("12", "Calculation.\nFINAL_ANSWER: 12", language)[0], 1.0)
            self.assertEqual(score_v2("12", "Calculation.\n정답: 12", language)[0], 0.0)

    def test_curated_review_notes_do_not_change_reference_feedback(self):
        for language in ("en", "ko"):
            train = as_v2_gepa_data(load_v2_split(CURATED_DATA, "train", language))
            by_id = {row["additional_context"]["question_id"]: row for row in train}
            self.assertEqual(len(train), 1000)
            self.assertEqual(sum("gold_solution" in row["additional_context"] for row in train), 1000)
            self.assertIn("gold_solution", by_id["HRM8K:OMNI-MATH:1870"]["additional_context"])
            feedback = BilingualMathEvaluator(language)(
                by_id["HRM8K:OMNI-MATH:1870"], "FINAL_ANSWER: 0").feedback
            self.assertIn(by_id["HRM8K:OMNI-MATH:1870"]["additional_context"]["gold_solution"], feedback)

    def test_math_is_restored_verbatim(self):
        source = r"First compute $x^2+1=5$. Then answer 2."
        masked, math = mask_math(source)
        self.assertEqual(masked, "First compute [[MATH_0]]. Then answer 2.")
        translated = restore_math("먼저 [[MATH_0]]을 계산합니다. 답은 2입니다.", math)
        self.assertIn(r"$x^2+1=5$", translated)
        self.assertEqual(quality_flags(source, translated), [])
        unfinished = "Result:\n\\[\\boxed{9}."
        masked, expressions = mask_math(unfinished)
        self.assertEqual(restore_math(masked, expressions), unfinished)
        self.assertEqual(len(expressions), 1)

    def test_translation_flags_focus_on_changed_values_and_prose(self):
        self.assertEqual(quality_flags("$2+3=5$.", "$2+3=5$."), [])
        self.assertEqual(quality_flags("There are 12 edges.", "모서리는 12개이며, 모두 12개다."), [])
        self.assertIn("missing_prose_number", quality_flags("There are 12 edges.", "모서리가 있다."))
        self.assertIn("new_prose_number", quality_flags("There are 12 edges.", "모서리는 13개다."))
        self.assertIn("no_hangul_detected", quality_flags("There are 12 edges.", "12 edges."))
        self.assertIn("source_unbalanced_math_delimiter", quality_flags(
            r"Answer: \[\boxed{9}.", r"정답: \[\boxed{9}."))

    def test_plain_retry_preserves_math_across_paragraphs(self):
        replies = iter(("먼저 [[MATH_0]]을 계산한다.", "따라서 [[MATH_1]]이다."))

        class FakeCompletions:
            def create(self, **_kwargs):
                return SimpleNamespace(
                    choices=[SimpleNamespace(message=SimpleNamespace(content=next(replies)))],
                    id="fake", usage=None,
                )

        client = SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions()))
        translated, requests = _translate_plain_chunks(
            client, Settings(api_key="fake"),
            {"id": "example", "solution_en": "First compute $2+2=4$.\n\nTherefore $x=4$."},
        )
        self.assertEqual(translated, "먼저 $2+2=4$을 계산한다.\n\n따라서 $x=4$이다.")
        self.assertEqual(len(requests), 2)

    def test_segment_retry_preserves_math_when_model_only_translates_prose(self):
        class FakeCompletions:
            def create(self, **_kwargs):
                content = json.dumps({"translations": [
                    {"id": "0", "text": "먼저 계산한다"},
                    {"id": "2", "text": ". 그런 다음"},
                    {"id": "4", "text": "가 정답이다."},
                ]}, ensure_ascii=False)
                return SimpleNamespace(
                    choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
                    id="fake", usage=None,
                )

        client = SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions()))
        translated, requests = _translate_prose_segments(
            client, Settings(api_key="fake"),
            {"id": "example", "solution_en": "First compute $2+2=4$. Then $x=4$ is the answer."},
        )
        self.assertEqual(translated, "먼저 계산한다 $2+2=4$. 그런 다음 $x=4$ 가 정답이다.")
        self.assertEqual(quality_flags("First compute $2+2=4$. Then $x=4$ is the answer.", translated), [])
        self.assertEqual(len(requests), 1)

    def test_segment_retry_recovers_from_invalid_json_batch(self):
        replies = iter(("not JSON", "먼저 계산한다", ". 그런 다음", "가 정답이다."))

        class FakeCompletions:
            def create(self, **_kwargs):
                return SimpleNamespace(
                    choices=[SimpleNamespace(message=SimpleNamespace(content=next(replies)))],
                    id="fake", usage=None,
                )

        client = SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions()))
        translated, requests = _translate_prose_segments(
            client, Settings(api_key="fake"),
            {"id": "example", "solution_en": "First compute $2+2=4$. Then $x=4$ is the answer."},
        )
        self.assertEqual(translated, "먼저 계산한다 $2+2=4$. 그런 다음 $x=4$ 가 정답이다.")
        self.assertEqual([item["status"] for item in requests],
                         ["segment_batch_error", "segment_success", "segment_success", "segment_success"])

    def test_refresh_keeps_fallback_review_requirement(self):
        row = {"solution_ko": "둘과 둘을 더한다.",
               "translation_strategy": "plain_paragraph_fallback"}
        self.assertEqual(current_flags("Add two and two.", row), ["fallback_translation"])

    def test_english_gepa_receives_gold_only_for_train(self):
        class StopBeforeModel(Exception):
            pass

        with TemporaryDirectory() as directory:
            root = Path(directory)
            data_dir, prompt_dir, runs_dir = root / "omni_v2", root / "prompts", root / "runs"
            for path in (data_dir, prompt_dir, runs_dir):
                path.mkdir()
            train = []
            for index, (label, difficulty) in enumerate(
                [("low_lt_3_5", "2"), *([("middle_3_5_to_6_0", "5")] * 3),
                 ("high_gt_6_0", "7")]
            ):
                train.append({"id": f"train-{index}", "source_subset": "OMNI-MATH",
                              "question": f"한국어 {index}", "question_ko": f"한국어 {index}",
                              "question_en": f"English {index}", "solution_en": "Reference proof.",
                              "answer": "1", "difficulty": difficulty, "difficulty_bin": label})
            val = [{**train[0], "id": "val-0", "question_en": "Held-out English"}]
            for split, rows in (("train", train), ("val", val)):
                (data_dir / f"{split}.jsonl").write_text(
                    "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
            (prompt_dir / "seed_en.md").write_text("English seed", encoding="utf-8")
            (prompt_dir / "reflection_en.md").write_text("<curr_param> <side_info>", encoding="utf-8")
            with patch("motif_gepa_ko.experiment.Settings.from_env", return_value=Settings(api_key="fake")), patch(
                "motif_gepa_ko.experiment.gepa.optimize", side_effect=StopBeforeModel
            ) as optimize:
                with self.assertRaises(StopBeforeModel):
                    optimize_run(data_dir=data_dir, prompts_dir=prompt_dir, runs_dir=runs_dir,
                                 run_id="v2-en-test", max_metric_calls=10, max_api_calls=20,
                                 minibatch_size=5, seed=0, language="en")
            arguments = optimize.call_args.kwargs
            self.assertIsInstance(arguments["evaluator"], BilingualMathEvaluator)
            self.assertEqual(arguments["trainset"][0]["additional_context"]["gold_solution"], "Reference proof.")
            self.assertNotIn("gold_solution", arguments["valset"][0]["additional_context"])
            config = json.loads((runs_dir / "v2-en-test" / "config.json").read_text(encoding="utf-8"))
            self.assertEqual(config["language"], "en")

if __name__ == "__main__":
    unittest.main()
