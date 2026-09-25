# 한국어 GEPA 진화·평가 실행

이 문서는 고정된 [HRM8K 분할](DATA_SPLITS.md)로 **한국어 시스템 프롬프트만** GEPA 원본 엔진을 통해 진화시키고, 보류 문항에서 초기·최종 프롬프트를 비교하는 방법이다. `train` 240문항은 반성 피드백, `val` 60문항은 후보 선택에 사용한다. `test_*`는 진화가 끝난 뒤에만 평가한다.

## 사전 확인

프로젝트 폴더 `motif-gepa-ko`에서 실행한다. 로컬 `.env`의 인프론 키와 Modal의 `motif-gepa-infron` Secret은 이미 설정돼 있어야 한다. Windows PowerShell에서 Modal CLI 출력 오류가 나지 않도록 현재 터미널에 UTF-8을 설정한다.

```powershell
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
.\.venv\Scripts\python.exe .\scripts\prepare_hrm8k_splits.py --check
.\.venv\Scripts\python.exe -m unittest discover -s tests
.\.venv\Scripts\modal.exe run .\modal_experiment.py::preflight
```

원격 사전 점검은 GEPA, 프롬프트, train 240개·val 60개를 확인하며 모델 API는 호출하지 않는다.

풀이와 reflection에는 `temperature=0`을 사용한다. 풀이 출력 한도는 2,048토큰이고, reflection 출력 한도는 4,096토큰이다. 예비 실행에서는 두 역할 모두 2,048토큰이었다. 모델 API 요청 제한 시간은 120초다. 로컬 `.env`를 이전 예시에서 복사했다면 `MOTIF_TIMEOUT_SECONDS=60`일 수 있으므로 로컬 장시간 실행 전 120으로 조정한다. 인프론의 Motif 3 무료 제공은 앞서 확인한 공지상 **2026년 9월 29일까지**이므로 실행 직전에 모델 요금과 계정 한도를 다시 확인한다.

## 진화 실행

기본 예산은 **GEPA 평가 180회**와 **모델 논리 호출 250회**다. 검증 세트 전체 60문항이 후보마다 재평가되므로 이 기본값은 짧은 **예비 진화**다. 실제 Motif API로 GEPA의 제안·평가·채택 과정을 실행하지만, 장기 실험에 앞서 경로와 기록을 확인하는 작은 예산이다. 모의 실행이나 단순 연결 점검을 뜻하지 않는다. 초기 `val` 평가에 60회가 쓰이고, 이후 채택 후보 하나당 `val` 60회와 훈련 묶음 평가가 추가된다. 따라서 반복 횟수나 채택 후보 수는 고정되어 있지 않으며, 개선이 반드시 일어나는 것도 아니다. 모델 논리 호출 상한에는 문제 풀이와 reflection 호출이 모두 들어간다. GEPA의 `max_metric_calls`는 반복 한 번의 평가 묶음만큼 초과할 수 있으므로 `max_api_calls`도 함께 지정한다. 인프론 SDK의 자동 HTTP 재시도는 논리 호출 횟수에 포함되지 않는다.

### Modal에서 실행하기

```powershell
.\.venv\Scripts\modal.exe run --detach .\modal_experiment.py::optimize --run-id ko-pilot-01 --max-metric-calls 180 --max-api-calls 250 --minibatch-size 3 --seed 0
```

`--detach`를 사용하면 로컬 터미널이나 컴퓨터를 종료해도 원격 함수는 계속 실행된다. Modal 함수 제한은 진화와 보류 평가 모두 24시간으로 설정했다. 중간 상태는 `motif-gepa-ko-runs` Volume에 저장되며, GEPA가 상태를 저장할 때·각 반복이 끝날 때·함수가 종료될 때 명시적으로 commit한다. 강제 종료 시 저장·commit 이후 진행 중이던 한 반복의 일부 기록은 남지 않을 수 있다. 각 `run-id`는 실험 설정을 고정한다. 같은 ID로 설정을 바꾸면 오류가 나므로 새로운 ID를 사용한다.

### 긴 진화 실행: 1,200회 예산·훈련 묶음 5문항

예비 실행과 같은 train 240문항·val 60문항, 초기 프롬프트, 난수 시드 0을 사용하고 새 실행 ID에서 처음부터 탐색한다. 한 반복에서 부모 프롬프트로 훈련 문제 5개를 풀며, 제안이 생기면 같은 5개로 다시 평가한다. 전체 val 60문항 평가는 제안이 훈련 묶음 심사를 통과한 경우에만 수행한다. 이 설정은 예비 실행과 예산과 묶음 크기가 모두 다르므로 진화 경로 차이를 한 변수의 효과로 해석하지 않는다.

```powershell
.\.venv\Scripts\modal.exe run --detach .\modal_experiment.py::optimize --run-id ko-main-b1200-m5-s0 --max-metric-calls 1200 --max-api-calls 1800 --minibatch-size 5 --seed 0
```

`max-api-calls`는 풀이와 reflection을 합한 한 프로세스의 안전 상한이며, GEPA 평가 예산 1,200회와 다르다. 실제 평가 수는 마지막 반복만큼 1,200회를 넘을 수 있다. 실행 종료 후 `run_status.json`의 `phase=complete`, `audit.json`의 `passed=true`를 확인하고 전체 기록을 내려받는다. `lineage.json`과 `attempt_timeline.md`에서 부모·자식 계보와 중단 시도를 구분해 분석한다. 현재 코드에서 오류로 미완료된 시도는 `decision=interrupted`, 해당 제안은 `decision=evaluation_incomplete`로 기록한다. 보류 `test_*` 평가는 이 실행의 최종 후보를 확정한 뒤에만 진행한다.

### 로컬에서 실행하기

```powershell
.\.venv\Scripts\python.exe -m motif_gepa_ko.cli optimize --run-id ko-pilot-01 --max-metric-calls 180 --max-api-calls 250
```

로컬 실행 결과는 `runs/ko-pilot-01/`에 저장된다. 같은 ID에 GEPA 상태가 있으면 원본 GEPA가 이어서 실행할 수 있다. 단, 앱의 `max_api_calls`는 **새 프로세스의 호출 상한**이며 이전 프로세스까지 합산한 총량은 아니다.

## 프롬프트 변화와 검증 점수 확인

Modal 결과를 로컬로 받으려면 다음 명령을 사용한다.

```powershell
.\.venv\Scripts\modal.exe volume ls motif-gepa-ko-runs ko-pilot-01
.\.venv\Scripts\modal.exe volume get motif-gepa-ko-runs ko-pilot-01 .\downloaded-ko-pilot-01
```

실제 다운로드 경로에서 아래 파일을 확인한다. 모든 필드의 의미와 연결 키는 [진화 기록 형식](ARTIFACT_SCHEMA.md)에 정리했다.

| 파일 | 내용 |
| --- | --- |
| `evolution.md` | 채택된 모든 한국어 프롬프트 전문, 부모 후보와 검증 정확도, 줄 단위 차이. 실행 완료 후 생성 |
| `validation.jsonl` | 초기 후보와 검증을 받은 후보의 검증 평균, 문항 ID별 점수, 후보 프롬프트와 가능한 경우 응답. 검증 직후 한 줄씩 추가 |
| `events.jsonl` | 훈련 묶음 ID, 각 평가의 점수·응답·궤적, reflection 입력·출력, 제안, 채택·거절, 상태 저장 이벤트 |
| `api_requests.jsonl` | 풀이·reflection 호출별 응답·소요 시간·가능한 경우 사용량과 API 응답 ID. API 키는 저장하지 않음 |
| `iterations/<id>/attempt.json`, `attempt_timeline.md` | 부모·제안·자식 관계, 전후 훈련 점수, 제안 프롬프트와 채택 여부를 반복별 JSON과 한국어 타임라인으로 보존 |
| `lineage.json`, `candidates.csv` | 채택 후보와 거절 제안을 포함한 관계 그래프, 후보별 점수 표 |
| `proposal_graph.md` | 부모 후보→제안→채택 자식을 보이는 관계 그림. 거절 제안도 표시 |
| `candidate_tree.html` | 후보 계보를 브라우저에서 탐색 |
| `best_prompt.md`, `seed_prompt.md` | 평가에 쓸 최종·초기 프롬프트 |
| `summary.json`, `config.json`, `run_manifest.json`, `gepa_result.json` | 최종 점수·예산·모델·데이터와 코드 해시·채택 후보별 검증 세부 점수 |
| `audit.json`, `run_status.json` | 기록 일치성 검사와 완료·중단 상태. `passed=true`와 `complete`를 확인 |
| `inputs/` | 실제 사용한 train·val 문항과 두 초기 프롬프트의 사본 |
| `gepa_state.bin`, `run_log.json`, `iterations/` | GEPA 원본 상태와 반복별 추적 기록. `iterations/seed/`는 초기 후보 |

GEPA는 **초기 후보와 훈련 묶음 심사를 통과해 채택된 후보만** 전체 `val`에서 평가한다. 거절된 제안에는 전체 검증 점수가 없으며, `events.jsonl`의 묶음 평가 및 거절 사유와 `iterations/<id>/trace.json`, `components/system_prompt.txt`로 발자취를 확인한다. 채택된 후보의 `iterations/<id>/meta.json`과 `val_scores.json`에는 검증 평균·문항별 점수가, `outputs/`와 `trajectories/`에는 검증 응답과 추적 정보가 있다. GEPA 내부 검증 ID는 `val.jsonl`의 **0부터 시작하는 행 번호**이며 `validation.jsonl`은 이를 원래 문항 ID로 바꿔 기록한다. `iterations/<id>/reflective_dataset.json`에는 reflection에 제공한 구조화 피드백이 저장된다.

`events.jsonl`과 `validation.jsonl`은 실행 중 추가되고, GEPA 상태는 반복 사이와 정상 종료 시 저장된다. `evolution.md`, `gepa_result.json`, `summary.json`은 정상 완료 시 생성된다. 실행이 비정상 종료되면 마지막으로 저장된 상태 이후의 미완료 반복이나 마지막 원격 commit 이후의 기록은 누락될 수 있다. 거절 후보에게도 전체 검증 점수를 매기려면 추가 실험을 별도로 설계해야 하며, 이는 원본 GEPA의 선택 과정과 API 사용량을 바꾼다.

다운로드한 결과를 나중에 API 키 없이 다시 검사하려면 다음 명령을 사용한다. `passed: True`가 출력되면 후보·부모·프롬프트·검증 점수·입력 사본의 일치성 검사를 통과한 것이다.

```powershell
.\.venv\Scripts\python.exe -m motif_gepa_ko.cli audit --run-dir .\downloaded-ko-pilot-01
```

원격 로그와 진행 상태는 Modal 대시보드의 실행 화면에서도 볼 수 있다. 중간에 멈추려면 실행 디렉터리에 `gepa.stop` 파일을 만들거나 Modal 대시보드에서 작업을 중지한다. 반복 중 종료되면 마지막 저장 상태 이후의 호출은 다시 발생할 수 있다.

## 보류 문항에서 초기·최종 프롬프트 비교

진화가 완료된 뒤에만 실행한다. 먼저 `test_id` 앞 20문항으로 평가 경로를 확인한다. 각 문항을 두 프롬프트로 한 번씩 풀기 때문에 20문항은 모델 호출 40회다.

```powershell
.\.venv\Scripts\modal.exe run --detach .\modal_experiment.py::evaluate --run-id ko-pilot-01 --split test_id --limit 20 --max-api-calls 40
```

전체 평가 시 `--limit 0`을 사용한다. 세 분할은 별도 작업으로 순서대로 실행한다. `test_id` 1,019문항은 최대 2,038회, MATH 두 분할은 각각 200문항·400회 호출이다. 이미 완료된 문항은 같은 실행 ID의 결과 파일을 읽어 건너뛴다.

```powershell
.\.venv\Scripts\modal.exe run --detach .\modal_experiment.py::evaluate --run-id ko-pilot-01 --split test_id --limit 0 --max-api-calls 2100
.\.venv\Scripts\modal.exe run --detach .\modal_experiment.py::evaluate --run-id ko-pilot-01 --split test_ood_math_l1_l2 --limit 0 --max-api-calls 450
.\.venv\Scripts\modal.exe run --detach .\modal_experiment.py::evaluate --run-id ko-pilot-01 --split test_ood_math_l3_l5 --limit 0 --max-api-calls 450
```

평가 파일 `test_*_paired.jsonl`에는 문항별 초기·최종 응답, 추출한 숫자, 정오답, 피드백이 있다. `test_*_summary.json`에는 정확도, 개선·악화 문항 수, 형식 오류 수를 기록한다. 한 번의 생성으로 구한 점수이므로 샘플링 변동 가능성은 결과 해석에 남긴다. MATH 전이는 문제 유형과 난도가 함께 달라지는 평가다.

## 채점 규칙

응답의 **마지막 비어 있지 않은 줄**에서 `정답: 숫자`만 읽는다. 부호, 천 단위 쉼표, 소수점은 허용하고 `Decimal`로 기준 숫자와 비교한다. 풀이 중간에 정답 숫자가 등장해도 마지막 줄이 다르면 오답이다. 형식이 없으면 형식 오류로 따로 집계한다. GEPA에 주는 피드백은 한국어로 오답 유형과 기준 정답을 설명하며, 보류 평가 문항은 GEPA의 reflection에 들어가지 않는다.
