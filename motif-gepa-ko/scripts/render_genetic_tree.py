"""Render a completed single-prompt GEPA run as a paper-style search tree.

Example:
    python scripts/render_genetic_tree.py runs/<run-id>/<run-id> reports/<run-id>

The renderer applies the same dominated-program removal as GEPA's official
candidate-tree visualization to the saved per-instance frontier.
"""

from __future__ import annotations

import argparse
import html
import json
import math
from pathlib import Path

from gepa.gepa_utils import find_dominator_programs


SELECTED = "#1bd9e5"
FRONTIER = "#ffad08"
OTHER = "#d9d9d9"
STROKE = "#202020"
NODE_RADIUS = 68
LEAF_SPACING = 218
LEVEL_SPACING = 206
LEFT_MARGIN = 125
TOP_MARGIN = 190


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def prepare(run_dir: Path) -> dict:
    lineage = read_json(run_dir / "lineage.json")
    state = read_json(run_dir / "gepa_state.json")
    summary = read_json(run_dir / "summary.json")
    result = read_json(run_dir / "gepa_result.json")
    audit = read_json(run_dir / "audit.json")
    nodes = {int(row["candidate_idx"]): row for row in lineage["nodes"]}
    if set(nodes) != set(range(len(nodes))):
        raise ValueError("Candidate indices are not contiguous from zero")

    children: dict[int, list[int]] = {idx: [] for idx in nodes}
    for edge in lineage["edges"]:
        parent = int(edge["parent_candidate_idx"])
        child = int(edge["child_candidate_idx"])
        children[parent].append(child)
    for descendants in children.values():
        descendants.sort()

    iteration_by_candidate = {0: 0}
    for proposal in lineage["proposal_nodes"]:
        child = proposal.get("child_candidate_idx")
        if child is not None and proposal.get("decision") == "accepted":
            iteration_by_candidate[int(child)] = int(proposal["iteration"])
    if set(iteration_by_candidate) != set(nodes):
        raise ValueError("An accepted candidate lacks its GEPA iteration number")

    raw_frontier_ids = set(state["summary"]["pareto_front_iteration_ids"])
    raw_frontier = {
        idx for idx, row in nodes.items() if row["iteration_id"] in raw_frontier_ids
    }
    per_instance_front = {
        val_id: set(candidate_ids)
        for val_id, candidate_ids in result["per_val_instance_best_candidates"].items()
    }
    scores_list = list(result["val_aggregate_scores"])
    if len(scores_list) != len(nodes):
        raise ValueError("The saved GEPA scores do not match the candidate tree")
    frontier = set(find_dominator_programs(per_instance_front, scores_list))
    if not frontier.issubset(raw_frontier):
        raise ValueError("The plotted frontier is absent from the saved state")
    best_idx = int(summary["best_idx"])
    if best_idx not in nodes:
        raise ValueError("Selected candidate is absent from the lineage")
    # Each accepted mutation has one parent in this single-prompt experiment.
    for idx, row in nodes.items():
        expected = 0 if idx == 0 else 1
        if len(row["parent_candidate_indices"]) != expected:
            raise ValueError("This renderer requires a single-parent mutation tree")

    leaf_counter = 0
    positions: dict[int, tuple[float, float]] = {}

    def place(idx: int, depth: int) -> float:
        nonlocal leaf_counter
        if children[idx]:
            child_x = [place(child, depth + 1) for child in children[idx]]
            x = (child_x[0] + child_x[-1]) / 2
        else:
            x = LEFT_MARGIN + leaf_counter * LEAF_SPACING
            leaf_counter += 1
        positions[idx] = (x, TOP_MARGIN + depth * LEVEL_SPACING)
        return x

    place(0, 0)
    if set(positions) != set(nodes):
        raise ValueError("The lineage is disconnected from the seed candidate")
    width = max(680, LEFT_MARGIN * 2 + (leaf_counter - 1) * LEAF_SPACING)
    height = max(y for _, y in positions.values()) + NODE_RADIUS + 108
    scores = {idx: float(row["val_accuracy"]) for idx, row in nodes.items()}
    best_score = max(scores.values())
    tied_best = [idx for idx in nodes if math.isclose(scores[idx], best_score)]

    return {
        "run_id": summary["run_id"],
        "nodes": nodes,
        "edges": lineage["edges"],
        "positions": positions,
        "iterations": iteration_by_candidate,
        "frontier": frontier,
        "raw_frontier": raw_frontier,
        "best_idx": best_idx,
        "gepa_best_idx": best_idx,
        "selection_policy": "gepa",
        "tied_best": tied_best,
        "width": width,
        "height": height,
        "metric_calls": int(summary["gepa_metric_calls"]),
        "iteration_count": int(audit["iteration_count"]),
        "proposal_count": int(audit["proposal_count"]),
    }


def render_svg(data: dict) -> str:
    width, height = data["width"], data["height"]
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width:.0f} {height:.0f}" '
        'role="img" aria-label="GEPA accepted candidate genetic tree">',
        '<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" '
        'markerWidth="8" markerHeight="8" orient="auto-start-reverse">'
        f'<path d="M 0 0 L 10 5 L 0 10 z" fill="{STROKE}"/></marker></defs>',
        '<rect width="100%" height="100%" fill="#fff"/>',
        f'<text x="{width/2:.1f}" y="39" text-anchor="middle" '
        'font-family="Arial, sans-serif" font-size="22" font-weight="700">'
        'GEPA candidate genetic tree</text>',
        f'<text x="{width/2:.1f}" y="66" text-anchor="middle" '
        'font-family="Arial, sans-serif" font-size="14" fill="#555">'
        f'{html.escape(data["run_id"])} · {data["iteration_count"]} iterations · '
        f'{data["metric_calls"]} metric calls</text>',
    ]
    for edge in data["edges"]:
        x1, y1 = data["positions"][int(edge["parent_candidate_idx"])]
        x2, y2 = data["positions"][int(edge["child_candidate_idx"])]
        dx, dy = x2 - x1, y2 - y1
        distance = math.hypot(dx, dy)
        ux, uy = dx / distance, dy / distance
        parts.append(
            f'<line x1="{x1+ux*NODE_RADIUS:.2f}" y1="{y1+uy*NODE_RADIUS:.2f}" '
            f'x2="{x2-ux*(NODE_RADIUS+3):.2f}" y2="{y2-uy*(NODE_RADIUS+3):.2f}" '
            f'stroke="{STROKE}" stroke-width="1.5" marker-end="url(#arrow)"/>'
        )
    for idx, node in data["nodes"].items():
        x, y = data["positions"][idx]
        selected = idx == data["best_idx"]
        fill = SELECTED if selected else FRONTIER if idx in data["frontier"] else OTHER
        count = int(node["val_examples_scored"])
        correct = round(float(node["val_accuracy"]) * count)
        percent = float(node["val_accuracy"]) * 100
        iteration_label = "seed · iter 0" if idx == 0 else f'iter {data["iterations"][idx]}'
        parts.extend([
            f'<a href="#candidate-{idx}" aria-label="Candidate {idx}, validation {correct} of {count}">',
            f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{NODE_RADIUS}" '
            f'fill="{fill}" stroke="{STROKE}" stroke-width="1.7"/>',
            f'<text x="{x:.2f}" y="{y-20:.2f}" text-anchor="middle" '
            'font-family="Arial, sans-serif" font-size="24" font-weight="700">'
            f'{idx}</text>',
            f'<text x="{x:.2f}" y="{y+2:.2f}" text-anchor="middle" '
            'font-family="Arial, sans-serif" font-size="14">'
            f'{html.escape(iteration_label)}</text>',
            f'<text x="{x:.2f}" y="{y+28:.2f}" text-anchor="middle" '
            'font-family="Arial, sans-serif" font-size="17">'
            f'{correct}/{count} ({percent:.0f}%)</text>',
            '</a>',
        ])
        if selected:
            label_x = x if idx == 0 else x + NODE_RADIUS + 10
            label_y = y - NODE_RADIUS - 13 if idx == 0 else y - NODE_RADIUS + 12
            label_anchor = "middle" if idx == 0 else "start"
            parts.append(
                f'<text x="{label_x:.2f}" y="{label_y:.2f}" '
                f'text-anchor="{label_anchor}" '
                'font-family="Arial, sans-serif" font-size="13" font-weight="700" '
                f'fill="#087b87">{"TEST SELECTED" if data["selection_policy"] != "gepa" else "FINAL SELECTED"}</text>'
            )
        elif idx in data["tied_best"]:
            parts.append(
                f'<text x="{x+NODE_RADIUS+10:.2f}" y="{y-NODE_RADIUS+12:.2f}" '
                'text-anchor="start" '
                'font-family="Arial, sans-serif" font-size="13" font-weight="700" '
                'fill="#a76700">TIED TOP SCORE</text>'
            )
    legend_y = height - 43
    parts.append(
        f'<g font-family="Arial, sans-serif" font-size="14">'
        f'<circle cx="115" cy="{legend_y}" r="9" fill="{SELECTED}" stroke="{STROKE}"/>'
        f'<text x="132" y="{legend_y+5}">'
        f'{"test selected" if data["selection_policy"] != "gepa" else "final selected"}</text>'
        f'<circle cx="392" cy="{legend_y}" r="9" fill="{FRONTIER}" stroke="{STROKE}"/>'
        f'<text x="409" y="{legend_y+5}">Pareto frontier</text>'
        f'<circle cx="622" cy="{legend_y}" r="9" fill="{OTHER}" stroke="{STROKE}"/>'
        f'<text x="639" y="{legend_y+5}">other candidate</text>'
        '</g>'
    )
    parts.append('</svg>')
    return "\n".join(parts) + "\n"


def render_html(data: dict, svg: str) -> str:
    rows = []
    details = []
    for idx, node in data["nodes"].items():
        parent = node["parent_candidate_indices"]
        status = "최종 선정; Pareto" if idx == data["best_idx"] else (
            "Pareto" if idx in data["frontier"] else "Pareto 외"
        )
        count = int(node["val_examples_scored"])
        correct = round(float(node["val_accuracy"]) * count)
        rows.append(
            f'<tr><td><a href="#candidate-{idx}">#{idx}</a></td>'
            f'<td>{"seed" if idx == 0 else data["iterations"][idx]}</td>'
            f'<td>{"—" if not parent else "#" + str(parent[0])}</td>'
            f'<td>{correct}/{count} ({100*float(node["val_accuracy"]):.0f}%)</td>'
            f'<td>{html.escape(status)}</td></tr>'
        )
        details.append(
            f'<details id="candidate-{idx}"><summary>후보 #{idx} · '
            f'{correct}/{count} · {html.escape(status)}</summary>'
            f'<p>GEPA 반복: {data["iterations"][idx]}; '
            f'부모: {"초기" if not parent else "#" + str(parent[0])}; '
            f'iteration ID: <code>{html.escape(node["iteration_id"])}</code></p>'
            f'<pre>{html.escape(node["system_prompt"])}</pre></details>'
        )
    return f'''<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>GEPA genetic tree — {html.escape(data["run_id"])}</title>
<style>
body{{font-family:Arial,sans-serif;color:#202020;max-width:1100px;margin:2rem auto;padding:0 1rem;line-height:1.5}}
h1{{font-size:1.6rem}} .chart{{overflow-x:auto;border:1px solid #ddd;border-radius:8px}}
.chart svg{{width:100%;min-width:700px;height:auto}} .chart a{{cursor:pointer}}
table{{border-collapse:collapse;width:100%;margin:1.5rem 0}} th,td{{padding:.55rem .7rem;border-bottom:1px solid #ddd;text-align:left}}
th{{background:#f5f5f5}} details{{border:1px solid #ddd;border-radius:6px;margin:.55rem 0;padding:.6rem .8rem}}
summary{{cursor:pointer;font-weight:600}} pre{{white-space:pre-wrap;overflow-wrap:anywhere;background:#f7f7f7;padding:1rem}}
.note{{background:#f5fbfc;border-left:4px solid #1bd9e5;padding:.7rem 1rem}}
</style></head><body>
<h1>GEPA 프롬프트 진화 트리</h1>
<p>실행: <code>{html.escape(data["run_id"])}</code>. 노드를 클릭하면 해당 시스템 프롬프트 전문으로 이동합니다.</p>
<div class="chart">{svg}</div>
<p class="note">색 분류는 GEPA의 공식 트리 시각화와 같습니다. 저장된 문항별 최고점 후보에서
지배 후보를 제거한 후 Pareto 후보를 주황색으로, 최종 선정 후보를 청록색으로 표시합니다.
원시 후보 {len(data["raw_frontier"])}개 중 그림의 Pareto 후보는 {len(data["frontier"])}개입니다.
{f'이번 그림은 test 평가용 동률 해소 규칙에 따라 #{data["best_idx"]}을 강조합니다. GEPA 기본 최종 선택은 #{data["gepa_best_idx"]}입니다.' if data["selection_policy"] != "gepa" else ''}</p>
<h2>후보별 검증 성적</h2>
<table><thead><tr><th>후보</th><th>GEPA 반복</th><th>부모</th><th>검증</th><th>구분</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table>
<h2>시스템 프롬프트 전문</h2>{''.join(details)}
<script>
document.querySelectorAll('.chart a[href^="#candidate-"]').forEach(link => {{
  link.addEventListener('click', () => {{
    const detail = document.querySelector(link.getAttribute('href'));
    if (detail) detail.open = true;
  }});
}});
</script>
</body></html>
'''


def render_markdown(data: dict) -> str:
    lines = [
        f'# GEPA 프롬프트 진화 트리: `{data["run_id"]}`',
        '',
        '![후보 프롬프트 계보도](genetic_tree.svg)',
        '',
        f'- 총 **{data["iteration_count"]}회 반복**, 제안 **{data["proposal_count"]}개**, '
        f'평가 호출 **{data["metric_calls"]}회**.',
        f'- {"test 평가 선정" if data["selection_policy"] != "gepa" else "GEPA 최종 선정"} '
        f'후보: **#{data["best_idx"]}** (청록색).',
        f'- 공식 GEPA 트리 시각화와 같은 지배 후보 제거 후 Pareto 후보: '
        f'**{len(data["frontier"])}개**. 최종 선정 후보도 이 수에 포함된다.',
        f'- 저장된 원시 문항별 최고점 후보의 합집합: **{len(data["raw_frontier"])}개**. '
        '모두 틀린 문항에서의 0점 동률도 포함하므로 이 집합을 그대로 색칠하지 않는다.',
        '- 노드의 큰 숫자는 후보 번호다. `iter`는 해당 후보가 채택된 실제 GEPA 반복 번호다.',
        '',
        '| 후보 | 채택된 반복 | 부모 | 검증 성적 | Pareto | 최종 선정 |',
        '|---:|---:|---:|---:|:---:|:---:|',
    ]
    for idx, node in data["nodes"].items():
        parent = node["parent_candidate_indices"]
        count = int(node["val_examples_scored"])
        correct = round(float(node["val_accuracy"]) * count)
        lines.append(
            f'| #{idx} | {"seed" if idx == 0 else data["iterations"][idx]} | '
            f'{"—" if not parent else "#" + str(parent[0])} | '
            f'{correct}/{count} ({100*float(node["val_accuracy"]):.0f}%) | '
            f'{"예" if idx in data["frontier"] else "아니요"} | '
            f'{"예" if idx == data["best_idx"] else "아니요"} |'
        )
    ties = ", ".join(f'#{idx}' for idx in data["tied_best"])
    selection_explanation = (
        f'검증 최고 성적은 {ties}가 동률이다. GEPA 기본 규칙은 먼저 등록된 '
        f'#{data["gepa_best_idx"]}을 선택하지만, 이번 test 평가에서는 사전에 정한 '
        f'`latest_val_tie` 규칙에 따라 나중에 등록된 #{data["best_idx"]}를 선택했다. '
        '원래 GEPA 결과 파일은 수정하지 않았다.'
        if data["selection_policy"] != "gepa" else
        f'최고 검증 성적은 {ties}가 동률이다. GEPA의 `best_idx`는 최고점 후보 중 '
        f'번호가 가장 작은 #{data["best_idx"]}을 반환하므로 최종 프롬프트는 초기 프롬프트다.'
    )
    lines += [
        '',
        selection_explanation,
        '주황색은 공식 `gepa.visualization.candidate_tree_dot_from_data`가 사용하는 '
        '`gepa.gepa_utils.find_dominator_programs`로 정했다. 이는 문항별 최고점 '
        '기여가 다른 후보들에 의해 모두 덮이는 후보를 제거한다. 검증 평균 최고점과 '
        'Pareto 포함 여부는 서로 다른 기준이다.',
        '',
        '근거 파일: 완료된 Modal 실행의 `lineage.json`, `gepa_result.json`, '
        '`gepa_state.json`, `summary.json`, `audit.json`. '
        '각 프롬프트 전문은 [클릭 가능한 트리](genetic_tree.html)에서 확인할 수 있다.',
        '',
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--selected-candidate", type=int,
                        help="Highlight a validation-best tie candidate chosen for held-out evaluation")
    args = parser.parse_args()
    data = prepare(args.run_dir)
    if args.selected_candidate is not None:
        if args.selected_candidate not in data["tied_best"]:
            raise ValueError("The test-selected candidate must tie for the top validation score")
        data["best_idx"] = args.selected_candidate
        data["selection_policy"] = "latest_val_tie"
    args.output_dir.mkdir(parents=True, exist_ok=True)
    svg = render_svg(data)
    (args.output_dir / "genetic_tree.svg").write_text(svg, encoding="utf-8")
    (args.output_dir / "genetic_tree.html").write_text(render_html(data, svg), encoding="utf-8")
    (args.output_dir / "GENETIC_TREE.md").write_text(render_markdown(data), encoding="utf-8")
    print(f'Rendered {len(data["nodes"])} candidates to {args.output_dir}')


if __name__ == "__main__":
    main()
