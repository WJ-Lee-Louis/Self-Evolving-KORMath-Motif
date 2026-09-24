"""Inspect local configuration or make one small authenticated Motif call."""

import argparse
import importlib.util

from motif_gepa_ko.gepa_setup import load_prompt_assets
from motif_gepa_ko.model import MotifLM
from motif_gepa_ko.settings import Settings


def main() -> None:
    parser = argparse.ArgumentParser(description="Motif 3 / GEPA 연결 확인")
    parser.add_argument(
        "--check-config",
        action="store_true",
        help="API 호출 없이 로컬 설정과 한국어 프롬프트 파일 확인",
    )
    args = parser.parse_args()

    settings = Settings.from_env(require_key=not args.check_config)
    seed, reflection = load_prompt_assets()
    if importlib.util.find_spec("gepa") is None:
        raise RuntimeError("GEPA가 설치되지 않았습니다. README의 설치 명령을 실행하세요.")

    print(f"모델: {settings.model}")
    print(f"API 주소: {settings.base_url}")
    print(f"한국어 초기 프롬프트: {len(seed)}자")
    print(f"한국어 reflection 템플릿: {len(reflection)}자")
    print(f"API 키 설정: {'완료' if settings.api_key else '대기'}")

    if args.check_config:
        print("로컬 설정 확인 완료. API 호출은 수행하지 않았습니다.")
        return

    reply = MotifLM(settings)("안녕하세요. 연결 확인을 위해 한국어로 짧게 답해주세요.")
    print(f"Motif 응답: {reply}")


if __name__ == "__main__":
    main()
