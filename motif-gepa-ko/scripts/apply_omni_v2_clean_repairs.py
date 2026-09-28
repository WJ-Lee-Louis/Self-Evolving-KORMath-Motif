"""Apply eight inspected Motif translation repairs to the complete clean train file."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path

from motif_gepa_ko.translation import quality_flags


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "omni_v2_clean"
TRANSLATIONS = DATA / "train_solutions_ko.jsonl"
REPAIRS = DATA / "translation_repairs"


def read(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> None:
    train = {row["id"]: row for row in read(DATA / "train.jsonl")}
    translations = read(TRANSLATIONS)
    if len(translations) != 1000:
        raise ValueError("All 1,000 clean train translations must be downloaded first")
    by_id = {row["id"]: row for row in translations}
    if len(by_id) != 1000 or set(by_id) != set(train):
        raise ValueError("Missing or duplicate clean train translation IDs")
    paths = sorted(REPAIRS.glob("*.json"))
    if len(paths) != 8:
        raise ValueError("Expected eight inspected Motif repair candidates")
    reviewed_at = datetime.now(timezone.utc).isoformat()
    applied = []
    for path in paths:
        candidate = json.loads(path.read_text(encoding="utf-8"))
        identifier = candidate["id"]
        if identifier not in train or identifier.split(":")[-1] != path.stem:
            raise ValueError(f"Repair ID mismatch: {path}")
        source = train[identifier]["solution_en"]
        if hashlib.sha256(source.encode("utf-8")).hexdigest() != candidate["source_solution_sha256"]:
            raise ValueError(f"Repair source changed: {identifier}")
        text = candidate["candidate_solution_ko"]
        flags = quality_flags(source, text)
        if flags != candidate["candidate_quality_flags"]:
            raise ValueError(f"Repair quality flags changed: {identifier}")
        row = by_id[identifier]
        row["solution_ko"] = text
        row["quality_flags"] = flags
        row["translator_model"] = candidate["translator_model"]
        row["translation_strategy"] = "motif_repair_after_review"
        row["repair_response_id"] = candidate["response_id"]
        row["review_status"] = "approved"
        row["reviewed_by"] = "Codex"
        row["reviewed_at_utc"] = reviewed_at
        row["review_note"] = (
            "Motif 전체 재번역 후보와 원문을 대조했다. 표시 수식 블록 21개가 모두 유지되었다."
            if path.stem == "1682" else
            "Motif 전체 재번역 후보와 원문을 대조했다. 원문 수식 구분자 결함 또는 "
            "문장 분할 번역의 어색함을 수정하고 해설 결론을 확인했다."
        )
        applied.append(identifier)
    payload = "".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n"
                      for row in translations)
    temp = TRANSLATIONS.with_suffix(".jsonl.tmp")
    temp.write_text(payload, encoding="utf-8")
    os.replace(temp, TRANSLATIONS)
    print("Applied inspected repair IDs:", ", ".join(applied))


if __name__ == "__main__":
    main()
