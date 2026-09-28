"""Apply documented translation review decisions to the clean train solutions."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from motif_gepa_ko.translation import quality_flags


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "omni_v2_clean"
TRANSLATIONS = DATA / "train_solutions_ko.jsonl"
DECISIONS = DATA / "translation_review_decisions.jsonl"


def rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def main() -> None:
    train = {row["id"]: row for row in rows(DATA / "train.jsonl")}
    translations = rows(TRANSLATIONS)
    translated = {row["id"]: row for row in translations}
    if len(translated) != len(translations):
        raise ValueError("Duplicate translation ID")
    decisions = rows(DECISIONS)
    seen = set()
    for decision in decisions:
        identifier = decision["id"]
        if identifier in seen or identifier not in train or identifier not in translated:
            raise ValueError(f"Duplicate or missing review ID: {identifier}")
        seen.add(identifier)
        row = translated[identifier]
        source = train[identifier]["solution_en"]
        flags = quality_flags(source, row["solution_ko"])
        if row.get("translation_strategy") in {"plain_paragraph_fallback", "prose_segments_fallback", "whole_plain_translation"}:
            flags.append("fallback_translation")
        if (decision["source_solution_sha256"] != digest(source)
                or decision["target_solution_sha256"] != digest(row["solution_ko"])
                or decision["quality_flags"] != flags):
            raise ValueError(f"Review source, translation or flags changed: {identifier}")
        row["quality_flags"] = flags
        row["review_status"] = "approved"
        row["review_note"] = decision["note"]
        row["reviewed_by"] = decision["reviewer"]
        row["reviewed_at_utc"] = decision["reviewed_at_utc"]
    payload = "".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n"
                      for row in translations)
    temp = TRANSLATIONS.with_suffix(".jsonl.tmp")
    temp.write_text(payload, encoding="utf-8")
    os.replace(temp, TRANSLATIONS)
    pending = [row["id"] for row in translations
               if row.get("quality_flags") and row.get("review_status") != "approved"]
    print(json.dumps({"decisions_applied": len(decisions), "pending_review": pending},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
