# Omni v2 문안 교정본

`omni_v2_clean_curated`는 실행 중인 `omni_v2_clean` 파일을 보존하면서 확인된 문안 손상을 고친 데이터 버전이다. train 1,000개, val 50개, test 760개의 **문항 ID·순서·정답·난이도·한국어 질문은 동일**하다. 실행 중인 영어·한국어 Modal 작업은 이 디렉터리를 사용하지 않는다.

- 영어 질문·해설과 한국어 해설에서 잘못 변환된 `\frac`, `\times`, `\triangle`을 복원했다. 검토된 일반 문장 `first`, `find`와 작성자 표시의 탭도 고쳤다. 원문·교정문 SHA-256과 적용 횟수는 [text_repairs.jsonl](text_repairs.jsonl)에 있다.
- 한국어 해설의 `source_solution_sha256`을 교정된 영어 해설에 맞추고 품질 플래그를 다시 계산했다.
- 영어 참고 해설의 검토 메모 18건은 `reference_solution_review_notes`로 기록했다. 명백한 내부 모순과 단순한 풀이 생략이 섞여 있어, 메모만으로 참고 해설을 자동 제외하거나 정답을 변경하지 않는다. 문항별 메모는 [source_solution_issues.jsonl](source_solution_issues.jsonl)에 있다.
- [manifest.json](manifest.json)은 상위 버전 해시, 파일 해시, 수정 유형별 횟수와 검토 메모 대상 ID를 기록한다.

이 버전은 현재 실행에 쓰지 않은 데이터 관리용 문안 교정본이다. 실험 로더는 1,000개 train 문항에 대해 기존과 동일하게 해당 언어의 참고 해설을 reflection 피드백에 제공한다. 검토 메모는 피드백 내용에 들어가지 않는다. 1,000개 풀이의 수학적 정당성을 전수 증명했다는 뜻은 아니다. 이 버전으로 새 실험을 시작하면 문안과 입력 해시가 달라지므로 별도 실행 ID로 관리해야 한다.

```powershell
.\.venv\Scripts\python.exe .\scripts\build_omni_v2_clean_curated.py --check
```
