"""Environment-based Infron settings; the API key is never stored in source."""

from dataclasses import dataclass
import os
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BASE_URL = "https://llm.onerouter.pro/v1"
DEFAULT_MODEL = "motif/motif-3"


@dataclass(frozen=True)
class Settings:
    api_key: str
    base_url: str = DEFAULT_BASE_URL
    model: str = DEFAULT_MODEL
    timeout_seconds: float = 60.0
    temperature: float = 0.0
    max_output_tokens: int = 2048

    @classmethod
    def from_env(cls, *, require_key: bool = True) -> "Settings":
        load_dotenv(PROJECT_ROOT / ".env")
        key = os.getenv("INFRON_API_KEY", "").strip()
        if require_key and not key:
            raise ValueError("INFRON_API_KEY가 없습니다. .env 파일 또는 환경 변수에 설정하세요.")

        timeout = float(os.getenv("MOTIF_TIMEOUT_SECONDS", "60"))
        if timeout <= 0:
            raise ValueError("MOTIF_TIMEOUT_SECONDS는 0보다 커야 합니다.")
        temperature = float(os.getenv("MOTIF_TEMPERATURE", "0"))
        if not 0 <= temperature <= 2:
            raise ValueError("MOTIF_TEMPERATURE는 0에서 2 사이여야 합니다.")
        max_output_tokens = int(os.getenv("MOTIF_MAX_OUTPUT_TOKENS", "2048"))
        if max_output_tokens < 1:
            raise ValueError("MOTIF_MAX_OUTPUT_TOKENS는 1 이상이어야 합니다.")

        return cls(
            api_key=key,
            base_url=os.getenv("INFRON_BASE_URL", DEFAULT_BASE_URL).rstrip("/"),
            model=os.getenv("MOTIF_MODEL", DEFAULT_MODEL).strip(),
            timeout_seconds=timeout,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
        )
