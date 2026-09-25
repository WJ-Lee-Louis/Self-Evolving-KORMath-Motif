"""Build reproducible text-only HRM8K/Omni-MATH GEPA splits.

Run with: python scripts/prepare_omni_splits.py [--check]
The source CSV is never changed. No API calls are made.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT.parent / "datasets" / "HRM8K" / "HRM8K"
SOURCE = SOURCE_DIR / "omni-math_do_test.csv"
FLAGS = ROOT / "data" / "omni_design" / "quality_flags.csv"
OUTPUT = ROOT / "data" / "omni_v1"
SEED = "hrm8k-omni-ko-gepa-v1-20260925"
EXPECTED_SOURCE_SHA256 = "70e7264b5d0813a7f965ea84485bd5b0d339d72358e901dad87c594551936547"
SPLITS = ("train", "val", "test_id")
BINS = ("low_lt_3_5", "middle_3_5_to_6_0", "high_gt_6_0")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def normalized(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold()


def difficulty_bin(value: str) -> str:
    difficulty = Decimal(value)
    if difficulty < Decimal("3.5"):
        return BINS[0]
    if difficulty <= Decimal("6.0"):
        return BINS[1]
    return BINS[2]


def rank(index: int) -> tuple[str, int]:
    return digest(f"{SEED}|{index}".encode("utf-8")), index


def apportion(sizes: dict[str, int], target: int) -> dict[str, int]:
    total = sum(sizes.values())
    quotients = {name: sizes[name] * target / total for name in BINS}
    counts = {name: int(quotients[name]) for name in BINS}
    remaining = target - sum(counts.values())
    for name in sorted(BINS, key=lambda part: (-(quotients[part] - counts[part]), BINS.index(part)))[:remaining]:
        counts[name] += 1
    return counts


def make_record(index: int, row: dict[str, str]) -> dict[str, object]:
    answer = Decimal(row["answer"])
    if not answer.is_finite() or answer != answer.to_integral_value():
        raise ValueError(f"Non-integer answer at source row {index}")
    return {
        "id": f"HRM8K:OMNI-MATH:{index:04d}",
        "source_subset": "OMNI-MATH",
        "source_row_index": index,
        "question": row["question"],
        "answer": str(int(answer)),
        "difficulty": row["difficulty"],
        "difficulty_bin": difficulty_bin(row["difficulty"]),
    }


def build() -> dict[str, bytes]:
    source_bytes = SOURCE.read_bytes()
    if digest(source_bytes) != EXPECTED_SOURCE_SHA256:
        raise ValueError("Omni-MATH source checksum changed; review exclusions and splits first")
    rows = read_csv(SOURCE)
    if len(rows) != 1909:
        raise ValueError(f"Expected 1909 source rows, got {len(rows)}")
    flags = read_csv(FLAGS)
    exclusions: dict[int, dict[str, str]] = {}
    for flag in flags:
        index = int(flag["source_row_index"])
        if index in exclusions or not 0 <= index < len(rows):
            raise ValueError(f"Duplicate or invalid quality flag index: {index}")
        if not flag["decision"].startswith("exclude_"):
            raise ValueError(f"Unresolved quality flag at {index}")
        exclusions[index] = {"reason": flag["decision"], "detail": flag["reason"]}

    # Prevent exact reuse of GSM8K/MATH test questions in Omni training or validation.
    other_originals: dict[str, list[dict[str, object]]] = defaultdict(list)
    for subset, filename in (("GSM8K", "gsm8k_test.csv"), ("MATH", "math_do_test.csv")):
        for other_index, other in enumerate(read_csv(SOURCE_DIR / filename)):
            other_originals[normalized(other["original"])].append(
                {"subset": subset, "source_row_index": other_index}
            )
    cross_source_matches = {}
    for index, row in enumerate(rows):
        matches = other_originals.get(normalized(row["original"]), [])
        if matches:
            cross_source_matches[str(index)] = matches
            exclusions.setdefault(index, {
                "reason": "exclude_cross_source_exact_overlap",
                "detail": "Same normalized English original in HRM8K GSM8K or MATH",
            })

    # Keep at most one rendering of each problem after quality exclusions.
    seen_original: dict[str, int] = {}
    seen_korean: dict[str, int] = {}
    for index, row in enumerate(rows):
        if index in exclusions:
            continue
        original, korean = normalized(row["original"]), normalized(row["question"])
        prior = seen_original.get(original, seen_korean.get(korean))
        if prior is not None:
            if rows[prior]["answer"] != row["answer"]:
                raise ValueError(f"Duplicate problem has conflicting answers: {prior}, {index}")
            exclusions[index] = {
                "reason": "exclude_duplicate",
                "detail": f"Same normalized English or Korean text as retained source row {prior}",
            }
            continue
        seen_original[original] = index
        seen_korean[korean] = index

    candidates = [index for index in range(len(rows)) if index not in exclusions]
    by_bin = {name: [] for name in BINS}
    for index in candidates:
        by_bin[difficulty_bin(rows[index]["difficulty"])].append(index)
    for indices in by_bin.values():
        indices.sort(key=rank)
    sizes = {name: len(indices) for name, indices in by_bin.items()}
    test_counts = apportion(sizes, round(len(candidates) * 0.20))
    val_counts = apportion(sizes, round(len(candidates) * 0.10))
    chosen = {name: [] for name in SPLITS}
    for name in BINS:
        indices = by_bin[name]
        test_end = test_counts[name]
        val_end = test_end + val_counts[name]
        chosen["test_id"].extend(indices[:test_end])
        chosen["val"].extend(indices[test_end:val_end])
        chosen["train"].extend(indices[val_end:])
    if set.union(*(set(chosen[name]) for name in SPLITS)) != set(candidates):
        raise ValueError("Split coverage failed")
    if sum(len(chosen[name]) for name in SPLITS) != len(candidates):
        raise ValueError("Split overlap detected")

    output: dict[str, bytes] = {}
    split_manifest: dict[str, object] = {}
    for name in SPLITS:
        indices = sorted(chosen[name])
        records = [make_record(index, rows[index]) for index in indices]
        content = "".join(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n" for record in records).encode("utf-8")
        filename = f"{name}.jsonl"
        output[filename] = content
        split_manifest[name] = {
            "file": filename,
            "rows": len(records),
            "sha256": digest(content),
            "source_row_indices": indices,
            "difficulty_bin_counts": dict(Counter(record["difficulty_bin"] for record in records)),
            "difficulty_label_counts": dict(sorted(Counter(record["difficulty"] for record in records).items(), key=lambda pair: Decimal(pair[0]))),
        }
    manifest = {
        "schema_version": 1,
        "source": {
            "path_from_project": "../datasets/HRM8K/HRM8K/omni-math_do_test.csv",
            "rows": len(rows),
            "sha256": digest(source_bytes),
            "source_row_index_base": 0,
        },
        "quality_flags_path_from_project": "data/omni_design/quality_flags.csv",
        "quality_flags_sha256": digest(FLAGS.read_bytes()),
        "selection_seed": SEED,
        "selection_rule": "Exclude audited quality defects, exact GSM8K/MATH overlaps, and duplicate English/Korean originals; SHA-256 rank within difficulty bins; allocate 70/10/20 train/val/test using largest remainders.",
        "difficulty_bins": {
            BINS[0]: "difficulty < 3.5",
            BINS[1]: "3.5 <= difficulty <= 6.0",
            BINS[2]: "difficulty > 6.0",
        },
        "source_difficulty_counts": dict(sorted(Counter(row["difficulty"] for row in rows).items(), key=lambda pair: Decimal(pair[0]))),
        "excluded_counts_by_reason": dict(sorted(Counter(item["reason"] for item in exclusions.values()).items())),
        "excluded_source_rows": {str(index): exclusions[index] for index in sorted(exclusions)},
        "cross_source_exact_matches": cross_source_matches,
        "usable_rows": len(candidates),
        "splits": split_manifest,
    }
    output["manifest.json"] = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="verify existing generated files")
    parser.add_argument("--force", action="store_true", help="replace modified generated files")
    args = parser.parse_args()
    if args.check and args.force:
        parser.error("--check and --force cannot be combined")
    expected = build()
    if not args.check:
        OUTPUT.mkdir(parents=True, exist_ok=True)
    for name, content in expected.items():
        path = OUTPUT / name
        if args.check:
            if not path.exists() or path.read_bytes() != content:
                raise SystemExit(f"Mismatch or missing: {path}")
        elif path.exists() and path.read_bytes() != content and not args.force:
            raise SystemExit(f"Refusing to overwrite modified file: {path}; use --force")
        elif not path.exists() or path.read_bytes() != content:
            path.write_bytes(content)
        print(f"{'Verified' if args.check else 'Ready'}: {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
