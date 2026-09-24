"""Strict, inspectable scoring for integer-answer HRM8K subsets."""

from decimal import Decimal, InvalidOperation
import re

from gepa.adapters.default_adapter.default_adapter import EvaluationResult


_FINAL = re.compile(
    r"^\s*정답\s*:\s*([+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?)\s*\.?\s*$"
)


def extract_final_number(response: str) -> Decimal | None:
    """Read only the last nonblank line, never numbers in intermediate reasoning."""
    lines = response.strip().splitlines()
    if not lines:
        return None
    match = _FINAL.fullmatch(lines[-1])
    if match is None:
        return None
    try:
        return Decimal(match.group(1).replace(",", ""))
    except InvalidOperation:
        return None


def score_response(answer: str, response: str) -> tuple[float, str, str | None]:
    expected = Decimal(answer)
    parsed = extract_final_number(response)
    if parsed is None:
        return (
            0.0,
            "마지막 줄에서 `정답: 숫자` 형식을 찾지 못했습니다. 풀이를 검산하고 마지막 줄에 정수 답을 명확히 적으세요. "
            f"이 문제의 정답은 {answer}입니다.",
            None,
        )
    if parsed == expected:
        return 1.0, "정답입니다. 풀이와 최종 숫자 형식을 유지하세요.", str(parsed)
    return (
        0.0,
        f"최종 답 {parsed}은 오답이며 정답은 {answer}입니다. 문제의 조건, 단위, 계산과 마지막 대입을 다시 확인하세요.",
        str(parsed),
    )


class KoreanMathEvaluator:
    def __call__(self, data: dict, response: str) -> EvaluationResult:
        score, feedback, _ = score_response(data["answer"], response)
        return EvaluationResult(score, feedback)
