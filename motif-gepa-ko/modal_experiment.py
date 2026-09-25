"""Detached Modal GEPA search and held-out comparison with persistent output."""

from pathlib import Path

import modal


ROOT = Path(__file__).resolve().parent
app = modal.App("motif-gepa-ko")
volume = modal.Volume.from_name("motif-gepa-ko-runs", create_if_missing=True)
image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install("openai>=1.0,<3", "python-dotenv>=1.0,<2")
    .env({"MOTIF_TIMEOUT_SECONDS": "1800", "MOTIF_TEMPERATURE": "0", "MOTIF_MAX_OUTPUT_TOKENS": "16384",
          "MOTIF_REFLECTION_MAX_OUTPUT_TOKENS": "4096"})
    .add_local_python_source("gepa", "motif_gepa_ko")
    .add_local_dir(str(ROOT / "data" / "hrm8k_v1"), remote_path="/workspace/data/hrm8k_v1")
    .add_local_dir(str(ROOT / "data" / "omni_v1"), remote_path="/workspace/data/omni_v1")
    .add_local_dir(str(ROOT / "prompts"), remote_path="/workspace/prompts")
)
secret = modal.Secret.from_name("motif-gepa-infron", required_keys=["INFRON_API_KEY"])
# Modal limits one Function attempt to 24 hours. A retry starts a new attempt;
# GEPA restores the same run_id from the committed state on the Volume.
resume_retries = modal.Retries(initial_delay=0.0, max_retries=10)


def dataset_dir(dataset: str) -> Path:
    if dataset not in {"hrm8k_v1", "omni_v1"}:
        raise ValueError(f"Unknown dataset: {dataset}")
    return Path("/workspace/data") / dataset


@app.function(image=image, timeout=120, cpu=0.25, memory=512)
def preflight_remote(dataset: str = "hrm8k_v1") -> dict:
    import gepa
    from gepa.core.data_loader import ListDataLoader
    from types import SimpleNamespace
    from motif_gepa_ko.artifacts import make_manifest
    from motif_gepa_ko.data import as_gepa_data, load_split
    from motif_gepa_ko.gepa_setup import load_prompt_assets
    from motif_gepa_ko.sampling import OmniStratifiedBatchSampler, batch_bin_counts
    from motif_gepa_ko.settings import PROJECT_ROOT

    data_dir = dataset_dir(dataset)
    seed, reflection = load_prompt_assets(Path("/workspace/prompts"))
    train = load_split(data_dir, "train")
    archive_probe = make_manifest(
        PROJECT_ROOT, {"run_id": "preflight"},
        {"train": data_dir / "train.jsonl", "val": data_dir / "val.jsonl"},
        Path("/workspace"),
    )
    result = {
        "gepa_optimize_available": callable(gepa.optimize),
        "dataset": dataset,
        "train_rows": len(train),
        "val_rows": len(load_split(data_dir, "val")),
        "seed_chars": len(seed),
        "reflection_chars": len(reflection),
        "artifact_schema_version": archive_probe["schema_version"],
        "code_files_hashed": len(archive_probe["code_sha256"]),
    }
    if dataset == "omni_v1":
        sampler = OmniStratifiedBatchSampler(train, seed=0)
        selected = sampler.next_minibatch_ids(ListDataLoader(as_gepa_data(train)), SimpleNamespace(i=0))
        result["batch_sampling"] = sampler.describe()
        result["sample_batch_ids"] = [train[index]["id"] for index in selected]
        result["sample_batch_bins"] = batch_bin_counts(selected, train)
    return result


@app.function(image=image, secrets=[secret], volumes={"/results": volume}, timeout=86400,
              retries=resume_retries, cpu=0.5, memory=1024)
def optimize_remote(run_id: str, max_metric_calls: int, max_api_calls: int, minibatch_size: int, seed: int,
                    dataset: str = "hrm8k_v1", batch_sampling: str = "auto") -> dict:
    from motif_gepa_ko.experiment import optimize_run

    volume.reload()
    try:
        return optimize_run(
            data_dir=dataset_dir(dataset),
            prompts_dir=Path("/workspace/prompts"),
            runs_dir=Path("/results"),
            run_id=run_id,
            max_metric_calls=max_metric_calls,
            max_api_calls=max_api_calls,
            minibatch_size=minibatch_size,
            seed=seed,
            batch_sampling=batch_sampling,
            checkpoint_hook=volume.commit,
        )
    finally:
        volume.commit()


@app.function(image=image, secrets=[secret], volumes={"/results": volume}, timeout=86400,
              retries=resume_retries, cpu=0.5, memory=1024)
def evaluate_remote(run_id: str, split: str, limit: int, max_api_calls: int,
                    dataset: str = "hrm8k_v1") -> dict:
    from motif_gepa_ko.experiment import evaluate_run

    volume.reload()
    try:
        return evaluate_run(
            data_dir=dataset_dir(dataset),
            runs_dir=Path("/results"),
            run_id=run_id,
            split=split,
            limit=limit,
            max_api_calls=max_api_calls,
        )
    finally:
        volume.commit()


@app.local_entrypoint()
def preflight(dataset: str = "hrm8k_v1") -> None:
    print(preflight_remote.remote(dataset))


@app.local_entrypoint()
def optimize(
    run_id: str,
    max_metric_calls: int = 180,
    max_api_calls: int = 250,
    minibatch_size: int = 3,
    seed: int = 0,
    dataset: str = "hrm8k_v1",
    batch_sampling: str = "auto",
) -> None:
    print(optimize_remote.spawn(run_id, max_metric_calls, max_api_calls, minibatch_size, seed,
                                dataset, batch_sampling).get())


@app.local_entrypoint()
def evaluate(run_id: str, split: str, limit: int = 20, max_api_calls: int = 100,
             dataset: str = "hrm8k_v1") -> None:
    print(evaluate_remote.spawn(run_id, split, limit, max_api_calls, dataset).get())
