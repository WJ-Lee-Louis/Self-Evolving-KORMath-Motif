"""Request fresh Motif translations for rows with damaged source math markup.

This writes review candidates under ignored runs/. It never edits the dataset.
Run one repair process at a time to limit concurrent API requests.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import time

from openai import OpenAI

from motif_gepa_ko.settings import Settings
from motif_gepa_ko.translation import quality_flags


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "omni_v2_clean"
OUTPUT = ROOT / "runs" / "omni_v2_clean_translation_repair"


def read(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ids", nargs="+", help="Full IDs or four-digit Omni row numbers")
    args = parser.parse_args()
    train = {row["id"]: row for row in read(DATA / "train.jsonl")}
    translated = {row["id"]: row for row in read(DATA / "train_solutions_ko.jsonl")}
    settings = Settings.from_env()
    client = OpenAI(api_key=settings.api_key, base_url=settings.base_url,
                    timeout=settings.timeout_seconds, max_retries=0)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for raw_id in args.ids:
        identifier = raw_id if raw_id.startswith("HRM8K:") else f"HRM8K:OMNI-MATH:{int(raw_id):04d}"
        if identifier not in train:
            raise ValueError(f"Unknown training row: {identifier}")
        source = train[identifier]["solution_en"]
        target = OUTPUT / f"{identifier.split(':')[-1]}.json"
        if target.exists():
            raise FileExistsError(f"Review candidate already exists: {target}")
        messages = [
            {"role": "system", "content": (
                "Translate every English prose sentence in the supplied math solution "
                "into Korean. Return only the complete Korean translation. "
                "Copy all mathematical expressions, variables, numerical values, "
                "and LaTeX commands exactly, even if the source has broken or "
                "unbalanced math delimiters. Do not solve the problem again, "
                "omit any step, or add new reasoning. Do not leave English prose "
                "untranslated."
            )},
            {"role": "user", "content": (
                f"Problem: {train[identifier]['question_en']}\n\n"
                f"Reference solution to translate:\n{source}"
            )},
        ]
        started = time.perf_counter()
        response = client.chat.completions.create(
            model=settings.model,
            messages=messages,
            temperature=0,
            max_completion_tokens=12000,
            extra_body={"usage": {"include": True}},
        )
        content = response.choices[0].message.content if response.choices else None
        if not isinstance(content, str) or not content.strip():
            raise ValueError(f"Empty repair translation: {identifier}")
        korean = content.strip()
        if not re.search(r"[가-힣]", korean):
            raise ValueError(f"No Korean prose in repair translation: {identifier}")
        artifact = {
            "id": identifier,
            "source_solution_sha256": hashlib.sha256(source.encode("utf-8")).hexdigest(),
            "previous_quality_flags": translated.get(identifier, {}).get("quality_flags", []),
            "candidate_quality_flags": quality_flags(source, korean),
            "candidate_solution_ko": korean,
            "translator_model": settings.model,
            "response_id": response.id,
            "usage": response.usage.model_dump(mode="json") if response.usage else None,
            "seconds": round(time.perf_counter() - started, 3),
        }
        target.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(identifier, "candidate saved", target, artifact["candidate_quality_flags"], flush=True)


if __name__ == "__main__":
    main()
