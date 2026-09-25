# Omni-MATH 원본 감사 기록

- [quality_flags.csv](quality_flags.csv): HRM8K Omni-MATH CSV의 0부터 시작하는 원본 행 번호와 수동 제외 사유. 그림 참조 39행에는 텍스트만으로 풀릴 수 있는 652행도 포함한다.
- [source_audit.json](source_audit.json): 원본 SHA-256, 난이도 분포, 정확히 같은 원문 중복 및 GSM8K/MATH와의 일치 정보. `python scripts/audit_omni_source.py`로 재생성한다.
- [최종 데이터 설계](../../docs/OMNI_EVOLUTION_DESIGN.md)와 [분할 manifest](../omni_v1/manifest.json): 제외 후 1,818행을 실제 train·val·test로 나눈 결과.

원본 CSV는 수정하지 않는다. 자동 검색으로 추린 그림 후보를 한국어 문제문과 영어 원문으로 확인했으나, 모든 의미상 결함을 탐지한 보증은 아니다.
