# HRM8K 데이터 구성과 고정 분할 (v1)

이 문서는 한국어 시스템 프롬프트를 GEPA로 진화시키는 첫 실험의 **확정된 데이터 구성**을 기록한다. 분할 파일은 [`../data/hrm8k_v1/`](../data/hrm8k_v1/)에 있고, [재생성 스크립트](../scripts/prepare_hrm8k_splits.py)가 만든다. 원본 HRM8K CSV는 수정하지 않았다.

## 1. 원본 HRM8K는 무엇인가

원본은 [HAERAE-HUB/HRM8K](https://huggingface.co/datasets/HAERAE-HUB/HRM8K), 복제 커밋 `c360cabf8d733a82455565358b3dc965aab9ba8d`이다. **공식 제공 분할은 모두 `test`**이며, 아래 5개 하위 집합의 합계는 8,011문항이다. 따라서 이 프로젝트의 `train`·`val`은 원저자의 공식 학습·검증 분할이 아니라 **프로젝트가 새로 만든 분할**이다. GEPA가 일부 문항을 보고 프롬프트를 수정하므로, 이 실험 결과를 공식 HRM8K 전체 벤치마크 점수로 표기하지 않는다.

| HRM8K 하위 집합 | 원본 CSV (`../../datasets/HRM8K/HRM8K/` 아래) | 문항 수 | 성격과 이 프로젝트의 사용 |
| --- | --- | ---: | --- |
| GSM8K | `gsm8k_test.csv` | 1,319 | 영어 GSM8K 평가 문제의 한국어 번역. 모든 정답이 정수형 숫자. **진화·검증·동일 분포 평가에 전량 사용** |
| MATH | `math_do_test.csv` | 2,885 | 영어 MATH 문제의 한국어 번역 중 숫자 정답 문제. `level` 1–5와 `type` 제공. **다른 문제군 평가에 400문항 사용** |
| OMNI_MATH | `omni-math_do_test.csv` | 1,909 | 더 어려운 수학 문제의 번역과 난도 정보. v1에서는 사용하지 않음 |
| MMMLU | `mmmlu_test.csv` | 470 | 수학 객관식. `answer`의 숫자는 계산값이 아닌 **선택지 번호**이므로 v1에서는 사용하지 않음 |
| KSM | `ksm_test.csv` | 1,428 | 한국 수학 시험·경시 문제. 정답에 분수·π·수식도 있어 현재 숫자 채점기와 출력 형식으로는 전체 평가가 어려워 v1에서는 사용하지 않음 |

KSM 원본의 1,428문항 중 1,207문항은 십진수 숫자로 읽히고 221문항은 수식 등 다른 형식이다. 향후 KSM을 추가한다면 숫자형만 선택했다는 사실을 별도로 보고하거나, 수식 동치 채점기를 준비해야 한다. HRM8K의 구성·제작 취지는 [원본 데이터 카드](https://huggingface.co/datasets/HAERAE-HUB/HRM8K)를 참고한다.

## 2. 실제 생성된 분할

| 프로젝트 분할 | 생성 파일 | 원본 하위 집합과 선택 규칙 | 문항 수 | GEPA에서의 역할 |
| --- | --- | --- | ---: | --- |
| `train` | [`train.jsonl`](../data/hrm8k_v1/train.jsonl) | GSM8K 1,319문항을 고정 해시 순서로 정렬한 **앞 240개** | 240 | 실패 사례를 보여 주고 한국어 프롬프트 진화 |
| `val` | [`val.jsonl`](../data/hrm8k_v1/val.jsonl) | 같은 해시 순서의 **다음 60개** | 60 | 후보 프롬프트 선택 |
| `test_id` | [`test_id.jsonl`](../data/hrm8k_v1/test_id.jsonl) | GSM8K의 **나머지 1,019개 전부** | 1,019 | 같은 문제군의 보류 평가 |
| `test_ood_math_l1_l2` | [`test_ood_math_l1_l2.jsonl`](../data/hrm8k_v1/test_ood_math_l1_l2.jsonl) | MATH Level 1 **71개** + Level 2 **129개** | 200 | 다른 유형의 비교적 쉬운 수학 문제 평가 |
| `test_ood_math_l3_l5` | [`test_ood_math_l3_l5.jsonl`](../data/hrm8k_v1/test_ood_math_l3_l5.jsonl) | MATH Level 3 **66개** + Level 4 **69개** + Level 5 **65개** | 200 | 다른 유형의 어려운 수학 문제 평가 |

`train`·`val`·`test_id`는 GSM8K 원본을 **빠짐없이, 중복 없이** 나눈다(240 + 60 + 1,019 = 1,319). MATH 원본의 Level별 전체 수는 Level 1 309개, Level 2 556개, Level 3 663개, Level 4 698개, Level 5 659개다. MATH 평가 2개는 서로 겹치지 않는 400문항이고, 나머지 **2,485문항은 v1에서 사용하지 않는다**. 두 MATH 평가 집합은 `train`이나 `val`에 들어가지 않는다.

### 정확히 어느 원본 행인가

각 JSONL 레코드에는 다음 필드가 있다.

- `id`: 예를 들어 `HRM8K:GSM8K:0007`. 마지막 숫자는 원본 CSV의 **0부터 시작하는 데이터 행 번호**다. 헤더는 세지 않는다.
- `source_subset`, `source_row_index`: 원본 하위 집합과 행 번호.
- `question`: 모델에 전달할 한국어 문제.
- `answer`: 채점에 쓰는 정수 문자열. 원본의 `18.0`, `70,000.0` 등을 각각 `18`, `70000`으로 정규화했다.
- MATH 레코드에만 `level`, `type`이 추가된다.

**모든 분할에 속한 원본 행 번호의 전체 목록**은 [`manifest.json`](../data/hrm8k_v1/manifest.json)의 `splits.<분할명>.source_row_indices`에 오름차순으로 저장돼 있다. 이 목록과 JSONL의 `id`가 정확한 문항 구성을 정의한다. 예를 들어 `train`의 첫 원본 행 번호는 `7, 9, 10, 12, 18, 23, 26, 30`, `val`은 `8, 27, 32, 33, 74, 147, 188, 202`다. **이 숫자는 무작위 추첨 순서가 아니라 원본 CSV에서의 위치**다.

## 3. 선택 방법과 재현성

선택 문자열은 `hrm8k-ko-gepa-v1-20260923`이다. GSM8K는 각 원본 행 번호 `i`의 `SHA-256("선택 문자열|GSM8K|i")`를 계산하여 해시값 오름차순으로 정렬한다. 앞 240개, 다음 60개, 나머지를 차례로 배정한다. MATH는 Level 안에서 `SHA-256("선택 문자열|MATH|Level N|i")`로 정렬한 뒤 위 표에 적힌 수만큼 선택한다. 해시가 같으면 원본 행 번호가 작은 문항이 먼저다. Python의 난수 생성기 버전에 의존하지 않는다.

| 사용한 원본 | SHA-256 |
| --- | --- |
| `gsm8k_test.csv` | `e603ccfec40beaba66b0ae7f46fe400ed3a02d892b8622a5097a2bee2eb7e05f` |
| `math_do_test.csv` | `48bae14a224e626c4000cc1100ec2cc432b3d8b130b619c4567e1dd4a073dc88` |

| 생성 파일 | SHA-256 |
| --- | --- |
| `train.jsonl` | `932f6caf017689226123de364f1a84c748f58eba67074ddcd8cc6d2b5a3eb453` |
| `val.jsonl` | `62f66ef5612eb6b3e96d70914ebce4a0fbfb2ef6b8c0a6cf978d0fdd2b40c245` |
| `test_id.jsonl` | `1c317c99a5814745c1dba1a5a6a1e3b7ae00253687c0d854db22d6a4b0ac0435` |
| `test_ood_math_l1_l2.jsonl` | `77871695e156d6722027e13c1ef4e08228c8e76811231a29635d2879d0f9481f` |
| `test_ood_math_l3_l5.jsonl` | `1570b21ac6cbb0f6ec6c75eaf997d84646f29ec5544716115d88f0223383f748` |

스크립트는 원본 파일의 행 수·해시, 숫자 정답, 원문 기준 중복, 분할 간 교집합과 GSM8K 전량 분할을 검사한다. 프로젝트 폴더에서 다음 명령으로 동일한 결과인지 확인할 수 있다.

```powershell
.\.venv\Scripts\python.exe .\scripts\prepare_hrm8k_splits.py --check
```

## 4. 평가에 사용할 때 지킬 경계

`train`만 GEPA의 수정 피드백에 넣고, `val`은 후보 선택에만 쓴다. 세 `test_*` 파일은 최종 프롬프트를 선택할 때까지 점수나 정답을 확인하지 않는다. 그 뒤 **동일한 Motif 모델·채점 규칙·생성 설정**으로 초기 프롬프트와 최종 프롬프트를 각 평가 집합의 동일 문항에 적용한다. 결과는 집합별 정확도 변화와 문항별 정오답 전환을 따로 기록한다.

`test_id`는 같은 GSM8K 문제군의 보류 평가다. MATH의 두 집합은 **데이터셋 간 전이 평가**다. 문제 형식과 난도도 함께 달라지므로, MATH 결과만으로 하나의 원인에 대한 엄밀한 분포 외 일반화 효과를 주장하지 않는다. MATH 정답은 모두 숫자로 정규화할 수 있으므로 v1의 숫자 채점기를 공유할 수 있다. 답안 추출 실패율은 수학적 오답과 별도로 기록한다.
