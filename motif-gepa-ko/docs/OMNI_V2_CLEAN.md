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

## 한국어 해설 완성 및 감사

2026-09-28에 [Modal 번역 작업](https://modal.com/apps/woojin716/main/ap-YSr9Bfw0BANB7uG9tJrBVd)을 중단하고 마지막 저장본 987개를 내려받았다. 남은 13개는 Codex가 영어 원문을 직접 읽어 **요약 번역**했다. 이 13개 원문은 논증 공백이나 모순이 많으므로, 번역문에서 이를 숨기지 않았다. [직접 번역 스크립트](../scripts/complete_omni_v2_clean_codex.py)에 정확한 문항과 한국어 문구를 보존한다. Motif를 통한 추가 번역은 진행하지 않는다.

최종 1,000개 중 979개는 Motif 번역을 기반으로 하고, 13개는 Codex 직접 요약 번역이며, 8개는 Motif 번역을 Codex가 원문과 대조해 직접 수정했다. 이전에 생성한 Motif 수정 후보 8개는 수식·결론 확인 후 반영했다. 각 문항의 번역 방식, 원문 SHA-256, 검토 상태는 [한국어 해설 파일](../data/omni_v2_clean/train_solutions_ko.jsonl)에 있다. 수식·숫자 차이 등 44건의 [개별 검토 결정](../data/omni_v2_clean/translation_review_decisions.jsonl)도 별도로 보존한다. 과거 31개 검토 메모는 인코딩이 손상되었으므로 문구 그대로 해석하지 말고 SHA·품질 플래그와 아래 감사 파일을 사용한다.

[전수 구조 감사](../data/omni_v2_clean/translation_audit.jsonl)는 1,000개 전체에 대해 ID 일치, 원문 SHA, 한글 존재 여부, 수식 토큰·숫자 집합 차이, 수식 구분자, 최종 답 숫자 포함 여부를 검사한다. 결과 요약은 [감사 요약](../data/omni_v2_clean/translation_audit_summary.json)에 있다. 수식 토큰 차이 40건과 숫자 집합 차이 56건은 실제 오류와 표기·문장 축약이 섞인 **검토 신호**다. 영어 원문부터 수식 구분자가 깨진 경우 7건과 영어 해설 검토 메모 18건은 [원본 해설 검토 메모](../data/omni_v2_clean/source_solution_issues.jsonl)에 기록했다. 이 18건에는 계산의 명백한 모순과 풀이 생략이 섞여 있으며, 전체를 검증된 원본 오류로 간주하지 않는다. 원본 답 숫자가 영어 해설에 그대로 나타나지 않는 74건에는 분수 답을 `100a+b`로 바꾸는 마지막 계산을 원문이 생략한 경우도 있으므로 단독으로 오답으로 판단하지 않는다.

이 감사는 **1,000개 풀이의 수학적 정당성을 각각 증명한 검증이 아니다.** 원본 해설의 오류가 reflection에 들어갈 수 있고, 영어 실행도 같은 원본을 사용한다. 따라서 이번 두 언어 실험의 진화 경로와 점수는 탐색 결과로 해석하고, 엄밀한 언어 간 성능 주장에는 원본 풀이 품질을 더 확인해야 한다. 한국어와 영어는 동일한 문제 분할, 난이도 표집, 모델, 예산과 시드를 사용한다.

원본 영어 텍스트에는 `\frac`가 폼피드 문자로, `\times`가 탭으로 바뀐 듯한 제어문자가 있다. train의 영어 질문 14개와 영어 해설 27개에 나타나며 중복을 합치면 28개 문항이다. 한국어 해설 27개에도 원본 해설에서 이어진 제어문자가 있다. 한국어 질문에는 없다. 각 문항과 필드별 수량은 감사 파일의 `control_characters`에 있다. 이번 실행의 입력 해시는 고정되었으므로 원본을 현장에서 수정하지 않았다. 이 차이는 **언어 간 성능 비교의 잠재적 교란요인**이며, 확증 실험을 한다면 양쪽 언어의 수식을 교정한 새 데이터 버전으로 두 실행을 다시 시작해야 한다.

데이터 관리용 [교정본](../data/omni_v2_clean_curated/README.md)을 별도 생성했다. train·val·test 전체의 확인된 제어문자를 복원하고, 영어 해설 검토 메모 18건을 메타데이터로 보존한다. 이 메모는 해설을 자동 제외하거나 수학적 내용을 바꾸지 않는다. 현재 영어·한국어 실행에는 반영되지 않는다. 원본 공식 파일과 실행 중인 데이터의 해시를 보존하면서 번역·문안 복원 내역을 추적하려는 목적이다.

```powershell
$env:PYTHONIOENCODING='utf-8'
.\.venv\Scripts\python.exe .\scripts\audit_omni_v2.py --dataset omni_v2_clean
.\.venv\Scripts\python.exe .\scripts\audit_omni_v2_clean_explanations.py
.\.venv\Scripts\modal.exe run .\modal_experiment.py::preflight --dataset omni_v2_clean --language ko
```

## 한국어 진화 실행

2026-09-28 15:39 KST에 [한국어 Modal 작업](https://modal.com/apps/woojin716/main/ap-VvwymeJHaXwPNWaIxdDwTT)을 시작했다. 실행 ID는 `ko-omni-v2-clean-b600-t720-s0`이다. train 1,000개·val 50개, 미니배치 5개에 쉬움/중간/어려움 1:3:1, metric 호출 600회, API 호출 1,200회, 시드 0을 사용한다. 한국어 해설 파일의 실행 시점 SHA-256은 `e50fb3eca132604e0dce208a0e0270669e506aa2e3ca4158d2df370ad72844f8`이다. Modal Volume의 `run_manifest.json`에 입력 파일과 코드 해시가 보존된다. 영어 실행은 같은 분할·예산·시드로 별도 진행 중이다.

```powershell
.\.venv\Scripts\modal.exe run --detach .\modal_experiment.py::optimize --dataset omni_v2_clean --language ko --run-id ko-omni-v2-clean-b600-t720-s0 --minibatch-size 5 --batch-sampling omni_difficulty_1_3_1 --max-metric-calls 600 --max-api-calls 1200 --seed 0
```
