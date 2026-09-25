# 진화 기록 형식과 분석 방법 (schema v1)

이 문서는 한 실행 ID의 `runs/<run-id>/` 또는 Modal Volume의 같은 경로에 남는 기록을 설명한다. 목적은 **성능 변화와 프롬프트 변화의 근거를 같은 후보·반복·문항 ID로 연결**하는 것이다. 실제 모델 호출 전 입력 파일을 복사하고, 제안·평가 이벤트는 발생할 때마다 JSONL에 추가한다. 완료 시에는 독립적인 기록 감사 결과를 만든다.

## 실행을 다시 식별하는 파일

| 파일 | 역할 |
| --- | --- |
| `config.json` | 모델 ID·API 주소·풀이와 reflection의 개별 출력 한도, 난수 시드, GEPA 및 모델 호출 예산, 분할 파일 해시 |
| `run_manifest.json` | 실행 시각, GEPA 커밋(알 수 있으면), GEPA·프로젝트 핵심 코드 해시, Python 환경, 입력·코드 사본 경로와 해시. API 키는 기록하지 않음 |
| `inputs/train.jsonl`, `inputs/val.jsonl` | GEPA가 실제로 읽은 문항의 바이트 단위 사본. 순서와 문항 ID를 보존 |
| `inputs/seed_ko.md`, `inputs/reflection_ko.md` | 초기 시스템 프롬프트와 reflection 템플릿 원본 사본 |
| `inputs/code/` | 실행에 사용한 프로젝트·GEPA 핵심 Python 파일의 사본. 나중에 코드가 바뀌어도 당시 구현을 읽을 수 있음 |
| `run_sessions.jsonl`, `run_status.json` | 프로세스별 시작·완료·중단, 호출 수와 현재 실행 상태. 재개 시 세션이 추가됨 |
| `api_requests.jsonl` | 실제 풀이·reflection 호출마다 역할, 모델에 보낸 메시지 전문과 응답, 해시, 소요 시간, 제공된 경우 API 응답 ID·토큰 사용량·종료 사유·오류 상태를 기록. 키는 제외 |

`run_id`가 같더라도 설정·입력·핵심 코드가 바뀌면 이어서 실행하지 않는다. GEPA 커밋은 양쪽 환경에서 확인할 수 있을 때 추가로 비교한다. `config.json`의 해시와 `run_manifest.json`의 입력 사본을 함께 확인한다. GEPA에 전달하는 문항 레코드에는 `additional_context.question_id`를 메타데이터로 실어 궤적과 원본 문항을 잇는다. 이 필드는 모델의 사용자 메시지에는 추가되지 않는다.

## 실행 중에 쌓이는 기록

| 파일 | 저장 내용과 시점 |
| --- | --- |
| `events.jsonl` | 시간순 원시 이벤트. `event_id = 세션 UUID:순번`, UTC 시각, `iteration_id` 포함. 부모 선택, 훈련 묶음 문항 ID, 부모·제안 평가 점수와 응답·피드백, reflection 입력·출력, 채택·거절, 검증 평균, 저장 시점 등을 기록 |
| `validation.jsonl` | 초기 후보와 **전체 검증을 받은 채택 후보**마다 후보 전문, 부모 후보, 평균 정확도, 원래 HRM8K 문항 ID별 점수, 가능한 경우 응답을 기록 |
| `iterations/<iteration_id>/attempt.json` | 그 반복의 부모·제안·채택 자식, 훈련 묶음별 전후 점수, 검증 결과, 프롬프트 전문·부모 대비 diff, 해당 이벤트 전문을 한 파일에 모음. 반복 종료 시 생성 |
| `iterations/<iteration_id>/trace.json` | GEPA의 해당 반복 원본 추적 정보. 평가 응답·피드백과 선택 결과 포함 |
| `iterations/<iteration_id>/reflective_dataset.json` | reflection 모델에 전달한 구조화 피드백 |
| `iterations/<iteration_id>/meta.json`, `components/` | GEPA가 저장한 부모·채택 상태와 제안 또는 채택 프롬프트 |
| `iterations/<iteration_id>/val_scores.json`, `outputs/`, `trajectories/` | **채택 후보에만** 생성되는 문항별 검증 점수·응답·궤적 |

초기 후보는 `iterations/seed/`와 `candidate_idx=0`이다. `events.jsonl`의 `minibatch_evaluation` 및 `attempt.json`의 훈련 묶음 점수는 **train 문항의 중간 평가**다. `validation.jsonl`의 `average_score`와 `val_scores.json`은 **val 문항의 전체 평가**다. 거절 제안은 원본 GEPA 절차상 val 전체를 평가하지 않으므로 `val_accuracy=null`로 표시한다. `test_*` 문항은 이 단계에 사용하지 않는다.

## 계보와 사후 분석 파일

| 파일 | 분석에 쓰는 필드 |
| --- | --- |
| `lineage.json` | 채택 후보 `nodes`, 후보 간 `edges`, 거절을 포함한 모든 제안 `proposal_nodes`, 부모 후보→제안→채택 자식 `proposal_edges`, 최선 후보 번호 |
| `candidates.csv` | 채택 후보의 부모 번호·반복 ID·검증 정확도·프롬프트 해시를 스프레드시트로 읽기 쉬운 표 |
| `proposal_graph.md` | 채택·거절 제안을 모두 포함하는 Mermaid 관계 그림. 그래프의 제안 번호를 반복 상세 파일에 연결 |
| `attempt_timeline.md` | 반복순으로 모든 제안 프롬프트, 전후 훈련 점수, 채택 여부와 검증 정확도를 읽는 문서 |
| `evolution.md`, `candidate_tree.html` | 채택된 후보 프롬프트의 변화와 계보 시각화. 거절 제안까지 보려면 타임라인 사용 |
| `gepa_result.json`, `gepa_state.bin`, `run_log.json` | GEPA 자체의 최종 후보·점수·상태·반복 기록 |
| `audit.json`, `summary.json` | 기록 간 후보·부모·문항별 검증 점수·프롬프트·반복 ID가 맞는지 점검한 결과와 최종 요약 |

연결 키는 `candidate_idx`와 `iteration_id`다. `lineage.json`의 `nodes[].iteration_id`에서 채택 후보의 `iterations/<id>/`로 이동한다. 거절 제안은 후보 풀에 들어가지 않으므로 `candidate_idx`가 없고, `proposal_nodes[].proposal_key`와 `attempt_file`로 찾는다. `proposal_edges`의 `parent_proposed`는 후보→제안, `accepted_as`는 제안→채택 후보 관계다. 고정된 기본 GEPA 설정은 반복당 부모 하나와 제안 하나를 만든다. 향후 여러 제안을 동시에 만드는 전략을 쓸 경우, 제안별 부모 연결 로직을 별도로 검증해야 한다.

`validation.jsonl`에는 GEPA 내부의 0부터 시작하는 val 행 번호 대신 **원래 문항 ID**를 키로 쓴다. `val_scores.json`의 `"0"`, `"1"` 등은 `inputs/val.jsonl`의 행 번호로 해석한다. `audit.json`은 두 표현의 점수와 GEPA 결과가 같은지 확인한다.
중단된 실행을 재개할 때 GEPA가 저장된 초기 후보 점수를 다시 callback으로 알리면 `validation.jsonl`에 초기 후보 행이 다시 나타날 수 있다. 이 행을 새 모델 호출로 세지 않는다. 실제 호출은 `api_requests.jsonl`과 `run_sessions.jsonl`로 확인하고, 후보별 최종 점수는 `gepa_result.json` 및 `audit.json`과 대조한다.

`api_requests.jsonl`의 풀이 호출에는 `question_matches`가 있다. 실제 사용자 메시지와 일치하는 train·val 문항 ID를 배열로 담으므로, 동일한 문제 텍스트가 여러 행에 있으면 후보 ID를 임의로 하나만 고르지 않는다. `system_prompt_sha256`으로 요청 당시 후보 프롬프트와 `lineage.json`의 프롬프트 해시를 연결할 수 있다. 응답 메타데이터의 `requested_max_completion_tokens`와 `finish_reason`으로 역할별 출력 한도와 응답 잘림 여부를 점검한다.

## 보류 평가 기록

진화 완료 후 `evaluate` 명령을 실행하면 분할별 `test_*_metadata.json`, `test_*_sessions.jsonl`, `test_*_api_requests.jsonl`, `test_*_paired.jsonl`, `test_*_summary.json`을 만든다. 원본 test 분할도 `inputs/`에 복사한다. 메타데이터는 데이터·초기/최종 프롬프트·모델·채점 코드의 해시를 고정하며, 채점 코드가 진화 실행 때와 다르면 평가를 중지한다. `paired.jsonl`은 문항 전문, 정답, 두 프롬프트의 응답·점수·피드백을 같은 행에 보존한다. `summary.json`은 비교에 사용한 정확한 문항 ID 목록과 개선·악화 건수를 담는다. 처음 20문항을 평가한 뒤 전체 평가로 확장할 수 있으며, 각 호출 내역은 `sessions.jsonl`에 따로 남는다.

## 중단과 감사의 범위

GEPA 상태는 반복 사이와 정상 종료 시 저장된다. Modal에서는 상태 저장·반복 종료·함수 종료 시 Volume을 commit한다. 강제 종료가 진행 중인 한 반복을 끊으면 마지막 commit 이후 이벤트나 미완료 평가가 빠질 수 있다. 오류가 callback으로 전달된 반복은 `attempt.json`의 `decision=interrupted`, 미완료 제안은 `decision=evaluation_incomplete`로 기록하고 성능에 따른 거절과 구분한다. 재실행 시 `run_log.json`과 일치하는 반복이 **확정된 타임라인**이며, 이전 시도에서 남은 다른 `iterations/` 디렉터리는 복구 가능한 참고 기록이다. `run_status.json`이 `complete`이고 `audit.json`의 `passed`가 `true`일 때만 완전한 실행 결과로 취급한다.

`audit.json`은 파일 존재, 해시, 후보·부모 연결, 전체 val 문항별 점수와 반복 요약의 일치 여부를 검사한다. 이 검사가 통과해도 모델 응답의 통계적 재현성이나 프롬프트 개선의 유의성을 보증하지는 않는다. 성능 주장은 별도로 보류 `test_*` 비교를 완료한 뒤 제시한다.
다운로드한 실행도 `python -m motif_gepa_ko.cli audit --run-dir <실행 폴더>`로 같은 검사를 다시 할 수 있다. 이 명령은 API 키와 모델 호출을 사용하지 않는다.

`val`은 GEPA가 후보를 고르는 데 사용하므로 독립적인 성능 입증 지표로 해석하지 않는다. `test_id`와 두 MATH 보류 분할의 초기·최종 비교를 함께 보고한다. API 제공자의 동일한 모델 ID가 미래에도 완전히 같은 가중치·서빙 설정을 가리킨다는 보장은 없으므로, 매 호출의 실제 응답 메타데이터를 가능한 범위에서 함께 보존한다.
