"""Durable, inspectable metadata for one GEPA experiment run."""

import csv
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import gepa


SCHEMA_VERSION = 1


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def write_text(path: Path, value: str) -> None:
    """Replace a complete artifact atomically on the same filesystem."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as file:
            file.write(value)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def write_json(path: Path, value: Any) -> None:
    write_text(path, json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n")


def append_jsonl(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as file:
        file.write(json.dumps(value, ensure_ascii=False, default=str) + "\n")
        file.flush()
        os.fsync(file.fileno())


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def snapshot_input(source: Path, target: Path) -> None:
    """Never overwrite the exact input bytes archived by an earlier process."""
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if sha256_file(source) != sha256_file(target):
            raise ValueError(f"저장된 실험 입력과 현재 파일이 다릅니다: {target}")
        return
    temporary = target.with_name(f".{target.name}.{uuid4().hex}.tmp")
    try:
        shutil.copyfile(source, temporary)
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def gepa_revision(project_root: Path) -> str | None:
    upstream = project_root.parent / "upstream" / "gepa"
    if not (upstream / ".git").exists():
        return None
    completed = subprocess.run(
        ["git", "-C", str(upstream), "rev-parse", "HEAD"],
        capture_output=True, text=True, check=False,
    )
    return completed.stdout.strip() if completed.returncode == 0 else None


def code_file_map() -> dict[str, Path]:
    project_code = Path(__file__).resolve().parent
    gepa_code = Path(gepa.__file__).resolve().parent
    code_files = {
        f"motif_gepa_ko/{name}": project_code / name
        for name in (
            "experiment.py", "artifacts.py", "scoring.py", "model.py", "data.py",
            "settings.py", "gepa_setup.py", "sampling.py",
        )
    }
    code_files.update({
        f"gepa/{name}": gepa_code / name
        for name in (
            "api.py", "core/engine.py", "core/state.py", "core/result.py", "core/callbacks.py",
            "adapters/default_adapter/default_adapter.py",
            "proposer/reflective_mutation/reflective_mutation.py",
        )
    })
    return code_files


def snapshot_code(run_dir: Path) -> dict[str, Path]:
    copies = {}
    for name, source in code_file_map().items():
        target = run_dir / "inputs" / "code" / name
        snapshot_input(source, target)
        copies[name] = target
    return copies


def make_manifest(project_root: Path, config: dict, input_paths: dict[str, Path], run_dir: Path,
                  code_copies: dict[str, Path] | None = None) -> dict:
    code_files = code_file_map()
    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": config["run_id"],
        "created_at_utc": utc_now(),
        "gepa_git_revision": gepa_revision(project_root),
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "config": config,
        "inputs": {
            name: {"path": str(path.relative_to(run_dir)).replace("\\", "/"), "sha256": sha256_file(path)}
            for name, path in input_paths.items()
        },
        "code_sha256": {name: sha256_file(path) for name, path in code_files.items()},
        "code_snapshots": {
            name: {"path": str(path.relative_to(run_dir)).replace("\\", "/"), "sha256": sha256_file(path)}
            for name, path in (code_copies or {}).items()
        },
    }


def write_lineage(run_dir: Path, candidates: list[dict], parents: list[list],
                  iteration_ids: list[str], val_scores: list[float], val_subscores: list[dict],
                  total_metric_calls: int | None, trace_entries: list[dict] | None = None) -> dict:
    """Keep accepted-candidate ancestry queryable independently of GEPA pickle."""
    if not (len(candidates) == len(parents) == len(iteration_ids) == len(val_scores) == len(val_subscores)):
        raise ValueError("후보 계보 필드의 길이가 일치하지 않습니다.")
    nodes = []
    edges = []
    for idx, (candidate, parent_indices, iteration_id, score, subscores) in enumerate(
        zip(candidates, parents, iteration_ids, val_scores, val_subscores, strict=True)
    ):
        parent_indices = [int(parent) for parent in parent_indices if parent is not None]
        node = {
            "candidate_idx": idx,
            "iteration_id": iteration_id,
            "parent_candidate_indices": parent_indices,
            "parent_iteration_ids": [iteration_ids[parent] for parent in parent_indices],
            "system_prompt": candidate["system_prompt"],
            "prompt_sha256": sha256_text(candidate["system_prompt"]),
            "val_accuracy": score,
            "val_examples_scored": len(subscores),
            "val_score_file": f"iterations/{iteration_id}/val_scores.json",
            "prompt_file": f"iterations/{iteration_id}/components/system_prompt.txt",
        }
        nodes.append(node)
        edges.extend({"parent_candidate_idx": parent, "child_candidate_idx": idx} for parent in parent_indices)
    proposal_nodes = []
    proposal_edges = []
    for trace in trace_entries or []:
        iteration_id = trace.get("iteration_id")
        path = run_dir / "iterations" / str(iteration_id) / "attempt.json"
        if not path.exists():
            continue
        attempt = json.loads(path.read_text(encoding="utf-8"))
        for position, proposal in enumerate(attempt["proposals"]):
            proposal_key = f"{iteration_id}:{proposal['proposal_id'] or position}"
            parent = proposal["parent_candidate_idx"]
            child = proposal["child_candidate_idx"]
            proposal_nodes.append({
                "proposal_key": proposal_key,
                "iteration": attempt["iteration"],
                "iteration_id": iteration_id,
                "proposal_id": proposal["proposal_id"],
                "parent_candidate_idx": parent,
                "child_candidate_idx": child,
                "decision": proposal["decision"],
                "prompt_sha256": proposal["prompt_sha256"],
                "val_accuracy": proposal["val_accuracy"],
                "attempt_file": f"iterations/{iteration_id}/attempt.json",
            })
            if parent is not None:
                proposal_edges.append({
                    "from": f"candidate:{parent}", "to": f"proposal:{proposal_key}",
                    "relationship": "parent_proposed",
                })
            if child is not None:
                proposal_edges.append({
                    "from": f"proposal:{proposal_key}", "to": f"candidate:{child}",
                    "relationship": "accepted_as",
                })
    best_idx = max(range(len(nodes)), key=lambda idx: nodes[idx]["val_accuracy"])
    lineage = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_dir.name,
        "updated_at_utc": utc_now(),
        "total_metric_calls": total_metric_calls,
        "best_candidate_idx": best_idx,
        "nodes": nodes,
        "edges": edges,
        "proposal_nodes": proposal_nodes,
        "proposal_edges": proposal_edges,
    }
    write_json(run_dir / "lineage.json", lineage)
    return lineage


def write_candidate_table(run_dir: Path, lineage: dict) -> None:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=(
        "candidate_idx", "iteration_id", "parent_candidate_indices", "parent_iteration_ids",
        "val_accuracy", "val_examples_scored", "prompt_sha256", "prompt_file", "val_score_file",
    ))
    writer.writeheader()
    for node in lineage["nodes"]:
        writer.writerow({key: json.dumps(node[key], ensure_ascii=False) if isinstance(node[key], list) else node[key]
                         for key in writer.fieldnames})
    write_text(run_dir / "candidates.csv", output.getvalue())


def write_proposal_graph(run_dir: Path, lineage: dict) -> None:
    """Mermaid view of accepted candidates and every attempted mutation."""
    lines = ["# 부모·제안·자식 관계", "", "```mermaid", "flowchart LR"]
    for node in lineage["nodes"]:
        idx = node["candidate_idx"]
        lines.append(f'    C{idx}["후보 {idx}<br/>val {node["val_accuracy"]:.3f}"]')
    proposal_index = {item["proposal_key"]: idx for idx, item in enumerate(lineage["proposal_nodes"])}
    for idx, proposal in enumerate(lineage["proposal_nodes"]):
        decision = "채택" if proposal["child_candidate_idx"] is not None else "거절"
        lines.append(f'    P{idx}["제안 {idx + 1}<br/>{decision}"]')
        lines.append(f"    class P{idx} {'accepted' if decision == '채택' else 'rejected'}")
    for edge in lineage["proposal_edges"]:
        source = edge["from"]
        target = edge["to"]
        source_id = f"C{source.split(':', 1)[1]}" if source.startswith("candidate:") else f"P{proposal_index[source.split(':', 1)[1]]}"
        target_id = f"C{target.split(':', 1)[1]}" if target.startswith("candidate:") else f"P{proposal_index[target.split(':', 1)[1]]}"
        lines.append(f"    {source_id} --> {target_id}")
    lines.extend([
        "    classDef accepted fill:#d7f5dc,stroke:#21803a,color:#111",
        "    classDef rejected fill:#fde0e0,stroke:#b63838,color:#111",
        "```", "", "제안 번호와 원본 반복 ID의 대응:", "",
        "| 그래프 | 반복 ID | 제안 ID | 상세 파일 |", "| --- | --- | --- | --- |",
    ])
    for idx, proposal in enumerate(lineage["proposal_nodes"]):
        lines.append(
            f"| 제안 {idx + 1} | `{proposal['iteration_id']}` | "
            f"`{proposal['proposal_id']}` | `{proposal['attempt_file']}` |"
        )
    write_text(run_dir / "proposal_graph.md", "\n".join(lines) + "\n")


def audit_run(run_dir: Path, result: Any, val_ids: list[str]) -> dict:
    """Fail visibly if a completed optimization lacks the records needed for analysis."""
    issues = []
    manifest_path = run_dir / "run_manifest.json"
    if not manifest_path.exists():
        issues.append("실험 입력·코드 출처 기록이 없습니다.")
    else:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for name, item in {**manifest["inputs"], **manifest.get("code_snapshots", {})}.items():
            path = run_dir / item["path"]
            if not path.exists() or sha256_file(path) != item["sha256"]:
                issues.append(f"저장된 입력 {name}의 해시가 맞지 않습니다.")
    lineage = json.loads((run_dir / "lineage.json").read_text(encoding="utf-8"))
    nodes = lineage["nodes"]
    if len(nodes) != result.num_candidates:
        issues.append("계보의 후보 수와 GEPA 후보 수가 다릅니다.")
    validation = read_jsonl(run_dir / "validation.jsonl")
    by_idx = {row["candidate_idx"]: row for row in validation}
    for idx, candidate in enumerate(result.candidates):
        if idx >= len(nodes):
            break
        node = nodes[idx]
        if node["system_prompt"] != candidate["system_prompt"]:
            issues.append(f"후보 {idx}: 프롬프트가 계보와 다릅니다.")
        if node["prompt_sha256"] != sha256_text(candidate["system_prompt"]):
            issues.append(f"후보 {idx}: 프롬프트 해시가 다릅니다.")
        if node["parent_candidate_indices"] != [int(p) for p in result.parents[idx] if p is not None]:
            issues.append(f"후보 {idx}: 부모 관계가 GEPA 결과와 다릅니다.")
        if idx not in by_idx:
            issues.append(f"후보 {idx}: 검증 이벤트가 없습니다.")
            continue
        row = by_idx[idx]
        if row["candidate"] != candidate:
            issues.append(f"후보 {idx}: 검증 프롬프트가 GEPA 결과와 다릅니다.")
        if abs(row["average_score"] - result.val_aggregate_scores[idx]) > 1e-9:
            issues.append(f"후보 {idx}: 검증 평균이 GEPA 결과와 다릅니다.")
        expected = {val_ids[int(key)]: score for key, score in result.val_subscores[idx].items()}
        if row["scores_by_question_id"] != expected:
            issues.append(f"후보 {idx}: 문항별 검증 점수가 GEPA 결과와 다릅니다.")
        if len(expected) != len(val_ids):
            issues.append(f"후보 {idx}: 전체 검증 문항을 평가하지 않았습니다.")
        iteration_dir = run_dir / "iterations" / node["iteration_id"]
        prompt_path = run_dir / node["prompt_file"]
        if not prompt_path.exists() or prompt_path.read_text(encoding="utf-8") != candidate["system_prompt"]:
            issues.append(f"후보 {idx}: 저장된 프롬프트 파일이 GEPA 결과와 다릅니다.")
        for filename in ("meta.json", "val_scores.json"):
            if not (iteration_dir / filename).exists():
                issues.append(f"후보 {idx}: {filename}이 없습니다.")
        if idx != 0 and not (iteration_dir / "trace.json").exists():
            issues.append(f"후보 {idx}: trace.json이 없습니다.")
        score_path = iteration_dir / "val_scores.json"
        if score_path.exists():
            stored_scores = json.loads(score_path.read_text(encoding="utf-8"))
            if stored_scores != {str(key): score for key, score in result.val_subscores[idx].items()}:
                issues.append(f"후보 {idx}: GEPA 문항별 점수 파일이 결과와 다릅니다.")
    run_log = json.loads((run_dir / "run_log.json").read_text(encoding="utf-8")) if (run_dir / "run_log.json").exists() else []
    proposal_count = 0
    for entry in run_log:
        iteration_id = entry.get("iteration_id")
        if not iteration_id:
            issues.append("반복 기록에 iteration_id가 없습니다.")
            continue
        iteration_dir = run_dir / "iterations" / iteration_id
        attempt_path = iteration_dir / "attempt.json"
        if not attempt_path.exists():
            issues.append(f"반복 {iteration_id}: attempt.json이 없습니다.")
            continue
        attempt = json.loads(attempt_path.read_text(encoding="utf-8"))
        if attempt["iteration_id"] != iteration_id:
            issues.append(f"반복 {iteration_id}: 시도 ID가 다릅니다.")
        expected_children = list(entry.get("new_program_indices") or [])
        if not expected_children and entry.get("new_program_idx") is not None:
            expected_children = [entry["new_program_idx"]]
        if attempt["accepted_candidate_indices"] != expected_children:
            issues.append(f"반복 {iteration_id}: 채택된 자식 후보 번호가 다릅니다.")
        if attempt["selected_parent_candidate_idx"] != entry.get("selected_program_candidate"):
            issues.append(f"반복 {iteration_id}: 선택된 부모 후보 번호가 다릅니다.")
        trace_path = iteration_dir / "trace.json"
        if not trace_path.exists():
            issues.append(f"반복 {iteration_id}: trace.json이 없습니다.")
        elif json.loads(trace_path.read_text(encoding="utf-8")) != entry:
            issues.append(f"반복 {iteration_id}: trace.json이 GEPA 로그와 다릅니다.")
        if entry.get("proposed_candidate") and not attempt["proposals"]:
            issues.append(f"반복 {iteration_id}: 제안 프롬프트 기록이 없습니다.")
        if entry.get("proposed_candidate") and len(attempt["proposals"]) == 1:
            proposal = attempt["proposals"][0]
            if proposal["candidate"] != entry["proposed_candidate"]:
                issues.append(f"반복 {iteration_id}: 제안 프롬프트가 GEPA 추적 기록과 다릅니다.")
            if not expected_children:
                prompt_path = iteration_dir / "components" / "system_prompt.txt"
                if not isinstance(proposal["candidate"], dict) or not prompt_path.exists() or \
                        prompt_path.read_text(encoding="utf-8") != proposal["candidate"]["system_prompt"]:
                    issues.append(f"반복 {iteration_id}: 거절 제안의 프롬프트 파일이 다릅니다.")
        proposal_count += len(attempt["proposals"])
        if not (iteration_dir / "meta.json").exists():
            issues.append(f"반복 {iteration_id}: meta.json이 없습니다.")
    if len(lineage.get("proposal_nodes", [])) != proposal_count:
        issues.append("제안 그래프의 노드 수와 반복 기록의 제안 수가 다릅니다.")
    for proposal in lineage.get("proposal_nodes", []):
        parent = proposal["parent_candidate_idx"]
        child = proposal["child_candidate_idx"]
        if parent is not None and not any(
            edge["from"] == f"candidate:{parent}" and edge["to"] == f"proposal:{proposal['proposal_key']}"
            for edge in lineage.get("proposal_edges", [])
        ):
            issues.append(f"제안 {proposal['proposal_key']}: 부모 연결이 없습니다.")
        if child is not None and not any(
            edge["from"] == f"proposal:{proposal['proposal_key']}" and edge["to"] == f"candidate:{child}"
            for edge in lineage.get("proposal_edges", [])
        ):
            issues.append(f"제안 {proposal['proposal_key']}: 채택 자식 연결이 없습니다.")
    events = read_jsonl(run_dir / "events.jsonl")
    event_ids = [record["event_id"] for record in events if "event_id" in record]
    if len(event_ids) != len(set(event_ids)):
        issues.append("이벤트 ID가 중복됩니다.")
    report = {
        "schema_version": SCHEMA_VERSION,
        "checked_at_utc": utc_now(),
        "candidate_count": result.num_candidates,
        "iteration_count": len(run_log),
        "proposal_count": proposal_count,
        "validation_record_count": len(validation),
        "event_count": len(events),
        "passed": not issues,
        "issues": issues,
    }
    write_json(run_dir / "audit.json", report)
    return report


def audit_saved_run(run_dir: Path) -> dict:
    """Recheck an exported or downloaded run without an API key or model call."""
    from gepa.core.result import GEPAResult

    run_dir = run_dir.resolve()
    result = GEPAResult.from_dict(json.loads((run_dir / "gepa_result.json").read_text(encoding="utf-8")))
    val_rows = read_jsonl(run_dir / "inputs" / "val.jsonl")
    if not val_rows:
        raise ValueError("저장된 val 문항 사본이 없습니다.")
    report = audit_run(run_dir, result, [row["id"] for row in val_rows])
    status_path = run_dir / "run_status.json"
    phase = json.loads(status_path.read_text(encoding="utf-8")).get("phase") if status_path.exists() else None
    if phase != "complete":
        report["issues"].append(f"실행 상태가 complete가 아닙니다: {phase}")
        report["passed"] = False
        write_json(run_dir / "audit.json", report)
    return report
