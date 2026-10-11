# P00: 기존 프로젝트와 로컬 API 연결

- 날짜: 2026-10-11
- 상태: 채택 (패키지 배치는 0002 결정으로 대체)

ROADMAP의 첫 작업 지침에 따라 P00만 구현한다. React/Vite 프로젝트와 의존성을
유지한다. Python 패키지 배치는 [0002](0002-uv-src-layout.md)에 따라 `src/plan_route/`로 통일한다.
API 응답은 Pydantic 모델로 정의하며 P00에는 health 라우터만 둔다.

프런트엔드는 별도 API client를 통해 health를 조회한다. HTTP 오류 및 잘못된 응답을
실패로 표시하고, 5초 제한과 재시도를 제공한다. React effect 해제 시 요청을 취소하여
이전 요청 결과가 화면을 덮어쓰지 않도록 한다.

로컬 CORS origin 두 개만 허용하고 Vite 포트를 5173으로 고정한다. P00에서 필요한
개발 의존성은 pytest/httpx/ruff이다. 기존에 설치된 Konva는 유지하되 사용하지 않는다.
도메인 데이터 모델 및 알고리즘은 P01 이후에 추가한다.
