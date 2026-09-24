# Motif 3 기반 한국어 GEPA 실험 준비

확정된 HRM8K 데이터 구성과 문항별 분할 규칙은 [데이터 분할 문서](docs/DATA_SPLITS.md)를 참고하세요. 생성된 JSONL과 전체 원본 행 번호 목록은 [`data/hrm8k_v1/`](data/hrm8k_v1/)에 있습니다.

이 폴더는 한국어 수학 문제에 대한 **시스템 프롬프트 진화**를 실행합니다. HRM8K 분할, 숫자 채점 규칙, 예비 실행 예산을 고정했습니다. `upstream/gepa` 원본은 수정하지 않습니다.

## 현재 구성

- `src/motif_gepa_ko/model.py`: 인프론의 OpenAI 호환 API를 GEPA의 `task_lm`과 `reflection_lm`에 연결할 수 있는 호출 함수
- `src/motif_gepa_ko/gepa_setup.py`: 초기 한국어 시스템 프롬프트와 한국어 reflection 템플릿을 읽고 `gepa.optimize` 인자를 준비
- `prompts/seed_ko.md`: 진화할 초기 시스템 프롬프트
- `prompts/reflection_ko.md`: 실패 기록을 읽고 **한국어로** 새 지침을 제안하도록 하는 템플릿
- `src/motif_gepa_ko/smoke.py`: API 키 없이 설정을 점검하거나, 키 발급 후 Motif 3를 한 번 호출
- `modal_smoke.py`: Modal Secret으로 인프론 키를 주입해 원격에서 한 번 호출
- `src/motif_gepa_ko/experiment.py`: GEPA 진화, 한국어 피드백, 후보 계보 기록과 보류 평가
- `modal_experiment.py`: Modal에서 장시간 실행하고 Volume에 결과 저장

GEPA 원본은 `../upstream/gepa`, HRM8K 원본은 `../datasets/HRM8K`에 있습니다. 복제 시점의 정보는 [GEPA 기록](../upstream/README.md)과 [데이터셋 기록](../datasets/README.md)에 남겼습니다.

Modal 계정 연결, 결제 한도 및 원격 API 연결 시험은 [Modal 설정 안내](docs/MODAL_SETUP.md)를 참고하세요.
실제 진화 및 보류 평가 명령은 [실험 실행 문서](docs/EXPERIMENT_RUN.md)를 참고하세요.
반복별 제안·채택·거절, 검증 점수, 부모·자식 관계와 입력 출처의 저장 형식은 [진화 기록 형식](docs/ARTIFACT_SCHEMA.md)에 정리했습니다.

## 설치 (Windows PowerShell)

이 폴더에서 실행합니다.

```powershell
py -3.10 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ..\upstream\gepa -e .
.\.venv\Scripts\python.exe -m motif_gepa_ko.smoke --check-config
```

`--check-config`는 API를 호출하지 않습니다. 모델 이름, GEPA 설치 여부, 한국어 프롬프트 파일만 확인합니다.

## Motif 3 무료 이용 조건과 API 키 연결

2026년 9월 23일 확인 기준, [Motif 대표의 공지](https://www.linkedin.com/posts/junghwan-lim-340b63161_for-the-first-time-were-making-our-model-activity-7505690381896916992-R9lF)는 **인프론에서 Motif 3를 9월 29일까지 무료 제공**한다고 안내합니다. [인프론의 무료 모델 페이지](https://models.infron.ai/models/motif/motif-3)에는 입력·출력 가격이 모두 100만 토큰당 0달러로 표시됩니다. 무료 여부와 한도는 실제 실행 직전에 모델 페이지와 대시보드에서 다시 확인합니다.

[인프론의 일반 무료 모델 정책](https://infron.ai/docs/overview/free-models)은 대부분의 `:free` 모델에 계정 잔액 **5달러 이상**을 요구합니다. 다만 인프론 공식 계정은 [Motif 3에 대한 5달러 최소 잔액 요건을 제거했다고 공지했습니다](https://www.sotwe.com/InfronAI?lang=en) (공식 게시물의 공개 미러). 따라서 **Motif 3 무료 호출을 위해 5달러를 충전해야 한다고 단정할 수 없습니다**. [공식 시작 안내](https://infron.ai/docs/overview/quickstart)는 API 키 생성을 결제 설정보다 앞에 두고, 결제 설정은 일부 기능에 필요하다고 설명합니다. 실제 계정 화면에서 결제 또는 충전을 강제한다면 즉시 결제하지 말고 화면의 요구 사항을 확인한 뒤 `support@infron.ai`에 Motif 3 예외의 계정 적용 여부를 문의하세요. 이 프로젝트는 아직 무결제 계정에서 실제 호출을 검증하지 않았습니다.

1. [인프론 로그인](https://infron.ai/login)에서 계정을 만듭니다.
2. [API Keys 화면](https://infron.ai/dashboard/apiKeys)에서 **Add new key**를 눌러 키를 발급받습니다. 이 순서는 [인프론 공식 시작 안내](https://infron.ai/docs/overview/quickstart)에 나와 있습니다.
3. `.env.example`을 `.env`로 복사하고 `INFRON_API_KEY=` 뒤에 키를 입력합니다. `.env`는 `.gitignore`에 포함돼 있습니다.
4. 아래 연결 확인을 실행합니다.

```powershell
Copy-Item .env.example .env
# .env를 편집해 INFRON_API_KEY를 입력한 뒤 실행
.\.venv\Scripts\python.exe -m motif_gepa_ko.smoke
```

코드는 인프론 공식 문서의 `https://llm.onerouter.pro/v1` 주소와 `motif/motif-3` 모델 ID를 사용합니다. 계정 상태에 따라 API가 `402`(잔액/한도) 또는 `429`(호출 제한)를 반환할 수 있으므로, 연결 시험 결과로 사용 가능 여부를 확인해야 합니다. [Motif 3 API 문서](https://app.infron.ai/models/motif/motif-3/api-reference)

## GEPA 실행

예비 실험은 아래 명령으로 시작합니다. 보류 평가와 결과 다운로드 방법은 [실험 실행 문서](docs/EXPERIMENT_RUN.md)에 있습니다.

```powershell
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
.\.venv\Scripts\modal.exe run --detach .\modal_experiment.py::optimize --run-id ko-pilot-01 --max-metric-calls 180 --max-api-calls 250
```

채택된 한국어 프롬프트 전문과 줄 단위 차이는 `evolution.md`, 거절을 포함한 모든 제안과 중간 평가는 `attempt_timeline.md`·`iterations/<id>/attempt.json`·`events.jsonl`, 부모·자식 관계는 `lineage.json`에 기록됩니다. 고정 분할은 `.\.venv\Scripts\python.exe .\scripts\prepare_hrm8k_splits.py --check`로 재검증할 수 있습니다.
