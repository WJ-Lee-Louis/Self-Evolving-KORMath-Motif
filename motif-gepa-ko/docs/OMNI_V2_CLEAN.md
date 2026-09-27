# Omni-MATH 독립 문항 분할 (`omni_v2_clean`)

## 변경 이유와 범위

기존 영어 실행 `en-omni-v2-b600-s0`는 초기 검증에서 네 문항에 대한 응답을 받은 뒤 `HRM8K:OMNI-MATH:0153`에서 멈췄다. 이 문항은 데이터에 없는 “problem 32”의 값을 요구한다. Motif API는 이 문항에 답변 텍스트 대신 HTTP 500 `repetition_detected`를 반환했다. 네 번의 실패 호출 시간은 각각 약 638·380·355·510초였다. 초기 검증의 다른 문항 `0032`를 푸는 도중 Modal 선점도 한 차례 있었다. 당시 호출은 약 4,943초 경과했으며, 선점 뒤 동일한 실행 ID에서 재시작했다. 이 실행에서는 아직 프롬프트 진화가 시작되지 않았다.

답변 텍스트가 돌아오면 수학 오답 또는 형식 오류로 채점할 수 있다. API가 HTTP 오류를 반환하여 텍스트가 없으면 정오답을 판정할 수 없다. 새 코드에는 요청당 720초 제한과 재시도 3회를 적용했다. 그래도 실패하는 호출은 오류와 시도 기록을 남기고 Modal 재개 대상으로 넘긴다. 반복 실패를 가짜 수학 오답으로 기록하지 않는다. 자세한 정책은 [API 요청 시간 정책](API_TIMEOUT_RETRY.md)에 있다.

## 재현 가능한 분할

`omni_v2_clean`은 기존 `omni_v2` 입력·선별 규칙과 난이도 경계를 유지하며, 다른 번호의 문제를 참조하는 문항 8개를 분할 전에 제외한다. 제외한 원본 행 번호는 `134, 143, 153, 154, 287, 639, 717, 930`이며 모두 중간 난이도다. 제외 사유와 각 분할의 원본 행 번호 및 SHA-256은 [manifest](../data/omni_v2_clean/manifest.json)에 기록한다. 원본 `omni_v2` 데이터와 이전 실행 기록은 그대로 보존한다.

| 분할 | 쉬움 (<3.5) | 중간 (3.5~6.0) | 어려움 (>6.0) | 합계 |
| --- | ---: | ---: | ---: | ---: |
| `train` | 243 | 682 | 75 | **1,000** |
| `val` | 10 | 30 | 10 | **50** |
| `test_id` | 190 | 519 | 51 | **760** |

원본 분할의 train에서 `0134, 0143, 0287`이 빠지고 `0142, 0374, 0975`가 들어간다. val에서 `0142, 0153, 0374, 0975`가 빠지고 `0074, 0175, 0416, 1047`이 들어간다. test에서는 val로 이동한 네 문항과 문맥 의존 문항 `0154, 0639, 0717, 0930`이 빠진다. 행 번호는 `HRM8K:OMNI-MATH:<네 자리 번호>`의 마지막 번호다. 분할은 원본과 같은 시드의 SHA-256 순서로 다시 생성한다.

영어 질문에서 명시적으로 다른 번호의 문제를 참조하는 패턴을 검사했으며, 남은 문항에는 이 패턴이 없다. 자동 검사는 암묵적인 문맥 누락이나 문제 원문의 모든 품질 결함을 보증하지 않는다. 특정 문항이 다시 지속적으로 실패하면 API 시도 기록과 원문을 검토해야 한다.

```powershell
.\.venv\Scripts\python.exe .\scripts\prepare_omni_v2.py --check
.\.venv\Scripts\python.exe .\scripts\prepare_omni_v2_clean.py --check
.\.venv\Scripts\python.exe -m unittest discover -s tests -q
```

## 영어 재실행

기존 영어 실행은 중지했고, 저장된 실행 디렉터리는 지우지 않았다. 2026-09-27 22:54 KST에 아래 명령으로 **새 run ID**의 영어 실행을 시작했다. 실행 링크는 [Modal 작업](https://modal.com/apps/woojin716/main/ap-qUBAIW9Vy6OI8gnD7UD1f2)이다. 기존 실행 ID로 이어서 수행하면 데이터·설정·코드 해시가 달라 재현성 검사를 통과할 수 없다. 영어 train 피드백에는 매칭된 원본 영어 모범해설이 이미 포함된다.

```powershell
$env:PYTHONIOENCODING='utf-8'
.\.venv\Scripts\modal.exe run .\modal_experiment.py::preflight --dataset omni_v2_clean --language en
.\.venv\Scripts\modal.exe run --detach .\modal_experiment.py::optimize --dataset omni_v2_clean --language en --run-id en-omni-v2-clean-b600-t720-s0 --minibatch-size 5 --batch-sampling omni_difficulty_1_3_1 --max-metric-calls 600 --max-api-calls 1200 --seed 0
```

## 한국어 해설 번역 연결

현재 별도 Modal 번역 작업은 기존 `omni_v2` train 1,000개를 번역 중이며 계속 실행한다. 결과가 완성되면 공통 train 997개 번역을 새 분할로 옮기고, 새로 들어온 `0142, 0374, 0975` 세 문항을 추가 번역해야 한다. 기존 train의 `0134, 0143, 0287` 번역은 새 분할에서 사용하지 않는다. 새 한국어 train 1,000개의 ID·원문 해시·한국어 해설 검토가 끝나야 `omni_v2_clean`의 한국어 사전 확인과 진화를 시작할 수 있다. 같은 난이도·시드·모델·평가 문항을 사용해 두 언어를 비교한다.
