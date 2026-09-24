"""Create the fixed HRM8K splits used by the Korean GEPA experiment.

Run from anywhere with ``python scripts/prepare_hrm8k_splits.py``. The source
CSV files are never modified. ``--check`` verifies the committed outputs.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from collections import Counter
from decimal import Decimal, InvalidOperation
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = PROJECT_ROOT.parent / "datasets" / "HRM8K" / "HRM8K"
OUTPUT_ROOT = PROJECT_ROOT / "data" / "hrm8k_v1"
SOURCE_REVISION = "c360cabf8d733a82455565358b3dc965aab9ba8d"
SEED = "hrm8k-ko-gepa-v1-20260923"
SOURCES = {
    "GSM8K": {
        "filename": "gsm8k_test.csv",
        "rows": 1319,
        "sha256": "e603ccfec40beaba66b0ae7f46fe400ed3a02d892b8622a5097a2bee2eb7e05f",
    },
    "MATH": {
        "filename": "math_do_test.csv",
        "rows": 2885,
        "sha256": "48bae14a224e626c4000cc1100ec2cc432b3d8b130b619c4567e1dd4a073dc88",
    },
}
MATH_QUOTAS = {
    "test_ood_math_l1_l2": {"Level 1": 71, "Level 2": 129},
    "test_ood_math_l3_l5": {"Level 3": 66, "Level 4": 69, "Level 5": 65},
}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_source(name: str) -> list[dict[str, str]]:
    spec = SOURCES[name]
    path = SOURCE_ROOT / spec["filename"]
    actual_hash = digest(path.read_bytes())
    if actual_hash != spec["sha256"]:
        raise ValueError(f"Source SHA-256 mismatch: {path}: {actual_hash}")
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        required = {"question", "answer", "original"}
        if name == "MATH":
            required.update({"level", "type"})
        if not required.issubset(reader.fieldnames or []):
            raise ValueError(f"Missing columns in {path}: {required - set(reader.fieldnames or [])}")
        rows = list(reader)
    if len(rows) != spec["rows"]:
        raise ValueError(f"Unexpected row count in {path}: {len(rows)}")
    if any(not row["question"].strip() or not row["original"].strip() for row in rows):
        raise ValueError(f"Blank problem text in {path}")
    return rows


def canonical_answer(value: str) -> str:
    try:
        number = Decimal(value.strip().replace(",", ""))
    except InvalidOperation as exc:
        raise ValueError(f"Non-numeric answer: {value!r}") from exc
    if not number.is_finite() or number != number.to_integral_value():
        raise ValueError(f"Expected a finite integer answer: {value!r}")
    return str(int(number))


def rank(namespace: str, index: int) -> tuple[str, int]:
    key = f"{SEED}|{namespace}|{index}".encode("utf-8")
    return digest(key), index


def normalized_original(row: dict[str, str]) -> str:
    return re.sub(r"\s+", " ", row["original"].casefold()).strip()


def serialize_jsonl(records: list[dict[str, object]]) -> bytes:
    return ("".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in records)).encode("utf-8")


def make_records(name: str, rows: list[dict[str, str]], indices: list[int]) -> list[dict[str, object]]:
    records = []
    for index in sorted(indices):
        row = rows[index]
        record: dict[str, object] = {
            "id": f"HRM8K:{name}:{index:04d}",
            "source_subset": name,
            "source_row_index": index,
            "question": row["question"],
            "answer": canonical_answer(row["answer"]),
        }
        if name == "MATH":
            record["level"] = row["level"]
            record["type"] = row["type"]
        records.append(record)
    return records


def build() -> dict[str, bytes]:
    gsm8k = read_source("GSM8K")
    math = read_source("MATH")

    gsm8k_ranked = sorted(range(len(gsm8k)), key=lambda i: rank("GSM8K", i))
    selections = {
        "train": ("GSM8K", gsm8k_ranked[:240]),
        "val": ("GSM8K", gsm8k_ranked[240:300]),
        "test_id": ("GSM8K", gsm8k_ranked[300:]),
    }
    for split_name, quotas in MATH_QUOTAS.items():
        chosen = []
        for level, count in quotas.items():
            candidates = [i for i, row in enumerate(math) if row["level"] == level]
            if len(candidates) < count:
                raise ValueError(f"Too few MATH {level} rows: {len(candidates)}")
            chosen.extend(sorted(candidates, key=lambda i: rank(f"MATH|{level}", i))[:count])
        selections[split_name] = ("MATH", chosen)

    gsm8k_sets = [set(selections[name][1]) for name in ("train", "val", "test_id")]
    if len(set.union(*gsm8k_sets)) != len(gsm8k) or sum(map(len, gsm8k_sets)) != len(gsm8k):
        raise ValueError("GSM8K train/val/test_id must partition all source rows")
    math_sets = [set(selections[name][1]) for name in MATH_QUOTAS]
    if math_sets[0] & math_sets[1]:
        raise ValueError("MATH OOD test sets overlap")
    original_sets = [{normalized_original(row) for row in rows} for rows in (gsm8k, math)]
    if any(len(original_sets[i]) != len(rows) for i, rows in enumerate((gsm8k, math))):
        raise ValueError("Duplicate normalized English originals within a source subset")
    if original_sets[0] & original_sets[1]:
        raise ValueError("GSM8K and MATH share normalized English originals")

    output: dict[str, bytes] = {}
    split_metadata: dict[str, object] = {}
    manifest: dict[str, object] = {
        "schema_version": 1,
        "selection_seed": SEED,
        "selection_rule": "Sort row indices by SHA-256(seed|namespace|zero-based row index); take fixed counts. MATH is stratified by level.",
        "source_revision": SOURCE_REVISION,
        "sources": {
            name: {
                "path_from_project": f"../datasets/HRM8K/HRM8K/{spec['filename']}",
                "rows": spec["rows"],
                "sha256": spec["sha256"],
            }
            for name, spec in SOURCES.items()
        },
        "splits": split_metadata,
        "unused_math_rows": len(math) - sum(len(part) for part in math_sets),
    }
    for split_name, (source_name, indices) in selections.items():
        records = make_records(source_name, gsm8k if source_name == "GSM8K" else math, indices)
        filename = f"{split_name}.jsonl"
        data = serialize_jsonl(records)
        output[filename] = data
        metadata: dict[str, object] = {
            "file": filename,
            "source_subset": source_name,
            "rows": len(records),
            "sha256": digest(data),
            "source_row_indices": sorted(indices),
        }
        if source_name == "MATH":
            metadata["level_counts"] = dict(sorted(Counter(str(row["level"]) for row in records).items()))
            metadata["type_counts"] = dict(sorted(Counter(str(row["type"]) for row in records).items()))
        split_metadata[split_name] = metadata
    output["manifest.json"] = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="verify all generated files without modifying them")
    parser.add_argument("--force", action="store_true", help="replace existing generated files if they differ")
    args = parser.parse_args()
    if args.check and args.force:
        parser.error("--check and --force cannot be combined")
    expected = build()
    if not args.check:
        OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    for filename, data in expected.items():
        path = OUTPUT_ROOT / filename
        if args.check:
            if not path.exists() or path.read_bytes() != data:
                raise SystemExit(f"Mismatch or missing generated file: {path}")
        elif path.exists() and path.read_bytes() != data and not args.force:
            raise SystemExit(f"Refusing to replace modified generated file: {path}; use --force")
        elif not path.exists() or path.read_bytes() != data:
            path.write_bytes(data)
        print(f"{'Verified' if args.check else 'Ready'}: {path.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
