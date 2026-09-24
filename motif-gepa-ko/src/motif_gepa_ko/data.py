"""Read the fixed HRM8K project splits."""

import json
from pathlib import Path


SPLITS = (
    "train",
    "val",
    "test_id",
    "test_ood_math_l1_l2",
    "test_ood_math_l3_l5",
)


def load_split(data_dir: Path, split: str) -> list[dict]:
    if split not in SPLITS:
        raise ValueError(f"알 수 없는 분할: {split}")
    path = data_dir / f"{split}.jsonl"
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not records or len({item["id"] for item in records}) != len(records):
        raise ValueError(f"분할이 비었거나 중복 ID가 있습니다: {path}")
    return records


def as_gepa_data(records: list[dict]) -> list[dict]:
    return [
        {"input": item["question"], "answer": item["answer"],
         "additional_context": {"question_id": item["id"]}}
        for item in records
    ]
