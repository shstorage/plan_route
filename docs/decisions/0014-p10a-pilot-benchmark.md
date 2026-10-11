# 0014 — P10A: 예비 장면, 독립 정답 근거와 실행 기록

상태: 적용 / 2026-10-11. P10A만 구현하며 P10B/C 본 실험은 별도 단계다.

## 예비 장면과 정답 범위

11개 장면은 1 m 격자, 외경 0.2 m, 길이 가중치 1, 굽힘 가중치 2를 사용한다.
대부분 7×7×3 m이고 층간 장면은 7×7×5 m다. 현재 시드는 정수 좌표 이동만 결정한다.
이는 좌표 원점 회귀를 확인하는 예비 장면군이며 시드별 독립 무작위 공간 표본이 아니다.

| case ID 끝부분 | 기대 상태 | 독립 격자 목적함수 비용 |
|---|---|---:|
| straight | SUCCESS | 4 |
| bend | SUCCESS | 10 |
| ordered | SUCCESS | 10 |
| duplicate | SUCCESS | 10 |
| wall_detour | SUCCESS | 18 |
| closed_wall | NO_PATH | 경로 없음 |
| keep_out | SUCCESS | 18 |
| clearance | SUCCESS | 10 |
| budget | SEARCH_LIMIT_REACHED | 10 (충분한 예산일 때) |
| unapproved | UNAPPROVED_RULE | 규칙 적용 전 그래프 비용 4; 실행 금지 |
| vertical | SUCCESS | 8 |

`case.json`은 원본 EngineeringProject, 해석 근거, 수동 정의한 자유 셀, 경유점,
포트 방향, 기대 상태와 해석적으로 만든 중심선 witness를 보존한다.
벽은 x≈3.5에 있고 반경 0.1 m를 고려한 차단 셀은 x=3이다. 우회 장면에서는 y=1~3을 막는다.
최소 이격 장면의 가운데 상자는 0.5 m 이격과 반경을 더하면 x/y=2~4를 차단한다.
모든 셀과 witness는 작성 시 지정하며 솔버 출력으로 정답을 만들지 않는다.

기준 계산은 명시적 단위 길이 그래프의 간선을 열거하고 Bellman–Ford 방식으로 완화한다.
생산 코드의 voxelizer, compiler, heap, 휴리스틱, 비용 계산 함수를 사용하지 않는다.
진입 방향·순서·포트 방향과 즉시 역행 제외를 그래프 정의에 포함한다.
컴파일된 자유 셀과 이 수동 그래프가 같은지도 별도로 대조한다.
최적성은 자기 간섭을 제외한 격자 목적함수에 한정되며 연속공간 최적성은 주장하지 않는다.

성공 사례는 수동 witness로 가능성을 명시하고 Validator 검사도 실행한다.
그 검사는 witness의 구현 일치 확인이며 Validator가 반환한 VALID를 정답 생성 기준으로 재사용하지 않는다.
닫힌 벽은 건물 y/z 단면 전체를 가로막아 출발·도착을 나누므로 별도의 불능 근거가 있다.
검색 예산 초과는 feasible witness가 있는 장면에서 별도 상태로 검사한다.
역행·대각선·벽 통과·금지구역 통과의 고의 손상 경로와 기대 위반 코드를 실행 전에 지정한다.

## 실행과 보존

`uv run python scripts/run_benchmark.py --seed 42 --config benchmarks/pilot.json`으로 실행한다.
기본은 A*/Dijkstra 각각 2회, 총 44회다. 기대된 NO_PATH/예산 초과/미승인은 정상적인 계약 검사 통과다.
`passed_runs`는 유효 경로 발견 수나 성공률이 아니다. 성공 32회, NO_PATH 4회,
예산 초과 4회, 미승인 4회가 기본 설정의 기대 상태 분포다.

`data/benchmarks/<batch_id>/<case_id>/<run_id>/`에 입력과 결과를 별도 보존한다.
batch/run ID는 UUID를 포함하며 파일 생성은 exclusive 방식이다. 같은 입력도 이전 결과를 덮어쓰지 않는다.
요청의 정렬된 JSON 해시와 시나리오 해시로 같은 입력을 비교하고 각 run의 UTC 시작/종료 시각을 남긴다.

배치의 `environment.json`에는 Git commit/dirty 상태, 실제 소스 해시·파일별 해시,
Python/uv/Node와 패키지 버전, OS/CPU/RAM 정보를 저장한다. 조회 불가능한 환경 값은 null이다.
`source.zip`은 실행한 Python 소스, 합성 fixture, 잠금 파일, 기본 설정과 실행 README를 보존한다.
커밋되지 않은 변경도 소스 파일로 남긴다. 프런트엔드 화면 전체를 복원하는 아카이브는 아니다.
배치의 환경 정보는 그 batch ID를 가진 모든 run에 적용된다.

`manifest.json`은 시작 시 계획 기록이며 덮어쓰지 않는다. 완료 판정은 `summary.json`의 COMPLETE다.
중단된 실행은 남은 입력/결과를 유지하지만 자동 재개는 지원하지 않는다. 다시 실행하면 새 배치가 생긴다.
CLI는 기대 상태/비용/셀/witness/고의 손상 검사 중 실패가 있으면 종료 코드 1을 반환한다.
각 입력은 `input.json`, 상세 결과는 `run.json`, 요약 행은 UTF-8 BOM의 `runs.csv`다.

기존 API의 `data/results/<request_hash>.json`은 현재 요청 결과를 저장하는 별도 용도로 유지한다.
논문 반복 기록에는 위 벤치마크 저장소를 사용한다.

## 시간 의미

`RouteSolveReport.timings`는 단조 시계로 서비스 호출을 계측한다.
`compile_ms`는 voxel 생성·규칙 컴파일, `search_ms`는 탐색 호출 전체(입력 재확인·재탐색 포함),
`validate_ms`는 최종 연속 검증이며 실행하지 않으면 0이다.
`total_ms`는 report 생성까지 포함한 경로 서비스 시간이다. API 파싱·HTTP·파일 저장은 포함하지 않는다.
기존 `runtime_ms`는 솔버 내부 시간으로 유지하고, 웹 화면은 새 total 값을 표시한다.
기준 계산 시간은 `oracle_ms`로 별도 기록하며 witness/probe/셀 대조·출력 시간도 total에 포함하지 않는다.

## 검수와 남은 범위

Python 168개 테스트, Ruff, frontend lint/build 통과. 반복 run 및 새 batch의 원본 보존,
CSV/JSON 일치, 소스 아카이브 해시, 시드 재현, 단계별 시간 경계를 검사했다.
예비 44회 모두 기대 계약과 일치했고 고의 손상 검사 4개도 통과했다.
이번 장면은 exact 모드만 유발한다. 휴리스틱 필드는 보존하되 그 결과의 기준 비용 일치를 주장하지 않는다.
휴리스틱 유발 장면·해상도/밀도 다양화·시간 순서 무작위화·별도 평가 표본·통계/그림은 P10B,
규칙 변경 대조 및 원인 추적 평가는 P10C에 남긴다.
