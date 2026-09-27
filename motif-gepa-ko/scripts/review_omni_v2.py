"""Inspect and explicitly approve flagged Korean reference translations."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path

from motif_gepa_ko.translation import quality_flags


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "omni_v2"
TRANSLATIONS = DATA / "train_solutions_ko.jsonl"


def read(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def current_flags(source: str, row: dict) -> list[str]:
    flags = quality_flags(source, row["solution_ko"])
    if row.get("translation_strategy") == "plain_paragraph_fallback":
        flags.append("fallback_translation")
    return flags


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--id", help="show one source/translation pair")
    parser.add_argument("--approve", action="store_true", help="mark inspected flagged translation as approved")
    parser.add_argument("--note", help="required review explanation when approving")
    parser.add_argument("--refresh-flags", action="store_true", help="recompute machine quality flags")
    args = parser.parse_args()
    if args.approve and (not args.id or not args.note):
        parser.error("--approve requires --id and --note")
    if not TRANSLATIONS.exists():
        raise SystemExit("No downloaded train_solutions_ko.jsonl file is present")
    rows = read(TRANSLATIONS)
    train = {row["id"]: row for row in read(DATA / "train.jsonl")}
    if args.refresh_flags:
        for row in rows:
            row["quality_flags"] = current_flags(train[row["id"]]["solution_en"], row)
            if row.get("review_status") == "approved":
                row.pop("review_status")
                row.pop("review_note", None)
                row.pop("reviewed_at_utc", None)
        temp = TRANSLATIONS.with_suffix(".jsonl.tmp")
        temp.write_text(
            "".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in rows),
            encoding="utf-8",
        )
        os.replace(temp, TRANSLATIONS)
    flagged = [row for row in rows if row.get("quality_flags") and row.get("review_status") != "approved"]
    if not args.id:
        print(f"Translated: {len(rows)}/1000; flagged pending review: {len(flagged)}")
        for row in flagged:
            print(row["id"], ", ".join(row["quality_flags"]))
        return
    chosen = next((row for row in rows if row["id"] == args.id), None)
    if chosen is None:
        raise SystemExit(f"Unknown translated ID: {args.id}")
    source = train[chosen["id"]]
    flags_now = current_flags(source["solution_en"], chosen)
    if flags_now != chosen.get("quality_flags", []):
        raise SystemExit("Stored quality flags differ from current checker; inspect code/version before approval")
    print("ID:", args.id, "answer:", source["answer"], "difficulty:", source["difficulty"])
    print("FLAGS:", flags_now, "STATUS:", chosen.get("review_status", "pending"))
    print("\nENGLISH PROBLEM\n", source["question_en"])
    print("\nKOREAN PROBLEM\n", source["question_ko"])
    print("\nENGLISH REFERENCE SOLUTION\n", source["solution_en"])
    print("\nKOREAN TRANSLATION\n", chosen["solution_ko"])
    if args.approve:
        chosen["review_status"] = "approved"
        chosen["review_note"] = args.note
        chosen["reviewed_at_utc"] = datetime.now(timezone.utc).isoformat()
        temp = TRANSLATIONS.with_suffix(".jsonl.tmp")
        temp.write_text(
            "".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in rows),
            encoding="utf-8",
        )
        os.replace(temp, TRANSLATIONS)
        print("\nApproval saved.")


if __name__ == "__main__":
    main()
