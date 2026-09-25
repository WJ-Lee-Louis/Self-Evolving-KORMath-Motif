"""Reproducible GEPA search and held-out prompt comparison."""

import difflib
import json
import re
import time
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

import gepa
from gepa.core.state import GEPAState

from motif_gepa_ko.artifacts import (
    SCHEMA_VERSION, append_jsonl, audit_run, make_manifest, read_jsonl,
    sha256_file, sha256_text, snapshot_code, snapshot_input, utc_now, write_candidate_table,
    write_json, write_lineage, write_proposal_graph, write_text,
)
from motif_gepa_ko.data import as_gepa_data, load_split
from motif_gepa_ko.gepa_setup import load_prompt_assets
from motif_gepa_ko.model import MotifLM
from motif_gepa_ko.scoring import KoreanMathEvaluator, score_response
from motif_gepa_ko.settings import PROJECT_ROOT, Settings


def _write_json(path: Path, value: Any) -> None:
    write_json(path, value)


def _sha256(path: Path) -> str:
    return sha256_file(path)


def _run_path(runs_dir: Path, run_id: str) -> Path:
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}", run_id):
        raise ValueError("run_id는 영문·숫자로 시작하고 영문·숫자·_·-만 사용해야 합니다.")
    return runs_dir / run_id


class CountedLM:
    """Bound logical LLM calls across both GEPA roles."""

    def __init__(self, lm: MotifLM, max_calls: int, *, log_path: Path | None = None,
                 session_id: str | None = None,
                 question_lookup: dict[str, list[dict]] | None = None):
        self.lm = lm
        self.max_calls = max_calls
        self.calls = 0
        self.log_path = log_path
        self.session_id = session_id
        self.context: dict[str, Any] = {}
        self.question_lookup = question_lookup or {}

    def __call__(self, prompt: Any) -> str:
        if self.calls >= self.max_calls:
            raise RuntimeError(f"API 논리 호출 상한 {self.max_calls}회에 도달했습니다.")
        self.calls += 1
        started = time.perf_counter()
        record = {
            "schema_version": SCHEMA_VERSION,
            "session_id": self.session_id,
            "logical_call_number": self.calls,
            "started_at_utc": utc_now(),
            "role": "reflection" if isinstance(prompt, str) else "task",
            "request": prompt,
            "prompt_sha256": sha256_text(json.dumps(prompt, ensure_ascii=False, default=str)),
            **self.context,
        }
        if not isinstance(prompt, str):
            user_text = next((message.get("content") for message in prompt if message.get("role") == "user"), None)
            system_text = next((message.get("content") for message in prompt if message.get("role") == "system"), None)
            record["question_matches"] = self.question_lookup.get(user_text, []) if isinstance(user_text, str) else []
            record["system_prompt_sha256"] = sha256_text(system_text) if isinstance(system_text, str) else None
        try:
            response = self.lm(prompt)
            record.update({
                "status": "success", "response": response,
                "response_sha256": sha256_text(response),
            })
            return response
        except BaseException as exc:
            record.update({
                "status": "error", "error_type": type(exc).__name__,
                "http_status_code": getattr(exc, "status_code", None),
            })
            raise
        finally:
            record["duration_seconds"] = round(time.perf_counter() - started, 3)
            record["response_metadata"] = getattr(self.lm, "last_response_metadata", None)
            if self.log_path is not None:
                append_jsonl(self.log_path, record)


class EvolutionLog:
    def __init__(
        self,
        run_dir: Path,
        train_ids: list[str],
        val_ids: list[str],
        checkpoint_hook: Callable[[], None] | None = None,
    ):
        self.run_dir = run_dir
        self.path = run_dir / "events.jsonl"
        self.validation_path = run_dir / "validation.jsonl"
        self.train_ids = train_ids
        self.val_ids = val_ids
        self.checkpoint_hook = checkpoint_hook
        self.session_id = uuid4().hex
        self.sequence = 0
        self.iteration_ids: dict[int, str] = {}
        self.iteration_events: dict[int, list[dict]] = {}

    def _append(self, kind: str, fields: dict) -> dict:
        self.sequence += 1
        iteration = fields.get("iteration")
        record = {
            "schema_version": SCHEMA_VERSION,
            "event_id": f"{self.session_id}:{self.sequence}",
            "run_id": self.run_dir.name,
            "recorded_at_utc": utc_now(),
            "event": kind,
            "iteration_id": self.iteration_ids.get(iteration, "seed" if iteration == 0 else None),
            **fields,
        }
        append_jsonl(self.path, record)
        if isinstance(iteration, int) and iteration > 0:
            self.iteration_events.setdefault(iteration, []).append(record)
        return record

    def on_iteration_start(self, event: dict) -> None:
        iteration_id = event["state"].full_program_trace[-1]["iteration_id"]
        self.iteration_ids[event["iteration"]] = iteration_id
        self._append("iteration_start", {"iteration": event["iteration"]})

    def on_candidate_selected(self, event: dict) -> None:
        self._append("parent_selected", {
            "iteration": event["iteration"], "candidate_idx": event["candidate_idx"],
            "candidate": event["candidate"], "parent_val_accuracy": event["score"],
        })

    def on_proposal_end(self, event: dict) -> None:
        parents = [item for item in self.iteration_events.get(event["iteration"], [])
                   if item["event"] == "parent_selected"]
        parent = parents[0] if len(parents) == 1 else None
        candidate = dict(parent["candidate"]) if parent else None
        if candidate is not None:
            candidate.update(event["new_instructions"])
        self._append("proposal", {
            "iteration": event["iteration"],
            "proposal_id": (event.get("metadata") or {}).get("proposal_id"),
            "parent_candidate_idx": parent["candidate_idx"] if parent else None,
            "candidate": candidate,
            "prompt_sha256": sha256_text(candidate["system_prompt"]) if candidate else None,
            "new_instructions": event["new_instructions"],
            "prompts": event["prompts"],
            "raw_lm_outputs": event["raw_lm_outputs"],
            "metadata": event.get("metadata"),
        })

    def on_minibatch_sampled(self, event: dict) -> None:
        positions = event["minibatch_ids"]
        self._append("minibatch", {
            "iteration": event["iteration"],
            "train_positions": positions,
            "train_ids": [self.train_ids[int(i)] for i in positions],
        })

    def on_evaluation_end(self, event: dict) -> None:
        trajectories = event.get("trajectories") or []
        question_ids = [item.get("data", {}).get("additional_context", {}).get("question_id")
                        for item in trajectories]
        self._append("minibatch_evaluation", {
            "iteration": event["iteration"],
            "role": "parent" if event["candidate_idx"] is not None else "proposal",
            "candidate_idx": event["candidate_idx"],
            "parent_ids": event["parent_ids"],
            "train_question_ids": question_ids,
            "scores": event["scores"],
            "mean_score": sum(event["scores"]) / len(event["scores"]) if event["scores"] else None,
            "outputs": event["outputs"],
            "trajectories": event["trajectories"],
            "objective_scores": event["objective_scores"],
            "is_seed_candidate": event["is_seed_candidate"],
        })

    def on_reflective_dataset_built(self, event: dict) -> None:
        self._append("reflection_feedback", {
            "iteration": event["iteration"], "candidate_idx": event["candidate_idx"],
            "components": event["components"],
            "dataset_file": f"iterations/{event['iteration_id']}/reflective_dataset.json",
        })
        iteration_dir = self.run_dir / "iterations" / event["iteration_id"]
        iteration_dir.mkdir(parents=True, exist_ok=True)
        _write_json(iteration_dir / "reflective_dataset.json", event["dataset"])

    def on_valset_evaluated(self, event: dict) -> None:
        def question_ids(values: dict) -> dict:
            return {self.val_ids[int(i)]: value for i, value in values.items()}

        record = {
            "schema_version": SCHEMA_VERSION,
            "run_id": self.run_dir.name,
            "recorded_at_utc": utc_now(),
            "iteration": event["iteration"],
            "iteration_id": self.iteration_ids.get(event["iteration"], "seed" if event["iteration"] == 0 else None),
            "candidate_idx": event["candidate_idx"],
            "candidate": event["candidate"],
            "prompt_sha256": sha256_text(event["candidate"]["system_prompt"]),
            "average_score": event["average_score"],
            "num_examples_evaluated": event["num_examples_evaluated"],
            "total_valset_size": event["total_valset_size"],
            "parent_ids": event["parent_ids"],
            "is_best_program": event["is_best_program"],
            "scores_by_question_id": question_ids(event["scores_by_val_id"]),
            "outputs_by_question_id": question_ids(event["outputs_by_val_id"] or {}),
        }
        append_jsonl(self.validation_path, record)
        self._append("validation", {
            "iteration": record["iteration"], "candidate_idx": record["candidate_idx"],
            "average_score": record["average_score"],
            "num_examples_evaluated": record["num_examples_evaluated"],
            "is_best_program": record["is_best_program"],
        })

    def on_candidate_accepted(self, event: dict) -> None:
        self._append("accepted", {
            "iteration": event["iteration"], "new_candidate_idx": event["new_candidate_idx"],
            "train_minibatch_score_after": event["new_score"], "parent_ids": event["parent_ids"],
        })

    def on_candidate_rejected(self, event: dict) -> None:
        self._append("rejected", {
            "iteration": event["iteration"],
            "train_minibatch_score_before": event["old_score"],
            "train_minibatch_score_after": event["new_score"],
            "reason": event["reason"],
        })

    def on_iteration_end(self, event: dict) -> None:
        iteration = event["iteration"]
        state = event["state"]
        trace = state.full_program_trace[-1]
        self._append("iteration_end", {
            "iteration": iteration, "proposal_accepted": event["proposal_accepted"],
            "metric_calls_so_far": state.total_num_evals,
        })
        iteration_dir = self.run_dir / "iterations" / trace["iteration_id"]
        iteration_dir.mkdir(parents=True, exist_ok=True)
        _write_json(iteration_dir / "trace.json", trace)
        records = self.iteration_events.pop(iteration, [])
        error_events = [item for item in records if item["event"] == "error"]
        interrupted = bool(error_events)
        parent_idx = trace.get("selected_program_candidate")
        accepted_indices = list(trace.get("new_program_indices") or [])
        if not accepted_indices and trace.get("new_program_idx") is not None:
            accepted_indices = [trace["new_program_idx"]]
        unused_accepted = set(accepted_indices)
        proposals = []
        for proposal in (item for item in records if item["event"] == "proposal"):
            matching = next((idx for idx in sorted(unused_accepted)
                             if proposal["candidate"] == state.program_candidates[idx]), None)
            if matching is not None:
                unused_accepted.remove(matching)
            parent = proposal["parent_candidate_idx"]
            if parent is None and len([item for item in records if item["event"] == "proposal"]) == 1:
                parent = parent_idx
            before = state.program_candidates[parent]["system_prompt"] if parent is not None else None
            after = proposal["candidate"]["system_prompt"] if proposal["candidate"] else None
            diff = list(difflib.unified_diff(before.splitlines(), after.splitlines(),
                                             fromfile=f"candidate-{parent}", tofile="proposal", lineterm="")) \
                if before is not None and after is not None else []
            proposals.append({
                "proposal_id": proposal["proposal_id"],
                "parent_candidate_idx": parent,
                "parent_iteration_id": state.iteration_ids_by_candidate_idx[parent] if parent is not None else None,
                "candidate": proposal["candidate"],
                "prompt_sha256": proposal["prompt_sha256"],
                "prompt_diff": diff,
                "decision": "accepted" if matching is not None else (
                    "evaluation_incomplete" if interrupted else "not_added_to_candidate_pool"
                ),
                "child_candidate_idx": matching,
                "child_iteration_id": state.iteration_ids_by_candidate_idx[matching] if matching is not None else None,
                "val_accuracy": state.get_program_average_val_subset(matching)[0] if matching is not None else None,
            })
        tasks = []
        for task in trace.get("tasks", []):
            ids = [self.train_ids[int(position)] for position in task.get("subsample_ids", [])]
            before_scores = task.get("subsample_scores")
            after_scores = task.get("new_subsample_scores")
            tasks.append({
                "parent_candidate_idx": task.get("parent_idx"),
                "train_question_ids": ids,
                "scores_before": before_scores,
                "scores_after": after_scores,
                "mean_before": sum(before_scores) / len(before_scores) if before_scores else None,
                "mean_after": sum(after_scores) / len(after_scores) if after_scores else None,
            })
        attempt = {
            "schema_version": SCHEMA_VERSION,
            "run_id": self.run_dir.name,
            "iteration": iteration,
            "iteration_id": trace["iteration_id"],
            "recorded_at_utc": utc_now(),
            "decision": "interrupted" if interrupted else (
                "accepted" if accepted_indices else "rejected" if proposals else "no_proposal"
            ),
            "error_type": error_events[-1]["error_type"] if interrupted else None,
            "selected_parent_candidate_idx": parent_idx,
            "selected_parent_iteration_id": state.iteration_ids_by_candidate_idx[parent_idx] if parent_idx is not None else None,
            "accepted_candidate_indices": accepted_indices,
            "train_tasks": tasks,
            "proposals": proposals,
            "rejections": [item for item in records if item["event"] == "rejected"],
            "validations": [item for item in records if item["event"] == "validation"],
            "metric_calls_so_far": state.total_num_evals,
            "events": records,
            "trace_file": f"iterations/{trace['iteration_id']}/trace.json",
        }
        _write_json(iteration_dir / "attempt.json", attempt)
        scores = [state.get_program_average_val_subset(idx)[0] for idx in range(len(state.program_candidates))]
        write_lineage(self.run_dir, state.program_candidates, state.parent_program_for_candidate,
                      state.iteration_ids_by_candidate_idx, scores, state.prog_candidate_val_subscores,
                      state.total_num_evals, state.full_program_trace)
        if self.checkpoint_hook is not None:
            self.checkpoint_hook()
        outcome = "중단" if interrupted else "채택" if event["proposal_accepted"] else "미채택"
        print(f"GEPA 반복 {iteration}: 후보 {outcome}", flush=True)

    def on_state_saved(self, event: dict) -> None:
        self._append("state_saved", {"iteration": event["iteration"], "run_dir": event["run_dir"]})
        if self.checkpoint_hook is not None:
            self.checkpoint_hook()

    def on_error(self, event: dict) -> None:
        self._append("error", {
            "iteration": event["iteration"],
            "error_type": type(event["exception"]).__name__,
            "http_status_code": getattr(event["exception"], "status_code", None),
            "will_continue": event["will_continue"],
        })

    def on_optimization_end(self, event: dict) -> None:
        self._append("optimization_end", {
            "best_candidate_idx": event["best_candidate_idx"],
            "total_iterations": event["total_iterations"],
            "total_metric_calls": event["total_metric_calls"],
        })


class FileLogger:
    def __init__(self, path: Path):
        self.path = path

    def log(self, message: str) -> None:
        with self.path.open("a", encoding="utf-8") as file:
            file.write(str(message) + "\n")


def _write_evolution_report(run_dir: Path, result: Any) -> None:
    lines = ["# 한국어 시스템 프롬프트 진화 기록", ""]
    for idx, candidate in enumerate(result.candidates):
        prompt = candidate["system_prompt"]
        parents = result.parents[idx]
        lines.extend([
            f"## 후보 {idx}{' (최종 선택)' if idx == result.best_idx else ''}",
            "",
            f"- 부모 후보: {parents}",
            f"- 검증 정확도: {result.val_aggregate_scores[idx]:.4f}",
            "",
            "### 전체 프롬프트", "",
            *["> " + line for line in prompt.splitlines()],
            "",
        ])
        parent = next((p for p in parents if p is not None), None)
        if parent is not None:
            before = result.candidates[parent]["system_prompt"].splitlines()
            diff = list(difflib.unified_diff(before, prompt.splitlines(), fromfile=f"후보 {parent}", tofile=f"후보 {idx}", lineterm=""))
            lines.extend(["### 부모 대비 변화", "", "```diff", *diff, "```", ""])
    lines.extend(["채택되지 않은 제안은 `attempt_timeline.md`와 `iterations/<id>/attempt.json`에서 확인합니다.", ""])
    write_text(run_dir / "evolution.md", "\n".join(lines))


def _write_attempt_timeline(run_dir: Path, trace_entries: list[dict]) -> None:
    """Readable chronological companion to the complete machine-readable attempts."""
    lines = ["# GEPA 진화 시도 전체 타임라인", "",
             "훈련 묶음 점수는 제안 선택 단계의 값입니다. 전체 검증 점수는 채택 후보에만 있습니다.", ""]
    for trace in trace_entries:
        iteration_id = trace["iteration_id"]
        path = run_dir / "iterations" / iteration_id / "attempt.json"
        if not path.exists():
            lines.extend([f"## 반복 {trace.get('i', '?')} · {iteration_id}", "",
                          "반복 기록 파일이 없습니다. `audit.json`을 확인하세요.", ""])
            continue
        attempt = json.loads(path.read_text(encoding="utf-8"))
        lines.extend([
            f"## 반복 {attempt['iteration']} · {iteration_id}", "",
            f"- 결정: {attempt['decision']}",
            f"- 선택된 부모 후보: {attempt['selected_parent_candidate_idx']} "
            f"(`{attempt['selected_parent_iteration_id']}`)",
            f"- 채택된 자식 후보: {attempt['accepted_candidate_indices']}",
            f"- 누적 GEPA 평가 호출: {attempt['metric_calls_so_far']}",
            f"- 상세 메타데이터: `iterations/{iteration_id}/attempt.json`", "",
        ])
        for task in attempt["train_tasks"]:
            lines.extend([
                f"- 훈련 묶음: {', '.join(task['train_question_ids'])}",
                f"  - 부모 문항별 점수: {task['scores_before']}; 평균 {task['mean_before']}",
                f"  - 자식 문항별 점수: {task['scores_after']}; 평균 {task['mean_after']}",
            ])
        if attempt["train_tasks"]:
            lines.append("")
        for proposal in attempt["proposals"]:
            lines.extend([
                f"### 제안 {proposal['proposal_id'] or 'ID 없음'}", "",
                f"- 부모: {proposal['parent_candidate_idx']}",
                f"- 결정: {proposal['decision']}",
                f"- 자식 후보: {proposal['child_candidate_idx']}",
                f"- 전체 검증 정확도: {proposal['val_accuracy'] if proposal['val_accuracy'] is not None else '미평가'}",
                f"- 프롬프트 SHA-256: `{proposal['prompt_sha256']}`", "",
            ])
            prompt = proposal["candidate"]["system_prompt"] if proposal["candidate"] else None
            if prompt:
                lines.extend(["#### 제안 프롬프트", "", "````text", prompt, "````", ""])
            if proposal["prompt_diff"]:
                lines.extend(["#### 부모 대비 변경", "", "````diff", *proposal["prompt_diff"], "````", ""])
        for rejection in attempt["rejections"]:
            lines.extend([f"- 거절 사유: {rejection['reason']}", ""])
        if not attempt["proposals"]:
            lines.extend(["이 반복에서는 새 프롬프트 제안이 생성되지 않았습니다.", ""])
    write_text(run_dir / "attempt_timeline.md", "\n".join(lines) + "\n")


def _finalize_optimization(run_dir: Path, result: Any, seed_prompt: str,
                           val_ids: list[str], logical_calls: int,
                           session_id: str, session_path: Path) -> dict:
    best = result.best_candidate
    if not isinstance(best, dict):
        raise TypeError("GEPA 결과의 best_candidate 형식이 예상과 다릅니다.")
    write_text(run_dir / "best_prompt.md", best["system_prompt"] + "\n")
    _write_json(run_dir / "gepa_result.json", result.to_dict())
    write_text(run_dir / "candidate_tree.html", result.candidate_tree_html())
    _write_evolution_report(run_dir, result)
    state = GEPAState.load(str(run_dir))
    lineage = write_lineage(run_dir, result.candidates, result.parents,
                            state.iteration_ids_by_candidate_idx, result.val_aggregate_scores,
                            result.val_subscores, result.total_metric_calls, state.full_program_trace)
    write_candidate_table(run_dir, lineage)
    write_proposal_graph(run_dir, lineage)
    _write_attempt_timeline(run_dir, state.full_program_trace)
    audit = audit_run(run_dir, result, val_ids)
    if not audit["passed"]:
        raise RuntimeError("실험 기록 감사를 통과하지 못했습니다. audit.json을 확인하세요.")
    summary = {
        "run_id": run_dir.name,
        "best_idx": result.best_idx,
        "best_val_accuracy": result.best_score,
        "seed_val_accuracy": result.val_aggregate_scores[0],
        "num_candidates": result.num_candidates,
        "gepa_metric_calls": result.total_metric_calls,
        "logical_api_calls_this_process": logical_calls,
        "changed": best["system_prompt"] != seed_prompt,
        "artifact_audit_passed": True,
    }
    _write_json(run_dir / "summary.json", summary)
    append_jsonl(session_path, {
        "session_id": session_id, "event": "archive_complete", "at_utc": utc_now(),
        "logical_api_calls": logical_calls, "artifact_audit_passed": True,
    })
    _write_json(run_dir / "run_status.json", {
        "phase": "complete", "session_id": session_id, "updated_at_utc": utc_now(),
    })
    return summary


def optimize_run(
    *,
    data_dir: Path,
    prompts_dir: Path,
    runs_dir: Path,
    run_id: str,
    max_metric_calls: int = 180,
    max_api_calls: int = 250,
    minibatch_size: int = 3,
    seed: int = 0,
    checkpoint_hook: Callable[[], None] | None = None,
) -> dict:
    train_records = load_split(data_dir, "train")
    val_records = load_split(data_dir, "val")
    if max_metric_calls < len(val_records) or max_api_calls < max_metric_calls or minibatch_size < 1:
        raise ValueError("예산 조건: max_metric_calls >= val 크기, max_api_calls >= max_metric_calls, minibatch_size >= 1")
    if {r["id"] for r in train_records} & {r["id"] for r in val_records}:
        raise ValueError("train과 val에 같은 문항이 있습니다.")
    settings = Settings.from_env()
    seed_prompt, reflection_prompt = load_prompt_assets(prompts_dir)
    run_dir = _run_path(runs_dir, run_id)
    run_dir.mkdir(parents=True, exist_ok=True)
    config = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "model": settings.model,
        "base_url": settings.base_url,
        "temperature": settings.temperature,
        "max_output_tokens": settings.max_output_tokens,
        "reflection_max_output_tokens": settings.reflection_max_output_tokens,
        "timeout_seconds": settings.timeout_seconds,
        "max_metric_calls": max_metric_calls,
        "max_api_calls": max_api_calls,
        "minibatch_size": minibatch_size,
        "seed": seed,
        "train_count": len(train_records),
        "val_count": len(val_records),
        "train_sha256": _sha256(data_dir / "train.jsonl"),
        "val_sha256": _sha256(data_dir / "val.jsonl"),
        "seed_prompt_sha256": _sha256(prompts_dir / "seed_ko.md"),
        "reflection_prompt_sha256": _sha256(prompts_dir / "reflection_ko.md"),
    }
    config_path = run_dir / "config.json"
    if config_path.exists() and json.loads(config_path.read_text(encoding="utf-8")) != config:
        raise ValueError("같은 run_id의 설정이 다릅니다. 새 run_id를 사용하세요.")
    _write_json(config_path, config)
    input_sources = {
        "train": data_dir / "train.jsonl",
        "val": data_dir / "val.jsonl",
        "seed_prompt": prompts_dir / "seed_ko.md",
        "reflection_template": prompts_dir / "reflection_ko.md",
    }
    input_paths = {}
    for name, source in input_sources.items():
        target = run_dir / "inputs" / source.name
        snapshot_input(source, target)
        input_paths[name] = target
    code_copies = snapshot_code(run_dir)
    manifest_path = run_dir / "run_manifest.json"
    proposed_manifest = make_manifest(PROJECT_ROOT, config, input_paths, run_dir, code_copies)
    if manifest_path.exists():
        old_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for field in ("config", "inputs", "code_sha256", "code_snapshots"):
            if old_manifest[field] != proposed_manifest[field]:
                raise ValueError(f"같은 run_id의 실행 출처가 다릅니다: {field}")
        old_revision = old_manifest.get("gepa_git_revision")
        new_revision = proposed_manifest.get("gepa_git_revision")
        if old_revision and new_revision and old_revision != new_revision:
            raise ValueError("같은 run_id의 GEPA 커밋이 다릅니다.")
    else:
        _write_json(manifest_path, proposed_manifest)
    write_text(run_dir / "seed_prompt.md", seed_prompt + "\n")
    recorder = EvolutionLog(
        run_dir, [record["id"] for record in train_records],
        [record["id"] for record in val_records], checkpoint_hook,
    )
    question_lookup: dict[str, list[dict]] = {}
    for split_name, records in (("train", train_records), ("val", val_records)):
        for record in records:
            question_lookup.setdefault(record["question"], []).append({"split": split_name, "id": record["id"]})
    lm = CountedLM(MotifLM(settings), max_api_calls,
                   log_path=run_dir / "api_requests.jsonl", session_id=recorder.session_id,
                   question_lookup=question_lookup)
    session_path = run_dir / "run_sessions.jsonl"
    append_jsonl(session_path, {
        "session_id": recorder.session_id, "event": "started", "at_utc": utc_now(),
        "max_metric_calls": max_metric_calls, "max_api_calls": max_api_calls,
    })
    _write_json(run_dir / "run_status.json", {
        "phase": "optimizing", "session_id": recorder.session_id, "updated_at_utc": utc_now(),
    })
    try:
        result = gepa.optimize(
            seed_candidate={"system_prompt": seed_prompt},
            trainset=as_gepa_data(train_records),
            valset=as_gepa_data(val_records),
            task_lm=lm,
            evaluator=KoreanMathEvaluator(),
            reflection_lm=lm,
            reflection_prompt_template=reflection_prompt,
            reflection_minibatch_size=minibatch_size,
            max_metric_calls=max_metric_calls,
            seed=seed,
            run_dir=str(run_dir),
            callbacks=[recorder],
            logger=FileLogger(run_dir / "gepa.log"),
            write_agent_state=True,
        )
    except BaseException as exc:
        append_jsonl(session_path, {
            "session_id": recorder.session_id, "event": "interrupted", "at_utc": utc_now(),
            "logical_api_calls": lm.calls, "error_type": type(exc).__name__,
            "http_status_code": getattr(exc, "status_code", None),
        })
        _write_json(run_dir / "run_status.json", {
            "phase": "interrupted", "session_id": recorder.session_id,
            "updated_at_utc": utc_now(), "error_type": type(exc).__name__,
            "http_status_code": getattr(exc, "status_code", None),
        })
        raise
    finally:
        _write_json(run_dir / "api_calls.json", {"logical_calls_this_process": lm.calls, "limit": max_api_calls})
    append_jsonl(session_path, {
        "session_id": recorder.session_id, "event": "optimization_finished", "at_utc": utc_now(),
        "logical_api_calls": lm.calls, "gepa_metric_calls": result.total_metric_calls,
        "num_candidates": result.num_candidates,
    })
    try:
        return _finalize_optimization(run_dir, result, seed_prompt,
                                      [record["id"] for record in val_records],
                                      lm.calls, recorder.session_id, session_path)
    except BaseException as exc:
        append_jsonl(session_path, {
            "session_id": recorder.session_id, "event": "archive_failed", "at_utc": utc_now(),
            "logical_api_calls": lm.calls, "error_type": type(exc).__name__,
        })
        audit_path = run_dir / "audit.json"
        audit_issues = json.loads(audit_path.read_text(encoding="utf-8"))["issues"] if audit_path.exists() else []
        _write_json(run_dir / "run_status.json", {
            "phase": "artifact_incomplete", "session_id": recorder.session_id,
            "updated_at_utc": utc_now(), "error_type": type(exc).__name__,
            "issues": audit_issues,
        })
        raise


def evaluate_run(
    *,
    data_dir: Path,
    runs_dir: Path,
    run_id: str,
    split: str,
    limit: int = 20,
    max_api_calls: int = 100,
) -> dict:
    if not split.startswith("test_"):
        raise ValueError("보류 평가에는 test_* 분할만 사용할 수 있습니다.")
    if limit < 0 or max_api_calls < 2:
        raise ValueError("limit >= 0, max_api_calls >= 2여야 합니다.")
    run_dir = _run_path(runs_dir, run_id)
    if not (run_dir / "summary.json").exists():
        raise FileNotFoundError("먼저 GEPA 실행을 완료해야 합니다.")
    settings = Settings.from_env()
    config = json.loads((run_dir / "config.json").read_text(encoding="utf-8"))
    run_manifest = json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))
    scoring_sha256 = _sha256(Path(__file__).with_name("scoring.py"))
    if run_manifest["code_sha256"]["motif_gepa_ko/scoring.py"] != scoring_sha256:
        raise ValueError("진화 때와 채점 코드가 다릅니다. 보류 평가의 점수 정의를 바꾸지 마세요.")
    if (
        settings.model != config["model"]
        or settings.base_url != config["base_url"]
        or settings.temperature != config["temperature"]
        or settings.max_output_tokens != config["max_output_tokens"]
    ):
        raise ValueError("진화 때와 평가 때의 모델 ID 또는 생성 설정이 다릅니다.")
    source_path = data_dir / f"{split}.jsonl"
    snapshot_input(source_path, run_dir / "inputs" / source_path.name)
    records = load_split(data_dir, split)
    if limit:
        records = records[:limit]
    output_path = run_dir / f"{split}_paired.jsonl"
    done = set()
    if output_path.exists():
        done = {json.loads(line)["id"] for line in output_path.read_text(encoding="utf-8").splitlines() if line.strip()}
    prompts = {
        "seed": (run_dir / "seed_prompt.md").read_text(encoding="utf-8").strip(),
        "best": (run_dir / "best_prompt.md").read_text(encoding="utf-8").strip(),
    }
    metadata = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "split": split,
        "dataset_sha256": _sha256(source_path),
        "seed_prompt_sha256": sha256_text(prompts["seed"]),
        "best_prompt_sha256": sha256_text(prompts["best"]),
        "model": settings.model,
        "base_url": settings.base_url,
        "temperature": settings.temperature,
        "max_output_tokens": settings.max_output_tokens,
        "scoring_code_sha256": scoring_sha256,
    }
    metadata_path = run_dir / f"{split}_metadata.json"
    if metadata_path.exists() and json.loads(metadata_path.read_text(encoding="utf-8")) != metadata:
        raise ValueError("이전 보류 평가와 데이터·프롬프트·모델·채점 코드가 다릅니다. 새 run_id를 사용하세요.")
    _write_json(metadata_path, metadata)
    session_id = uuid4().hex
    session_path = run_dir / f"{split}_sessions.jsonl"
    append_jsonl(session_path, {
        "session_id": session_id, "event": "started", "at_utc": utc_now(),
        "limit": limit, "max_api_calls": max_api_calls,
        "selected_question_ids": [item["id"] for item in records],
    })
    lm = CountedLM(MotifLM(settings), max_api_calls,
                   log_path=run_dir / f"{split}_api_requests.jsonl", session_id=session_id)
    try:
        for item in records:
            if item["id"] in done:
                continue
            if lm.calls + 2 > max_api_calls:
                break
            row = {
                "id": item["id"], "question": item["question"], "answer": item["answer"],
                "source_subset": item.get("source_subset"),
                "source_row_index": item.get("source_row_index"),
            }
            for name, prompt in prompts.items():
                lm.context = {"split": split, "question_id": item["id"], "prompt_variant": name}
                response = lm([{"role": "system", "content": prompt}, {"role": "user", "content": item["question"]}])
                score, feedback, parsed = score_response(item["answer"], response)
                row[name] = {"score": score, "parsed_answer": parsed, "feedback": feedback, "response": response}
            append_jsonl(output_path, row)
    except BaseException as exc:
        append_jsonl(session_path, {
            "session_id": session_id, "event": "interrupted", "at_utc": utc_now(),
            "logical_api_calls": lm.calls, "error_type": type(exc).__name__,
            "http_status_code": getattr(exc, "status_code", None),
        })
        raise
    all_rows = [json.loads(line) for line in output_path.read_text(encoding="utf-8").splitlines() if line.strip()] if output_path.exists() else []
    by_id = {row["id"]: row for row in all_rows}
    selected = [by_id[item["id"]] for item in records if item["id"] in by_id]
    summary = {
        "split": split,
        "selected": len(records),
        "completed": len(selected),
        "seed_accuracy": sum(row["seed"]["score"] for row in selected) / len(selected) if selected else None,
        "best_accuracy": sum(row["best"]["score"] for row in selected) / len(selected) if selected else None,
        "improved": sum(row["seed"]["score"] < row["best"]["score"] for row in selected),
        "regressed": sum(row["seed"]["score"] > row["best"]["score"] for row in selected),
        "format_errors_seed": sum(row["seed"]["parsed_answer"] is None for row in selected),
        "format_errors_best": sum(row["best"]["parsed_answer"] is None for row in selected),
        "logical_api_calls_this_process": lm.calls,
        "dataset_sha256": metadata["dataset_sha256"],
        "seed_prompt_sha256": metadata["seed_prompt_sha256"],
        "best_prompt_sha256": metadata["best_prompt_sha256"],
        "question_ids": [row["id"] for row in selected],
    }
    _write_json(run_dir / f"{split}_summary.json", summary)
    append_jsonl(session_path, {
        "session_id": session_id, "event": "finished", "at_utc": utc_now(),
        "logical_api_calls": lm.calls, "completed": len(selected), "selected": len(records),
    })
    return summary
