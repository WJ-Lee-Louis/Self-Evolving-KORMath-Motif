# Modal 계정 연결과 Motif 원격 호출 확인

2026년 9월 23일 기준. 이 문서는 Modal 계정 연결과 **원격 Motif 호출 확인** 절차입니다. 진화와 평가 실행은 [실험 실행 문서](EXPERIMENT_RUN.md)에 있습니다.

## 1. 계정과 결제 한도 확인

1. [Modal 가입](https://modal.com/signup)에서 계정을 생성하고 로그인합니다. 일반 사용자는 GitHub 계정으로 가입할 수 있습니다.
2. Modal의 [청구 안내](https://modal.com/docs/guide/billing)에 따르면 **Modal 사용에는 결제 수단 등록이 필요**합니다. Motif 3의 무료 API 요금과는 별개입니다. [현재 요금표](https://modal.com/pricing)의 Starter 구독료는 0달러이고 월별 무료 컴퓨팅 크레딧이 있으나, 초과 사용은 과금될 수 있습니다.
3. Modal 대시보드의 **Usage & Billing**에서 사용 한도와 순지출 한도를 확인하고 프로젝트 예산에 맞게 설정합니다. [Modal 예산 문서](https://modal.com/docs/guide/budgets)를 참고하세요.

## 2. 로컬 CLI를 Modal 계정에 연결

PowerShell에서 `motif-gepa-ko` 디렉터리로 이동한 뒤 실행합니다.

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[modal]"
.\.venv\Scripts\modal.exe setup
.\.venv\Scripts\modal.exe token info
```

`modal setup`은 브라우저를 열어 로그인과 워크스페이스 선택을 요청합니다. 완료되면 Modal CLI 토큰이 **로컬 사용자 설정**에 저장됩니다. 이 토큰은 `INFRON_API_KEY`와 다르며 프로젝트 `.env`에 넣지 않습니다. `token info`는 연결된 워크스페이스를 확인하는 명령입니다. [공식 시작 안내](https://modal.com/docs/guide/getting-started)

## 3. 인프론 키를 Modal Secret에 등록

[Modal Secrets 화면](https://modal.com/secrets)에서 **New secret → Custom** 유형을 선택합니다. [Modal 공식 예제](https://modal.com/docs/examples/opencode_server)에서도 임의의 환경 변수용으로 `Custom`을 사용합니다. 다음과 같이 입력하세요.

| 입력란 | 값 |
| --- | --- |
| Secret name | `motif-gepa-infron` |
| Key 또는 Environment variable name | `INFRON_API_KEY` |
| Value | 발급받은 **API 키 문자열만** 입력 (`INFRON_API_KEY=`와 따옴표는 제외) |

저장 전에 CLI에서 사용하는 워크스페이스·환경과 대시보드에서 선택한 워크스페이스·환경이 같은지도 확인합니다. `modal_smoke.py`는 이 이름의 Secret을 원격 컨테이너에 주입합니다. 로컬 `.env` 파일이나 키 문자열을 Modal 이미지에 포함하지 않습니다. [Modal Secrets 문서](https://modal.com/docs/guide/secrets)

로컬 `.env` 전체를 Secret으로 옮겨도 괜찮다면 CLI 대안은 다음과 같습니다. 이 명령은 `.env`의 다른 설정 값도 함께 전송합니다.

```powershell
.\.venv\Scripts\modal.exe secret create motif-gepa-infron --from-dotenv .env
.\.venv\Scripts\modal.exe secret list
```

키나 Modal 토큰을 채팅, Git, 터미널 명령 인수에 직접 붙여넣지 마세요.

## 4. 원격 연결 확인

```powershell
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
.\.venv\Scripts\modal.exe run .\modal_smoke.py
```

`원격 Motif 응답:`이 출력되면 Modal 인증, Secret 주입, 원격 컨테이너에서 인프론 API 호출까지 확인된 것입니다. 이 시험은 Modal의 CPU와 메모리를 짧게 사용하며, Motif 3가 무료로 제공되는 동안 모델 호출 요금은 모델 페이지 기준 0달러입니다. 인프론·Modal의 요금과 한도는 실행 직전에 각 대시보드에서 다시 확인하세요.

## GEPA 진화 실행

수치 정답 채점기, 한국어 피드백, 호출 상한, 프롬프트 변화 기록 및 Modal Volume 저장이 구현됐습니다. 실행 명령과 보류 평가 절차는 [실험 실행 문서](EXPERIMENT_RUN.md)를 참고하세요. 원격 이미지는 `data/hrm8k_v1`의 고정 분할과 필요한 Python 코드·프롬프트만 전송합니다. `.env`와 HRM8K 원본 저장소는 이미지에 포함되지 않습니다. 외부 API를 호출하므로 Modal GPU는 필요하지 않습니다.
