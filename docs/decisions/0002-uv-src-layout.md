# P00: uv src 레이아웃으로 백엔드 통일

- 날짜: 2026-10-11
- 상태: 채택
- 근거: 사용자가 문서를 먼저 수정한 후 백엔드를 기존 uv 패키지로 이전하도록 요청함.

FastAPI 앱과 API 모듈을 `src/plan_route/main.py`, `src/plan_route/api/`로 옮긴다.
기존 `src/plan_route/__init__.py`와 uv 기본 CLI는 보존한다. `models/`, `services/`는
패키지 위치만 마련하고 후속 Phase의 기능은 구현하지 않는다.

실행 경로는 `plan_route.main:app`, 내부 import는 `plan_route.*`로 통일한다.
pytest의 루트 pythonpath 설정을 제거하여 uv가 설치한 패키지를 실제로 테스트한다.
기존 uv_build의 기본 src 레이아웃으로 백엔드가 wheel에도 포함되므로 별도 빌드 설정이나
의존성 변경은 필요하지 않다. 이전 루트 백엔드 폴더는 검증 후 삭제한다.
