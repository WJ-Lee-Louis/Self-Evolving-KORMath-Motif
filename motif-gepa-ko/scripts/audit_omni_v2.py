"""Report split integrity and Korean training-solution translation progress."""

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", choices=("omni_v2", "omni_v2_clean", "omni_v2_clean_curated"), default="omni_v2")
    args = parser.parse_args()
    data = ROOT / "data" / args.dataset
    manifest = json.loads((data / "manifest.json").read_text(encoding="utf-8"))
    seen = set()
    splits = {}
    for split in ("train", "val", "test_id"):
        path = data / f"{split}.jsonl"
        records = read_jsonl(path)
        expected = manifest["splits"][split]
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected["sha256"]:
            raise ValueError(f"Dataset hash changed: {path}")
        ids = {row["id"] for row in records}
        if len(ids) != expected["rows"] or seen & ids:
            raise ValueError(f"Count or ID overlap failure: {split}")
        seen.update(ids)
        splits[split] = records
    if len(seen) != manifest["cleaned_pool_rows"]:
        raise ValueError("Incomplete cleaned pool")
    translation_path = data / "train_solutions_ko.jsonl"
    translated = read_jsonl(translation_path) if translation_path.exists() else []
    train_by_id = {row["id"]: row for row in splits["train"]}
    translated_ids = set()
    flags = Counter()
    pending_review = 0
    for item in translated:
        identifier = item["id"]
        if identifier not in train_by_id or identifier in translated_ids:
            raise ValueError(f"Unknown or duplicate translation: {identifier}")
        source_hash = hashlib.sha256(train_by_id[identifier]["solution_en"].encode()).hexdigest()
        if item["source_solution_sha256"] != source_hash:
            raise ValueError(f"Stale translation: {identifier}")
        translated_ids.add(identifier)
        flags.update(item.get("quality_flags", []))
        if item.get("quality_flags") and item.get("review_status") != "approved":
            pending_review += 1
    print(json.dumps({
        "splits": {name: len(rows) for name, rows in splits.items()},
        "forced_test_multi_match_rows": len(manifest["forced_test_multi_match_source_rows"]),
        "translated_train": len(translated),
        "remaining_train": len(train_by_id) - len(translated),
        "quality_flags": dict(flags),
        "pending_review": pending_review,
        "untrusted_references": sum(row.get("reference_solution_status") == "untrusted"
                                    for row in splits["train"]),
        "translation_ready": len(translated) == 1000 and pending_review == 0,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
