# IEPBL: 한국어 프롬프트 진화 실험

이 저장소에는 GEPA 원본 코드, 한국어 수학 데이터셋 원본, Motif 3 실험 코드를 분리해 둡니다. 원본 GEPA와 HRM8K는 각각 지정된 커밋의 Git 하위 모듈로 연결합니다.

| 경로 | 용도 |
| --- | --- |
| `upstream/gepa/` | [GEPA 공식 저장소](https://github.com/gepa-ai/gepa)의 복제본 |
| `datasets/HRM8K/` | [HRM8K 데이터셋](https://huggingface.co/datasets/HAERAE-HUB/HRM8K)의 복제본 |
| `motif-gepa-ko/` | 인프론 Motif 3 API 연결과 한국어 프롬프트 실험 설정 |

## 저장소 받기

```powershell
git clone --recurse-submodules https://github.com/WJ-Lee-Louis/Self-Evolving-KORMath-Motif.git
cd Self-Evolving-KORMath-Motif\motif-gepa-ko
```

이미 복제했다면 루트 폴더에서 `git submodule update --init --recursive`를 실행합니다. 하위 모듈은 GEPA `d771eb21b5dd3228bc3f567293d2ccfc423fc900`, HRM8K `c360cabf8d733a82455565358b3dc965aab9ba8d`에 고정됩니다.

설치와 API 키 발급은 [`motif-gepa-ko/README.md`](motif-gepa-ko/README.md), 확정된 데이터 분할은 [`DATA_SPLITS.md`](motif-gepa-ko/docs/DATA_SPLITS.md), 실험 실행은 [`EXPERIMENT_RUN.md`](motif-gepa-ko/docs/EXPERIMENT_RUN.md)를 참고하세요. `.env`, `.venv`, `runs/`와 다운로드한 실행 결과는 Git 추적에서 제외합니다.
