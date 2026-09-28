"""Resumable Motif translation of Omni v2 training reference solutions."""

from __future__ import annotations

from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import re
import time
from typing import Callable

from openai import APIConnectionError, APITimeoutError, InternalServerError, OpenAI

from motif_gepa_ko.settings import Settings


MATH = re.compile(
    r"\\begin\{([A-Za-z*]+)\}[\s\S]*?\\end\{\1\}|\\\[[\s\S]*?\\\]|\\\([\s\S]*?\\\)|\$\$[\s\S]*?\$\$|\$[^$]*\$|\\\[[\s\S]*$|\\\([\s\S]*$"
)
NUMBER = re.compile(r"(?<![A-Za-z0-9])-?\d+(?:\.\d+)?(?![A-Za-z0-9])")


def mask_math(text: str) -> tuple[str, list[str]]:
    expressions: list[str] = []

    def replace(match: re.Match) -> str:
        placeholder = f"[[MATH_{len(expressions)}]]"
        expressions.append(match.group())
        return placeholder

    return MATH.sub(replace, text), expressions


def restore_math(text: str, expressions: list[str]) -> str:
    for index, expression in enumerate(expressions):
        placeholder = f"[[MATH_{index}]]"
        if text.count(placeholder) != 1:
            raise ValueError(f"The model changed or duplicated {placeholder}")
        text = text.replace(placeholder, expression)
    if re.search(r"\[\[MATH_\d+\]\]", text):
        raise ValueError("The translation contains an unknown math placeholder")
    return text


def quality_flags(source: str, translation: str) -> list[str]:
    source_masked, source_math = mask_math(source)
    target_masked, target_math = mask_math(translation)
    flags = []
    if (source.count(r"\[") != source.count(r"\]")
            or source.count(r"\(") != source.count(r"\)")
            or source.count("$") % 2):
        flags.append("source_unbalanced_math_delimiter")
    if Counter(source_math) != Counter(target_math):
        flags.append("math_expression_mismatch")
    # Repeating an existing number in the Korean prose is usually harmless.
    # Missing numbers or new values need inspection; formulae are checked above.
    source_numbers = set(NUMBER.findall(source_masked))
    target_numbers = set(NUMBER.findall(target_masked))
    if source_numbers - target_numbers:
        flags.append("missing_prose_number")
    if target_numbers - source_numbers:
        flags.append("new_prose_number")
    source_prose = re.sub(r"\[\[MATH_\d+\]\]", "", source_masked)
    if re.search(r"[A-Za-z]", source_prose) and not re.search(r"[가-힣]", translation):
        flags.append("no_hangul_detected")
    return flags


def _json_object(content: str) -> dict:
    content = content.strip()
    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?\s*", "", content)
        content = re.sub(r"\s*```$", "", content)
    return json.loads(content)


def _load_done(path: Path, records: dict[str, dict]) -> set[str]:
    done: set[str] = set()
    if not path.exists():
        return done
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        identifier = item["id"]
        if identifier in done or identifier not in records:
            raise ValueError(f"Duplicate or unknown translation ID: {identifier}")
        expected = hashlib.sha256(records[identifier]["solution_en"].encode("utf-8")).hexdigest()
        if item["source_solution_sha256"] != expected:
            raise ValueError(f"Stale source solution for {identifier}")
        done.add(identifier)
    return done


def _append_lines(path: Path, items: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        for item in items:
            handle.write(json.dumps(item, ensure_ascii=False, separators=(",", ":")) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def _translate_plain_chunks(client: OpenAI, settings: Settings, item: dict) -> tuple[str, list[dict]]:
    """Retry a failed JSON translation in smaller prose chunks.

    These rows always need human review, even when mechanical checks pass.
    """
    masked, expressions = mask_math(item["solution_en"])
    chunks = [part for part in re.split(r"\n\s*\n", masked) if part.strip()]
    if not chunks:
        raise ValueError("The source solution contains no text to translate")
    outputs = []
    requests = []
    for index, chunk in enumerate(chunks):
        started = time.perf_counter()
        response = client.chat.completions.create(
            model=settings.model,
            messages=[
                {"role": "system", "content": (
                    "Translate the supplied English mathematical prose into Korean. "
                    "Return only the translated passage, with no preface or JSON. "
                    "Preserve every [[MATH_n]] placeholder exactly once and in place. "
                    "Keep every numerical value. Do not solve or explain the problem anew."
                )},
                {"role": "user", "content": chunk},
            ],
            temperature=0,
            max_completion_tokens=min(settings.max_output_tokens, 8192),
            extra_body={"usage": {"include": True}},
        )
        content = response.choices[0].message.content if response.choices else None
        if not content or not content.strip():
            raise ValueError(f"Empty plain translation chunk {index}")
        expected = Counter(re.findall(r"\[\[MATH_\d+\]\]", chunk))
        actual = Counter(re.findall(r"\[\[MATH_\d+\]\]", content))
        if expected != actual:
            raise ValueError(f"Plain translation changed math placeholders in chunk {index}")
        outputs.append(content.strip())
        requests.append({
            "status": "fallback_success", "ids": [item["id"]], "chunk_index": index,
            "response_id": response.id,
            "usage": response.usage.model_dump(mode="json") if response.usage else None,
            "seconds": round(time.perf_counter() - started, 3),
        })
    return restore_math("\n\n".join(outputs), expressions), requests


def _translate_prose_segments(client: OpenAI, settings: Settings, item: dict) -> tuple[str, list[dict]]:
    """Keep every math span locally and ask Motif to translate only prose spans.

    This is the last fallback when a model cannot preserve math placeholders in
    a long paragraph. Small batches use JSON; each failed batch is retried as
    independent plain-text requests so a single bad segment does not spoil all.
    """
    masked, expressions = mask_math(item["solution_en"])
    parts = re.split(r"(\[\[MATH_\d+\]\])", masked)
    indices = [index for index, part in enumerate(parts)
               if not re.fullmatch(r"\[\[MATH_\d+\]\]", part) and re.search(r"[A-Za-z]", part)]
    requests: list[dict] = []

    def preserve_space(index: int, translated: str) -> str:
        original = parts[index]
        return (re.match(r"^\s*", original).group()
                + translated.strip()
                + re.search(r"\s*$", original).group())

    def plain(index: int) -> str:
        started = time.perf_counter()
        response = client.chat.completions.create(
            model=settings.model,
            messages=[
                {"role": "system", "content": (
                    "Translate the supplied English mathematical prose into Korean. "
                    "Return only its translation. Keep all numerical values and "
                    "do not add or remove a mathematical step."
                )},
                {"role": "user", "content": parts[index]},
            ],
            temperature=0,
            max_completion_tokens=min(settings.max_output_tokens, 4096),
            extra_body={"usage": {"include": True}},
        )
        content = response.choices[0].message.content if response.choices else None
        if not isinstance(content, str) or not content.strip():
            raise ValueError(f"Empty prose segment translation {index}")
        requests.append({"status": "segment_success", "ids": [item["id"]],
                         "segment_index": index, "response_id": response.id,
                         "usage": response.usage.model_dump(mode="json") if response.usage else None,
                         "seconds": round(time.perf_counter() - started, 3)})
        return preserve_space(index, content)

    for start in range(0, len(indices), 5):
        group = indices[start:start + 5]
        payload = [{"id": str(index), "text": parts[index]} for index in group]
        started = time.perf_counter()
        try:
            response = client.chat.completions.create(
                model=settings.model,
                messages=[
                    {"role": "system", "content": (
                        "Translate each English mathematical prose text into Korean. "
                        "Keep every numerical value. Return JSON with a 'translations' "
                        "array of objects containing exactly 'id' and 'text'. "
                        "Do not solve the problem or add steps."
                    )},
                    {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
                ],
                temperature=0,
                max_completion_tokens=min(settings.max_output_tokens, 4096),
                extra_body={"usage": {"include": True}},
            )
            content = response.choices[0].message.content if response.choices else None
            if not isinstance(content, str) or not content.strip():
                raise ValueError("Empty batch of prose segment translations")
            translated = _json_object(content)["translations"]
            if (not isinstance(translated, list) or len(translated) != len(group)
                    or {x["id"] for x in translated} != {str(x) for x in group}):
                raise ValueError("Segment translation IDs do not match")
            by_id = {x["id"]: x["text"] for x in translated}
            if not all(isinstance(by_id[str(x)], str) and by_id[str(x)].strip() for x in group):
                raise ValueError("Empty segment translation")
            for index in group:
                parts[index] = preserve_space(index, by_id[str(index)])
            requests.append({"status": "segment_batch_success", "ids": [item["id"]],
                             "segment_indices": group, "response_id": response.id,
                             "usage": response.usage.model_dump(mode="json") if response.usage else None,
                             "seconds": round(time.perf_counter() - started, 3)})
        except Exception as exc:
            requests.append({"status": "segment_batch_error", "ids": [item["id"]],
                             "segment_indices": group, "error_type": type(exc).__name__,
                             "error": str(exc)[:500],
                             "seconds": round(time.perf_counter() - started, 3)})
            for index in group:
                parts[index] = plain(index)
    return restore_math("".join(parts), expressions), requests


def _translate_whole_plain(client: OpenAI, settings: Settings, item: dict) -> tuple[str, list[dict]]:
    """Translate the complete source without masking equations; review the result."""
    started = time.perf_counter()
    response = client.chat.completions.create(
        model=settings.model,
        messages=[
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
                f"Problem: {item['question_en']}\n\n"
                f"Reference solution to translate:\n{item['solution_en']}"
            )},
        ],
        temperature=0,
        max_completion_tokens=min(settings.max_output_tokens, 12000),
        extra_body={"usage": {"include": True}},
    )
    content = response.choices[0].message.content if response.choices else None
    if not isinstance(content, str) or not content.strip():
        raise ValueError("Empty whole-solution translation")
    if re.search(r"[A-Za-z]", item["solution_en"]) and not re.search(r"[가-힣]", content):
        raise ValueError("No Korean prose in whole-solution translation")
    return content.strip(), [{
        "status": "whole_plain_success", "ids": [item["id"]],
        "response_id": response.id,
        "usage": response.usage.model_dump(mode="json") if response.usage else None,
        "seconds": round(time.perf_counter() - started, 3),
    }]


def translate_train(
    train_path: Path,
    output_path: Path,
    *,
    max_records: int = 0,
    batch_size: int = 2,
    batch_chars: int = 5500,
    checkpoint: Callable[[], None] | None = None,
    prefer_segments: bool = False,
    prefer_full_plain: bool = False,
) -> dict:
    if batch_size < 1 or batch_chars < 1 or max_records < 0:
        raise ValueError("Invalid translation batch settings")
    records = [json.loads(line) for line in train_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(records) != 1000:
        raise ValueError("The frozen v2 train split must contain 1,000 records")
    by_id = {item["id"]: item for item in records}
    done = _load_done(output_path, by_id)
    settings = Settings.from_env()
    client = OpenAI(api_key=settings.api_key, base_url=settings.base_url,
                    timeout=settings.timeout_seconds, max_retries=0)
    requests_path = output_path.with_name("translation_requests.jsonl")
    failures_path = output_path.with_name("translation_failures.jsonl")
    completed_now = 0

    def send_batch(batch: list[dict]) -> None:
        nonlocal completed_now
        if prefer_full_plain and len(batch) == 1:
            item = batch[0]
            try:
                restored, whole_requests = _translate_whole_plain(client, settings, item)
                whole_row = {
                    "id": item["id"], "solution_ko": restored,
                    "source_solution_sha256": hashlib.sha256(item["solution_en"].encode("utf-8")).hexdigest(),
                    "quality_flags": [*quality_flags(item["solution_en"], restored), "fallback_translation"],
                    "translator_model": settings.model,
                    "translation_strategy": "whole_plain_translation",
                }
                _append_lines(output_path, [whole_row])
                _append_lines(requests_path, whole_requests)
                completed_now += 1
                if checkpoint:
                    checkpoint()
                print(f"Translated whole solution {len(done) + completed_now}/{len(records)}", flush=True)
                return
            except Exception as whole_exc:
                _append_lines(requests_path, [{
                    "status": "whole_plain_error", "ids": [item["id"]],
                    "error_type": type(whole_exc).__name__, "error": str(whole_exc)[:500],
                }])
                if checkpoint:
                    checkpoint()
        if prefer_segments and len(batch) == 1:
            item = batch[0]
            try:
                restored, segment_requests = _translate_prose_segments(client, settings, item)
                segment_row = {
                    "id": item["id"], "solution_ko": restored,
                    "source_solution_sha256": hashlib.sha256(item["solution_en"].encode("utf-8")).hexdigest(),
                    "quality_flags": [*quality_flags(item["solution_en"], restored), "fallback_translation"],
                    "translator_model": settings.model,
                    "translation_strategy": "prose_segments_fallback",
                }
                _append_lines(output_path, [segment_row])
                _append_lines(requests_path, segment_requests)
                completed_now += 1
                if checkpoint:
                    checkpoint()
                print(f"Translated with segment strategy {len(done) + completed_now}/{len(records)}", flush=True)
                return
            except Exception as segment_exc:
                _append_lines(requests_path, [{
                    "status": "segment_strategy_error", "ids": [item["id"]],
                    "error_type": type(segment_exc).__name__, "error": str(segment_exc)[:500],
                }])
                if checkpoint:
                    checkpoint()
        payload = []
        expressions_by_id = {}
        for item in batch:
            masked, expressions = mask_math(item["solution_en"])
            expressions_by_id[item["id"]] = expressions
            payload.append({"id": item["id"], "problem_en": item["question_en"],
                            "solution_en": masked, "answer": item["answer"]})
        messages = [
            {"role": "system", "content": (
                "Translate each English math reference solution into faithful Korean prose. "
                "Translate prose only; preserve every [[MATH_n]] placeholder exactly once. "
                "Keep all Arabic numerals and the mathematical meaning. Do not solve the "
                "problem anew, omit steps, or add facts. Return only JSON with one key "
                "'translations', an array of objects with exactly 'id' and 'solution_ko'."
            )},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ]
        started = time.perf_counter()
        try:
            response = client.chat.completions.create(
                model=settings.model, messages=messages, temperature=0,
                max_completion_tokens=(
                    min(settings.max_output_tokens, 4096) if len(batch) > 1
                    else min(settings.max_output_tokens, 8192)
                ),
                extra_body={"usage": {"include": True}},
            )
            content = response.choices[0].message.content if response.choices else None
            if not content:
                raise ValueError("Empty model translation response")
            parsed = _json_object(content)
            translated = parsed["translations"]
            if not isinstance(translated, list) or {x["id"] for x in translated} != {x["id"] for x in batch}:
                raise ValueError("Translation response IDs do not match the request")
            by_translation_id = {x["id"]: x["solution_ko"] for x in translated}
            output = []
            for item in batch:
                translated_text = by_translation_id[item["id"]]
                if not isinstance(translated_text, str) or not translated_text.strip():
                    raise ValueError(f"Empty translation for {item['id']}")
                restored = restore_math(translated_text.strip(), expressions_by_id[item["id"]])
                output.append({
                    "id": item["id"], "solution_ko": restored,
                    "source_solution_sha256": hashlib.sha256(item["solution_en"].encode("utf-8")).hexdigest(),
                    "quality_flags": quality_flags(item["solution_en"], restored),
                    "translator_model": settings.model,
                })
        except Exception as exc:
            _append_lines(requests_path, [{
                "status": "error", "ids": [item["id"] for item in batch],
                "error_type": type(exc).__name__, "error": str(exc)[:500],
                "response_preview": content[:1000] if isinstance(locals().get("content"), str) else None,
                "seconds": round(time.perf_counter() - started, 3),
            }])
            if checkpoint:
                checkpoint()
            if not isinstance(exc, (ValueError, KeyError, TypeError,
                                    APITimeoutError, APIConnectionError, InternalServerError)):
                raise
            if len(batch) == 1:
                item = batch[0]
                try:
                    restored, fallback_requests = _translate_plain_chunks(client, settings, item)
                    output = [{
                        "id": item["id"], "solution_ko": restored,
                        "source_solution_sha256": hashlib.sha256(item["solution_en"].encode("utf-8")).hexdigest(),
                        "quality_flags": [*quality_flags(item["solution_en"], restored), "fallback_translation"],
                        "translator_model": settings.model,
                        "translation_strategy": "plain_paragraph_fallback",
                    }]
                    _append_lines(output_path, output)
                    _append_lines(requests_path, fallback_requests)
                    completed_now += 1
                    if checkpoint:
                        checkpoint()
                    print(f"Translated with fallback {len(done) + completed_now}/{len(records)}", flush=True)
                    return
                except Exception as fallback_exc:
                    _append_lines(requests_path, [{
                        "status": "fallback_error", "ids": [item["id"]],
                        "error_type": type(fallback_exc).__name__, "error": str(fallback_exc)[:500],
                    }])
                try:
                    restored, segment_requests = _translate_prose_segments(client, settings, item)
                    output = [{
                        "id": item["id"], "solution_ko": restored,
                        "source_solution_sha256": hashlib.sha256(item["solution_en"].encode("utf-8")).hexdigest(),
                        "quality_flags": [*quality_flags(item["solution_en"], restored), "fallback_translation"],
                        "translator_model": settings.model,
                        "translation_strategy": "prose_segments_fallback",
                    }]
                    _append_lines(output_path, output)
                    _append_lines(requests_path, segment_requests)
                    completed_now += 1
                    if checkpoint:
                        checkpoint()
                    print(f"Translated with segment fallback {len(done) + completed_now}/{len(records)}", flush=True)
                    return
                except Exception as segment_exc:
                    _append_lines(requests_path, [{
                        "status": "segment_fallback_error", "ids": [item["id"]],
                        "error_type": type(segment_exc).__name__, "error": str(segment_exc)[:500],
                    }])
                _append_lines(failures_path, [{
                    "id": batch[0]["id"], "error_type": type(exc).__name__,
                    "error": str(exc)[:500],
                    "source_solution_sha256": hashlib.sha256(
                        batch[0]["solution_en"].encode("utf-8")
                    ).hexdigest(),
                }])
                if checkpoint:
                    checkpoint()
                print(f"Translation needs retry: {batch[0]['id']}: {exc}", flush=True)
                return
            midpoint = len(batch) // 2
            send_batch(batch[:midpoint])
            send_batch(batch[midpoint:])
            return

        _append_lines(output_path, output)
        completed_now += len(output)
        usage = response.usage.model_dump(mode="json") if response.usage else None
        _append_lines(requests_path, [{
            "status": "success", "ids": [item["id"] for item in batch],
            "response_id": response.id, "usage": usage,
            "seconds": round(time.perf_counter() - started, 3),
        }])
        if checkpoint:
            checkpoint()
        print(f"Translated {len(done) + completed_now}/{len(records)} training solutions", flush=True)

    pending = [item for item in records if item["id"] not in done]
    if max_records:
        pending = pending[:max_records]
    batch: list[dict] = []
    characters = 0
    for item in pending:
        length = len(item["solution_en"]) + len(item["question_en"])
        if batch and (len(batch) >= batch_size or characters + length > batch_chars):
            send_batch(batch)
            batch, characters = [], 0
        batch.append(item)
        characters += length
    if batch:
        send_batch(batch)
    all_done = _load_done(output_path, by_id)
    return {"total": len(records), "previously_done": len(done),
            "completed_now": completed_now, "remaining": len(records) - len(all_done),
            "output_path": str(output_path)}
