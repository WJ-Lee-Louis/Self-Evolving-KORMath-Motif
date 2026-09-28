"""Reproducible, full-coverage structural audit of 1,000 bilingual explanations.

This does not establish mathematical correctness or semantic translation quality;
every finding requiring that judgment remains in the review queue.
"""

from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
import re

from motif_gepa_ko.translation import mask_math, quality_flags


DATA = Path(__file__).resolve().parents[1] / "data" / "omni_v2_clean"
NUM = re.compile(r"(?<![A-Za-z0-9])-?\d+(?:\.\d+)?(?![A-Za-z0-9])")
HANGUL = re.compile(r"[가-힣]")
LATIN_WORD = re.compile(r"\b[A-Za-z]{3,}\b")
IGNORE_WORDS = {
    "WLOG", "SAS", "MIT", "OEIS", "Fig", "mod", "gcd", "lcm", "lim",
    "sin", "cos", "tan", "max", "min", "sup", "inf", "Aquaesulian",
}


def read(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def math_balance(text: str) -> bool:
    return (text.count(r"\(") == text.count(r"\)")
            and text.count(r"\[") == text.count(r"\]")
            and text.count("$") % 2 == 0)


def main() -> None:
    train = {r["id"]: r for r in read(DATA / "train.jsonl")}
    translations = read(DATA / "train_solutions_ko.jsonl")
    issue_path = DATA / "source_solution_issues.jsonl"
    source_issues = {r["id"] for r in read(issue_path)} if issue_path.exists() else set()
    if len(train) != 1000 or len(translations) != 1000:
        raise ValueError("Expected exactly 1,000 source and translation rows")
    if {r["id"] for r in translations} != set(train):
        raise ValueError("Missing, extra, or duplicate translation ID")

    audit = []
    counts = Counter()
    for target in translations:
        identifier = target["id"]
        source = train[identifier]
        english = source["solution_en"]
        korean = target["solution_ko"]
        if sha(english) != target["source_solution_sha256"]:
            raise ValueError(f"Source SHA-256 mismatch: {identifier}")
        source_masked, source_math = mask_math(english)
        target_masked, target_math = mask_math(korean)
        missing_math = list((Counter(source_math) - Counter(target_math)).elements())
        added_math = list((Counter(target_math) - Counter(source_math)).elements())
        missing_numbers = sorted(set(NUM.findall(english)) - set(NUM.findall(korean)))
        added_numbers = sorted(set(NUM.findall(korean)) - set(NUM.findall(english)))
        # Mathematics and URLs can contain English words. This is only a review hint.
        prose = re.sub(r"https?://\S+", "", target_masked)
        prose = re.sub(r"\\[A-Za-z]+", "", prose)
        latin_words = [w for w in LATIN_WORD.findall(prose) if w not in IGNORE_WORDS]
        answer = str(source["answer"])
        answer_in_source = bool(re.search(r"(?<!\d)" + re.escape(answer) + r"(?!\d)", english))
        answer_in_target = bool(re.search(r"(?<!\d)" + re.escape(answer) + r"(?!\d)", korean))
        control_characters = {
            field: {"form_feed": text.count("\x0c"), "tab": text.count("\t")}
            for field, text in (("question_en", source["question_en"]),
                                ("solution_en", english), ("solution_ko", korean))
        }
        findings = []
        source_prose = re.sub(r"\[\[MATH_\d+\]\]", "", source_masked)
        if not korean.strip() or (re.search(r"[A-Za-z]", source_prose) and not HANGUL.search(korean)):
            findings.append("no_korean_explanation")
        if not math_balance(korean):
            findings.append("inherited_source_math_delimiter" if not math_balance(english)
                            else "introduced_target_math_delimiter")
        if missing_math or added_math:
            findings.append("math_span_change")
        if missing_numbers or added_numbers:
            findings.append("number_set_change")
        if latin_words:
            findings.append("latin_prose_candidate")
        if not answer_in_source:
            findings.append("source_omits_final_answer_value")
        if any(control_characters[field][key] for field in ("question_en", "solution_en")
               for key in ("form_feed", "tab")):
            findings.append("english_source_control_character")
        if any(control_characters["solution_ko"].values()):
            findings.append("korean_solution_control_character")
        if target.get("quality_flags") and target.get("review_status") != "approved":
            findings.append("pending_translation_review")
        if target.get("source_solution_issue") or identifier in source_issues:
            findings.append("known_source_solution_issue")
        counts.update(findings)
        audit.append({
            "id": identifier,
            "source_solution_sha256": sha(english),
            "target_solution_sha256": sha(korean),
            "source_length": len(english),
            "target_length": len(korean),
            "translation_strategy": target.get("translation_strategy", "motif_primary"),
            "review_status": target.get("review_status"),
            "stored_quality_flags": target.get("quality_flags", []),
            "recomputed_quality_flags": quality_flags(english, korean),
            "missing_math_spans": missing_math,
            "added_math_spans": added_math,
            "missing_numbers": missing_numbers,
            "added_numbers": added_numbers,
            "latin_prose_words": latin_words,
            "answer_in_source_explanation": answer_in_source,
            "answer_in_korean_explanation": answer_in_target,
            "source_solution_issue": target.get("source_solution_issue"),
            "control_characters": control_characters,
            "findings": findings,
        })
    report = DATA / "translation_audit.jsonl"
    report.write_text("".join(json.dumps(r, ensure_ascii=False, separators=(",", ":")) + "\n" for r in audit), encoding="utf-8")
    summary = {"dataset": "omni_v2_clean", "rows_checked": len(audit),
               "finding_counts": dict(counts), "report": report.name,
               "scope": "structural full-coverage; semantic and mathematical review is separate"}
    (DATA / "translation_audit_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
