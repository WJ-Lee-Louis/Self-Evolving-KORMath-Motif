# Omni-MATH 보류 test 4분할 평가

2026-09-30에 영어 직렬 평가가 148/760문항만 완료된 것을 확인하고, 한국어와 영어의 동일한 `omni_v2_clean/test_id.jsonl` 760문항을 각각 4개 Modal 함수로 분할했다. 원본 순서의 행 번호 `i`에 대해 `i % 4`가 샤드 번호다. 각 샤드는 **190문항**을 담당하며 별도 Modal 컨테이너에서 CPU 1개를 요청한다. 문항별 초기·선정 프롬프트 응답은 순차적으로 호출하고, 완료된 한 쌍마다 Modal Volume에 저장한다.

| 언어 | 진화 실행 ID | 평가 프롬프트 | 기존 완료 기록 | 샤드 Modal 앱 |
|---|---|---|---:|---|
| 한국어 | `ko-omni-v2-clean-b600-t720-s0` | GEPA 최종 #6, val 35/50 | 없음 | [0](https://modal.com/apps/woojin716/main/ap-0aCj5ehhpj9bYx73Scp8bP), [1](https://modal.com/apps/woojin716/main/ap-sJeRwWG7bEvTolgPzj89ZG), [2](https://modal.com/apps/woojin716/main/ap-mwVxn7tsILZIx40rphrKds), [3](https://modal.com/apps/woojin716/main/ap-COOwDW6H5bsURViO7adGTv) |
| 영어 | `en-omni-v2-clean-b600-t720-s0` | 검증 동률 후 최신 후보 #4, val 38/50 | **148문항**, 샤드별 37문항 | [0](https://modal.com/apps/woojin716/main/ap-3zqkl3Uq3Q9DrZ6EtHKUQm), [1](https://modal.com/apps/woojin716/main/ap-t30Foj9VTVzDiA6GlCRyOh), [2](https://modal.com/apps/woojin716/main/ap-cUwjBdSRvL7KqdERBJlDdd), [3](https://modal.com/apps/woojin716/main/ap-9BWKZRwgXScziAfqyIR2lg) |

기존 [영어 직렬 평가 앱](https://modal.com/apps/woojin716/main/ap-ROLnnVp8UK5nwEeFBl4NOu)은 중단했다. 완료된 148개의 응답 쌍을 질문·정답·프롬프트 해시와 원본 test 파일 SHA-256으로 확인한 뒤 네 샤드에 복사했다. 기존 기록과 복사 내역 `<run-id>/heldout/test_id_shards_4/bootstrap.json`은 Modal Volume에 남는다. 진행 중이었으나 응답 쌍으로 저장되지 않은 문항만 새 샤드가 다시 호출한다.

각 샤드의 `metadata.json`, `paired.jsonl`, `api_requests.jsonl`, `sessions.jsonl`, `summary.json`은 Modal Volume의 `<run-id>/heldout/test_id_shards_4/shard_<0..3>/`에 저장된다. 채점 함수는 각 진화 실행 당시 보존한 코드의 SHA-256을 확인하여 로드한다. 영어 원래의 GEPA 결과는 #0을 최종 선택했으나, 영어 test는 test 조회 전에 정한 `latest_val_tie` 규칙으로 #4를 평가한다. 한국어는 최고 검증 점수 단독 후보 #6을 평가한다.

마지막 샤드가 끝나면 `aggregate_shards_if_complete`가 네 샤드의 데이터·프롬프트·채점 해시 일치, 760개 문항 ID의 정확한 1회 포함, 샤드별 완료 건수를 확인하고 `<run-id>/heldout/test_id_shards_aggregate.json`을 쓴다. 자동 집계가 누락되면 다음 명령을 다시 실행할 수 있다. 완료 전에는 `None`을 반환한다.

```powershell
.\.venv\Scripts\modal.exe run .\modal_experiment.py::aggregate_test_shards --dataset omni_v2_clean --language ko --run-id ko-omni-v2-clean-b600-t720-s0 --shard-count 4
.\.venv\Scripts\modal.exe run .\modal_experiment.py::aggregate_test_shards --dataset omni_v2_clean --language en --run-id en-omni-v2-clean-b600-t720-s0 --shard-count 4
```

Modal의 각 함수 실행 한도는 24시간이며, 각 샤드는 중단 시 저장한 완료 응답 쌍부터 재개한다. 네 함수가 병렬로 실행되더라도 같은 Motif API 계정의 공급자 처리량이 4배로 늘어난다는 보장은 없으므로, 완료 속도와 HTTP 오류를 함께 관찰해야 한다.
