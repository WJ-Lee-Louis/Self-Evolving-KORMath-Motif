"""Bilingual Omni v2 input selection and answer-only evaluation."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import re

from gepa.adapters.default_adapter.default_adapter import EvaluationResult

from motif_gepa_ko.data import load_split


LANGUAGES = ("ko", "en")
V2_DATASETS = ("omni_v2", "omni_v2_clean")
FINAL_LINE = re.compile(
    r"^\s*FINAL_ANSWER\s*:\s*([+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?)\s*\.?\s*$"
)


def load_v2_split(data_dir: Path, split: str, language: str) -> list[dict]:
    if data_dir.name not in V2_DATASETS or language not in LANGUAGES:
        raise ValueError("An Omni v2 dataset and language ko/en are required")
    records = load_split(data_dir, split)
    translations = {}
    if split == "train" and language == "ko":
        path = data_dir / "train_solutions_ko.jsonl"
        if not path.exists():
            raise FileNotFoundError(f"Korean training solutions are incomplete: {path}")
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                item = json.loads(line)
                if item["id"] in translations:
                    raise ValueError(f"Duplicate translation ID: {item['id']}")
                translations[item["id"]] = item
        if set(translations) != {item["id"] for item in records}:
            raise ValueError("Training translation IDs do not match the 1,000 fixed training rows")
    result = []
    for item in records:
        record = dict(item)
        record["question"] = item[f"question_{language}"]
        if split == "train":
            if language == "ko":
                translated = translations[item["id"]]
                expected_hash = hashlib.sha256(item["solution_en"].encode("utf-8")).hexdigest()
                if translated["source_solution_sha256"] != expected_hash:
                    raise ValueError(f"Stale Korean solution for {item['id']}")
                if translated.get("quality_flags") and translated.get("review_status") != "approved":
                    raise ValueError(f"Korean solution needs review: {item['id']}: {translated['quality_flags']}")
                record["gold_solution"] = translated["solution_ko"]
            else:
                record["gold_solution"] = item["solution_en"]
            if not record["gold_solution"].strip():
                raise ValueError(f"Empty gold solution: {item['id']}")
        else:
            # Held-out source solutions remain on disk but never enter the
            # GEPA data instance or the reflection feedback.
            record.pop("gold_solution", None)
        result.append(record)
    return result


def as_v2_gepa_data(records: list[dict]) -> list[dict]:
    result = []
    for item in records:
        context = {"question_id": item["id"]}
        if "gold_solution" in item:
            context["gold_solution"] = item["gold_solution"]
        result.append({"input": item["question"], "answer": item["answer"],
                       "additional_context": context})
    return result


def extract_final_number(response: str) -> Decimal | None:
    lines = response.strip().splitlines()
    if not lines:
        return None
    match = FINAL_LINE.fullmatch(lines[-1])
    if match is None:
        return None
    try:
        return Decimal(match.group(1).replace(",", ""))
    except InvalidOperation:
        return None


def score_v2(answer: str, response: str, language: str,
             gold_solution: str | None = None) -> tuple[float, str, str | None]:
    if language not in LANGUAGES:
        raise ValueError(f"Unknown language: {language}")
    expected = Decimal(answer)
    parsed = extract_final_number(response)
    score = float(parsed == expected) if parsed is not None else 0.0
    if language == "ko":
        if parsed is None:
            feedback = f"마지막 줄에서 `FINAL_ANSWER: 정수` 형식을 찾지 못했습니다. 정답은 {answer}입니다."
        elif score:
            feedback = "최종 답이 맞습니다. 풀이가 모범해설과 일치하는지 살펴보세요."
        else:
            feedback = f"최종 답 {parsed}은 오답이고 정답은 {answer}입니다. 풀이를 모범해설과 비교하세요."
        if gold_solution:
            feedback += f"\n모범해설:\n{gold_solution}"
    else:
        if parsed is None:
            feedback = f"The final line did not match `FINAL_ANSWER: integer`. The correct answer is {answer}."
        elif score:
            feedback = "The final answer is correct. Compare the reasoning with the reference solution."
        else:
            feedback = f"The final answer {parsed} is incorrect; the correct answer is {answer}. Compare the reasoning with the reference solution."
        if gold_solution:
            feedback += f"\nReference solution:\n{gold_solution}"
    return score, feedback, str(parsed) if parsed is not None else None


class BilingualMathEvaluator:
    def __init__(self, language: str):
        if language not in LANGUAGES:
            raise ValueError(language)
        self.language = language

    def __call__(self, data: dict, response: str) -> EvaluationResult:
        solution = data.get("additional_context", {}).get("gold_solution")
        score, feedback, _ = score_v2(data["answer"], response, self.language, solution)
        return EvaluationResult(score, feedback)
