"""Build a versioned text-repair copy without changing either running experiment.

Review notes about source explanations are retained as metadata. They do not
alter reference feedback or imply that a source solution is incorrect.
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

from motif_gepa_ko.translation import quality_flags


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data" / "omni_v2_clean"
DESTINATION = ROOT / "data" / "omni_v2_clean_curated"


def read(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def sha(data: bytes | str) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def repaired(text: str) -> tuple[str, dict[str, int]]:
    counts = {
        "frac": text.count("\x0crac"),
        "times": text.count("\times"),
        "triangle": text.count("\triangle"),
        "first": text.count("fi\x0crst"),
        "find": text.count("\x0cfind"),
    }
    text = (text.replace("\x0crac", r"\frac")
                .replace("\times", r"\times")
                .replace("\triangle", r"\triangle")
                .replace("fi\x0crst", "first")
                .replace("\x0cfind", "find"))
    # Other tabs in the source are plain indentation (one author credit).
    if "\x0c" in text:
        raise ValueError("Unknown form-feed pattern")
    if "\t" in text:
        counts["plain_tabs"] = text.count("\t")
        text = text.replace("\t", " ")
    return text, {name: count for name, count in counts.items() if count}


def encoded(rows: list[dict]) -> bytes:
    return "".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n"
                   for row in rows).encode("utf-8")


def build() -> tuple[dict[str, bytes], dict]:
    issues = {}
    for issue in read(SOURCE / "source_solution_issues.jsonl"):
        issues.setdefault(issue["id"], []).append(issue["issue_type"])
    split_bytes = {}
    source_train = {}
    summary = Counter()
    log = []
    for split in ("train", "val", "test_id"):
        rows = read(SOURCE / f"{split}.jsonl")
        for row in rows:
            for field in ("question_en", "solution_en"):
                before = row[field]
                after, counts = repaired(before)
                if counts:
                    row[field] = after
                    summary.update({f"{field}_{name}": count for name, count in counts.items()})
                    log.append({"id": row["id"], "split": split, "field": field,
                                "before_sha256": sha(before), "after_sha256": sha(after),
                                "repairs": counts})
            if split == "train":
                if row["id"] in issues:
                    row["reference_solution_review_notes"] = issues[row["id"]]
                source_train[row["id"]] = row
        split_bytes[f"{split}.jsonl"] = encoded(rows)
    translations = read(SOURCE / "train_solutions_ko.jsonl")
    for row in translations:
        original = row["solution_ko"]
        translated, counts = repaired(original)
        if counts:
            row["solution_ko"] = translated
            summary.update({f"solution_ko_{name}": count for name, count in counts.items()})
            log.append({"id": row["id"], "split": "train", "field": "solution_ko",
                        "before_sha256": sha(original), "after_sha256": sha(translated),
                        "repairs": counts})
        source = source_train[row["id"]]
        row["source_solution_sha256"] = sha(source["solution_en"])
        row["quality_flags"] = quality_flags(source["solution_en"], row["solution_ko"])
        if row["id"] in issues:
            row["reference_solution_review_notes"] = issues[row["id"]]
    split_bytes["train_solutions_ko.jsonl"] = encoded(translations)
    split_bytes["text_repairs.jsonl"] = encoded(log)
    split_bytes["source_solution_issues.jsonl"] = encoded(read(SOURCE / "source_solution_issues.jsonl"))
    parent = SOURCE / "manifest.json"
    parent_manifest = json.loads(parent.read_text(encoding="utf-8"))
    manifest = {
        "dataset_version": "omni_v2_clean_curated",
        "parent_dataset_version": "omni_v2_clean",
        "parent_manifest_sha256": sha(parent.read_bytes()),
        "split_policy": "same IDs, order, difficulty labels and answers as parent",
        "files": {name: {"rows": len(payload.splitlines()), "sha256": sha(payload)}
                  for name, payload in split_bytes.items()},
        "splits": {name: {"rows": len(split_bytes[f"{name}.jsonl"].splitlines()),
                           "sha256": sha(split_bytes[f"{name}.jsonl"])}
                   for name in ("train", "val", "test_id")},
        "cleaned_pool_rows": parent_manifest["cleaned_pool_rows"],
        "forced_test_multi_match_source_rows": parent_manifest["forced_test_multi_match_source_rows"],
        "text_repair_counts": dict(summary),
        "reference_review_note_ids": sorted(issues),
        "reference_review_note_count": len(issues),
        "caveat": "Review notes include incomplete derivations and possible inconsistencies. They do not automatically suppress or rewrite source solutions.",
    }
    split_bytes["manifest.json"] = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    return split_bytes, manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    files, manifest = build()
    if args.check:
        for name, payload in files.items():
            path = DESTINATION / name
            if not path.exists() or path.read_bytes() != payload:
                raise ValueError(f"Curated file differs: {path}")
    else:
        DESTINATION.mkdir(parents=True, exist_ok=True)
        for name, payload in files.items():
            (DESTINATION / name).write_bytes(payload)
    print(json.dumps({"dataset_version": manifest["dataset_version"],
                      "split_rows": {name: manifest["files"][name]["rows"]
                                     for name in ("train.jsonl", "val.jsonl", "test_id.jsonl")},
                      "text_repair_counts": manifest["text_repair_counts"],
                      "reference_review_note_count": manifest["reference_review_note_count"]},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
