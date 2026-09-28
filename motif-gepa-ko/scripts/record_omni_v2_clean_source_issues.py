"""Preserve review notes about supplied English reference explanations.

Notes may describe an explicit contradiction or merely an abbreviated proof.
They are not a verdict on the official answer or a reason to suppress feedback.
The running English and Korean datasets are not edited.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


DATA = Path(__file__).resolve().parents[1] / "data" / "omni_v2_clean"
ISSUES = {
    "0020": ("incomplete_construction", "원문은 7개 점 배치라면서 정삼각형의 꼭짓점 3개와 변의 중점 3개만 제시한다."),
    "0844": ("arithmetic_contradiction", "원문은 AC^2-AD^2=41^2 뒤에 AC=840, AD=841이라고 썼다. 그러면 좌변은 음수다."),
    "1010": ("missing_final_transform", "원문은 넓이 23/9에서 끝난다. 문항이 요구하는 100m+n=2309 계산이 빠졌다."),
    "1776": ("logical_gap", "원문은 m=6이 최대라면서 n=420을 제시한다. 하지만 420의 세제곱근의 바닥값은 7이다."),
    "1780": ("arithmetic_contradiction", "원문 식 3*(2020+505)은 7575이며 제시한 답 3030과 다르다."),
    "1789": ("logical_gap", "높이에서 변의 비 5:4:3은 얻지만 크기 x=5를 도출하지 않고 넓이 150을 제시한다."),
    "1798": ("missing_proof", "원문은 12개가 가능하다고만 하고 구체적인 배치와 13개 불가능 증명을 제시하지 않는다."),
    "1814": ("missing_proof", "원문은 gcd(n,100) 조건에서 승리 출발 수 951로 가는 계산을 제시하지 않는다."),
    "1818": ("arithmetic_contradiction", "원문의 둘레 전개는 P(ABCD)+32와 서로 모순되는 식을 만들고 CD=10으로 비약한다."),
    "1827": ("missing_proof", "원문은 2013개 직선이 모든 점 배치에 충분하고 필요한 이유를 증명하지 않는다."),
    "1832": ("missing_construction", "1000쌍의 상호 초대를 달성하는 구체적인 배치를 제시하지 않는다."),
    "1847": ("arithmetic_error", "원문은 1부터 280까지의 짝수가 64개라고 하나 실제로는 140개다."),
    "1849": ("logical_contradiction", "양변에 인수가 남아야 한다면서 한쪽에서 인수 2016개 전부 지우는 경우를 사용한다."),
    "1855": ("counting_contradiction", "원문은 조합수 C(200,100)을 적고도 별도 계산 없이 규칙 수가 100이라고 결론짓는다."),
    "1870": ("arithmetic_and_logic_error", "원문은 C(120,4)=2550240이라 하나 실제 8214570이다. 모든 쌍이 친구인 배치는 약한 네쌍을 만들지 않는다."),
    "1883": ("logical_error", "행합 S, 열합 T가 각각 일정하다는 조건만으로 S=T라고 단정한다."),
    "1897": ("graph_argument_error", "원문은 방향 순환의 각 정점에 들어오는 간선이 2개라고 하나 일반적인 방향 순환에서는 1개다."),
    "1898": ("incorrect_equivalence", "원문은 (10^t-1)/(cm)이 유한소수 iff cm이 10^t-1을 나눈다고 하나 9/2 반례가 있다."),
}


def read(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> None:
    train = {r["id"]: r for r in read(DATA / "train.jsonl")}
    records = []
    for suffix, (kind, evidence) in ISSUES.items():
        identifier = f"HRM8K:OMNI-MATH:{suffix}"
        row = train[identifier]
        records.append({
            "id": identifier,
            "issue_type": kind,
            "evidence_ko": evidence,
            "source_solution_sha256": hashlib.sha256(row["solution_en"].encode("utf-8")).hexdigest(),
            "action": "source retained for parallel English/Korean experiments; interpret reference feedback cautiously",
        })
    path = DATA / "source_solution_issues.jsonl"
    path.write_text("".join(json.dumps(r, ensure_ascii=False, separators=(",", ":")) + "\n" for r in records), encoding="utf-8")
    print(f"Recorded {len(records)} source explanation issues")


if __name__ == "__main__":
    main()
