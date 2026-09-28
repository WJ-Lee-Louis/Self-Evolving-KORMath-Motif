"""Detached, resumable translation of Omni v2 training solutions."""

from pathlib import Path
from collections import Counter
import json

import modal


ROOT = Path(__file__).resolve().parent
app = modal.App("motif-gepa-ko-v2-translation")
volume = modal.Volume.from_name("motif-gepa-ko-v2-translations", create_if_missing=True)
image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install("openai>=1.0,<3", "python-dotenv>=1.0,<2")
    .env({"MOTIF_TIMEOUT_SECONDS": "720", "MOTIF_MAX_OUTPUT_TOKENS": "16384"})
    .add_local_python_source("motif_gepa_ko")
    .add_local_dir(str(ROOT / "data" / "omni_v2"), remote_path="/workspace/data/omni_v2")
    .add_local_dir(str(ROOT / "data" / "omni_v2_clean"), remote_path="/workspace/data/omni_v2_clean")
)
secret = modal.Secret.from_name("motif-gepa-infron", required_keys=["INFRON_API_KEY"])


def translation_path(dataset: str) -> Path:
    if dataset == "omni_v2":
        return Path("/translations/train_solutions_ko.jsonl")
    if dataset == "omni_v2_clean":
        return Path("/translations/omni_v2_clean/train_solutions_ko.jsonl")
    raise ValueError(f"Unknown translation dataset: {dataset}")


@app.function(image=image, secrets=[secret], volumes={"/translations": volume},
              timeout=86400, retries=modal.Retries(initial_delay=0.0, max_retries=10),
              cpu=0.5, memory=1024)
def translate_remote(max_records: int = 0, batch_size: int = 2,
                     dataset: str = "omni_v2", prefer_segments: bool = False,
                     prefer_full_plain: bool = False) -> dict:
    from motif_gepa_ko.translation import translate_train

    output_path = translation_path(dataset)
    volume.reload()
    try:
        return translate_train(
            Path("/workspace/data") / dataset / "train.jsonl",
            output_path,
            max_records=max_records,
            batch_size=batch_size,
            checkpoint=volume.commit,
            prefer_segments=prefer_segments,
            prefer_full_plain=prefer_full_plain,
        )
    finally:
        volume.commit()


@app.local_entrypoint()
def translate(max_records: int = 0, batch_size: int = 2,
              dataset: str = "omni_v2", prefer_segments: bool = False,
              prefer_full_plain: bool = False) -> None:
    print(translate_remote.spawn(max_records, batch_size, dataset,
                                 prefer_segments, prefer_full_plain).get())


@app.function(image=image, volumes={"/translations": volume}, timeout=120,
              cpu=0.25, memory=512)
def status_remote(dataset: str = "omni_v2") -> dict:
    volume.reload()
    path = translation_path(dataset)
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()] if path.exists() else []
    flags = Counter(flag for row in rows for flag in row.get("quality_flags", []))
    failures_path = path.with_name("translation_failures.jsonl")
    failures = [json.loads(line) for line in failures_path.read_text(encoding="utf-8").splitlines()
                if line.strip()] if failures_path.exists() else []
    done_ids = {row["id"] for row in rows}
    return {"translated": len(rows), "remaining": 1000 - len(rows),
            "quality_flags": dict(flags),
            "failed_pending_ids": sorted({row["id"] for row in failures} - done_ids),
            "volume": "motif-gepa-ko-v2-translations", "dataset": dataset}


@app.local_entrypoint()
def status(dataset: str = "omni_v2") -> None:
    print(status_remote.remote(dataset))
