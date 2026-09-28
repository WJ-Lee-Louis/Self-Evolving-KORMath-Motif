"""Reuse matching Korean solutions when moving from omni_v2 to omni_v2_clean."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from motif_gepa_ko.translation import quality_flags


ROOT = Path(__file__).resolve().parents[1]
OLD = ROOT / "data" / "omni_v2" / "train_solutions_ko.jsonl"
TRAIN = ROOT / "data" / "omni_v2_clean" / "train.jsonl"
OUTPUT = ROOT / "data" / "omni_v2_clean" / "train_solutions_ko.jsonl"


def read(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> None:
    source_rows = read(OLD)
    source = {row["id"]: row for row in source_rows}
    if len(source) != len(source_rows):
        raise ValueError("Duplicate source translation ID")
    train = read(TRAIN)
    if len(train) != 1000:
        raise ValueError("Expected 1,000 clean train questions")
    reused = []
    for item in train:
        if item["id"] not in source:
            continue
        row = dict(source[item["id"]])
        expected_hash = hashlib.sha256(item["solution_en"].encode("utf-8")).hexdigest()
        if row["source_solution_sha256"] != expected_hash:
            raise ValueError(f"Reference solution changed: {item['id']}")
        row["quality_flags"] = quality_flags(item["solution_en"], row["solution_ko"])
        if row.get("translation_strategy") in {"plain_paragraph_fallback", "prose_segments_fallback"}:
            row["quality_flags"].append("fallback_translation")
        if row.get("review_status") == "approved" and row["quality_flags"]:
            raise ValueError(f"Review must be repeated after rule change: {item['id']}")
        reused.append(row)
    payload = "".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in reused)
    if OUTPUT.exists() and OUTPUT.read_text(encoding="utf-8") != payload:
        raise FileExistsError("Clean translation file already has new content; refusing to overwrite")
    OUTPUT.write_text(payload, encoding="utf-8")
    print(f"Reused {len(reused)}; clean train still needs {len(train) - len(reused)} translations")


if __name__ == "__main__":
    main()
