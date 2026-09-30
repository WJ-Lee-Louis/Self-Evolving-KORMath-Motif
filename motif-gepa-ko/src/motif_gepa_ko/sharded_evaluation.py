"""Disjoint, resumable held-out evaluation shards for completed Omni v2 runs."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Callable
from uuid import uuid4

from motif_gepa_ko.artifacts import (
    SCHEMA_VERSION, append_jsonl, read_jsonl, sha256_file, sha256_text,
    snapshot_input, utc_now, write_json, write_text,
)
from motif_gepa_ko.bilingual import V2_DATASETS, load_v2_split, score_v2
from motif_gepa_ko.experiment import CountedLM, _run_path
from motif_gepa_ko.model import MotifLM
from motif_gepa_ko.settings import Settings


def shard_records(records: list[dict], index: int, count: int) -> list[dict]:
    if count < 2 or not 0 <= index < count:
        raise ValueError("A shard requires count >= 2 and 0 <= index < count")
    return records[index::count]


def shard_dir(run_dir: Path, split: str, index: int, count: int) -> Path:
    return run_dir / "heldout" / f"{split}_shards_{count}" / f"shard_{index}"


def bootstrap_unsharded_rows(
    *, data_dir: Path, runs_dir: Path, run_id: str, language: str,
    shard_count: int, selection_policy: str,
) -> dict:
    """Copy completed paired rows into disjoint shards before parallel jobs start."""
    run_dir = _run_path(runs_dir, run_id)
    source = data_dir / "test_id.jsonl"
    original_meta = json.loads((run_dir / "test_id_metadata.json").read_text(encoding="utf-8"))
    original_path = run_dir / "test_id_paired.jsonl"
    original_rows = read_jsonl(original_path)
    if (original_meta["run_id"] != run_id or original_meta["language"] != language
            or original_meta["dataset_sha256"] != sha256_file(source)
            or original_meta.get("selection_policy") != selection_policy):
        raise ValueError("The original evaluation metadata does not match this shard plan")
    config = json.loads((run_dir / "config.json").read_text(encoding="utf-8"))
    if config["dataset_version"] != data_dir.name or config["language"] != language:
        raise ValueError("The original run uses another dataset or language")
    seed = (run_dir / "seed_prompt.md").read_text(encoding="utf-8").strip()
    if selection_policy == "latest_val_tie":
        result = json.loads((run_dir / "gepa_result.json").read_text(encoding="utf-8"))
        scores = [float(value) for value in result["val_aggregate_scores"]]
        top = max(scores)
        selected_idx = max(idx for idx, score in enumerate(scores) if abs(score - top) < 1e-12)
        selected = result["candidates"][selected_idx]["system_prompt"].strip()
    elif selection_policy == "gepa":
        selected_idx = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))["best_idx"]
        selected = (run_dir / "best_prompt.md").read_text(encoding="utf-8").strip()
    else:
        raise ValueError("Unsupported selection policy")
    if (original_meta["seed_prompt_sha256"] != sha256_text(seed)
            or original_meta["best_prompt_sha256"] != sha256_text(selected)
            or original_meta["selected_candidate_idx"] != selected_idx):
        raise ValueError("The original evaluation used different prompts")
    records = load_v2_split(data_dir, "test_id", language)
    by_id = {item["id"]: (position, item) for position, item in enumerate(records)}
    if len(by_id) != len(records):
        raise ValueError("Duplicate IDs in the full test set")
    copied = {idx: [] for idx in range(shard_count)}
    seen = set()
    for row in original_rows:
        question_id = row["id"]
        if question_id in seen or question_id not in by_id:
            raise ValueError("Duplicate or unknown completed test row")
        seen.add(question_id)
        position, item = by_id[question_id]
        if row["question"] != item["question"] or row["answer"] != item["answer"]:
            raise ValueError("Original test row content does not match the fixed test set")
        copied[position % shard_count].append(row)
    for index, rows in copied.items():
        directory = shard_dir(run_dir, "test_id", index, shard_count)
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / "paired.jsonl"
        if target.exists():
            if read_jsonl(target) != rows:
                raise ValueError("A shard already contains different completed rows")
        else:
            write_text(target, "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows))
    bootstrap = {
        "run_id": run_id, "language": language, "shard_count": shard_count,
        "selection_policy": selection_policy,
        "selected_candidate_idx": selected_idx,
        "source_paired_sha256": sha256_file(original_path),
        "source_metadata_sha256": sha256_file(run_dir / "test_id_metadata.json"),
        "full_test_dataset_sha256": sha256_file(source),
        "copied_total": len(original_rows),
        "copied_per_shard": {str(index): len(rows) for index, rows in copied.items()},
        "bootstrapped_at_utc": utc_now(),
    }
    write_json(run_dir / "heldout" / f"test_id_shards_{shard_count}" / "bootstrap.json", bootstrap)
    return bootstrap


def _run_scorer(run_dir: Path, run_manifest: dict) -> tuple[Callable, str, str]:
    expected = run_manifest["code_sha256"]["motif_gepa_ko/bilingual.py"]
    current_path = Path(score_v2.__code__.co_filename)
    if sha256_file(current_path) == expected:
        return score_v2, expected, "current_code"
    frozen_path = run_dir / "inputs" / "code" / "motif_gepa_ko" / "bilingual.py"
    if not frozen_path.exists() or sha256_file(frozen_path) != expected:
        raise ValueError("The run's original scoring code snapshot is missing or changed")
    spec = importlib.util.spec_from_file_location(f"_frozen_score_{expected[:12]}", frozen_path)
    if spec is None or spec.loader is None:
        raise ValueError("Cannot load the run's original scoring code")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.score_v2, expected, "run_code_snapshot"


def evaluate_shard_run(
    *, data_dir: Path, runs_dir: Path, run_id: str, language: str,
    shard_index: int, shard_count: int, max_api_calls: int,
    selection_policy: str = "gepa",
    checkpoint_hook: Callable[[], None] | None = None,
) -> dict:
    run_dir = _run_path(runs_dir, run_id)
    if data_dir.name not in V2_DATASETS or language not in ("ko", "en"):
        raise ValueError("Omni v2 dataset and ko/en language required")
    if selection_policy not in {"gepa", "latest_val_tie"}:
        raise ValueError("Unsupported selection policy")
    status = json.loads((run_dir / "run_status.json").read_text(encoding="utf-8"))
    audit = json.loads((run_dir / "audit.json").read_text(encoding="utf-8"))
    if status.get("phase") != "complete" or not audit.get("passed"):
        raise ValueError("The GEPA run has not completed and passed its audit")
    config = json.loads((run_dir / "config.json").read_text(encoding="utf-8"))
    if config.get("dataset_version") != data_dir.name or config.get("language") != language:
        raise ValueError("Dataset or language differs from the completed GEPA run")
    settings = Settings.from_env()
    if (settings.model != config["model"] or settings.base_url != config["base_url"]
            or settings.temperature != config["temperature"]
            or settings.max_output_tokens != config["max_output_tokens"]):
        raise ValueError("Model or generation settings differ from the completed GEPA run")
    manifest = json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))
    scorer, scoring_hash, scoring_source = _run_scorer(run_dir, manifest)

    split = "test_id"
    source = data_dir / f"{split}.jsonl"
    all_records = load_v2_split(data_dir, split, language)
    records = shard_records(all_records, shard_index, shard_count)
    output_dir = shard_dir(run_dir, split, shard_index, shard_count)
    output_dir.mkdir(parents=True, exist_ok=True)
    snapshot_input(source, output_dir / "inputs" / source.name)
    prompts = {
        "seed": (run_dir / "seed_prompt.md").read_text(encoding="utf-8").strip(),
        "best": (run_dir / "best_prompt.md").read_text(encoding="utf-8").strip(),
    }
    optimization_summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    selected_candidate_idx = optimization_summary["best_idx"]
    tied_candidate_indices = None
    if selection_policy == "latest_val_tie":
        result = json.loads((run_dir / "gepa_result.json").read_text(encoding="utf-8"))
        scores = [float(value) for value in result["val_aggregate_scores"]]
        top = max(scores)
        tied_candidate_indices = [idx for idx, score in enumerate(scores)
                                  if abs(score - top) < 1e-12]
        selected_candidate_idx = max(tied_candidate_indices)
        prompts["best"] = result["candidates"][selected_candidate_idx]["system_prompt"].strip()
    same_prompt = prompts["seed"] == prompts["best"]
    calls_per_row = 1 if same_prompt else 2
    if max_api_calls < calls_per_row * len(records):
        raise ValueError("API call budget is below the full shard requirement")
    metadata = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id, "split": split, "language": language,
        "shard_index": shard_index, "shard_count": shard_count,
        "selected_question_ids": [item["id"] for item in records],
        "full_test_dataset_sha256": sha256_file(source),
        "seed_prompt_sha256": sha256_text(prompts["seed"]),
        "best_prompt_sha256": sha256_text(prompts["best"]),
        "selected_candidate_idx": selected_candidate_idx,
        "selection_policy": selection_policy,
        "validation_tie_candidate_indices": tied_candidate_indices,
        "model": settings.model, "base_url": settings.base_url,
        "temperature": settings.temperature,
        "max_output_tokens": settings.max_output_tokens,
        "scoring_code_sha256": scoring_hash,
        "scoring_runtime_source": scoring_source,
        "evaluation_code_sha256": sha256_file(Path(__file__)),
        "identical_prompt_policy": "reuse_seed_response" if same_prompt else "separate_inferences",
    }
    metadata_path = output_dir / "metadata.json"
    if metadata_path.exists() and json.loads(metadata_path.read_text(encoding="utf-8")) != metadata:
        raise ValueError("Existing shard metadata differs; refusing to mix evaluation protocols")
    write_json(metadata_path, metadata)
    write_text(output_dir / "selected_prompt.md", prompts["best"] + "\n")
    paired_path = output_dir / "paired.jsonl"
    prior_rows = read_jsonl(paired_path) if paired_path.exists() else []
    done_ids = [row["id"] for row in prior_rows]
    selected_ids = set(metadata["selected_question_ids"])
    if len(set(done_ids)) != len(done_ids) or not set(done_ids).issubset(selected_ids):
        raise ValueError("The shard contains duplicate or out-of-shard completed rows")
    done = set(done_ids)
    session_id = uuid4().hex
    session_path = output_dir / "sessions.jsonl"
    append_jsonl(session_path, {
        "session_id": session_id, "event": "started", "at_utc": utc_now(),
        "selected": len(records), "already_completed": len(done),
        "max_api_calls": max_api_calls,
    })
    lm = CountedLM(MotifLM(settings), max_api_calls,
                   log_path=output_dir / "api_requests.jsonl", session_id=session_id,
                   checkpoint_hook=checkpoint_hook)
    try:
        for item in records:
            if item["id"] in done:
                continue
            row = {
                "id": item["id"], "question": item["question"], "answer": item["answer"],
                "source_subset": item.get("source_subset"),
                "source_row_index": item.get("source_row_index"),
                "same_inference_reused": same_prompt,
            }
            for name, prompt in prompts.items():
                if name == "best" and same_prompt:
                    row["best"] = dict(row["seed"])
                    continue
                lm.context = {"split": split, "question_id": item["id"],
                              "prompt_variant": name, "shard_index": shard_index}
                response = lm([{"role": "system", "content": prompt},
                               {"role": "user", "content": item["question"]}])
                score, feedback, parsed = scorer(item["answer"], response, language)
                row[name] = {"score": score, "parsed_answer": parsed,
                             "feedback": feedback, "response": response}
            append_jsonl(paired_path, row)
            done.add(item["id"])
            if checkpoint_hook is not None:
                checkpoint_hook()
    except BaseException as exc:
        append_jsonl(session_path, {
            "session_id": session_id, "event": "interrupted", "at_utc": utc_now(),
            "logical_api_calls": lm.calls, "error_type": type(exc).__name__,
            "http_status_code": getattr(exc, "status_code", None),
        })
        raise
    all_rows = read_jsonl(paired_path)
    by_id = {row["id"]: row for row in all_rows}
    ordered = [by_id[item["id"]] for item in records]
    summary = {
        "schema_version": SCHEMA_VERSION, "run_id": run_id,
        "split": split, "language": language,
        "shard_index": shard_index, "shard_count": shard_count,
        "selected": len(records), "completed": len(ordered),
        "seed_correct": sum(row["seed"]["score"] for row in ordered),
        "best_correct": sum(row["best"]["score"] for row in ordered),
        "logical_api_calls_this_process": lm.calls,
        "full_test_dataset_sha256": metadata["full_test_dataset_sha256"],
        "selected_candidate_idx": metadata["selected_candidate_idx"],
    }
    write_json(output_dir / "summary.json", summary)
    append_jsonl(session_path, {
        "session_id": session_id, "event": "finished", "at_utc": utc_now(),
        "logical_api_calls": lm.calls, "completed": len(ordered),
    })
    if checkpoint_hook is not None:
        checkpoint_hook()
    return summary


def aggregate_shards_if_complete(
    *, data_dir: Path, runs_dir: Path, run_id: str, language: str, shard_count: int,
) -> dict | None:
    run_dir = _run_path(runs_dir, run_id)
    source = data_dir / "test_id.jsonl"
    records = load_v2_split(data_dir, "test_id", language)
    expected_ids = [item["id"] for item in records]
    full_hash = sha256_file(source)
    metadata_rows = []
    by_id = {}
    for index in range(shard_count):
        directory = shard_dir(run_dir, "test_id", index, shard_count)
        if not (directory / "summary.json").exists():
            return None
        metadata = json.loads((directory / "metadata.json").read_text(encoding="utf-8"))
        summary = json.loads((directory / "summary.json").read_text(encoding="utf-8"))
        rows = read_jsonl(directory / "paired.jsonl")
        expected_shard_ids = expected_ids[index::shard_count]
        if (metadata["selected_question_ids"] != expected_shard_ids
                or metadata["full_test_dataset_sha256"] != full_hash
                or summary["selected"] != len(expected_shard_ids)
                or summary["completed"] != len(expected_shard_ids)
                or len(rows) != len(expected_shard_ids)
                or {row["id"] for row in rows} != set(expected_shard_ids)):
            raise ValueError(f"Shard {index} is incomplete or does not match the test set")
        metadata_rows.append(metadata)
        for row in rows:
            if row["id"] in by_id:
                raise ValueError(f"Duplicate test question across shards: {row['id']}")
            by_id[row["id"]] = row
    common_keys = ("run_id", "split", "language", "shard_count",
                   "full_test_dataset_sha256", "seed_prompt_sha256",
                   "best_prompt_sha256", "selected_candidate_idx", "selection_policy",
                   "model", "base_url", "temperature", "max_output_tokens",
                   "scoring_code_sha256", "evaluation_code_sha256")
    if any(any(row[key] != metadata_rows[0][key] for key in common_keys)
           for row in metadata_rows[1:]):
        raise ValueError("Shard evaluation protocols differ")
    if set(by_id) != set(expected_ids):
        raise ValueError("The aggregate is missing or adds test questions")
    ordered = [by_id[question_id] for question_id in expected_ids]
    aggregate = {
        "schema_version": SCHEMA_VERSION, "run_id": run_id,
        "split": "test_id", "language": language,
        "shard_count": shard_count, "completed": len(ordered),
        "seed_correct": sum(row["seed"]["score"] for row in ordered),
        "best_correct": sum(row["best"]["score"] for row in ordered),
        "seed_accuracy": sum(row["seed"]["score"] for row in ordered) / len(ordered),
        "best_accuracy": sum(row["best"]["score"] for row in ordered) / len(ordered),
        "improved": sum(row["seed"]["score"] < row["best"]["score"] for row in ordered),
        "regressed": sum(row["seed"]["score"] > row["best"]["score"] for row in ordered),
        "full_test_dataset_sha256": full_hash,
        "seed_prompt_sha256": metadata_rows[0]["seed_prompt_sha256"],
        "best_prompt_sha256": metadata_rows[0]["best_prompt_sha256"],
        "selected_candidate_idx": metadata_rows[0]["selected_candidate_idx"],
        "question_ids": expected_ids,
    }
    write_json(run_dir / "heldout" / "test_id_shards_aggregate.json", aggregate)
    return aggregate
