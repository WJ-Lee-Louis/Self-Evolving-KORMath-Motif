"""Detached Modal GEPA search and held-out comparison with persistent output."""

from pathlib import Path

import modal


ROOT = Path(__file__).resolve().parent
app = modal.App("motif-gepa-ko")
volume = modal.Volume.from_name("motif-gepa-ko-runs", create_if_missing=True)
image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install("openai>=1.0,<3", "python-dotenv>=1.0,<2")
    .env({"MOTIF_TIMEOUT_SECONDS": "120", "MOTIF_TEMPERATURE": "0", "MOTIF_MAX_OUTPUT_TOKENS": "2048",
          "MOTIF_REFLECTION_MAX_OUTPUT_TOKENS": "4096"})
    .add_local_python_source("gepa", "motif_gepa_ko")
    .add_local_dir(str(ROOT / "data" / "hrm8k_v1"), remote_path="/workspace/data")
    .add_local_dir(str(ROOT / "prompts"), remote_path="/workspace/prompts")
)
secret = modal.Secret.from_name("motif-gepa-infron", required_keys=["INFRON_API_KEY"])


@app.function(image=image, timeout=120, cpu=0.25, memory=512)
def preflight_remote() -> dict:
    import gepa
    from motif_gepa_ko.artifacts import make_manifest
    from motif_gepa_ko.data import load_split
    from motif_gepa_ko.gepa_setup import load_prompt_assets
    from motif_gepa_ko.settings import PROJECT_ROOT

    data_dir = Path("/workspace/data")
    seed, reflection = load_prompt_assets(Path("/workspace/prompts"))
    archive_probe = make_manifest(
        PROJECT_ROOT, {"run_id": "preflight"},
        {"train": data_dir / "train.jsonl", "val": data_dir / "val.jsonl"},
        Path("/workspace"),
    )
    return {
        "gepa_optimize_available": callable(gepa.optimize),
        "train_rows": len(load_split(data_dir, "train")),
        "val_rows": len(load_split(data_dir, "val")),
        "seed_chars": len(seed),
        "reflection_chars": len(reflection),
        "artifact_schema_version": archive_probe["schema_version"],
        "code_files_hashed": len(archive_probe["code_sha256"]),
    }


@app.function(image=image, secrets=[secret], volumes={"/results": volume}, timeout=86400, cpu=0.5, memory=1024)
def optimize_remote(run_id: str, max_metric_calls: int, max_api_calls: int, minibatch_size: int, seed: int) -> dict:
    from motif_gepa_ko.experiment import optimize_run

    volume.reload()
    try:
        return optimize_run(
            data_dir=Path("/workspace/data"),
            prompts_dir=Path("/workspace/prompts"),
            runs_dir=Path("/results"),
            run_id=run_id,
            max_metric_calls=max_metric_calls,
            max_api_calls=max_api_calls,
            minibatch_size=minibatch_size,
            seed=seed,
            checkpoint_hook=volume.commit,
        )
    finally:
        volume.commit()


@app.function(image=image, secrets=[secret], volumes={"/results": volume}, timeout=86400, cpu=0.5, memory=1024)
def evaluate_remote(run_id: str, split: str, limit: int, max_api_calls: int) -> dict:
    from motif_gepa_ko.experiment import evaluate_run

    volume.reload()
    try:
        return evaluate_run(
            data_dir=Path("/workspace/data"),
            runs_dir=Path("/results"),
            run_id=run_id,
            split=split,
            limit=limit,
            max_api_calls=max_api_calls,
        )
    finally:
        volume.commit()


@app.local_entrypoint()
def preflight() -> None:
    print(preflight_remote.remote())


@app.local_entrypoint()
def optimize(
    run_id: str,
    max_metric_calls: int = 180,
    max_api_calls: int = 250,
    minibatch_size: int = 3,
    seed: int = 0,
) -> None:
    print(optimize_remote.spawn(run_id, max_metric_calls, max_api_calls, minibatch_size, seed).get())


@app.local_entrypoint()
def evaluate(run_id: str, split: str, limit: int = 20, max_api_calls: int = 100) -> None:
    print(evaluate_remote.spawn(run_id, split, limit, max_api_calls).get())
