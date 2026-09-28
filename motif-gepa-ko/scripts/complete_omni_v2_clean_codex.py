"""Add the remaining directly translated Korean reference explanations.

These are condensed translations of the supplied English prose, not corrected
mathematical proofs. Source defects are recorded separately for later auditing.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path

from motif_gepa_ko.translation import quality_flags


DATA = Path(__file__).resolve().parents[1] / "data" / "omni_v2_clean"
TRANSLATIONS = DATA / "train_solutions_ko.jsonl"

DIRECT = {
    "1776": r"""조건은 양의 정수 \(n\)이 \(\sqrt[3]{n}\)보다 작은 모든 양의 정수로 나누어떨어지는 것이다. \(m=\lfloor\sqrt[3]{n}\rfloor\)로 놓고 \(1,2,\ldots,m\)의 최소공배수를 \(L_m\)이라 하면, 원문은 \(L_m\le m^3\)인 범위를 찾는다. \(m=6\)에서는 \(L_6=60\le216=6^3\)이고, \(m=7\)에서는 \(L_7=420>343=7^3\)이라고 계산한다. 이어서 원문은 최대 정수가 \(\operatorname{lcm}(1,2,\ldots,7)=420\)이라고 결론짓고 \(\boxed{420}\)을 제시한다.""",
    "1780": r"""한 변이 \(2020\)인 정육면체 안에 크기 \(1\times1\times2020\)인 막대를 놓는다. 각 막대는 \(x,y,z\)축 방향 가운데 하나를 따라 놓이며, 내부에서 다른 막대와 겹칠 수 없고, 접촉은 면을 통해서만 이루어진다. 한 방향에 가능한 막대 위치는 \(2020^2\)개이므로 세 방향을 합치면 \(3\times2020^2\)개의 후보 위치가 있다. 원문은 접촉 조건을 만족시키면서 막대 수를 줄이기 위해 세 방향에 막대를 배치하는 격자형 구성을 제안한다. 각 방향에 적어도 \(2020\)개가 필요하다고 주장한 뒤 \(3\times(2020+505)\)라는 식을 적고, 최종 답으로 \(\boxed{3030}\)을 제시한다.""",
    "1789": r"""삼각형의 높이가 각각 \(h_a=12,h_b=15,h_c=20\)이고, 대응하는 변의 길이를 \(a,b,c\), 넓이를 \(A\)라 하자. 넓이 공식에서 \(a\cdot12=b\cdot15=c\cdot20=2A=k\)이므로 \(a=k/12,b=k/15,c=k/20\)이다. 따라서 변의 길이 비는 \(a:b:c=1/12:1/15:1/20=5:4:3\)이다. 변을 \(5x,4x,3x\)로 놓으면 \(A=\tfrac12(5x)(12)=30x\)가 된다. 원문은 이 관계를 이용해 \(A=150\)이라고 결론짓고 \(\boxed{150}\)을 답으로 제시한다.""",
    "1798": r"""\(8\times8\) 판의 각 칸에 \(1\)부터 \(64\)까지의 서로 다른 수를 놓고, 네 칸의 합이 \(100\)보다 작은 \(2\times2\) 타일을 최대한 많이 만들려 한다. 모든 수의 합은 \(64\cdot65/2=2080\)이고, 판을 겹치지 않는 타일 \(16\)개로 완전히 덮으면 타일당 평균 합은 \(130\)이다. 따라서 모든 타일의 합이 \(100\)보다 작을 수는 없다. 원문은 작은 수를 유리한 위치에 두고 큰 수를 가장자리 등에 분산하는 배치를 설명하지만, 구체적인 배치나 상한 증명은 제시하지 않는다. 가능한 최대 개수로 \(\boxed{12}\)를 제시한다.""",
    "1814": r"""현재 계산기에 표시된 정수 \(n\)에서 \(m\in\{1,2,\ldots,99\}\)을 골라 \(n\)의 \(m\%\), 곧 \(mn/100\)을 계산한다. 결과가 정수가 되려면 \(100\mid mn\), 동치로 \(100/\gcd(100,m)\mid n\)이어야 한다. 원문은 이 나눗셈 조건으로 다음 수를 만들 수 있는지 판단하고, 경제학자가 먼저 둘 때 통계학자가 이기는 출발 수를 세려 한다. 후보 출발 수는 모두 \(2019\)개라고 한다. 서로소성과 나머지 조건으로 패배 위치를 여집합에서 세어야 한다고 설명하지만 구체적인 계산은 생략한다. 최종 승리 위치 수로 \(\boxed{951}\)을 제시한다.""",
    "1818": r"""사각형 \(ABCD\)에서 \(\angle ABC=\angle BCD=150^\circ\)이고, 바깥쪽에 정삼각형 \(APB,BQC,CRD\)를 그린다. \(AB=18,BC=24\)이며 \(P(APQRD)=P(ABCD)+32\)일 때 \(CD\)를 구한다. 먼저 \(P(ABCD)=AB+BC+CD+DA\)이고 \(P(APQRD)=AP+PQ+QR+RD+DA\)라고 둔다. 정삼각형에서 \(AP=AB=18\), \(BQ=BC=24\), \(CR=CD\)임을 사용한다. 원문은 이어서 \(PQ=QB=24\), \(RD=RC=CD\)라고 주장하고 둘레 식을 단순화하지만, 그 과정의 식들은 서로 맞지 않는다. 원문이 제시한 결론은 \(CD=\boxed{10}\)이다.""",
    "1827": r"""한 평면에 빨간 점 \(2013\)개와 파란 점 \(2014\)개가 있으며 어떤 세 점도 한 직선 위에 있지 않다. 점을 지나지 않는 직선 \(k\)개를 그어 각 영역이 한 색의 점만 포함하도록 만드는 데 필요한 최소 \(k\)를 찾는다. 원문은 한 색의 점을 다른 색의 점으로부터 각각 분리하는 전략을 생각한다. 빨간 점이 \(2013\)개이므로 최악의 배치에서 그 수만큼 직선이 필요하다고 주장하며, 더 적은 수의 직선으로는 두 색이 같은 영역에 남을 수 있다고 설명한다. 모든 배치에 대한 엄밀한 상한·하한 증명은 제시하지 않고 \(\boxed{2013}\)을 결론으로 낸다.""",
    "1832": r"""등록자 \(2000\)명 각각이 다른 \(1000\)명에게 친구 초대를 보낸다. 두 사람이 서로 초대한 경우에만 친구이므로, 전체 최소 친구 쌍의 수를 구한다. 사람을 정점, 초대를 방향 간선으로 보면 전체 초대는 \(2000\times1000=2000000\)개다. 한 쌍 사이에 양방향 간선이 모두 있으면 친구 쌍 하나로 센다. 원문은 초대 관계를 두 무리로 균형 있게 나누는 구성을 논하지만, 구체적인 그래프나 최소성 증명을 제시하지 않는다. \(2000/2=1000\)을 계산해 최소 친구 쌍의 수로 \(\boxed{1000}\)을 제시한다.""",
    "1847": r"""\(S=\{1,2,\ldots,280\}\)의 모든 \(n\)원소 부분집합에 서로 두 수씩 서로소인 다섯 수가 포함되도록 하는 최소 \(n\)을 찾는다. 원문은 먼저 그러한 다섯 수를 포함하지 않는 가장 큰 부분집합을 구성하려 한다. 작은 소수 \(2,3,5,7,\ldots\)의 배수들을 이용해 서로소인 수 다섯 개가 동시에 뽑히지 않게 하는 방식을 설명한다. 예로 \(2,4,6,\ldots,280\), \(3,6,9,\ldots,279\) 같은 배수열을 제시한다. 그러나 배수들의 중복을 반영한 정확한 구성과 상한 계산은 생략한다. 원문은 결론적으로 필요한 최소 크기가 \(\boxed{217}\)이라고 한다.""",
    "1849": r"""양변이 모두 \((x-1)(x-2)\cdots(x-2016)\)인 식에서 인수 일부를 지우되, 양변에 적어도 하나의 인수가 남고 실수해가 없어지도록 하려 한다. 원래 식은 항등식이므로 모든 실수가 해이다. 원문은 양변에서 같은 인수를 동일하게 지우면 항등식이 유지되며, 균형을 깨는 방식으로 지워야 한다고 설명한다. 한쪽에서 \(2015\)개, 다른 쪽에서 \(2016\)개를 지우는 경우를 논해 합계 \(4031\)을 적었다가, 다시 \(k=2015\)라고 쓰고 마지막에는 \(\boxed{2016}\)을 결론으로 제시한다. 이 수치 전개는 원문 안에서도 서로 일치하지 않는다.""",
    "1855": r"""두 카드 집합 \(A,B\)에는 각각 \(100\)장이 있다. 총 \(200\)장의 상대적 순서만으로 승자를 정하는 규칙을 센다. 모든 \(i\)에서 \(a_i>b_i\)이면 \(A\)가 이겨야 하고, 승리 관계는 추이적이어야 한다. 원문은 두 집합의 카드가 전체 순서에서 차지하는 자리를 섞어 배열하고, 그 순서에 따라 순위 규칙을 정의하려 한다. \(A\)의 위치 \(100\)개를 고르는 방법 수로 \(\binom{200}{100}\)을 언급한 뒤, 여러 배치가 같은 결과를 낸다고 설명한다. 그러나 중복을 제거하는 계산이나 규칙과의 일대일 대응은 보이지 않은 채, 최종 규칙 수로 \(\boxed{100}\)을 제시한다.""",
    "1883": r"""양의 정수 \(n\)의 모든 양의 약수를 서로 다른 칸에 하나씩 넣은 직사각형 표에서 모든 행의 합이 같고 모든 열의 합도 같도록 하려 한다. 약수의 수를 \(k\), 표의 행과 열 수를 \(r,c\)라 하면 \(k=rc\)다. 행별 합을 \(S\), 열별 합을 \(T\)라 놓으면 약수의 합 \(\sigma(n)=rS=cT\)이다. 원문은 여러 행과 열에 서로 다른 약수들을 균등하게 분배하기 어렵다고 설명하고, \(1\times1\) 표가 가능한 \(n=1\)을 확인한다. 다른 수가 불가능하다는 일반 증명은 제시하지 않고 \(\boxed{1}\)을 유일한 답으로 결론짓는다.""",
    "1898": r"""유리수의 십진 전개가 유한하면 ‘짧다’고 한다. 기약분수의 분모에 소인수 \(2,5\)만 있으면 유한소수다. 양의 정수 \(t\)가 \(m\)-tastic이려면 어떤 \(c\in\{1,2,\ldots,2017\}\)에 대하여 \((10^t-1)/(cm)\)은 짧고, 모든 \(1\le k<t\)에서는 \((10^k-1)/(cm)\)이 짧지 않아야 한다. 원문은 \(10^t-1=9(10^{t-1}+\cdots+1)\)의 인수분해와 나눗셈·합동 조건을 검토하라고 한다. 가능한 최소 지수들을 세어 \(S(m)\)의 최대 크기를 찾겠다는 방향만 설명하고 구체적인 구성과 상한 계산은 제시하지 않는다. 주장하는 최대 크기는 \(\boxed{807}\)이다.""",
}


def read(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> None:
    sources = {r["id"]: r for r in read(DATA / "train.jsonl")}
    translations = read(TRANSLATIONS)
    done = {r["id"] for r in translations}
    if len(done) != len(translations):
        raise ValueError("Duplicate translation ID")
    missing = set(sources) - done
    direct_ids = {f"HRM8K:OMNI-MATH:{suffix}" for suffix in DIRECT}
    if missing != direct_ids:
        raise ValueError(f"Unexpected missing IDs: {sorted(missing ^ direct_ids)}")
    at = datetime.now(timezone.utc).isoformat()
    for suffix, translation in DIRECT.items():
        identifier = f"HRM8K:OMNI-MATH:{suffix}"
        source = sources[identifier]["solution_en"]
        translations.append({
            "id": identifier,
            "solution_ko": translation,
            "source_solution_sha256": hashlib.sha256(source.encode("utf-8")).hexdigest(),
            "quality_flags": quality_flags(source, translation),
            "translator_model": "Codex",
            "translation_strategy": "codex_direct_condensed_translation",
            "review_status": "approved",
            "reviewed_by": "Codex",
            "reviewed_at_utc": at,
            "review_note": "영어 원문을 직접 읽고 한국어로 요약 번역했다. 원문의 논리적 공백과 모순은 보정하지 않고 설명에 명시했다.",
            "source_solution_issue": "원본 영어 해설의 논증에 공백 또는 내부 모순이 있음",
        })
    translations.sort(key=lambda r: r["id"])
    temp = TRANSLATIONS.with_suffix(".jsonl.tmp")
    temp.write_text("".join(json.dumps(r, ensure_ascii=False, separators=(",", ":")) + "\n" for r in translations), encoding="utf-8")
    os.replace(temp, TRANSLATIONS)
    print(f"Completed {len(DIRECT)} direct Korean translations; total {len(translations)}")


if __name__ == "__main__":
    main()
