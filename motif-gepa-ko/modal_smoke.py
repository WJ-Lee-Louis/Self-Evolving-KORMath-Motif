"""One small remote Motif call to verify Modal auth and Secret wiring.

Run from the project directory with: modal run modal_smoke.py
"""

import modal


app = modal.App("motif-gepa-ko-smoke")

image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install("openai>=1.0,<3", "python-dotenv>=1.0,<2")
    .add_local_python_source("motif_gepa_ko")
)


@app.function(
    image=image,
    secrets=[modal.Secret.from_name("motif-gepa-infron", required_keys=["INFRON_API_KEY"])],
    timeout=120,
    cpu=0.25,
    memory=512,
)
def remote_smoke() -> str:
    from motif_gepa_ko.model import MotifLM
    from motif_gepa_ko.settings import Settings

    return MotifLM(Settings.from_env())(
        "안녕하세요. Modal에서 Motif 3 연결 확인 중입니다. 한국어로 짧게 답해주세요."
    )


@app.local_entrypoint()
def main() -> None:
    print("원격 Motif 응답:", remote_smoke.remote())
