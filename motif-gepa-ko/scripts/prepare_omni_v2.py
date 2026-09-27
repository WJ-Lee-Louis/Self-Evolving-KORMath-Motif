"""Create an independent, reproducible bilingual Omni-MATH split.

The quality exclusions are the same audited exclusions used for omni_v1, but
the allocation seed and every train/validation/test assignment are new.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import re

from prepare_omni_splits import (
    BINS, EXPECTED_SOURCE_SHA256, FLAGS, SOURCE, SOURCE_DIR, digest,
    difficulty_bin, make_record, normalized, read_csv,
)


ROOT = Path(__file__).resolve().parents[1]
ORIGINAL = ROOT / "data" / "omni_source" / "test.jsonl"
OUTPUT = ROOT / "data" / "omni_v2"
SEED = "omni-v2-bilingual-20260927"
EXPECTED_ORIGINAL_SHA256 = "7c87be8ee41ac7c7a597ef5a5500e84bd2b639a85a06db3da7f69bf9a32ef168"
TRAIN_COUNTS = dict(zip(BINS, (243, 682, 75), strict=True))
VAL_COUNTS = dict(zip(BINS, (10, 30, 10), strict=True))
EXPECTED_POOL_COUNTS = dict(zip(BINS, (443, 1239, 136), strict=True))


def cleaned_indices(rows: list[dict[str, str]]) -> tuple[list[int], dict[int, str]]:
    excluded = {int(row["source_row_index"]): row["decision"] for row in read_csv(FLAGS)}
    if len(excluded) != len(read_csv(FLAGS)):
        raise ValueError("Quality flags contain duplicate source indices")
    other_originals = {
        normalized(row["original"])
        for filename in ("gsm8k_test.csv", "math_do_test.csv")
        for row in read_csv(SOURCE_DIR / filename)
    }
    for index, row in enumerate(rows):
        if normalized(row["original"]) in other_originals:
            excluded.setdefault(index, "exclude_cross_source_exact_overlap")
    seen_en: dict[str, int] = {}
    seen_ko: dict[str, int] = {}
    for index, row in enumerate(rows):
        if index in excluded:
            continue
        en, ko = normalized(row["original"]), normalized(row["question"])
        prior = seen_en.get(en, seen_ko.get(ko))
        if prior is not None:
            if row["answer"] != rows[prior]["answer"]:
                raise ValueError(f"Conflicting answers for duplicate rows {prior}, {index}")
            excluded[index] = "exclude_duplicate"
            continue
        seen_en[en] = index
        seen_ko[ko] = index
    selected = [index for index in range(len(rows)) if index not in excluded]
    counts = Counter(difficulty_bin(rows[index]["difficulty"]) for index in selected)
    if counts != EXPECTED_POOL_COUNTS or len(selected) != 1818:
        raise ValueError(f"Unexpected cleaned pool: {len(selected)} rows; bins={counts}")
    return selected, excluded


def original_matches() -> dict[str, list[tuple[int, dict]]]:
    if digest(ORIGINAL.read_bytes()) != EXPECTED_ORIGINAL_SHA256:
        raise ValueError("Original Omni-MATH source checksum changed")
    matches: dict[str, list[tuple[int, dict]]] = defaultdict(list)
    for index, line in enumerate(ORIGINAL.read_text(encoding="utf-8").splitlines()):
        if line.strip():
            record = json.loads(line)
            matches[record["problem"]].append((index, record))
    return matches


def order(index: int, bin_name: str) -> tuple[str, int]:
    return digest(f"{SEED}|{bin_name}|{index}".encode()), index


def build(*, excluded_dependent_rows: frozenset[int] = frozenset()) -> dict[str, bytes]:
    if digest(SOURCE.read_bytes()) != EXPECTED_SOURCE_SHA256:
        raise ValueError("HRM8K source checksum changed")
    rows = read_csv(SOURCE)
    selected, excluded = cleaned_indices(rows)
    if not excluded_dependent_rows.issubset(selected):
        raise ValueError("A context-dependent row is absent from the original cleaned pool")
    if excluded_dependent_rows:
        selected = [index for index in selected if index not in excluded_dependent_rows]
        excluded.update({index: "exclude_missing_problem_context" for index in excluded_dependent_rows})
        unresolved = [
            index for index in selected
            if re.search(r"\b(?:problem|question|exercise)\s*\(?\s*\d+\b", rows[index]["original"], re.I)
        ]
        if unresolved:
            raise ValueError(f"Unresolved numbered-problem references: {unresolved}")
    source_matches = original_matches()
    matches_by_index: dict[int, list[tuple[int, dict]]] = {}
    for index in selected:
        matches = source_matches.get(rows[index]["original"], [])
        if not matches or any(not item["solution"].strip() for _, item in matches):
            raise ValueError(f"Missing original English solution for HRM8K row {index}")
        matches_by_index[index] = matches

    # A source problem with more than one possible solution row is harmless for
    # answer-only testing, but must not enter gold-solution training or val.
    forced_test = {index for index in selected if len(matches_by_index[index]) > 1}
    chosen = {name: [] for name in ("train", "val", "test_id")}
    for bin_name in BINS:
        candidates = sorted(
            (index for index in selected if difficulty_bin(rows[index]["difficulty"]) == bin_name
             and index not in forced_test),
            key=lambda index: order(index, bin_name),
        )
        train_end = TRAIN_COUNTS[bin_name]
        val_end = train_end + VAL_COUNTS[bin_name]
        if len(candidates) < val_end:
            raise ValueError(f"Insufficient clean rows in {bin_name}")
        chosen["train"].extend(candidates[:train_end])
        chosen["val"].extend(candidates[train_end:val_end])
        chosen["test_id"].extend(candidates[val_end:])
    chosen["test_id"].extend(forced_test)
    if set.union(*(set(v) for v in chosen.values())) != set(selected):
        raise ValueError("Split coverage or overlap failed")
    expected_test = len(selected) - 1000 - 50
    if [len(chosen[name]) for name in ("train", "val", "test_id")] != [1000, 50, expected_test]:
        raise ValueError("Unexpected split sizes")

    output: dict[str, bytes] = {}
    split_manifest = {}
    for split, indices in chosen.items():
        records = []
        for index in sorted(indices):
            row = rows[index]
            source_rows = matches_by_index[index]
            # The source solution is only needed for training. For val/test it
            # is retained as provenance, never loaded into GEPA's task input.
            solution_rows = [item for item in source_rows if str(item[1]["difficulty"]) == row["difficulty"]]
            source_index, source = (solution_rows or source_rows)[0]
            record = make_record(index, row)
            source_answer_digits = re.sub(r"[^0-9+-]", "", str(source["answer"]))
            if not source_answer_digits or int(source_answer_digits) != int(record["answer"]):
                raise ValueError(f"English/Korean answer mismatch for source row {index}")
            record.update({
                "question_ko": row["question"],
                "question_en": row["original"],
                "solution_en": source["solution"],
                "original_source_row_index": source_index,
                "original_source_match_count": len(source_rows),
            })
            records.append(record)
        content = "".join(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
                          for record in records).encode("utf-8")
        output[f"{split}.jsonl"] = content
        split_manifest[split] = {
            "rows": len(records), "sha256": digest(content),
            "difficulty_bin_counts": dict(Counter(record["difficulty_bin"] for record in records)),
            "source_row_indices": sorted(indices),
        }
    manifest = {
        "schema_version": 2,
        "selection_seed": SEED,
        "selection_rule": "Independent SHA-256 order within audited difficulty bins; force all multi-match English originals into test; allocate fixed train/val counts, then all remaining to test.",
        "difficulty_bins": {BINS[0]: "<3.5", BINS[1]: "3.5..6.0", BINS[2]: ">6.0"},
        "source": {"hrm8k_csv_sha256": digest(SOURCE.read_bytes()),
                   "original_omni_jsonl_sha256": digest(ORIGINAL.read_bytes()),
                   "quality_flags_sha256": digest(FLAGS.read_bytes())},
        "cleaned_pool_rows": len(selected),
        "excluded_rows": len(excluded),
        "forced_test_multi_match_source_rows": sorted(forced_test),
        "splits": split_manifest,
    }
    if excluded_dependent_rows:
        manifest["schema_version"] = 3
        manifest["selection_rule"] += " Exclude questions requiring absent numbered-problem context before allocation."
        manifest["excluded_context_dependency_source_rows"] = sorted(excluded_dependent_rows)
    output["manifest.json"] = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    output = build()
    if not args.check:
        OUTPUT.mkdir(parents=True, exist_ok=True)
    for name, content in output.items():
        path = OUTPUT / name
        if args.check:
            if not path.exists() or path.read_bytes() != content:
                raise SystemExit(f"Missing or changed: {path}")
        elif path.exists() and path.read_bytes() != content:
            raise SystemExit(f"Refusing to overwrite changed file: {path}")
        elif not path.exists():
            path.write_bytes(content)
    print("omni_v2: train=1000, val=50, test_id=768; deterministic files verified")


if __name__ == "__main__":
    main()
