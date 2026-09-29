# Omni-MATH 영어 보류 test 평가 계획

이 계획은 `en-omni-v2-clean-b600-t720-s0`의 test 평가를 시작하기 전에 기록했다.

- 데이터: `omni_v2_clean`, 영어 질문, `test_id` 760문항 전체. 진화에 사용한 train 1,000문항과 val 50문항은 test에 포함되지 않는다.
- 모델·생성 설정: 진화 실행의 `config.json`과 동일한 Motif 3, temperature 0, 최대 출력 16,384토큰.
- 비교 프롬프트: 초기 후보 #0과 **검증 최고점 동률에서 가장 나중에 생성된 후보**. 저장된 검증 점수의 최대값은 38/50(76%)이고 동률 후보는 #0과 #4이므로 평가 대상은 #4다.
- `latest_val_tie`는 이번 평가에서 명시한 동률 해소 규칙이다. GEPA의 기본 `best_idx` 규칙은 #0을 선택한다. 원래의 `summary.json`과 `best_prompt.md`는 변경하지 않는다.
- 후보 선택에는 검증 점수만 사용한다. test 응답이나 점수를 보고 후보를 다시 고르지 않는다.
- 평가 행의 `seed`는 #0, `best`는 이번 규칙으로 선택한 #4를 뜻한다. `test_id_metadata.json`과 `test_id_selected_prompt.md`에 선택 규칙, 후보 번호, 프롬프트 해시와 전문을 보존한다.
- 채점은 진화 당시 `inputs/code/motif_gepa_ko/bilingual.py`의 해시가 검증된 보존본을 사용한다. 현재 파일과 피드백 문구가 달라졌으므로 이 경로가 필요하다.
- 각 문항의 두 응답·점수는 `test_id_paired.jsonl`에 보존한다. Modal 중단 시 완료된 문항은 다시 호출하지 않고 이어서 평가한다.

```powershell
.\.venv\Scripts\modal.exe run --detach .\modal_experiment.py::evaluate --dataset omni_v2_clean --language en --run-id en-omni-v2-clean-b600-t720-s0 --split test_id --limit 0 --max-api-calls 1600 --selection-policy latest_val_tie
```

실행 앱: [Modal 평가 작업](https://modal.com/apps/woojin716/main/ap-ROLnnVp8UK5nwEeFBl4NOu). 시작 후 저장된 메타데이터에서 후보 #4, 동률 후보 #0·#4, `run_code_snapshot` 채점, `separate_inferences` 정책을 확인했다.

시각화: [test 평가 선택 #4의 트리](../reports/en-omni-v2-clean-b600-t720-s0-test-selected/GENETIC_TREE.md). [GEPA 기본 선택 #0의 트리](../reports/en-omni-v2-clean-b600-t720-s0/GENETIC_TREE.md)는 원래 결과를 나타내며 함께 보존한다.

한국어 실행 `ko-omni-v2-clean-b600-t720-s0`은 아직 진화 완료 기록이 없으므로 test 평가를 시작하지 않는다. 완료 후 같은 후보 선택 원칙을 적용할지는 별도 계획으로 고정한다.
