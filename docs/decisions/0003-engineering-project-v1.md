# P01: EngineeringProject v1 계약과 예제 정본

- 날짜: 2026-10-11
- 상태: 채택

도메인 정본은 `src/plan_route/fixtures/demo_project.json` 한 파일이다.
예제 로더와 OpenAPI 요청 예시는 같은 파일을 읽는다. `EngineeringProject` 모델을
계약으로 삼고 `scripts/export_schema.py`가 JSON Schema를 생성한다. 문서에는
생성 결과를 보관하며 테스트에서 모델과 일치하는지 확인한다.

전체 좌표와 치수의 단위는 m이고 z가 수직축이다. 지원 버전은 정확히 `1.0.0`,
study type은 `synthetic_benchmark`로 제한한다. AABB는 축별 `min_m < max_m`,
포트·Zone·Obstacle은 건물 범위 안에 있어야 한다. ID는 프로젝트 엔터티 전체에서
중복할 수 없고 규칙 대상은 실제 Pipe와 Zone 또는 Obstacle을 참조해야 한다.
`KEEP_OUT`은 Zone만 대상으로 하며 `MIN_CLEARANCE`는 명시적인 거리와 표면 기준을
요구한다. 두 규칙의 실행 의미는 P04에서 구현한다.

규칙의 출처·개정판·근거 문장과 승인 상태는 필수 데이터다. 미승인 규칙은
입력 데이터로 보관할 수 있으나 P01에는 적용 엔진이 없다. 앞으로 Compiler는
`status == approved`만 적용해야 한다. 모든 예제 수치는 연구자 가정이다.

`POST /api/projects/validate`는 유효성 검사만 하며 저장하지 않는다. 유효한 입력은
project ID와 버전을 응답한다. 잘못된 입력은 422 `INVALID_INPUT`과 위치·메시지를
응답한다. `GET /api/projects/demo`는 항상 정본 JSON을 파싱한 모델을 반환한다.
