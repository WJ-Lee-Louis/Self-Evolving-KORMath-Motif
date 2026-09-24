# IEPBL: 한국어 프롬프트 진화 실험

이 저장소에는 GEPA 원본 코드, 한국어 수학 데이터셋 원본, Motif 3 실험 코드를 분리해 둡니다. 모든 파일은 IEPBL 저장소 하나에서 관리합니다. GEPA와 HRM8K는 아래 원본 커밋의 스냅샷입니다.

| 경로 | 용도 |
| --- | --- |
| `upstream/gepa/` | [GEPA 공식 저장소](https://github.com/gepa-ai/gepa)의 복제본 |
| `datasets/HRM8K/` | [HRM8K 데이터셋](https://huggingface.co/datasets/HAERAE-HUB/HRM8K)의 복제본 |
| `motif-gepa-ko/` | 인프론 Motif 3 API 연결과 한국어 프롬프트 실험 설정 |

## 저장소 받기

```powershell
git clone https://github.com/WJ-Lee-Louis/Self-Evolving-KORMath-Motif.git
cd Self-Evolving-KORMath-Motif\motif-gepa-ko
```

원본 스냅샷은 GEPA `d771eb21b5dd3228bc3f567293d2ccfc423fc900`, HRM8K `c360cabf8d733a82455565358b3dc965aab9ba8d`입니다. 새로 복제해도 하위 모듈 설정은 필요하지 않습니다. 커밋과 푸시는 이 저장소의 `main` 브랜치에서 진행합니다.

설치와 API 키 발급은 [`motif-gepa-ko/README.md`](motif-gepa-ko/README.md), 확정된 데이터 분할은 [`DATA_SPLITS.md`](motif-gepa-ko/docs/DATA_SPLITS.md), 실험 실행은 [`EXPERIMENT_RUN.md`](motif-gepa-ko/docs/EXPERIMENT_RUN.md)를 참고하세요. `.env`, `.venv`, `runs/`와 다운로드한 실행 결과는 Git 추적에서 제외합니다.
