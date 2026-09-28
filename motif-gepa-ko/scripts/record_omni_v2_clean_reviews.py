"""Record direct source/translation review for the remaining Motif fallback rows."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from motif_gepa_ko.translation import quality_flags


DATA = Path(__file__).resolve().parents[1] / "data" / "omni_v2_clean"
NOTES = {
    "0015": "그래프 보조정리, 부등식과 최종 3822를 원문에 대조함. 수식은 보존됨.",
    "0251": "복소수 수열의 식과 최종 65536을 원문에 대조함. 수식은 보존됨.",
    "0712": "원문의 닫히지 않은 수식 구분자가 번역에서 나뉘어 표시됨. 각도 식과 결론 27을 대조함.",
    "0755": "중점 연결 정리와 둘레 식 및 결론 36을 원문에 대조함.",
    "0844": "번역은 원문의 식과 결론 580을 따름. 원본 해설의 AC=840, AD=841 주장은 식과 모순되어 원문 품질 문제로 별도 기록함.",
    "0929": "합동식, 주기 5와 최종 합계 2416을 원문에 대조함. 수식 분할만 다름.",
    "0975": "짝수·홀수 경우와 최종 합계 8093을 대조함. 수식 분할만 다름.",
    "0996": "순환 길이 6,3,2,1의 경우 분할과 합계 1470을 대조함.",
    "1010": "도형 해설의 수치와 넓이 23/9를 대조함. 원문은 문제에서 요구한 100m+n을 끝에 계산하지 않음.",
    "1381": "약수 개수와 각 경우의 큰 정수 및 최종 자릿수 합 27을 대조함. 번역의 수식은 일반 텍스트 형태라 추후 조판 개선 대상임.",
    "1519": "세율 계산과 24개 결론을 대조함. 원문 달러 기호 때문에 수식 구분자 검사가 경고함.",
    "1600": "소수 거듭제곱 목록과 최종 11개를 대조함. 수식 토큰 분할만 다름.",
    "1656": "인수분해 경우 나누기 및 최종 18개를 원문의 앞·중간·끝과 대조함. 수식 토큰 분할만 다름.",
}


def read(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def main() -> None:
    source = {r["id"]: r for r in read(DATA / "train.jsonl")}
    target = {r["id"]: r for r in read(DATA / "train_solutions_ko.jsonl")}
    path = DATA / "translation_review_decisions.jsonl"
    decisions = read(path)
    existing = {r["id"] for r in decisions}
    expected = {f"HRM8K:OMNI-MATH:{suffix}" for suffix in NOTES}
    pending = {identifier for identifier, row in target.items()
               if row.get("quality_flags") and row.get("review_status") != "approved"}
    if pending != expected:
        raise ValueError(f"Unexpected pending review IDs: {sorted(pending ^ expected)}")
    if existing & expected:
        raise ValueError("Review decision already exists")
    at = datetime.now(timezone.utc).isoformat()
    for suffix, note in NOTES.items():
        identifier = f"HRM8K:OMNI-MATH:{suffix}"
        row = target[identifier]
        english = source[identifier]["solution_en"]
        korean = row["solution_ko"]
        flags = quality_flags(english, korean)
        if row.get("translation_strategy") in {"plain_paragraph_fallback", "prose_segments_fallback", "whole_plain_translation"}:
            flags.append("fallback_translation")
        if flags != row["quality_flags"]:
            raise ValueError(f"Quality flags changed: {identifier}")
        decisions.append({"id": identifier, "source_solution_sha256": digest(english),
                          "target_solution_sha256": digest(korean), "quality_flags": flags,
                          "reviewer": "Codex", "reviewed_at_utc": at, "note": note})
    decisions.sort(key=lambda r: r["id"])
    path.write_text("".join(json.dumps(r, ensure_ascii=False, separators=(",", ":")) + "\n" for r in decisions), encoding="utf-8")
    print(f"Recorded {len(NOTES)} direct reviews; total decisions {len(decisions)}")


if __name__ == "__main__":
    main()
