# Omni-MATH v2: 한국어·영어 프롬프트 진화 비교

기존 `omni_v1` 실행은 프롬프트 변화 관찰용이다. **v2는 원본 정제 풀에서 독립적으로 다시 분할한 새 실험**이며, v1에서 진화한 프롬프트를 초기 프롬프트로 재사용하지 않는다. 한국어·영어 실행은 같은 Motif 3, 문항 ID, 정답, 난이도별 미니배치, 채점기, 호출 예산을 사용한다. 문제·풀이·모범해설·reflection에 쓰이는 언어만 바뀐다.

## 데이터 원본과 분할

HRM8K의 `omni-math_do_test.csv` 1,909행에서 기존 품질 감사 기준으로 91행을 제외한 **정수 정답 텍스트 문제 1,818행**을 사용한다. 영어 문제문은 HRM8K의 `original` 열에서, 영어 모범해설은 [원본 Omni-MATH 파일](../data/omni_source/README.md)에서 가져온다. v2 생성기는 원본 CSV에 품질 제외 규칙을 다시 적용하며, **v1의 train·val·test 배정을 사용하지 않는다.**

난이도 구간은 쉬움 `<3.5`, 중간 `3.5~6.0`, 어려움 `>6.0`이다. 정제 풀 전체에 어려움 문항이 **136개**뿐이라 train에 200개를 둘 수 없다. 확정된 배정은 다음과 같다.

| 분할 | 쉬움 | 중간 | 어려움 | 합계 | 용도 |
| --- | ---: | ---: | ---: | ---: | --- |
| `train` | 243 | 682 | 75 | **1,000** | GEPA 미니배치·모범해설 피드백 |
| `val` | 10 | 30 | 10 | **50** | 후보 프롬프트 선택 |
| `test_id` | 190 | 527 | 51 | **768** | 초기·진화 프롬프트 최종 비교 |

구간마다 고정 시드 `omni-v2-bilingual-20260927`와 SHA-256 순위를 써서 무작위처럼 결정적인 순서를 만든다. 영어 원문 하나가 원본 Omni-MATH 여러 행에 매칭되는 **16문항은 test에 우선 배정**하여 모범해설 매칭이 모호한 train 문항이 없도록 했다. 그 사실과 전체 원본 행 번호·파일 해시는 [manifest](../data/omni_v2/manifest.json)에 남는다. 이 test는 공개 벤치마크 파일을 프로젝트 내부에서 재분할한 것이므로 공식 Omni-MATH test 점수라고 보고하지 않는다.

```powershell
.\.venv\Scripts\python.exe .\scripts\prepare_omni_v2.py --check
.\.venv\Scripts\python.exe .\scripts\audit_omni_v2.py
```

각 JSONL 행에는 한국어·영어 문제, 정수 정답, 난이도, 영어 원본 해설, HRM8K 및 Omni-MATH 원본 행 번호가 있다. `question`은 기존 도구와의 호환을 위해 `question_ko`와 같다. **한국어 모범해설은 train 1,000문항에만 번역**하여 별도 `train_solutions_ko.jsonl`에 ID와 원문 해시로 연결한다. val·test 해설은 모델 입력이나 reflection 피드백에 전달하지 않는다.

## 모범해설 번역

[번역 코드](../src/motif_gepa_ko/translation.py)는 수식을 임시 표식으로 보호한 뒤 한국어 해설을 번역하고 수식을 원문 그대로 복원한다. 수식·숫자 보존을 검사하며, 문항별로 결과를 즉시 저장해 중단 시 이어서 실행한다. 자동 검사는 풀이 의미의 정확성을 보증하지 않으므로 무작위 표본도 읽어봐야 한다. 의심되는 문항은 검토해야 한국어 GEPA 사전확인을 통과한다. 번역 요청 기록에는 호출 ID·시간·토큰 사용량을 남기며 API 키는 저장하지 않는다.

Modal에서 로컬 PC 종료와 관계없이 실행하는 명령:

```powershell
$env:PYTHONIOENCODING='utf-8'
.\.venv\Scripts\modal.exe run --detach .\modal_translate_v2.py::translate --max-records 0 --batch-size 2
.\.venv\Scripts\modal.exe run .\modal_translate_v2.py::status
```

결과는 `motif-gepa-ko-v2-translations` Volume에 저장된다. 1,000문항이 끝난 뒤 아래처럼 다운로드하고 감사한다. `--force`는 이전에 다운로드한 로컬 파일을 최신 결과로 갱신할 때 사용한다.
응답 형식이 깨진 문항은 `translation_failures.jsonl`에 남기고 다음 문항을 처리한다. `::status`에서 미완료 ID를 확인하고 같은 번역 명령을 재실행하면 완료된 ID를 건너뛰고 이어서 처리한다. 최신 코드에서는 JSON 응답이 깨진 한 문항을 문단별 일반 텍스트 번역으로 한 번 더 시도한다. 이 경로에서 얻은 해설에는 `fallback_translation` 경고를 붙여 사람이 원문과 비교해 승인해야 한다.

```powershell
.\.venv\Scripts\modal.exe volume get --force motif-gepa-ko-v2-translations train_solutions_ko.jsonl .\data\omni_v2\train_solutions_ko.jsonl
.\.venv\Scripts\python.exe .\scripts\audit_omni_v2.py
.\.venv\Scripts\python.exe .\scripts\review_omni_v2.py --refresh-flags
.\.venv\Scripts\python.exe .\scripts\review_omni_v2.py
```

로컬에서 직접 번역하려면 `.\.venv\Scripts\python.exe .\scripts\translate_omni_v2.py`를 사용한다. 이것도 완료된 ID부터 이어서 실행하지만 PC를 켜둬야 한다. 번역 API 호출은 GEPA의 600회 평가 예산과 별개다. 다운로드한 번역 파일에는 먼저 `--refresh-flags`로 현재 품질 검사 기준을 다시 적용한다. 수식·숫자만으로 된 원문 해설에는 한국어 문자가 없어도 경고를 붙이지 않는다. 원문 숫자의 누락·새 숫자, 원본 해설의 수식 구분자 불균형은 검토 대상으로 남긴다.
표시된 문항은 `review_omni_v2.py --id <문항ID>`로 원문·번역을 나란히 읽고, 확인한 경우에만 `--approve --note "검토 내용"`으로 승인한다.

## GEPA 실행과 피드백

train 미니배치는 매번 쉬움 1·중간 3·어려움 1을 추출한다. val도 10:30:10으로 구성했다. 두 언어 모두 마지막 줄의 `FINAL_ANSWER: 정수`를 같은 코드로 채점한다. 풀이 모델에게는 문제문과 시스템 프롬프트만 전송된다. **train 채점기만** 정답과 해당 언어 모범해설을 피드백에 넣고, GEPA 원본 어댑터가 실제 풀이 응답과 그 피드백을 reflection에 제공한다. val과 test는 정답 채점만 수행한다.
어려운 train 문항은 75개이므로 GEPA 미니배치 반복이 75회를 넘으면 이 구간은 순환하며 다시 사용된다. 실제 반복 횟수와 재사용 여부는 실행 이벤트의 문항 ID로 확인한다.

언어별 600회는 문제 **채점 호출 상한**이다. 초기 val 50회, 반복별 미니배치 및 후보 검증이 여기에 포함된다. API 호출 상한 1,200회는 reflection까지 포함하는 프로세스당 안전장치다. 한국어·영어 실행은 반드시 다른 run ID를 사용한다.

```powershell
$env:PYTHONIOENCODING='utf-8'
.\.venv\Scripts\modal.exe run .\modal_experiment.py::preflight --dataset omni_v2 --language ko
.\.venv\Scripts\modal.exe run .\modal_experiment.py::preflight --dataset omni_v2 --language en
.\.venv\Scripts\modal.exe run --detach .\modal_experiment.py::optimize --dataset omni_v2 --language ko --run-id ko-omni-v2-b600-s0 --minibatch-size 5 --batch-sampling omni_difficulty_1_3_1 --max-metric-calls 600 --max-api-calls 1200 --seed 0
.\.venv\Scripts\modal.exe run --detach .\modal_experiment.py::optimize --dataset omni_v2 --language en --run-id en-omni-v2-b600-s0 --minibatch-size 5 --batch-sampling omni_difficulty_1_3_1 --max-metric-calls 600 --max-api-calls 1200 --seed 0
```

기존 v1 Modal 작업은 처음 전송된 원격 이미지로 계속 실행된다. 로컬 코드가 달라졌으므로 **편집된 현재 파일로 기존 run ID를 수동 재시작하지 않는다.** 이전 실행 코드는 IEPBL Git 리비전 `bbf05d3a055219b778152ad94176d5ab0d84c6e9`에 있다. 기존 작업이 끝나면 프롬프트와 계보 기록을 내려받아 관찰한 다음 v1 전용 파일을 정리할 수 있다. 이 작업에서 Git 커밋·푸시는 하지 않는다.

최종 test 768문항에서 초기·최종 프롬프트를 각각 평가하면 **언어별 최소 1,536회, 두 언어 합계 3,072회 풀이 호출**이 든다. 무료 API 기한까지 모두 끝난다고 보장할 수 없으므로 test 평가도 중단 후 재개 가능한 함수를 사용한다. 두 프롬프트의 응답을 받은 문항마다 결과를 Volume에 커밋하며, 24시간 제한 등으로 재시작하면 완료된 문항을 건너뛴다. 전체 평가 시 언어별로 `--split test_id --limit 0 --max-api-calls 1800`을 설정한다. 기한 때문에 일부 test만 우선 평가하면 두 언어에 같은 사전 고정 문항을 사용하고 부분 평가로 명시한다.

```powershell
.\.venv\Scripts\modal.exe run --detach .\modal_experiment.py::evaluate --dataset omni_v2 --language ko --run-id ko-omni-v2-b600-s0 --split test_id --limit 0 --max-api-calls 1800
.\.venv\Scripts\modal.exe run --detach .\modal_experiment.py::evaluate --dataset omni_v2 --language en --run-id en-omni-v2-b600-s0 --split test_id --limit 0 --max-api-calls 1800
```
