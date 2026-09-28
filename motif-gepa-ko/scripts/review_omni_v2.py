"""Inspect and explicitly approve flagged Korean reference translations."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path

from motif_gepa_ko.translation import quality_flags


ROOT = Path(__file__).resolve().parents[1]


def read(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def current_flags(source: str, row: dict) -> list[str]:
    flags = quality_flags(source, row["solution_ko"])
    if row.get("translation_strategy") in {"plain_paragraph_fallback", "prose_segments_fallback", "whole_plain_translation"}:
        flags.append("fallback_translation")
    return flags


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--id", help="show one source/translation pair")
    parser.add_argument("--dataset", choices=("omni_v2", "omni_v2_clean"), default="omni_v2")
    parser.add_argument("--approve", action="store_true", help="mark inspected flagged translation as approved")
    parser.add_argument("--candidate-file", type=Path,
                        help="inspected Motif repair candidate JSON; requires --id and --approve")
    parser.add_argument("--note", help="required review explanation when approving")
    parser.add_argument("--refresh-flags", action="store_true", help="recompute machine quality flags")
    args = parser.parse_args()
    data = ROOT / "data" / args.dataset
    translations = data / "train_solutions_ko.jsonl"
    if args.approve and (not args.id or not args.note):
        parser.error("--approve requires --id and --note")
    if args.candidate_file and not args.approve:
        parser.error("--candidate-file requires --approve")
    if not translations.exists():
        raise SystemExit("No downloaded train_solutions_ko.jsonl file is present")
    rows = read(translations)
    train = {row["id"]: row for row in read(data / "train.jsonl")}
    if args.refresh_flags:
        for row in rows:
            row["quality_flags"] = current_flags(train[row["id"]]["solution_en"], row)
            if row.get("review_status") == "approved":
                row.pop("review_status")
                row.pop("review_note", None)
                row.pop("reviewed_at_utc", None)
        temp = translations.with_suffix(".jsonl.tmp")
        temp.write_text(
            "".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in rows),
            encoding="utf-8",
        )
        os.replace(temp, translations)
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
    candidate = None
    if args.candidate_file:
        candidate = json.loads(args.candidate_file.read_text(encoding="utf-8"))
        source_hash = hashlib.sha256(source["solution_en"].encode("utf-8")).hexdigest()
        if candidate["id"] != args.id or candidate["source_solution_sha256"] != source_hash:
            raise SystemExit("Repair candidate does not match source ID and hash")
        if candidate["candidate_quality_flags"] != quality_flags(source["solution_en"], candidate["candidate_solution_ko"]):
            raise SystemExit("Repair candidate quality flags changed; inspect before approval")
        print("\nMOTIF REPAIR CANDIDATE\n", candidate["candidate_solution_ko"])
    if args.approve:
        if candidate:
            chosen["solution_ko"] = candidate["candidate_solution_ko"]
            chosen["quality_flags"] = candidate["candidate_quality_flags"]
            chosen["translator_model"] = candidate["translator_model"]
            chosen["translation_strategy"] = "motif_repair_after_review"
            chosen["repair_response_id"] = candidate["response_id"]
        chosen["review_status"] = "approved"
        chosen["review_note"] = args.note
        chosen["reviewed_at_utc"] = datetime.now(timezone.utc).isoformat()
        temp = translations.with_suffix(".jsonl.tmp")
        temp.write_text(
            "".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in rows),
            encoding="utf-8",
        )
        os.replace(temp, translations)
        print("\nApproval saved.")


if __name__ == "__main__":
    main()
