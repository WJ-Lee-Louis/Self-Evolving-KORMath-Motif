"""Audit HRM8K Omni-MATH source rows before designing a text-only GEPA split."""

from collections import Counter, defaultdict
import csv
import hashlib
import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT.parent / "datasets" / "HRM8K" / "HRM8K"
OUT_DIR = ROOT / "data" / "omni_design"


def read_rows(name: str) -> list[dict[str, str]]:
    with (SOURCE_DIR / name).open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold()


def main() -> None:
    source = SOURCE_DIR / "omni-math_do_test.csv"
    omni = read_rows(source.name)
    flags = read_rows_from_path(OUT_DIR / "quality_flags.csv")
    if len({int(flag["source_row_index"]) for flag in flags}) != len(flags):
        raise ValueError("quality_flags.csv에 중복 행 번호가 있습니다.")
    if any(not 0 <= int(flag["source_row_index"]) < len(omni) for flag in flags):
        raise ValueError("quality_flags.csv에 잘못된 행 번호가 있습니다.")

    by_original: dict[str, list[int]] = defaultdict(list)
    by_question: dict[str, list[int]] = defaultdict(list)
    for index, row in enumerate(omni):
        by_original[normalize(row["original"])].append(index)
        by_question[normalize(row["question"])].append(index)
    duplicate_groups = [
        {"source_row_indices": indices, "answers": [omni[i]["answer"] for i in indices],
         "difficulties": [omni[i]["difficulty"] for i in indices]}
        for indices in by_original.values() if len(indices) > 1
    ]
    duplicate_groups.sort(key=lambda group: group["source_row_indices"][0])
    question_duplicate_groups = [indices for indices in by_question.values() if len(indices) > 1]
    question_duplicate_groups.sort(key=lambda indices: indices[0])

    cross_source = {}
    cross_source_korean = {}
    for group, filename in (("MATH", "math_do_test.csv"), ("GSM8K", "gsm8k_test.csv")):
        other = read_rows(filename)
        other_originals: dict[str, list[int]] = defaultdict(list)
        other_questions: dict[str, list[int]] = defaultdict(list)
        for index, row in enumerate(other):
            other_originals[normalize(row["original"])].append(index)
            other_questions[normalize(row["question"])].append(index)
        cross_source[group] = [
            {"omni_source_row_index": index, "other_source_row_indices": other_originals[key]}
            for key, indices in by_original.items() if key in other_originals for index in indices
        ]
        cross_source[group].sort(key=lambda match: match["omni_source_row_index"])
        cross_source_korean[group] = [
            {"omni_source_row_index": index, "other_source_row_indices": other_questions[key]}
            for key, indices in by_question.items() if key in other_questions for index in indices
        ]
        cross_source_korean[group].sort(key=lambda match: match["omni_source_row_index"])

    difficulty = Counter(row["difficulty"] for row in omni)
    manifest = json.loads((ROOT / "data" / "hrm8k_v1" / "manifest.json").read_text(encoding="utf-8"))
    math_ood = {
        int(index)
        for split in ("test_ood_math_l1_l2", "test_ood_math_l3_l5")
        for index in manifest["splits"][split]["source_row_indices"]
    }
    cross_with_math_ood = [
        match for match in cross_source["MATH"]
        if any(index in math_ood for index in match["other_source_row_indices"])
    ]
    report = {
        "source_file": "datasets/HRM8K/HRM8K/omni-math_do_test.csv",
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "source_rows": len(omni),
        "difficulty_counts": dict(sorted(difficulty.items(), key=lambda item: float(item[0]))),
        "manual_quality_flags": dict(Counter(flag["decision"] for flag in flags)),
        "manual_quality_flag_source_row_indices": [int(flag["source_row_index"]) for flag in flags],
        "duplicate_groups_by_exact_normalized_english_original": duplicate_groups,
        "duplicate_groups_by_exact_normalized_korean_question": question_duplicate_groups,
        "exact_cross_source_matches": cross_source,
        "exact_cross_source_korean_matches": cross_source_korean,
        "exact_cross_with_existing_math_ood_holdout": cross_with_math_ood,
        "final_split_manifest": "data/omni_v1/manifest.json",
        "limitations": [
            "Rule-assisted manual visual review is not a guarantee that every malformed item was found.",
            "Exact normalized text matching does not detect paraphrases or translated overlaps.",
            "The generated split manifest is the authoritative count after exclusions and deduplication.",
        ],
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / "source_audit.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Omni rows={len(omni)}, English duplicate groups={len(duplicate_groups)}, "
          f"Korean duplicate groups={len(question_duplicate_groups)}, "
          f"MATH English matches={len(cross_source['MATH'])}, "
          f"MATH Korean matches={len(cross_source_korean['MATH'])}")
    print(path)


def read_rows_from_path(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


if __name__ == "__main__":
    main()
