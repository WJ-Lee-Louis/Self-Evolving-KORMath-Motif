"""Render self-contained, verbatim prompt histories from archived GEPA lineages."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

RUNS = {
    "en": {
        "id": "en-omni-v2-clean-b600-t720-s0",
        "iterations": ["seed", 4, 8, 19, 20, 22, 28],
        "pareto": {0, 4, 6},
        "notes": {
            0: "초기 지시문이다. 영어 단계별 풀이, 조건·계산 검산, 마지막 줄의 정수 답 형식만 요구한다.",
            1: "대수 조작·부등식·체계적 탐색을 풀이 방법으로 추가하고, 모든 제약 확인과 여러 부분 중 마지막 부분의 정수 답 출력을 명시했다.",
            2: "조건과 추론의 재검산을 더 강하게 요구하고, 경우 나누기·조합 공식·대수 조작과 풀이의 완전성을 예시로 추가했다. 답 형식의 구체적 예시도 넣었다.",
            3: "문제 조건 명시, 중간 계산과 근거 전부 제시, 대상 집합을 실제로 사용, 추측 대신 유도, 마지막 줄에 추가 문구 금지라는 점검표로 확장했다.",
            4: "부등식이나 식을 세운 뒤 중도에 멈추지 말고 끝까지 풀도록 하고, 중간 계산의 일관성과 최종 답 형식을 다시 확인하도록 추가했다.",
            5: "변수·조건을 식으로 옮기기, 경계 사례, 최적성·존재성 증명, 빠짐없는 계수와 포함배제, 원문 대입 검증 등 폭넓은 검사 목록을 덧붙였다.",
            6: "풀이 중단·수학 표기·검산·답 형식에 관한 반성문과 수정 지시문을 통째로 덧붙였다. 실제 프롬프트에는 사례 번호와 마크다운 코드 펜스도 남아 있다.",
        },
        "intro": (
            "GEPA의 기본 최종 선택은 **#0(초기 프롬프트, 38/50)**이다. "
            "#4도 38/50으로 동률이며, 별도 사전 규칙 `latest_val_tie`로 시작한 test 평가는 #4를 비교 대상으로 삼았다. "
            "이 규칙은 GEPA의 `best_idx`를 바꾸지 않는다."
        ),
        "flow": (
            "주요 연쇄는 **#0→#1→#4→#5**다. 풀이 방법 지정에서 시작해 풀이 완결을 요구하고, "
            "마지막에는 검증 목록을 크게 늘렸다. #2·#3·#6은 #0에서 각각 독립적으로 갈라진 가지다."
        ),
    },
    "ko": {
        "id": "ko-omni-v2-clean-b600-t720-s0",
        "iterations": ["seed", 3, 5, 8, 9, 10, 12, 14, 15],
        "pareto": {1, 6, 7},
        "notes": {
            0: "초기 지시문이다. 한국어로 차근차근 풀고 계산·조건을 검산한 뒤 정수 답 형식으로 끝내도록 요구한다.",
            1: "작은 사례 점검, 패턴·시뮬레이션 대신 불변량·조합 논증·정리 사용, 정확한 계산·오차 범위, 바닥 함수와 정수 조건 재확인을 추가했다.",
            2: "게임·반복 과정의 종료 여부를 유한 상태·불변량·단조 감소량으로 증명하라는 조항과 한국어 풀이 명시를 더했다. `FINAL_ANSWER: 없음` 허용도 추가돼 정수 채점 형식과 어긋날 수 있다.",
            3: "모든 경우를 빠짐없이 보도록 하고, 조합 문제의 체계적 열거·대칭성 활용과 다른 방법 또는 작은 경우를 통한 재검증을 추가했다.",
            4: "문제 해석을 여러 가지로 검토하도록 확장하면서, 새 체스 말의 공격 관계와 표준 체스 이동을 가정하지 말라는 특정 문제의 조건을 지시문에 넣었다.",
            5: "정답 형식을 `반드시` 지키고 답을 내기 전에 완전한 풀이를 제시하며, 답이 주어졌다면 그 답의 유도 과정을 쓰도록 덧붙였다.",
            6: "조건의 수학적 표현, 중간 결과 검증, 제약 만족, 대칭에 따른 중복 제거, 부등식·덮개 논증으로 상한 구하기, 답 암기 지양을 추가했다.",
            7: "문제의 모든 조건 반영과 풀이·결과 검증을 강화했다. 동시에 부모의 명시적 `한국어로` 지시를 빼고, 풀이 때 제공되지 않는 모범해설과 일치하는지도 살피라고 덧붙였다.",
            8: "게임 이론 문제에서 상대의 모든 선택을 검토하고 자신의 전략이 최적인지 검증하라는 지시를 추가했다.",
        },
        "intro": (
            "최고 검증 성적은 **#6(35/50)**이며 초기 #0(31/50)에서 직접 갈라졌다. "
            "노드가 더 깊다고 검증 점수가 반드시 높아지는 것은 아니다."
        ),
        "flow": (
            "#0에서 #1·#3·#6이 갈라졌다. #1에서는 #2, #3에서는 #4·#5·#7이 파생됐고, #7에서 다시 #8이 나왔다. "
            "최종 #6은 앞선 긴 가지를 거치지 않고 초기 지시문에 일반적인 수학 검증 절차를 추가했다."
        ),
    },
}


def render(language: str) -> tuple[Path, str]:
    spec = RUNS[language]
    run_id = spec["id"]
    source = ROOT / "runs" / run_id
    if language == "en":
        source /= run_id
    lineage = json.loads((source / "lineage.json").read_text(encoding="utf-8"))
    candidates = json.loads((source / "candidates.json").read_text(encoding="utf-8"))
    nodes = lineage["nodes"]
    tree_path = ROOT / "reports" / run_id / "GENETIC_TREE.md"
    tree_rows = {}
    for line in tree_path.read_text(encoding="utf-8").splitlines():
        columns = [part.strip() for part in line.split("|")[1:-1]]
        if len(columns) == 6 and columns[0].startswith("#"):
            tree_rows[int(columns[0][1:])] = columns
    expected = set(range(len(nodes)))
    if set(spec["notes"]) != expected or len(spec["iterations"]) != len(nodes):
        raise ValueError(f"Candidate annotations are incomplete for {language}")
    if set(tree_rows) != expected:
        raise ValueError(f"Genetic tree and lineage disagree for {language}")
    if lineage["run_id"] != run_id or len(candidates) != len(nodes):
        raise ValueError(f"Run sources are inconsistent for {language}")

    title = "영어" if language == "en" else "한국어"
    lines = [
        f"# {title} GEPA 시스템 프롬프트 진화 기록",
        "",
        "![후보 프롬프트 계보도](genetic_tree.svg)",
        "",
        f"실행 ID: `{run_id}`. 이 문서는 **채택돼 후보 풀에 들어간 노드만** 다룬다. "
        "채택되지 않은 제안은 실행 기록의 `attempt_timeline.md`에 남아 있다. "
        "아래 프롬프트는 `lineage.json`의 `system_prompt`를 개행과 문구까지 그대로 옮겼으며, "
        "각 SHA-256을 검증했다.",
        "",
        "`runs/`는 Git 추적 대상이 아니다. 맨 아래 원본 기록 링크는 실행 아티팩트를 로컬에 내려받은 환경에서만 열린다. "
        "프롬프트 전문과 점수표는 이 문서만으로 확인할 수 있다.",
        "",
        spec["intro"],
        "",
        spec["flow"],
        "",
        "표의 성적은 동일한 **validation 50문항**에 대한 결과다. "
        "자식 후보의 채택은 해당 반복의 미니배치 평가에 따른 것이므로 validation 점수가 부모보다 낮을 수 있다. "
        "아래 변화 설명은 프롬프트 문자열을 비교한 것이며, 특정 문구가 점수 변화를 일으켰다는 인과적 결론은 아니다.",
        "",
        "| 노드 | 부모 | 채택 반복 | validation | Pareto | GEPA 최종 선택 |",
        "|---:|---:|---:|---:|:---:|:---:|",
    ]
    for node in nodes:
        index = node["candidate_idx"]
        if index not in expected:
            raise ValueError("Candidate indices must be consecutive")
        parents = node["parent_candidate_indices"]
        if len(parents) > 1:
            raise ValueError("This report expects one parent per non-seed candidate")
        parent = f"#{parents[0]}" if parents else "—"
        prompt = node["system_prompt"]
        digest = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        if (digest != node["prompt_sha256"]
                or prompt != candidates[index]["system_prompt"]):
            raise ValueError(f"Prompt source or SHA-256 mismatch: {language} #{index}")
        score = round(node["val_accuracy"] * 50)
        if node["val_examples_scored"] != 50 or abs(score / 50 - node["val_accuracy"]) > 1e-9:
            raise ValueError(f"Validation score mismatch: {language} #{index}")
        tree = tree_rows[index]
        if (tree[1] != str(spec["iterations"][index])
                or tree[2] != parent
                or not tree[3].startswith(f"{score}/50 ")
                or tree[4] != ("예" if index in spec["pareto"] else "아니요")
                or tree[5] != ("예" if index == lineage["best_candidate_idx"] else "아니요")):
            raise ValueError(f"Genetic tree metadata mismatch: {language} #{index}")
        lines.append(
            f"| [#{index}](#노드-{index}) | {parent} | {spec['iterations'][index]} | "
            f"{score}/50 ({score * 2}%) | "
            f"{'예' if index in spec['pareto'] else '아니요'} | "
            f"{'예' if index == lineage['best_candidate_idx'] else '아니요'} |"
        )
    lines.append("")

    for node in nodes:
        index = node["candidate_idx"]
        parents = node["parent_candidate_indices"]
        parent = f"#{parents[0]}" if parents else "없음 (초기 프롬프트)"
        lines += [
            f"## 노드 {index}",
            "",
            f"**부모:** {parent} · **채택 반복:** {spec['iterations'][index]} "
            f"(`{node['iteration_id']}`) · **검증:** {round(node['val_accuracy'] * 50)}/50",
            "",
            f"**부모 대비 변화:** {spec['notes'][index]}",
            "",
            f"**원문 SHA-256:** `{node['prompt_sha256']}`",
            "",
            "**시스템 프롬프트 전문:**",
            "",
            "````text",
            node["system_prompt"],
            "````",
            "",
        ]

    relative_source = "../../runs/" + run_id + ("/" + run_id if language == "en" else "")
    lines += [
        "## 원본 기록",
        "",
        f"- [lineage.json]({relative_source}/lineage.json): 부모 관계, 검증 점수, 프롬프트 전문, SHA-256",
        f"- [candidates.json]({relative_source}/candidates.json): GEPA 후보 목록",
        f"- [attempt_timeline.md]({relative_source}/attempt_timeline.md): 거절된 제안을 포함한 전체 반복 기록",
        "- [GENETIC_TREE.md](GENETIC_TREE.md): Pareto 표시와 선택 후보의 계보 요약",
        "",
    ]
    destination = ROOT / "reports" / run_id / "PROMPT_EVOLUTION.md"
    return destination, "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Compare with existing reports")
    args = parser.parse_args()
    for language in ("en", "ko"):
        path, content = render(language)
        if args.check:
            if path.read_text(encoding="utf-8") != content:
                raise SystemExit(f"Outdated or missing report: {path}")
        else:
            path.write_text(content, encoding="utf-8")
        print(path)


if __name__ == "__main__":
    main()
