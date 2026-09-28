"""Replace manually identified defective Korean explanations with direct translations."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path

from motif_gepa_ko.translation import quality_flags


PATH = Path(__file__).resolve().parents[1] / "data" / "omni_v2_clean"
CORRECTIONS = {
    "0096": r"""\(DEGF\)를 \(AB\)와 한 변을 공유하는 작은 정사각형이라 하자. \(D,E\)는 \(AB\) 위에 있다. \(O\)는 \(\omega\)의 중심, \(K\)는 \(FG\)의 중점, \(H\)는 \(DEGF\)의 중심이다. 여섯 번째 정사각형의 넓이는 \(2\cdot\mathrm{OH}^{2}\)이다. \(KF=x\)라 놓자. \(KF^{2}+OK^{2}=OF^{2}\)이므로 \(x^{2}+(2x+5\sqrt{2})^{2}=10^{2}\)이다. 이를 풀면 \(x=\sqrt{2}\)를 얻는다. 따라서 \(OH=6\sqrt{2}\)이고, 구하는 넓이는 \(2\cdot OH^{2}=144\)이다.""",
    "0210": r"""순환 표기로 쓸 때 \(f\)와 \(g\)는 각각 길이가 \(1\)보다 큰 순환을 정확히 하나씩 가진다. \(f\)의 고정점이 \(k\)개라면 나머지 \(2012-k\)개 원소가 하나의 순환을 이루며, 그 순환을 정하는 방법은 \((2011-k)!\)가지다. \(f(a)=a\)이면 \(f(g(a))=g(f(a))=g(a)\)이므로 \(g(a)\) 역시 \(f\)의 고정점이다. 따라서 \(g\)는 \(f\)의 고정점 집합과 비고정점 집합을 각각 자기 자신으로 보낸다. \(g\)에는 길이가 \(1\)보다 큰 순환이 하나뿐이므로 두 집합 중 한쪽은 전부 고정해야 한다.

\(g\)가 \(f\)의 비고정점을 전부 고정하는 경우, \(f\)의 고정점 중 \(m\)개를 고정하고 나머지를 하나의 순환으로 만드는 방법은 \(\binom{k}{m}(k-m-1)!\)가지다. \(m=0,\ldots,k-2\)에 대해 합하면 \(\sum_{m=0}^{k-2}\frac{k!}{(k-m)m!}\)가지다. 반대로 \(g\)가 \(f\)의 고정점을 전부 고정하는 경우, \(f\)의 비고정점을 \(a_1,\ldots,a_{2012-k}\)로 놓아 \(f(a_i)=a_{i+1}\)라 하자. \(g(a_i)=a_j\)이면 가환성에 의해 \(g(a_{i+1})=a_{j+1}\)이므로 \(g\)는 순환상의 일정한 칸 수만큼 이동하는 형태다. 이 이동이 전체를 한 순환으로 만들려면 이동량이 \(2012-k\)와 서로소여야 하며, 가능한 수는 \(\phi(2012-k)\)개다.

이 두 경우를 더하고 허용되지 않는 \(g=f\)를 빼면, 고정점 수가 \(k\)인 \(f\) 하나에 대해 \(-1+\sum_{m=0}^{k-2}\frac{k!}{(k-m)m!}+\phi(2012-k)\)개의 \(g\)가 있다. 순열은 정확히 한 원소만 움직일 수 없으므로 \(k=0,\ldots,2010\)을 합산한다. 원문은 이를 \(2011\)로 나눈 나머지를 계산할 때 \(k=1\)항만 남는다고 하고, 윌슨 정리를 적용하여 최종 나머지 \(2\)를 얻는다.""",
    "0411": r"""우승할 수 있는 선수 가운데 가장 낮은 순위의 시드 번호 \(n\)을 구한다. 선수 \(x\)가 \(y\)를 직접 이기거나, \(x\)가 이긴 선수가 다시 다른 선수를 이기는 연쇄를 거쳐 \(y\)를 이겼다면 \(x\)가 \(y\)를 간접적으로 이겼다고 하자. 먼저 준결승에 오를 수 있는 가장 큰 시드 번호를 살핀다. 최종 우승자는 준결승의 선수 두 명을 이겨야 하므로, 그 가운데 두 번째로 좋은 선수도 이길 수 있어야 한다.

1번 시드를 간접적으로 이긴 선수의 시드를 최대화하려면 1번이 첫 라운드에서 4번에게, 4번이 다음 라운드에서 7번에게 지는 식으로 진행한다. 따라서 준결승에 오를 수 있는 최대 시드 번호는 \(3\cdot2011+1=6034\)다. 1번과 2번이 대진표의 서로 다른 사분면에 있다면 비슷한 논리로 준결승의 두 번째 선수에게 가능한 최대 시드는 6035번이고, 우승할 수 있는 시드의 최대 번호는 6038이다. 두 선수가 같은 사분면에 있으면 간접적으로 1번을 이긴 선수와 2번을 이긴 선수가 만나는 라운드에서는 시드 번호가 3씩 올라갈 수 없다. 따라서 그 사분면의 준결승 선수에게 가능한 최대 시드는 \(3\cdot2011-1=6032\)지만, 우승자는 그보다 최대 6만큼 높은 번호일 수 있어 여전히 상한은 6038이다.

원문은 6034, 6035, 6036, 6038번이 모두 준결승에 오르는 대진을 만들 수 있으므로 6038번도 우승할 수 있다고 한다. 또 그 대진에서 6038번의 위치를 더 낮은 번호 \(x\)와 바꾸면 그 선수도 우승할 수 있다고 설명한다. 따라서 우승 가능한 선수의 수는 6038명이다.""",
    "0525": r"""주어진 조건에서 계산할 합은 \(\displaystyle\sum_{i=0}^{3}\sum_{j=i}^{3}(10^{i}+10^{j})^{2}\)이다. 각 항을 전개하여 같은 \(10\)의 거듭제곱끼리 모으면, 원문에 따르면 \(10^{6}\)은 7번, \(10^{5}\)는 2번, \(10^{4}\)는 9번, \(10^{3}\)은 4번, \(10^{2}\)는 9번, \(10\)은 2번, \(1\)은 7번 나온다. 그러므로 원문은 답을 \(7294927\)이라고 한다.""",
    "0551": r"""순열 \(\pi\)의 순환을 살펴보자. \(\operatorname{ord}_{\pi}(n)\)은 \(\pi^{m}(n)=n\)을 만족하는 가장 작은 양의 정수 \(m\)이다. 주어진 조건에서 \(\operatorname{ord}_{\pi}(20)\mid20\), \(\operatorname{ord}_{\pi}(21)\mid21\)이다. 첫째, 20과 21은 같은 순환에 있을 수 없다. 같은 순환의 길이를 \(x\)라 하면 \(x>1\)이지만 \(x\mid20\)이고 \(x\mid21\)이므로 \(x=1\)이어야 하여 모순이다.

둘째, 길이가 각각 \(a,b\)인 서로 다른 순환에 20과 21이 들어 있고 \(a+b\le100\)인 경우의 확률을 센다. 나머지 98명 중 20의 순환에 넣을 \(a-1\)명과 21의 순환에 넣을 \(b-1\)명을 고른다. 각 순환 내부를 배열하는 방법은 \((a-1)!\), \((b-1)!\)가지이고, 남은 원소들의 순열은 \((100-a-b)!\)가지다. 따라서 전체 경우의 수는 \(\frac{98!}{(a-1)!(b-1)!(100-a-b)!}(a-1)!(b-1)!(100-a-b)!=98!\)이며 확률은 \(98!/100!=1/9900\)이다. 20의 약수는 6개, 21의 약수는 4개이므로 허용되는 \((a,b)\)가 24개다. 따라서 구하는 확률은 \(24/9900=2/825\)이다.""",
    "0882": r"""답은 72다. 72의 ‘primer’ 약수는 \(6,12,24,18,36,72\)로 여섯 개이고, 6 역시 서로 다른 소인수가 두 개인 primer 수이므로 72는 ‘primest’ 수다. 이제 72보다 작은 primest 수가 없음을 보인다. \(r<72\)가 그러한 수라고 가정하고 서로 다른 소인수의 개수로 경우를 나눈다.

서로 다른 소인수가 네 개 이상이면 \(r\ge2\cdot3\cdot5\cdot7=210>72\)이므로 불가능하다. 세 개이고 모두 지수가 1이라면 \(r=pqs\)이다. 이때 primer 약수는 \(pq,qs,sp,pqs\) 네 개뿐인데, 4는 primer 수가 아니다. 한 소인수의 지수가 2 이상인 최소 형태 \(r=p^{2}qs\)에는 \(pq,qs,sp,pqs,p^{2}q,sp^{2},p^{2}qs\)의 일곱 primer 약수가 있지만 7 역시 primer 수가 아니다. 지수의 합이 5 이상인 나머지 형태는 \(r\ge2^{3}\cdot3\cdot5=120>72\)다.

서로 다른 소인수가 두 개이고 \(r=p^{a}q^{b}\)이면 primer 약수는 \(p^{i}q^{j}\;(1\le i\le a,1\le j\le b)\) 꼴이므로 정확히 \(ab\)개다. 원문은 \(ab\)가 primer 수가 되려면 \(ab\ge6\)이어야 하며, 나머지 작은 경우를 제외하면 \(r\ge2^{3}\cdot3^{2}=72\)라고 설명한다. 소인수가 하나뿐인 수에는 primer 약수가 없으므로 불가능하다. 따라서 가장 작은 primest 수는 \(\boxed{72}\)다.""",
    "1087": r"""\(A=f(\{1,2,3\})\)라 하자. \(A\cap f(A)=\varnothing\)이므로 \(A\subseteq\{4,5\}\)다. \(A=\{4,5\}\)이면 \(\{1,2,3\}\)의 원소를 \(\{4,5\}\)로 보내는 전사 함수가 \(2^{3}-2=6\)개이고, 4와 5의 값을 \(\{1,2,3\}\)에서 고르는 방법이 9개여서 모두 54개다. \(A=\{4\}\)라면 1, 2, 3의 상은 모두 4로 정해지고, \(f(4)\)는 \(\{1,2,3,5\}\)에서 4가지, \(f(5)\)는 5가지로 정할 수 있어 20개다. \(A=\{5\}\)일 때도 20개이므로 총 \(54+20\cdot2=94\)개다.""",
    "1113": r"""\(i<j<k\)인 세 원소 \((i,j,k)\)를 하나 고정하고 이를 회전시키는 순열의 수를 센다. \(\pi(i),\pi(j),\pi(k)\)가 취할 세 값의 집합을 고르는 방법은 \(\binom{10}{3}\)가지이며, 그 집합을 정하면 세 상의 순서가 결정된다. 나머지 일곱 값은 임의로 배열할 수 있으므로 \(7!\)가지다. 따라서 고정한 세 원소를 회전시키는 순열은 \(\binom{10}{3}7!\)개다. 세 원소 자체의 선택도 \(\binom{10}{3}\)가지이므로 전체 회전된 세 원소의 수는 \(\binom{10}{3}^{2}\cdot7!=72576000\)이다.""",
}


def read(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> None:
    source = {r["id"]: r for r in read(PATH / "train.jsonl")}
    target = PATH / "train_solutions_ko.jsonl"
    rows = read(target)
    by_id = {r["id"]: r for r in rows}
    if len(rows) != 1000 or len(by_id) != 1000:
        raise ValueError("Expected 1,000 unique translations")
    at = datetime.now(timezone.utc).isoformat()
    for suffix, text in CORRECTIONS.items():
        identifier = f"HRM8K:OMNI-MATH:{suffix}"
        row = by_id[identifier]
        source_text = source[identifier]["solution_en"]
        original_hash = hashlib.sha256(row["solution_ko"].encode("utf-8")).hexdigest()
        if row.get("previous_translation_sha256") and row["solution_ko"] == text:
            continue
        if row["solution_ko"] == text:
            continue
        row["previous_translation_sha256"] = original_hash
        row["solution_ko"] = text
        row["quality_flags"] = quality_flags(source_text, text)
        row["translation_strategy"] = "codex_manual_correction"
        row["review_status"] = "approved"
        row["reviewed_by"] = "Codex"
        row["reviewed_at_utc"] = at
        row["review_note"] = "Codex가 영어 원문과 기존 한국어 번역을 직접 대조하여 문장, 수식 표기와 누락을 수정했다."
    temp = target.with_suffix(".jsonl.tmp")
    temp.write_text("".join(json.dumps(r, ensure_ascii=False, separators=(",", ":")) + "\n" for r in rows), encoding="utf-8")
    os.replace(temp, target)
    print("Directly corrected:", ", ".join(CORRECTIONS))


if __name__ == "__main__":
    main()
