"""Model and Korean instruction configuration for GEPA runs."""

from pathlib import Path

from motif_gepa_ko.model import MotifLM
from motif_gepa_ko.settings import PROJECT_ROOT, Settings


PROMPTS_DIR = PROJECT_ROOT / "prompts"


def load_prompt_assets(prompts_dir: Path = PROMPTS_DIR, language: str = "ko") -> tuple[str, str]:
    if language not in {"ko", "en"}:
        raise ValueError(f"Unsupported prompt language: {language}")
    seed = (prompts_dir / f"seed_{language}.md").read_text(encoding="utf-8").strip()
    reflection = (prompts_dir / f"reflection_{language}.md").read_text(encoding="utf-8").strip()
    if not seed:
        raise ValueError("초기 시스템 프롬프트가 비어 있습니다.")
    for placeholder in ("<curr_param>", "<side_info>"):
        if placeholder not in reflection:
            raise ValueError(f"{language} reflection template lacks {placeholder}")
    return seed, reflection


def make_gepa_model_kwargs(settings: Settings, prompts_dir: Path = PROMPTS_DIR) -> dict:
    """Return seed and model settings suitable for gepa.optimize."""
    seed, reflection = load_prompt_assets(prompts_dir)
    return {
        "seed_candidate": {"system_prompt": seed},
        "task_lm": MotifLM(settings),
        "reflection_lm": MotifLM(settings),
        "reflection_prompt_template": reflection,
    }
