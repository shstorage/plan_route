# plan_route

공개 자료와 합성 3D 건물 모델을 사용하는 배관 경로 최적화 연구 도구입니다.
실제 원전 배관 설계 또는 인허가 적합성 판단에 사용하지 않습니다.

현재 **P00~P08c와 P10A·P10B·P10C·P10D**를 구현했습니다. 층별 2D 도면에서 배관·장애물·제약·경유점을 편집하고 3D로 확인하며,
승인 규칙을 적용해 A* 또는 Dijkstra 경로를 계산한 뒤 원본 연속 기하로 독립 검증합니다.
별도 CLI는 합성 장면 비교 실험과 실행별 입력·결과·환경·통계·논문용 그림을 보존합니다.

| 범위 | 구현 상태 |
| --- | --- |
| P00~P08b | 스키마, 격자, 방향 인지 탐색, 규칙 컴파일, 독립 검증, 저장, 2D/3D UI, 순서 경유점 |
| P07b 보완 | 빈 프로젝트 생성, 기기·접속 Port·배관 추가/삭제, 기기 이동과 Port 연동 |
| P07c 보완 | 도면 중심 도구, 두 번 클릭 연결, 선택 속성창, 계산 전 점선/후 실선, 실제 브라우저 검수 |
| P07d 보완 | 배치/연결 분리, 2D/3D/프로젝트/결과 탭, 보조 보기·건물 설정 팝업, 다중 연결점 관리 |
| P07e 보완 | 한글 프로젝트 이름·도면 위 저장, 막힌 연결점 입력 오류 설명·선택·수정 흐름 |
| P07f 보완 | 저장 목록·이름 검색·선택 불러오기·저장 상태, 예제 작업 복사본 수정/재로드 |
| P07g 보완 | 저장 ID/파일명 안내, 미저장 이탈·전환 확인, 2D/3D 보조 창 크기 조절·최대화 |
| P07h 보완 | 상단·최대화 여백 해제, 8방향 테두리 드래그, 듀얼 모니터용 별도 브라우저 창 |
| P07i 보완 | 메인에서 계속, 보기 버튼 그룹, 보조 창 비율·중앙 배치, 확인 후 저장 프로젝트 삭제 |
| P08c | 자기 간섭·포트·경유점 검수, 탐색 보장 범위 표시, 규칙 내용에 연결된 승인 이력 |
| P10A | 11개 분석적 장면, 독립 기준 비용, 44회 예비 계약 검사와 실행 보존 |
| P10B | 개발 35개·평가 14개 합성 장면, 두 해상도, 600회 비교, 통계·PNG/PDF |
| P10C | 규칙 추가·거리 수정·개별 제거·중립 대조, 1,008회 실행, 출처·객체·구간 연결 검수 |
| P10D | 공개 기준의 적용 조건을 명시한 4개 사례·draft JSON, 144회 실행·분석적 경계와 실패 검수 |
| P10 문서 보완 | 주장·분모·보존 실험 근거와 선행연구 비교표 초안; 일부 원문 절/쪽 검토는 남음 |
| 다음 | 브라우저 수동 검수, 비교 원문 보완, 필요한 P09 선택 |

상세 진행 상태는 [ROADMAP](ROADMAP.md), 구현·논문 검토는
[2026-10-11 검토 기록](docs/reviews/2026-10-11-implementation-and-thesis-review.md)에 있습니다.
논문에 사용할 주장·실험 분모·선행연구 근거 수준은
[2026-10-13 주장·비교표](docs/reviews/2026-10-13-thesis-claims-and-comparison.md)에 정리했습니다.

공개 기준 사례와 현재 논문 준비 수준은 [P10D 연구성 검토](docs/reviews/2026-10-13-public-reference-and-research-readiness.md)에 있습니다.
`uv run python scripts/run_public_reference_study.py`로 독립 배치를 생성합니다.
사람 검토용 입력은 [benchmarks/public_examples](benchmarks/public_examples/)의 초안 JSON이며 승인 전 실행이 차단됩니다.
144회 중 최종 성공은 108회입니다. 실패 36회와 경계 의미의 차이도 결과로 보존했으며 규제 적합성을 주장하지 않습니다.

## 개발 환경

기존 uv/Vite 프로젝트를 유지합니다. `uv init`이나 `npm create vite`를 다시 실행하지 않습니다.
확인한 환경: Python 3.12.14, uv 0.12.7, Node.js 22.23.2, React 19.3.0, Vite 8.3.4.
정확한 의존성 버전은 `uv.lock`과 `frontend/package-lock.json`을 따릅니다.

새 환경에서는 Python 3.12, uv, Node.js 22.18 이상과 Git을 준비한 뒤 실행합니다.

```powershell
git clone https://github.com/shstorage/plan_route.git
cd plan_route
uv sync --locked
cd frontend
npm ci
cd ..
```

## 실행

프로젝트 루트의 터미널 1:

```powershell
uv run uvicorn plan_route.main:app --reload --host 127.0.0.1 --port 8000
```

- Health: http://127.0.0.1:8000/api/health → `{"status":"ok"}`
- 합성 플랜트 예제(UI 시작값, 60×40×12 m 2개 층): http://127.0.0.1:8000/api/projects/starter
- 소형 테스트 데모(12×10×4 m, 단위 테스트 기준): http://127.0.0.1:8000/api/projects/demo
- API 문서: http://127.0.0.1:8000/docs

프로젝트 루트의 터미널 2:

```powershell
cd frontend
npm run dev -- --host 127.0.0.1
```

http://127.0.0.1:5173 에 접속합니다. 기본 API 주소는 `http://127.0.0.1:8000`입니다.
변경하려면 `frontend/.env.example`을 `frontend/.env.local`로 복사하고
`VITE_API_BASE_URL`을 수정한 뒤 Vite를 재시작합니다. `VITE_` 변수는 브라우저에
노출되므로 비밀키를 넣지 않습니다.

CORS는 `http://127.0.0.1:5173`과 `http://localhost:5173`만 허용합니다.
Vite는 5173 포트가 사용 중이면 종료하도록 설정했습니다. 다른 포트로 조용히
이동하여 CORS 오류가 발생하는 것을 방지합니다. CORS는 인증/접근 제어가 아닙니다.

Vite는 개발 중 React 화면 파일을 브라우저에 제공합니다. 화면을 실행하는 **브라우저가 FastAPI에 직접 API 요청**을 보내고,
FastAPI가 검증·경로 계산·파일 저장을 처리합니다. 현재 데이터 저장은 JSON 파일이며 별도 DB 서버는 없습니다.
`npm run build`는 `frontend/dist/`에 배포용 정적 파일을 만듭니다. 실제 배포에는 이 폴더를 제공하는
정적 서버와 FastAPI 실행이 필요하며, 현재 FastAPI 앱에 정적 파일 서빙은 연결하지 않았습니다.

## 프로젝트 JSON과 입력 검증

도메인 정본 형식은 **EngineeringProject JSON**입니다. 기본 UI 예제는
`src/plan_route/fixtures/plant_starter_project.json`, 소형 테스트 예제는
`src/plan_route/fixtures/demo_project.json`입니다. 벤치마크도 같은 형식의 `project.json`을 생성합니다.
좌표·치수는 m, 수직축은 z이며 `schema_version`은 현재 `1.0.0`만 지원합니다.
규칙 출처에는 `synthetic_assumption`을 명시합니다. 이 수치는 실제 설계기준이 아닙니다.
`draft`·`needs_review`·`rejected` 규칙도 기록할 수 있지만 라우팅 실행 대상은 아닙니다.
규칙 실행은 아래 P04 컴파일과 P05 라우팅 API에서 수행합니다.

유효한 JSON 확인은 API 문서에서 `POST /api/projects/validate`의 예제 입력으로
할 수 있습니다. PowerShell에서는 다음처럼 실행합니다.

```powershell
$projectJson = Get-Content -Raw -Encoding UTF8 src/plan_route/fixtures/demo_project.json
Invoke-RestMethod -Uri http://127.0.0.1:8000/api/projects/validate -Method Post -ContentType 'application/json' -Body $projectJson
```

정상 입력은 `{"valid":true,"project_id":"SYNTH-DEMO-001","schema_version":"1.0.0"}`을
반환합니다. 잘못된 입력은 HTTP 422와 `error_code: INVALID_INPUT`, `details` 배열로
필드 위치와 오류를 반환합니다. 프로젝트 저장·불러오기는 아래 P06 API를 사용합니다.

Pydantic 모델에서 JSON Schema를 다시 생성하려면 루트에서 실행합니다.

```powershell
uv run python scripts/export_schema.py
```

결과 파일은 `docs/schema/engineering_project_v1.schema.json`입니다.

## 3D 격자 확인 (P02)

`voxelize_project(project, pipe_id)`는 검증된 EngineeringProject에서 건물 내부,
물리 장애물, Zone 셀 마스크를 만듭니다. 건물 최소점이 격자 기준점이고,
`world_to_grid`는 최소 경계 포함·최대 경계 제외 규칙을 사용합니다.
`grid_to_world`는 셀 중심을 반환하며 마지막 부분 셀은 건물 경계에서 잘립니다.

장애물 AABB는 배관 외경 반경·보온 두께·추가 마진(`clearance_margin_m`)의 합으로 팽창합니다. 셀이 확장된
장애물에 면·선·점으로 닿으면 보수적으로 차단됩니다. 배관 반경이 건물 밖으로
나가지 않도록 건물 경계 셀도 검사합니다. Zone은 별도 마스크에만 기록하며
기본 격자는 Zone 통행을 막지 않습니다. 승인된 규칙은 P04 컴파일 결과에서만 적용됩니다.

합성 예제의 높이 인덱스 2에 대한 텍스트 단면을 확인할 수 있습니다.

```powershell
@'
from plan_route.api.projects import load_demo_project
from plan_route.services.voxel_grid import voxelize_project
grid = voxelize_project(load_demo_project(), 'PIPE-101')
print('grid shape:', grid.spec.shape)
print(grid.slice_text(2))
'@ | uv run python -
```

출력에서 `X`는 배관 반경 때문에 사용할 수 없는 건물 경계 셀, `#`은 물리
장애물, `z`는 Zone, `.`은 그 외 셀입니다. 이 화면은 디버그용입니다.

## 3D A*와 Dijkstra 기준선 (P03)

`solve_route(project, pipe_id, algorithm='astar')`는 물리 장애물이 있는
6방향 격자에서 방향을 상태에 포함해 거리·방향 전환 비용을 최소화합니다.
`algorithm='dijkstra'`는 같은 상태와 비용으로 휴리스틱만 0으로 설정합니다.
출구 방향은 시작 Port의 `orientation`과 같고, 목표 Port에는 그 방향의 반대로
접근합니다. 포트와 셀 중심을 잇는 보정 구간은 길이·비용에 포함하며, 해당
구간의 방향 전환은 아직 엘보 수로 세지 않습니다.

다음 명령은 승인 규칙이 있는 정본 예제를 그대로 넣으면
`RULES_NOT_COMPILED`가 나오는 것을 먼저 보여줍니다. 이어서 **규칙을 제거한
실험용 사본**으로 물리 장애물만 고려한 기준 경로를 계산합니다. 이 경로는
규칙 준수 또는 연속 기하 검증 결과가 아닙니다.

```powershell
@'
from plan_route.api.projects import load_demo_project
from plan_route.models.engineering import EngineeringProject
from plan_route.services.astar import solve_route

project = load_demo_project()
print('원본:', solve_route(project, 'PIPE-101').status.value)
physical_only = EngineeringProject.model_validate({
    **project.model_dump(mode='json'), 'constraints': []
})
for method in ('astar', 'dijkstra'):
    result = solve_route(physical_only, 'PIPE-101', algorithm=method)
    print(method, result.status.value, result.bend_count,
          result.cost_breakdown.total_objective_cost if result.cost_breakdown else None)
'@ | uv run python -
```

결과 상태는 `SUCCESS`, `NO_PATH`, `SEARCH_LIMIT_REACHED`, `INVALID_INPUT`,
`RULES_NOT_COMPILED`, `UNAPPROVED_RULE`, `RULE_CONFLICT`로 구분합니다. 검색 한도는 프로젝트의 `max_expansions`이고
`solve_route(..., max_expansions=...)`로 실험 시 변경할 수 있습니다.
포트가 차단된 셀로 스냅되거나 스냅 거리가 허용치보다 길면 `INVALID_INPUT`입니다.
기본 허용치는 셀 대각선 길이의 절반이며 필요하면
`max_snap_distance_m`으로 더 엄격하게 설정할 수 있습니다.
P03에서 작성한 Python 탐색 함수는 P05 라우팅 API에서 사용합니다.

## 승인 규칙 컴파일 (P04)

`compile_constraints(project, pipe_id)`는 대상 배관의 승인된 `KEEP_OUT`과
`MIN_CLEARANCE` 규칙을 격자의 별도 차단 마스크로 변환합니다. 금지구역은 Zone 형상을
배관 외경 절반·보온 두께·추가 마진만큼 확장합니다. 최소 이격은 여기에 `distance_m`을 더합니다.
격자 셀이 확장 형상에 닿기만 해도 차단하는 보수적 근사입니다. 규칙별 영향 셀 수와
새로 차단된 셀 수, 규칙 ID, 문서·개정판·조항·근거 문구를 결과에 남깁니다.

대상 배관에 미승인 규칙이 하나라도 있으면 `UNAPPROVED_RULE`, 규칙이 포트 셀을
차단하면 `RULE_CONFLICT`, 잘못된 참조·누락된 거리 기준 등은 `INVALID_INPUT`입니다.
규칙별 마스크는 `compile_constraints` 결과의 `grid.rule_cells`에 들어 있습니다.
`solve_route(project, pipe_id, compilation=compiled)`로 전달해야 경로 탐색에 반영됩니다.
컴파일한 프로젝트 JSON이나 배관이 달라지면 탐색이 거부됩니다. 규칙 적용 결과는
`applied_rule_ids`에 기록됩니다. 이 단계는 격자 후보를 거르는 기능이며, 최종 연속
배관 기하 검증은 P05 검증기가 수행합니다.

API에서는 `POST /api/constraints/compile`에 `{"project": EngineeringProject JSON,
"pipe_id": "PIPE-101"}`를 보냅니다. 성공은 HTTP 200, 의미상 잘못된 입력은 422,
미승인·충돌은 409입니다. 스키마 자체가 잘못된 JSON은 기존 입력 검증 형식으로 422가
반환됩니다. 예제를 확인하려면 서버 실행 후 PowerShell에서 다음을 실행합니다.

```powershell
$project = Get-Content -Raw -Encoding UTF8 src/plan_route/fixtures/demo_project.json | ConvertFrom-Json
$body = @{ project = $project; pipe_id = 'PIPE-101' } | ConvertTo-Json -Depth 30
Invoke-RestMethod -Uri http://127.0.0.1:8000/api/constraints/compile -Method Post -ContentType 'application/json' -Body $body
```

## 독립 경로 검증과 라우팅 API (P05)

`POST /api/routing/solve`는 규칙 컴파일 → A* 또는 Dijkstra 탐색 → 원본 3D 형상
검증 순서로 실행합니다. 검증기는 격자 마스크를 읽지 않고 각 경로 선분과 건물 경계,
장애물 AABB, 승인된 Zone/이격 대상 사이의 **최단 유클리드 거리**를 계산합니다.
보온재를 포함한 배관 외면이 물리 장애물이나 금지구역에 닿아도 위반입니다.
최소 이격거리는 배관 외면부터 대상 표면까지 측정합니다. 선분별 위반 코드, 대상 ID,
규칙 ID·출처, 측정값과 요구값을 보고합니다. 수동 경로는
`POST /api/routing/validate`에 프로젝트, 배관 ID, `points_m`을 보내 검증합니다.

`SUCCESS`는 독립 검증에서 위반 0건일 때만 반환됩니다. 격자 탐색이 성공했어도
연속 기하 검증이 실패하면 `INVALID_ROUTE`와 위반 목록을 반환합니다.
`NO_PATH`와 `SEARCH_LIMIT_REACHED`는 탐색 결과로 HTTP 200,
`UNAPPROVED_RULE`·`RULE_CONFLICT`·검증 실패한 `/solve`는 HTTP 409입니다.
잘못된 배관 ID나 입력은 HTTP 422입니다. `/validate`의 `INVALID_ROUTE`는
정상적으로 수행한 검증 결과이므로 HTTP 200입니다.

보고서는 프로젝트 JSON과 배관 ID의 `scenario_hash`, 적용 규칙 ID,
`qa_validator`, 요청 기반 `result_id`와 함께 서버의 `data/results/<result_id>.json`에
원자적으로 저장됩니다. 같은 요청을 다시 실행하면 같은 이름의 결과를 교체합니다.
프로젝트 JSON 저장·재로드는 아래 P06 API에서 제공합니다. API 문서의 두 라우팅 엔드포인트에
합성 예제가 있습니다. PowerShell에서 데모를 실행하려면 앞서 만든 `$project`로:

```powershell
$body = @{ project = $project; pipe_id = 'PIPE-101' } | ConvertTo-Json -Depth 30
Invoke-RestMethod -Uri http://127.0.0.1:8000/api/routing/solve -Method Post -ContentType 'application/json' -Body $body
```

## 프로젝트 저장과 결과 화면 (P06)

`POST /api/projects/save`는 검증된 **EngineeringProject JSON 자체**를 받아 서버의
고정된 `data/projects/`에 저장합니다. 응답에는 프로젝트 ID, 스키마 버전,
저장 개정 번호, UTC 수정 시각, 문서 해시가 있습니다. 같은 ID를 다시 저장하면 개정
번호가 1 증가합니다. 임시 파일을 쓰고 원자적으로 교체하므로 교체 실패 시 이전
개정 파일은 유지됩니다. ID는 영문자로 시작하고 영문자·숫자·밑줄·하이픈만 허용하며,
클라이언트가 파일 경로를 지정할 수 없습니다.

`GET /api/projects/{project_id}`는 저장된 EngineeringProject JSON을 그대로 반환합니다.
개정 번호와 수정 시각은 `X-Project-Revision`, `X-Project-Updated-At` 응답 헤더에
있으며 브라우저에서 읽을 수 있도록 CORS에 노출합니다. 없는 ID는 HTTP 404,
형식이 잘못된 ID 또는 프로젝트 JSON은 HTTP 422입니다. 저장 파일은 버전·시각·해시를
함께 기록하며 로드 시 다시 검증합니다. 로컬 개발용 단일 프로세스 파일 저장 방식입니다.

`GET /api/projects`는 검증된 저장 목록을 `{projects, issues}`로 반환합니다.
목록에는 이름, ID, 개정, 수정 시각, 기기·배관 수가 있으며 최신 저장순으로 표시합니다.
손상되거나 해시가 맞지 않는 파일은 목록에서 제외하고 `issues`로 알립니다. 파일을 삭제하지 않습니다.

프런트 화면(`http://127.0.0.1:5173`)은 서버 응답을 기다리지 않고 빈 건물로 시작합니다.
합성 예제는 **프로젝트 → 저장·불러오기 → 예제 불러오기**로 엽니다.
도면 위 `경로 계산` 후 **계산 결과** 탭에서 경로 길이·방향 전환·비용·위반
건수와 세계좌표(m) 목록이 보입니다. 저장 후 **프로젝트 → 저장된 프로젝트** 목록에서 항목의 `불러오기`를
누르면 저장된 JSON과 개정 번호를 확인할 수 있습니다. 이름 검색·목록 새로고침을 제공하며, 이름을 바꾸어 저장하면 같은 항목을 갱신합니다.
JSON을 직접 수정했으면
다시 검증·실행하세요. 입력 필드 오류와 `NO_PATH`, `SEARCH_LIMIT_REACHED`,
`UNAPPROVED_RULE`, `RULE_CONFLICT`, `INVALID_ROUTE`는 서로 다른 메시지로 표시합니다.

## 층별 2D 도면 편집기 (P07)

React Konva(`konva`, `react-konva`)로 층별 배치도를 그립니다. 도메인 정본은 계속
EngineeringProject JSON이며 Konva `stage.toJSON()`이나 화면 픽셀을 저장하지 않습니다.
화면 px ↔ 세계좌표 m 변환은 `frontend/src/editor/coordinates.ts`에만 있으며
(평면 X 오른쪽, Y 위쪽, 화면 y는 반전), 편집 결과는 `model.ts`의 순수 함수가
AABB `min_m`/`max_m`와 Port `position_m`으로 되돌려 기록합니다.

- 도구: 선택, 배치(기기·벽·제약 구역), 별도 배관 연결, 화면 이동(pan), 휠/버튼 확대·축소, 화면 맞춤.
- 벽/Zone 추가: 도면에서 드래그해 직사각형을 그립니다(두 모서리 모두 스냅, z는 선택 층 범위).
  클릭만 하면 0.5 m 기본 정사각형이 생깁니다. 추가 도구에서는 기존 객체 위에도 그릴 수 있습니다.
- 연결점 추가: 기기 속성의 **연결점** 탭에서 X/Y/Z(m)와 바깥으로 향하는 방향을 입력합니다.
- 삭제: 선택 후 속성 패널의 `삭제` 또는 Delete/Backspace 키. 규칙 대상인 형상, 배관이 연결된 Port,
  장비의 마지막 Port는 삭제를 막고 이유를 표시합니다.
- 탐색 도메인 카드(도면 위): 도면(캔버스) = 경로 탐색 범위 = `building.bounds_m`(m)입니다. X/Y/Z 범위,
  층 바닥·천장 z, 격자 간격 `routing_config.grid_resolution_m`를 바꾸며 격자 칸 수를 미리 보여 줍니다.
  40만 칸 초과는 느릴 수 있다고 경고하고, 300만 칸 초과·0.05 m 미만 격자·범위 밖에 남는 객체는 거부합니다.
- 배관 단면 카드(도면 위): 선택한 배관의 외경·보온재 두께·추가 마진을 **mm로 입력**하고 m로 저장합니다.
  단면 그림과 함께 `외곽 지름 = 외경 + 2 × (보온재 + 마진)`을 보여 줍니다. 격자 차단, 규칙 컴파일,
  독립 Validator 모두 이 외곽을 배관 반경으로 사용하며 MIN_CLEARANCE 거리도 외곽 표면에서 잽니다.
  마진(`clearance_margin_m`, 기본 0)은 사용자가 정하는 연구용 가정값이며 규정 값이 아닙니다.
- 층 선택: 선택 층의 z 범위와 겹치는 형상·Port와 그 층으로 잘라낸 경로 구간만 표시합니다.
  도면 왼쪽 위 모서리의 작은 층 버튼(`L1 0–6m | L2`)으로 현재 층을 확인·전환합니다(z 범위는 현재 층만 표시, 나머지는 툴팁). 경로가 있는 층에는 파란 점이 붙고,
  경로가 다른 층으로 넘어가는 지점에는 `↑ L2` / `↓ L1` 표시가 나타납니다.
  `kind: slab` 장애물(층 바닥판)은 점선 외곽선으로만 그리고 내부 클릭은 아래 객체로 전달합니다.
- 스냅: 격자 간격과 같고 좌표계 원점 기준입니다. 끌 수 있습니다.
- 선택 객체를 드래그해 이동하고 모서리 점으로 크기를 바꿉니다. 속성 패널에서 m 좌표를 직접 입력할 수 있습니다.
- 잘못된 값(비숫자, 0.1 m 미만 변, 건물 경계 밖, 없는 ID, 거리 없는 MIN_CLEARANCE)은 반영하지 않고
  도면 위에 `반영되지 않음` 오류를 띄우며, 입력칸은 저장된 값으로 되돌립니다.
- Port를 선택한 배관의 시작/도착 Port로 지정할 수 있습니다.
- 규칙은 도면 아래 `제약 규칙` 패널에서 **전체 목록**으로 봅니다. 각 규칙은 문장으로 표시되고
  (예: "PIPE-103 배관 외곽은 ZONE-CABLE-L2 표면에서 0.5 m 이상 떨어져야 합니다."), 선택 배관 기준으로
  `적용 중` / `실행 차단 · 미승인` / `다른 배관` 배지가 붙습니다. 한 배관에 걸린 승인 규칙은 **개수와 관계없이 모두 동시에**
  적용됩니다(AND). 규칙 하나에 배관과 대상(Zone·장애물)을 여러 개 체크할 수 있고, 배관·대상마다 거리를 다르게 하려면
  규칙을 따로 만듭니다. 규칙을 펼치면 종류·거리·배관·대상·승인 상태를 고치거나 삭제할 수 있고, 그 대상이 2D·3D에서 자홍색으로 강조됩니다.
- 새 규칙은 `+ 규칙 추가` 또는 속성 패널의 `+ 이 객체에 규칙 추가`로 만들며, 출처(문서·개정·조항·근거)를 갖춘 `draft`로 시작합니다.
  `출처를 연구용 가정 기본값으로 자동 채우기`(기본 켜짐, 브라우저에 기억)를 켜 두면 출처가 `SYNTH-ASSUMPTION` · 개정 `1` ·
  다음 빈 조항 `A-n` · 규칙 내용을 그대로 적은 근거 문구(`연구용 가정(실제 법규·설계기준 값 아님): …`)로 채워집니다.
  끄면 생성된 값을 출발점으로 직접 고칠 수 있습니다. 자동 출처여도 규칙은 초안이며 승인은 직접 해야 합니다.
  배관에 미승인 규칙이 하나라도 있으면 실행 불가 안내가 나오며 서버는 `UNAPPROVED_RULE`을 반환합니다.
  속성 패널에는 선택 객체를 대상으로 하는 규칙 목록이 나오고, 누르면 규칙 패널에서 열립니다.
- 승인된 KEEP_OUT Zone은 붉게, 미승인 규칙 대상 Zone은 점선으로 표시합니다. 경로는 파란 polyline,
  검증 위반 구간은 붉은 굵은 선으로 표시합니다.
- 실행 취소/다시 실행은 `editor/history.ts`가 JSON 스냅샷(최대 50개)으로 관리합니다.
  JSON 텍스트를 직접 고치면 기록이 초기화되며 `JSON 검증` 후 도면에 반영됩니다.

도면을 수정하면 이전 경로 결과는 지워지므로 `경로 계산 실행`을 다시 눌러야 합니다.
JSON 텍스트 영역과 서버 저장은 같은 EngineeringProject를 사용합니다.

### 합성 플랜트 예제 (UI 시작값)

`SYNTH-PLANT-001`은 실제 시설이 아닌 **합성 2층 공정 건물**입니다: 60×40×12 m, 층고 6 m, 격자 0.5 m(230,400칸).
문·배관 관통부가 있는 내벽, 배관 샤프트 개구부가 있는 L2 바닥판, 기둥 4개, 장비 4대(탱크·펌프·열교환기·상부 탱크),
배관 3개(외경 168.3 / 114.3 / 88.9 mm), 전기실 KEEP_OUT, L2 케이블트레이 통로 0.5 m MIN_CLEARANCE를 포함합니다.
모든 규칙은 `synthetic_assumption`이며 수치는 예시일 뿐 실제 설계 기준이 아닙니다.
화면의 `예제 불러오기`에서 소형 데모(12×10 m)로 바꿀 수 있습니다.

측정(이 PC, 경로 1회): PIPE-101 0.3 s, PIPE-102 2.0 s, PIPE-103(층간) 2.9 s. 격자 마스킹은 장애물이 닿는
칸 범위만 검사하도록 바꿨으며 데모·플랜트 예제의 격자/규칙 마스크와 경로 결과가 변경 전과 동일함을 확인했습니다.

## 빈 프로젝트에서 기기·배관 구성 (P07b~P07f)

**Port는 기기의 배관 접속점**, **경유점은 배관이 중간에 반드시 지나야 하는 위치**입니다.
Port는 기기에 소속되고 배관의 시작/끝에서 ID로 참조합니다. 화면에서는 **연결점**으로 표시합니다.
경유점은 선택 배관에 순서대로 저장되며 중간 위치·통과 축을 지정합니다.
추가 연결점은 기기 속성창의 **연결점** 탭에서 만듭니다. 목록에서 수정할 점을 선택하거나 ×로 삭제합니다.

1. 처음부터 기본 20×12×6 m 빈 건물·1개 층으로 시작합니다. **+ 새 프로젝트 → 이름 입력 → 프로젝트 만들기**로 새 캔버스를 만듭니다.
   기존 도면에서 시작했다면 실행 취소로 이전 도면을 복원할 수 있습니다. 건물 크기·층·격자는 **건물·격자 설정** 팝업에서 바꿉니다.
2. **기기 추가** → 종류(탱크·펌프·열교환기·일반 기기) 선택 → 도면 클릭.
   몸체와 소속 Port 두 개가 함께 생깁니다. 예를 들어 펌프를 (5, 6), 열교환기를 (15, 6) m 근처에 배치합니다.
3. **배관 연결** → 펌프 오른쪽 연결점 → 열교환기 왼쪽 연결점을 클릭합니다. 같은 점을 두 번 선택하면 오류를 안내하며, Esc로 취소할 수 있습니다.
4. 생성된 **방향 화살표가 있는 점선**을 클릭하면 오른쪽에 배관 속성이 나옵니다. 외경·보온재·경유점을 수정하고 도면 위 **경로 계산**을 누릅니다.
   점선은 연결 관계이고 검증된 물리 경로가 아닙니다. 성공 계산 후 실제 경로를 **실선**으로 표시합니다.
   도면 위 **프로젝트 이름 / 프로젝트 저장**으로 이름을 바꾸고 저장할 수 있습니다. 한글 이름도 허용하며 저장 ID는 그대로 유지합니다.
   불러오기는 **프로젝트 → 저장·불러오기 → 저장된 프로젝트 목록**, 결과 표는 **계산 결과** 탭에서 봅니다. 빈 프로젝트 자체도 저장할 수 있습니다.

상단과 프로젝트 탭은 **저장됨 / 저장되지 않은 변경 있음**을 같은 문서 기준으로 표시합니다.
저장 목록의 기기·배관 수는 마지막 서버 저장본의 수입니다. 기기 추가·이동·삭제 후 저장하면 목록도 갱신됩니다.
프로젝트 이름 `test1`을 `test11`로 바꿔 저장하면 저장 ID를 유지하고 개정을 올려 목록의 이름을 갱신합니다.
페이지를 새로고침한 뒤에도 저장 목록에서 다시 열 수 있습니다. ID 직접 입력은 보조 상세 항목으로 유지합니다.

저장 목록의 **삭제**를 누르면 이름·파일명·개정을 표시하는 확인창이 열리며 기본 선택은 **취소**입니다.
**저장 파일 삭제**를 누르면 해당 저장본만 영구 삭제하고 목록을 갱신합니다. 계산 결과 기록은 유지합니다.
현재 작업의 저장 파일을 삭제해도 화면의 편집 내용은 유지되며 **미저장** 상태로 바뀝니다.
다시 저장하면 파일이 새로 만들어집니다. 확인 중 저장 개정이 바뀌거나 삭제에 실패하면 파일을 삭제하지 않고 오류를 표시합니다.

**예제 불러오기**는 새 ID의 작업 복사본을 만듭니다. 기기를 추가하고 **프로젝트 저장**을 누르면 복사본에 모두 반영됩니다.
수정한 예제를 다시 열 때는 저장 목록의 해당 항목에서 **불러오기**를 누르세요. 예제 원본과 이미 저장한 다른 복사본은 유지됩니다.
이전에 저장한 `SYNTH-PLANT-001`·`SYNTH-DEMO-001` 항목도 저장 목록에서 열 수 있습니다.

편집 중 프로젝트 JSON은 메모리에서 자동 갱신됩니다. **저장은 계산의 선행 조건이 아닙니다.**
서버에 저장하면 `data/projects/{project_id}.json`에 이름(`project_name`)과 도면을 보존합니다.
이름은 선택 필드로, 이름 없는 기존 JSON을 불러와도 새 null 필드를 추가하지 않습니다.

**새 프로젝트 만들기만으로는 서버 파일이 생기지 않습니다.** 기본 표시 이름 `새 프로젝트` 그대로
저장하면 파일명은 `SYNTH-NEW-<생성 시각>.json`입니다. 예제 복사본은 `SYNTH-COPY-<생성 시각>.json`을 씁니다.
한글 이름을 바꾸어 저장해도 ID/파일명은 유지됩니다. 같은 이름의 프로젝트도 ID로 구분합니다.
**프로젝트 → 저장·불러오기**의 요약에 현재 ID와 `data/projects/...json`을 표시하고 저장 목록에도 파일명을 표시합니다.
이 경로는 브라우저 PC가 아닌 **API 서버의 프로젝트 폴더** 기준입니다.

미저장 작업에서 새 프로젝트·예제·저장 프로젝트를 열면 **저장하고 계속 / 저장하지 않고 계속 / 취소**를 선택합니다.
저장에 실패하면 현재 작업을 유지합니다. 새로고침·브라우저 탭 닫기·다른 페이지 이동에는 브라우저의 기본 확인이 나타납니다.
아무것도 편집하지 않은 최초 빈 화면은 경고하지 않습니다. 앱 안의 2D/3D/프로젝트/결과 탭 전환은 도면을 유지합니다.
브라우저 경고의 문구는 브라우저가 정하며 강제 종료 등에서 항상 표시되지는 않습니다.
자동저장·개정별 이전 파일 복원은 제공하지 않으므로 필요한 프로젝트는 저장하고 별도 백업하세요.

`INVALID_INPUT`과 `port ... snaps to a physical blocked cell`은 연결점이 속한 **격자**가 기기·벽·건물 경계로 막혔다는 뜻입니다.
점 자체가 몸체 밖이어도 배관 외경·보온재와 보수적인 격자 판정 때문에 막힐 수 있습니다. 저장 여부와는 관계없습니다.
화면에서 연결점 이름·좌표·수정 안내와 **막힌 연결점 선택**을 표시하고 2D에는 빨간 테두리를 그립니다.
그 점이나 주변 기기를 옮기고 다시 계산하세요. 기기 몸체를 옮기면 소속 연결점도 함께 움직입니다.
재현 예: 펌프를 (5, 6)과 (8, 6) m에 추가하고 첫 펌프 오른쪽 → 두 번째 왼쪽을 연결하면 막힌 격자를 안내합니다.
두 번째 펌프를 선택해 X 위치(몸체 왼쪽)를 14 m로 적용하면 저장 전에도 SUCCESS/VALID가 됩니다.
막힌 칸을 통과하도록 충돌 검사를 완화하거나 연결점을 몰래 이동하지 않습니다.

기기 몸체를 클릭해 드래그하면 소속 Port도 같이 움직입니다. 오른쪽 선택 속성창에서
기기 종류·위치·크기·삭제, 연결점 좌표/방향·삭제, 배관 단면·경유점·삭제를 수정합니다.
벽·제약 구역은 상단 도구에서 만들고, 구역 속성의 **이 구역에 제약 설정**으로 규칙 편집을 엽니다.
**2D 배치 / 3D 보기 / 프로젝트 / 계산 결과** 탭으로 작업 화면을 전환합니다.
탭 옆에 모인 **3D/2D 함께 보기**는 현재 화면 안에 다른 보기를 열고, **3D/2D 새 창**은 별도 브라우저 창으로 엽니다.
함께 보기는 한 화면에서 비교할 때, 새 창은 다른 모니터에 둘 때 사용합니다. 각 버튼에 용도를 보여 주는 아이콘이 붙습니다.
보조 창의 제목을 화면 맨 위까지 드래그해 이동하고 **위·아래·좌·우 테두리와 네 모서리**에서 크기를 조절합니다.
포인터가 해당 방향 화살표로 바뀝니다. 오른쪽 아래 ◢ 손잡이도 유지합니다.
**최대화 / 원래 크기**는 브라우저 내용 영역 전체를 사용하고 복원하며 2D/3D canvas도 창 크기에 맞춰 조절됩니다.
손잡이에 포커스를 두면 방향키로도 크기를 바꿀 수 있습니다(Shift로 더 크게 변경).
작은 창에서는 본문을 스크롤합니다. 닫기 또는 Escape로 닫으며 창 크기는 다시 열 때 기본값으로 돌아갑니다.
**듀얼 모니터에서는 ‘새 창으로 열기’ 또는 ‘2D/3D 새 창’을 누르세요.** 실제 브라우저 창의 제목줄을
다른 모니터로 끌어 옮긴 뒤 OS 최대화·테두리 조절을 사용할 수 있습니다. 2D와 3D를 각각 별도 창으로 열 수 있습니다.
메인 창과 프로젝트·선택·편집·계산 결과를 공유하고 같은 보기 버튼을 다시 누르면 이미 열린 창을 표시합니다.
메인 작업 탭을 바꿔도 별도 창은 유지됩니다. 별도 창만 닫아도 도면은 메인에 남습니다.
별도 창의 **메인에서 계속**은 메인의 같은 2D/3D 탭을 열고 이 보조 창을 닫습니다. 프로젝트를 다시 로드하지 않습니다.
보조 창은 더 좁고 높은 비율로 시작하고, 넓은 화면에서도 콘텐츠를 중앙에 배치합니다.
2D의 속성 패널은 실제 보기 폭에 따라 옆/아래로 이동하며 3D 카메라는 canvas 비율에 맞춰 건물 전체를 보여 줍니다.
별도 2D/3D 창은 자체 크기 감지와 그리기를 사용하므로 메인 창이 배경이어도 화면을 갱신합니다.
메인 페이지를 떠나거나 새로고침하면 별도 창은 닫히므로 메인 창은 계속 열어 두세요.
브라우저가 팝업을 차단하면 허용 후 다시 눌러야 합니다. 실제 물리 듀얼 모니터 이동은 수동 검수 대상입니다.
창의 resize 정책은 [P07h 창 관리](docs/decisions/0023-p07h-window-edges-and-detached-views.md),
보기 배치·저장본 삭제 정책과 최신 검수는 [P07i 사용성 개선](docs/decisions/0024-p07i-view-layout-and-project-deletion.md)에 있습니다.
두 보기는 JSON과 선택·결과를 공유하고, 3D 속성에서도 위치·크기·연결점·단면을 수정합니다.
3D 탭과 3D 보조 창에도 **계산할 배관 선택 / 경로 계산**이 있습니다. 계산 요약을 바로 표시하며 결과는 2D와 공유합니다.
배관이 없거나 다른 작업을 처리하는 동안 계산 버튼은 비활성화됩니다.
프로젝트의 JSON은 **JSON 편집** 하위 탭에서 다룹니다. 내부 ID·규칙 상세·승인 관리처럼 부차적인 정보는 확장을 유지합니다.
몸체 크기를 바꾸면 Port 좌표는 유지하므로 접속 위치도 확인하세요. 종류 변경은 분류만 바꿉니다.
기기를 삭제하려면 연결된 배관을 먼저 삭제하거나 다른 Port에 연결해야 합니다.
규칙에서 참조하는 몸체·배관은 규칙을 먼저 정리해야 합니다. 몸체 단독 삭제는 참조 보호를 위해 차단합니다.

기기 몸체는 기존 `geometry_ref → Obstacle`의 합성 상자입니다. 기본 크기는 편집 시작값이며 실제 사양이 아닙니다.
기본 Port는 몸체 밖의 간략 외부 접속점입니다. 실제 노즐·장비 표면 접속·허용 진입 터널은 생략하고,
몸체 충돌 검사에 예외를 추가하지 않습니다. [P07b 생성/삭제 정책](docs/decisions/0017-p07b-blank-equipment-and-pipe-editor.md),
[P07c 화면·연결 정책](docs/decisions/0018-p07c-canvas-first-editing.md),
[P07d 탭·팝업·연결점 관리](docs/decisions/0019-p07d-workspace-tabs-and-nozzles.md)를 참조하세요.
새 프로젝트·오류 안내의 검수는 [P07e 결정 기록](docs/decisions/0020-p07e-project-names-and-route-input-feedback.md)에 있습니다.
저장 목록·예제 수정본의 검수는 [P07f 결정 기록](docs/decisions/0021-p07f-project-library-and-example-copies.md)에 있습니다.

## 3D 보기와 2D/3D 선택 연동 (P08)

React Three Fiber(`three`, `@react-three/fiber`, `@react-three/drei`)로 2D 편집기와 **같은 EngineeringProject JSON**을
3D로 그립니다. 메시는 JSON이 바뀔 때마다 다시 만들어지며, 메시 위치를 읽어 도메인 데이터로 저장하지 않습니다.

- 축 변환은 `frontend/src/viewer/axes.ts`의 `worldToScene` 한 곳에만 있습니다. 세계(m, +Z 위) →
  Three.js 장면(+Y 위)을 `scene = (x, z, -y)`로 바꾸며 회전(행렬식 +1)이라 길이·각도·좌우가 보존됩니다.
  배율이나 원점 이동은 없으므로 장면 단위도 m입니다.
- `viewer/scene.ts`가 JSON과 경로 결과로부터 그릴 내용(상자·Port·경로 구간)을 순수 함수로 만들고,
  `Viewer3D.tsx`는 그것을 렌더링만 합니다.
- 장애물은 불투명 상자, 바닥판(`kind: slab`)은 거의 투명한 상자(클릭 불가), 승인 KEEP_OUT Zone은 반투명 붉은색,
  기타 Zone은 반투명 노란색, 미승인 규칙 대상 Zone은 더 옅게 표시합니다. Port는 구와 방향 표시 짧은 선입니다.
- 경로는 중심선(Line)과 보온재 포함 외경 반경의 원통 구간·이음 구로 표시하며, 검증 위반 구간은 붉게 표시합니다.
  원통의 양 끝은 서버가 반환한 `points_m`과 정확히 일치합니다. `clearance_margin_m`은 몸체로 그리지 않습니다.
- 객체를 클릭하면 2D 도면과 속성 패널에서 같은 ID가 선택되고, 다른 층의 객체이면 2D 층 선택이 그 층으로 바뀝니다.
  2D에서 선택하면 3D에서 강조하고 ID 라벨을 띄웁니다.
- 축 이름·S/E·경유점 번호·선택 ID 라벨은 DOM 오버레이(drei `Html`)가 아니라 WebGL 스프라이트(`viewer/TextLabel.tsx`)로
  그립니다. `Html`을 쓸 때 처음 마운트된 라벨(X축) 내용이 비어 표시되지 않는 문제가 있었기 때문입니다.
- 조감도/평면도(세계 +Y가 화면 위쪽) 카메라 전환, 카메라 리셋, OrbitControls, X/Y/Z 축 표시,
  `규칙 대상 강조`로 선택한 규칙의 대상 객체와 출처 요약을 보여 줍니다.
- three.js는 `React.lazy`로 따로 불러오는 청크에 들어 있어 첫 화면 번들에 포함되지 않습니다.
  공유 단위 형상, 메모된 상자 컴포넌트, `frameloop="demand"`로 불필요한 다시 그리기를 줄였습니다.

## 시작/끝점 구분과 필수 경유점 (P08b)

선택한 배관의 **시작 Port는 초록 `S`, 끝 Port는 보라 `E`, 경유점은 주황 마름모(2D)·팔면체(3D)와 순번**으로
2D·3D에서 같은 색으로 표시합니다. 도면 위 `경로 순서` 줄에 `S → 1 → 2 → … → E`가 나오며, 칩을 누르면 그 객체가
선택되고 선택한 경유점은 ◀ ▶로 순서를 바꾸거나 ✕로 지웁니다.

- 추가: `+ 경유점 추가`를 누른 뒤 도면을 클릭할 때마다 선택 배관의 **마지막 순서**에 경유점이 붙습니다.
  스냅이 켜져 있으면 탐색 격자 **칸 중심**(`bounds_m.min_m + (i + 0.5) × 격자`)에 맞춥니다. 높이는 같은 층의
  이전 경유점(없으면 Port 기본 높이)을 쓰며 속성 패널에서 X/Y/Z를 직접 입력할 수 있습니다.
- 통과 방향(`pass_axis`): 벽 관통부(슬리브)처럼 **그 축으로 곧게 지나가야** 하는 지점이면 X/Y/Z를 지정합니다.
  경로는 그 점에서 꺾이지 않고 지정 축으로 들어와 같은 방향으로 나갑니다. 바닥판 관통은 Z입니다.
- 메모(`note`): 토목도면 번호, 철근 탐사 결과 등 근거를 남깁니다(500자 이하). 계산에는 쓰이지 않습니다.
- 저장 형식: `pipes[].waypoints = [{ id, position_m, pass_axis?, note? }]`. 선택 필드이므로 기존 JSON은 그대로 유효하고,
  경유점을 모두 지우면 필드가 사라져 원래 문서와 같아집니다. 경유점 ID도 프로젝트 전체에서 고유해야 합니다.
- 탐색: A* 상태에 "지금까지 순서대로 지난 경유점 수"를 넣어 최초 탐색을 한 번에 수행합니다.
  최적성은 **자기 간섭을 제외한 컴파일 격자의 목적함수**에 한정됩니다. 즉시 180도 역행은 그래프에서 제외합니다.
  테스트에서 Dijkstra 및 별도 소형 그래프 기준 계산과 같은 비용을 확인합니다. 경유점에서 꺾이는 횟수도 비용에 포함됩니다.
- 실패 구분: 경유점이 장애물·건물 경계 팽창·승인 규칙 영역 안이면 `WAYPOINT_BLOCKED`(409), 경유점 자체는 비어 있지만
  순서·통과 방향을 만족하는 경로가 없으면 `NO_PATH`, 격자 칸 중심에서 너무 멀면 `INVALID_INPUT`입니다.
- 자기 간섭: 같은 배관의 떨어진 두 부분이 외곽 지름(2 × 외곽 반경, 마진 포함)보다 가까우면 실제로는 겹치는 배관입니다.
  순서 전체 최적 탐색은 지나간 칸을 기억하지 않아, 경유점을 갔다 오는 경우 같은 칸이나 바로 옆 칸으로 되돌아올 수 있습니다.
  이렇게 겹치면 탐색기가 경유점 구간을 **하나씩 다시** 찾으며 앞서 깐 구간의 외곽 범위를 피합니다(결과 화면에
  "구간별로 다시 탐색" 안내, 순서 전체 최적은 보장 안 됨). 그래도 피할 수 없으면(예: 끝 Port가 시작 구간에 너무 가까움)
  겹친 경로를 그대로 돌려주고 검증기가 `SELF_CLEARANCE` 위반으로 `INVALID_ROUTE`를 냅니다.
  P08c에서는 같은 방향의 공선점을 합쳐 판정하고, 인접 구간의 역행을 항상 검출합니다.
  비역행 인접 접합부는 면제하며, 비인접 부분은 경로상 거리 `2√3 × 반경`을 넘는 점 쌍의 외곽 접촉을 검사합니다.
  이는 연구용 꺾은선 정책이며 실제 엘보의 곡률·제작 가능성을 검사하지 않습니다.
- 독립 검증: 연속 경로가 각 경유점을 **순서대로** 칸 대각선의 절반(`√3/2 × 격자`) 이내로 지나는지(`WAYPOINT_MISSED`),
  `pass_axis`가 있으면 그 점 앞뒤 구간이 그 축과 평행한지(`WAYPOINT_DIRECTION`) 다시 검사합니다.

합성 플랜트 예제에서 PIPE-102는 경유점 없이 계산하면 WALL-A의 **문 개구부**(y≈18.75 m)로 벽을 넘습니다.
경유점 `[30.25, 30.75, 4.75]`, 통과 방향 X를 주면 **슬리브 개구부**(y 30–31.5, z 4–5.5)로 곧게 관통하며
독립 검증 VALID입니다(P08b 확인 사례: 길이 39.0 → 60.0 m). 계산 시간은 환경과 입력에 따라 달라집니다.

경유점은 "반드시 여기를 지난다"는 조건입니다. 경유점이 없는 배관이 다른 틈으로 벽을 넘는 것을 막는
"승인된 개구부로만 통과"(ROADMAP P09B `ALLOWED_PASSAGE`)와 관통부를 여러 배관이 공유하는 별도 객체는 아직 없습니다.

## 연구 정확성 검수와 승인 이력 (P08c)

독립 검증기는 포트 방향과 직교 경로를 검사합니다. 출발 방향은 출발 포트의 바깥 방향,
도착 방향은 도착 포트의 바깥 방향의 반대입니다. 첫/마지막의 정확한 포트–해당 격자 중심 연결선만
직교·방향 검사의 예외이며, 충돌 검사는 계속 적용합니다. 같은 칸 연결에 격자 본체가 없으면 방향 검사는 없습니다.

경유점은 같은 방향의 공선점을 합친 구간에 순서대로 투영해 거리와 통과 축을 검사합니다.
근처 모서리가 축 조건을 만족하지 않아도 뒤의 적합한 통과를 계속 찾습니다. 허용오차는 `√3/2 × 격자`이며
개구부의 물리 허용오차를 뜻하지 않습니다. 반복 경유점은 같은 투영 위치를 공유할 수 있습니다.

결과의 **재현 정보와 보장 범위**에서 최초 탐색/재탐색 상태, 탐색 방식, 최적성, 허용오차를 볼 수 있습니다.
`EXACT_GRID`는 최초 격자 탐색, `HEURISTIC_LEGS`는 구간별 재탐색,
`EXACT_GRID_RETURNED`는 재탐색 실패 후 최초 경로 반환입니다. 최종 검증 실패에는 최적성 보장이 없습니다.
`NO_PATH`는 컴파일된 6방향 격자에서 경로가 없다는 뜻입니다. 검색 예산 초과와 연속공간 불능은 별개입니다.

규칙 수정은 개정 번호를 올리고 이전 승인을 해제합니다. 상태를 **검토 대기**로 두고 수치를 수정해 적용한 뒤,
현재 내용을 확인하고 **승인**을 선택해 검토자 이름을 입력하고 **현재 내용 승인·적용**을 누르세요.
`POST /api/constraints/approve`가 현재 내용의 해시·개정·검토자·서버 시각을 승인 이력에 연결합니다.
JSON에서 승인 후 내용을 바꾸면 컴파일과 검증이 차단됩니다. 저장 버튼으로 승인 이력까지 저장할 수 있습니다.

이력이 없는 기존 `approved` 규칙은 호환성을 위해 실행을 허용하고 결과의 `legacy_approval_rule_ids`에 표시합니다.
내용에 연결된 승인을 얻으려면 기존 규칙도 명시적으로 재승인하세요. 검토자 이름은 로컬 사용자 선언이며
로그인 인증이나 변조 방지 감사 저장소를 제공하지 않습니다.

자동 반례 재현: `uv run python scripts/review_regressions_20261011.py`.
계약·정책·검수 근거는 [P08c 설계 결정](docs/decisions/0013-p08c-validation-and-approval-contract.md)을 참조하세요.
브라우저 조작과 WebGL 시연은 별도 수동 검수가 필요합니다. 반복 실험은 아래 P10A 저장소를 사용합니다.

## 예비 벤치마크 실행 (P10A)

프로젝트 루트에서 실행합니다. API·Vite 서버를 켜지 않아도 동작합니다.

```bash
uv run python scripts/run_benchmark.py --seed 42 --config benchmarks/pilot.json
```

11개 소형 합성 장면을 A*와 Dijkstra로 각각 2회 계산합니다. 직선·굽힘·경유점·벽 우회·금지구역·이격·층간 이동과
완전 차단·예산 초과·미승인을 확인합니다. 별도 그래프 기준 계산으로 비용을 대조하며 고의 손상 경로도 검사합니다.
기본 예비 실행에서 44회 모두 예상 상태와 일치했습니다. 이 수치는 경로 성공률이나 알고리즘 우월성을 뜻하지 않습니다.

명령이 출력한 `output` 폴더에서 다음 파일을 확인하세요.

- `summary.json`: 완료 여부, 예상 계약 통과 수와 상태별 건수
- `runs.csv`: Excel에서 열 수 있는 각 실행의 길이·비용·상태·단계별 시간
- `environment.json`, `source.zip`: Git/실제 소스/환경 버전과 Python 소스 보관
- `<case_id>/case.json`: 독립 정답 근거와 수동 그래프·가능 경로
- `<case_id>/project.json`: 웹의 프로젝트 JSON 편집기에 붙여 넣을 EngineeringProject
- `<case_id>/<run_id>/input.json`, `run.json`: 각 실행의 원본 입력과 상세 결과

다시 실행하면 `data/benchmarks/`에 새 배치가 생기며 이전 결과를 보존합니다. 실패한 계약 검사가 있으면 종료 코드 1입니다.
`summary.json`이 없는 폴더는 중단된 배치이며 자동 재개를 지원하지 않습니다.
반복 수는 `benchmarks/pilot.json`의 `repeats`로 바꿀 수 있습니다. 시드는 현재 좌표 원점 이동만 바꾸므로
다른 시드를 독립 공간 표본으로 세면 안 됩니다.

웹 결과의 **경로 계산 시간**은 컴파일·탐색·검증을 포함합니다. 펼친 상세 정보에서 각 시간을 볼 수 있으며,
저장·네트워크 시간은 제외됩니다. 기존 API 결과 파일은 같은 요청을 덮어쓰므로 논문 반복 기록에 사용하지 마세요.
정답 범위와 11개 장면의 기준 비용은 [P10A 설계 결정](docs/decisions/0014-p10a-pilot-benchmark.md)에 기록했습니다.
본 비교 실험과 규칙 변경 분석은 아래 P10B·P10C를 사용합니다.

## 본 비교 실험 실행 (P10B)

```bash
uv run python scripts/run_benchmark.py --config benchmarks/comparison.json
```

고정 시드의 개발 장면 35개·별도 평가 장면 14개를 각각 1 m/0.5 m 격자로 계산하고,
A*·Dijkstra를 3회씩 반복합니다. 자기 간섭 재탐색 진단 2개를 더해 총 600회입니다.
2026-10-11 확인 실행에서 600회 모두 기대 상태와 일치했고 성공 exact 결과의 두 알고리즘 비용 차이는 0이었습니다.
상태는 SUCCESS 468회(휴리스틱 진단 6회 포함), NO_PATH 126회, 예상된 INVALID_ROUTE 진단 6회였습니다.
별도 검증기 시험 8개(유효 4개·손상 경로 4개)에서는 잘못된 승인·거부가 없었습니다.
같은 물리 공간의 해상도 비교와 반복 측정은 새 장면 수로 세지 않습니다.

출력 폴더에서 `comparison_report.md`를 먼저 열면 같은 조건의 비용·시간 대조를 볼 수 있습니다.
`scene_metrics.csv`는 반복을 장면별 중앙값으로 묶은 표이고, `comparison_statistics.json`에는
시드 단위 bootstrap 구간·표본 수·기준 계산 적용 범위가 있습니다.
`figures/`에는 논문에 삽입할 PNG와 PDF 3종이 생깁니다.

좁은 개구부 장면은 연속 직선 경로가 있어도 1 m 격자에서 NO_PATH이고 0.5 m에서는 SUCCESS입니다.
이번 witness 장면군의 성공률은 각각 83.3%/100%였습니다. 이 수치를 실무 건물의 성공률로 확대하지 마세요.
평가 시드 cluster가 2개뿐이라 신뢰구간도 기술 통계로 해석합니다. 실제 시간 값은 실행 환경에 따라 달라집니다.

`--seed`는 이 설정에서 실행 순서·통계 재표본화 시드를 바꿉니다. 공간 시드는 `scene_seeds`와
`evaluation_seeds`이며 서로 겹치면 실행을 거절합니다. `--config benchmarks/pilot.json`은 기존 P10A 실행을 유지합니다.
설계·정답·해석 한계는 [P10B 설계 결정](docs/decisions/0015-p10b-comparison-and-statistics.md)을 참조하세요.
규칙 영향은 아래 P10C에서 같은 알고리즘·같은 공간의 전후 입력으로 대조합니다.

## 규칙 변경 영향·추적성 대조 (P10C)

```powershell
uv run python scripts/run_benchmark.py --config benchmarks/changes.json
```

개발 시드 5개·평가 시드 2개의 동일한 물리 공간에서 규칙만 바꿉니다. 장면당 기준선,
KEEP_OUT 추가, 최소 이격 추가·거리 증가, 출처만 수정, 중복 규칙, 규칙별 개별 제거,
완전 봉쇄, 초안·승인 후 내용 변조 진단을 포함한 12개 입력을 만듭니다.
두 해상도·두 알고리즘·3회 반복으로 총 1,008회이며 API·Vite 없이 실행할 수 있습니다.

2026-10-12 직접 실행 결과: 1,008회 모두 기대 상태와 일치했습니다(SUCCESS 756,
NO_PATH 84, UNAPPROVED_RULE 168). 반복을 묶은 전후 대조는 308쌍이고,
그중 성공 exact 쌍 224개에만 비용·길이·굽힘·형상 차이를 계산했습니다.
반복 실행을 포함한 승인·출처·대상 연결 1,428건과 대조 경로의 규칙·객체·구간 연결 708건은 모두 완전했습니다.
이는 이 합성 입력에서 검사한 연결의 결과이며 실제 법규나 검증기의 완전성을 의미하지 않습니다.

평가 A*·1 m 장면의 평균 목적함수 변화는 KEEP_OUT 추가 +16, 이격 증가 +2,
이격 규칙 제거 −2였습니다. 출처만 수정하거나 중복 KEEP_OUT을 추가/제거하면 변화가 없었습니다.
최초 0.25 m 이격 추가도 이 평가 격자에서는 비용 변화가 0이므로,
`applied_rule_ids`만으로 규칙의 경로 영향 크기를 판단할 수 없습니다.

출력 폴더에서 `change_report.md`를 먼저 열어 보세요.

- `change_metrics.csv`: 전후 상태·비용·길이·굽힘·형상·합집합 차단 셀 변화와 반복 시간 중앙값
- `change_comparisons.json`: 전후 원본 실행 ID·규칙 정의 및 서로의 규칙으로 경로를 다시 검증한 결과
- `traceability_audit.json`: 실행별 규칙 내용·개정·승인·출처·대상과 기하 구간 연결 검사
- `change_statistics.json`: 대조 분모·추적성 분모·실패·시드 cluster 통계
- `figures/rule_change_objective.png` / `.pdf`: 평가 장면의 비용 변화 그림

같은 알고리즘의 전후 입력을 비교하며 P10B의 알고리즘 시간 비교와 구분합니다.
처리 순서에 의존하는 `newly_blocked_cells_count`를 유일한 인과 영향으로 해석하지 않습니다.
형상 지표는 양쪽 꼭짓점에서 상대 꺾은선까지의 거리 표본이며 정확한 연속 Hausdorff 거리가 아닙니다.
새 대조 화면을 웹에 추가한 단계는 아니며, 장면의 `project.json`은 기존 웹 JSON 입력에 불러올 수 있습니다.
설계·진단·한계는 [P10C 설계 결정](docs/decisions/0016-p10c-rule-changes-and-traceability.md)을 참조하세요.

## 저장 파일과 재현 범위

| 위치 | 저장 방식 |
| --- | --- |
| `data/projects/` | 실제 저장 프로젝트. ID별 최신 JSON과 개정·해시. 같은 ID 저장 시 교체; 백업 대상 |
| `data/results/` | 요청 기반 결과 ID. 동일 요청을 재실행하면 교체 |
| `data/benchmarks/` | 새 배치·장면·실행별 폴더를 만들어 반복 기록 보존 |
| `data/ui_checks/` | 브라우저 검수 기록·스크린샷·테스트 프로필. 일반 앱 실행에는 불필요 |

`data/projects/`는 저장·불러오기에, `data/results/`는 계산 결과 보존에 사용하며 필요할 때 자동 생성됩니다.
`data/benchmarks/`와 `data/ui_checks/`는 일반 편집기 운영에 필수는 아니지만 연구/검수 근거를 보존합니다.
`src/plan_route/fixtures/`는 예제 버튼과 테스트가 읽는 합성 원본이며 사용자 저장본과 별개입니다.
저장 개정 번호가 올라가도 이전 개정 파일을 따로 남기지는 않습니다. 자세한 정책과 실제 검수는
[P07g 저장·미저장 보호·보조 창 기록](docs/decisions/0022-p07g-unsaved-work-and-resizable-companions.md)에 있습니다.

이 폴더들은 Git에서 제외됩니다. 저장한 프로젝트와 측정 결과는 로컬에 남으며, 새로 clone한 환경에서는
예제 JSON과 `benchmarks/*.json` 설정으로 다시 실행합니다. 벤치마크의 `source.zip`은 Python 소스·예제·설정·의존성
파일 등을 보관하며 전체 프런트엔드 저장소를 대신하지 않습니다. 전체 구현은 Git 커밋으로 관리합니다.

## 연구에서 아직 확인할 부분

현재 결과는 합성 AABB 장면과 정해진 격자·꺾은선 정책에 한정됩니다. A* 자체의 새로움이나 실무 우월성,
실제 배관 제작·안전·인허가 적합성을 입증하지 않습니다. 논문 차별성 후보는 승인된 구조화 규칙의 추적성과
독립 검증을 결합한 재현 가능한 변경 분석입니다. P10C에서 합성 대조 근거를 확보했으며,
**선행연구와 같은 범위의 비교·논문 주장 확정·브라우저 수동 검수는 남아 있습니다**.

승인된 관통부만 통과하는 `ALLOWED_PASSAGE`, Soft Constraint, 여러 배관의 상호 간섭·공동 최적화,
CAD/IFC 내보내기는 P09의 선택 구현 범위입니다. 응력·열팽창·지지대·실제 엘보 제작 검토는 현재 제공하지 않습니다.

## 폴더 구조

```text
src/plan_route/main.py      FastAPI 앱과 로컬 CORS
src/plan_route/api/health.py GET /api/health 및 응답 타입
src/plan_route/api/projects.py 합성 예제 및 JSON 검증 API
src/plan_route/api/constraints.py 규칙 컴파일·현재 내용 승인 API
src/plan_route/api/routing.py 경로 탐색·검증 API
src/plan_route/models/      EngineeringProject 및 참조 검증
src/plan_route/fixtures/    합성 예제 JSON 정본
src/plan_route/services/    기하·탐색·규칙·검증·저장·벤치마크 구현
src/plan_route/services/geometry.py 연속 AABB 연산·배관 반경
src/plan_route/services/voxel_grid.py 좌표 변환·격자 마스크
src/plan_route/services/astar.py 방향 인지형 A*·Dijkstra
src/plan_route/services/compiler.py 승인 규칙 차단 마스크·출처 추적
src/plan_route/services/path_validator.py 독립 연속 기하 검증
src/plan_route/services/routing.py 컴파일·탐색·검증 실행
src/plan_route/services/report_store.py 결과 보고서 원자적 저장
src/plan_route/services/project_store.py 프로젝트 개정·해시·원자적 저장
src/plan_route/services/approval.py 규칙 개정·내용 해시와 승인 이력 연결
src/plan_route/services/benchmark.py 실행 보존·환경 기록·단계별 계측
src/plan_route/services/benchmark_cases.py 예비 벤치마크·검증기 시험
src/plan_route/services/benchmark_scenes.py 고정 시드 비교 장면·가능 경로 근거
src/plan_route/services/benchmark_reference.py 독립 소형 그래프 기준 계산
src/plan_route/services/benchmark_statistics.py 장면 집계·시드 bootstrap·그림
src/plan_route/services/benchmark_changes.py P10C 고정 공간의 규칙 변경 대조 입력
src/plan_route/services/benchmark_change_analysis.py 전후 경로·규칙 영향·추적성 분석
src/plan_route/models/benchmark.py 벤치마크 설정·장면·실행 계약
src/plan_route/models/results.py 탐색 상태·비용 분해 결과
frontend/src/api/client.ts  프로젝트·라우팅 API 타입 및 호출
frontend/src/App.tsx        데모·JSON 검증·저장·경로 결과 화면·편집 기록
frontend/src/editor/coordinates.ts 화면 px ↔ 세계좌표 m 변환·스냅·줌
frontend/src/editor/model.ts 형상·Port·규칙 편집 순수 함수와 입력 검사
frontend/src/editor/history.ts JSON 스냅샷 Undo/Redo
frontend/src/editor/RulesPanel.tsx 규칙 목록·편집·검토자 입력·승인
frontend/src/editor/RouteSequence.tsx 선택 배관의 S → 경유점 → E 순서 칩
frontend/src/editor/roles.ts 2D/3D 공통 시작·끝·경유점 색
frontend/src/editor/PlanEditor.tsx React Konva 층별 도면
frontend/src/editor/ObjectInspector.tsx 선택 기기·연결점·배관·형상 속성
frontend/src/editor/DomainPanel.tsx 탐색 도메인·격자, 배관 단면(외경·보온재·마진) 카드
src/plan_route/fixtures/plant_starter_project.json 합성 플랜트 예제(UI 시작값)
frontend/src/editor/editor.test.mjs 좌표·편집·기록 단위 테스트(node --test)
frontend/src/viewer/axes.ts 세계 m(+Z 위) → Three.js 장면(+Y 위) 단일 축 변환
frontend/src/viewer/scene.ts JSON·경로 → 3D 장면 모델, 카메라 프리셋
frontend/src/viewer/Viewer3D.tsx React Three Fiber 3D 보기
frontend/src/viewer/viewer.test.mjs 축 변환·메시 위치·경로 일치 테스트
tests/test_health.py       HTTP 응답 및 CORS 테스트
tests/test_schemas.py      스키마·참조·422 응답 테스트
tests/test_voxel_grid.py   경계·충돌·Zone 분리 테스트
tests/test_astar.py        최적 비용·실패 상태·방향 테스트
tests/test_constraint_compiler.py 규칙 적용·오류·API 테스트
tests/test_path_validator.py 독립 검증·라우팅 API 테스트
tests/test_project_store.py 저장·재로드·개정·경로침입 방지 테스트
tests/test_p07_editor_scenario.py 벽 이동 후 경로 변화 시나리오
tests/test_p07b_blank_project.py 실제 프런트 편집 JSON → API·저장·탐색 통합 검수
tests/test_plant_starter.py 플랜트 예제 라우팅·배관 마진 반영 테스트
tests/test_waypoints.py 경유점·순서 탐색·독립 검증 테스트
tests/test_p08c_*.py 검증 반례·독립 기준 계산·승인/결과 계약 테스트
tests/test_benchmark*.py 실행 보존·장면·기준 비용·통계 테스트
scripts/export_schema.py   JSON Schema 생성
scripts/review_regressions_20261011.py 검토 반례 재현
scripts/run_benchmark.py   예비/본 비교 실험 CLI
scripts/editor_blank_scenario.mjs 빈 상태에서 기기·배관 생성·이동·삭제 JSON 재현
scripts/check_editor_ui.mjs Edge headless 실제 클릭·API 계산·3D·모바일 검수
benchmarks/                pilot.json·comparison.json·changes.json 실행 설정
docs/schema/               생성된 JSON Schema
docs/decisions/            단계별 설계 결정
docs/reviews/              구현·논문 주장 검토 기록
```

Python 백엔드는 uv의 `src/plan_route/` 패키지로 통일합니다. `uv sync --locked`가
설치한 패키지를 사용하므로 별도의 `PYTHONPATH` 설정은 필요 없습니다.
기존 uv 기본 CLI는 유지하며, API 서버는 위의 uvicorn 명령으로 실행합니다.

## 검수

루트에서:

```powershell
uv run pytest -q
uv run ruff check .
```

프런트엔드에서:

```powershell
cd frontend
npm run build
npm run lint
npm run test:editor
npm run test:viewer
```

`test:editor`/`test:viewer`는 Node.js의 TypeScript 타입 제거 실행(Node 22.18+ 기본)과 `node --test`를 사용하므로
별도 테스트 의존성이 없습니다.

2026-10-11 이 문서 갱신 시 직접 실행한 검수: Python **189개**, editor **20개**, viewer **10개** 테스트 통과,
Ruff·frontend lint·build 통과. Starlette의 TestClient 폐기 예정 경고와 Vite의 500 kB 초과 청크 경고가 남아 있습니다.
이번 문서 갱신에서는 브라우저/WebGL 수동 검수와 600회 벤치마크를 다시 실행하지 않았으며,
위 실험 수치는 같은 날 앞선 P10B 실행 결과입니다.

2026-10-12 P10C 검수: `uv run pytest -q` **212개** 통과, `uv run ruff check .`와 `npm run build` 통과,
`changes.json`의 1,008회 계약 검사·대조 분석 통과. 프런트엔드 코드는 변경하지 않아 editor/viewer/lint는
이번에 재실행하지 않았습니다. 위 2026-10-11 결과는 당시 기록입니다. 브라우저 수동 시연은 남아 있습니다.

2026-10-12 P07b 보완 후 최신 검수: Python **214개**, editor **28개**, viewer **11개** 테스트 통과,
Ruff·frontend lint·build 통과. 프런트 편집 함수로 생성한 JSON의 저장/재로드·A*/Dijkstra·독립 검증까지 확인했습니다.
브라우저 드래그/WebGL 수동 시연은 수행하지 않았습니다. P10C 실험 수치는 당시 기록을 유지합니다.

P07i 최신 검수: Python **226**, editor **41**, viewer **12**, Ruff/lint/build 통과.
실제 headless Edge 전체 **113개**, 보기/삭제 집중 **23개** 흐름 통과, 미처리 오류 0건.
메인 RAF를 차단한 별도 2D/3D 측정·그리기, 카메라 중심/전체 건물 fitting,
메인에서 계속·좁은 창의 도면/속성 분리·삭제 취소/실패/개정 충돌/현재 문서 보존/재저장을 확인했습니다.
전체 기록은 `data/ui_checks/p07i-1791870334370/`, 집중 기록은 `data/ui_checks/p07i-1791870302364/`입니다(Git 제외).
`node scripts/check_editor_ui.mjs --views-only`로 보기/삭제만 빠르게 검수할 수 있습니다.

P07h 검수 기록: Python **219**, editor **40**, viewer **11**, Ruff/lint/build 통과.
실제 headless Edge **90개** 흐름 통과, 미처리 오류 0건. 기존 창 관리 74개와 합성 플랜트 대표 흐름 16개를 함께 검수했습니다.
세 배관 계산·양 층 표시·규칙 변경/미승인 차단/재승인·L2 탱크와 Port 드래그·별도 2D/3D 선택과 계산 공유·저장 재로드를 확인했습니다.
캡처/결과: `data/ui_checks/p07h-1791865040192/` (Git 제외). `plant-reports.json`에는 실제 UI 계산 응답 7건이 있습니다.
물리 듀얼 모니터 이동, 경유점·규칙 생성의 플랜트 브라우저 회귀는 미실시입니다.

P07f 검수 기록: Python **219**, editor **37**, viewer **11**, Ruff/lint/build 통과.
실제 브라우저 **42개** 흐름 통과, 미처리 오류 0건. `test1 → test11` 이름 변경/목록 반영,
새로고침 후 목록 불러오기, 기기·배관 JSON 재로드, 예제에 기기 추가 후 저장/재로드·원본 유지·저장 상태를 확인했습니다.
캡처/결과: `data/ui_checks/p07f-1791801967301/` (Git 제외).
P07e 검수 기록: Python **216**, editor **36**, viewer **11**, Ruff/lint/build 통과.
실제 브라우저 **34개** 흐름 통과, 미처리 오류 0건. 한글 이름 생성·변경·저장/로드, 가까운 기기 배치의 입력 오류,
막힌 연결점 선택, 기기 이동 후 **저장하지 않은 상태의 계산·독립 검증 성공**을 확인했습니다.
캡처/결과: `data/ui_checks/p07e-1791800792964/` (Git 제외).
P07d 검수 기록: Python **214**, editor **34**, viewer **11** 테스트와 Ruff/lint/build 통과.
실제 Edge에서 **28개** 흐름(탭·JSON 하위 탭·설정 모달·이동 가능한 보조 보기·3D 속성 수정·3D 계산/2D 결과 공유·연결점 추가/삭제·API 계산/저장·Undo·390 px 넘침)을 통과했습니다.
검수 스크립트는 `node scripts/check_editor_ui.mjs`이고, 두 개발 서버가 먼저 실행되어 있어야 합니다.
결과 JSON과 스크린샷은 `data/ui_checks/p07d-1791799875642/`에 있습니다(Git 제외).
P07c 검수 기록: Python **214**, editor **32**, viewer **11** 테스트와 Ruff/lint/build 통과.
`node scripts/check_editor_ui.mjs`로 기기 배치·실제 캔버스 연결·FastAPI 계산·속성 이동·삭제 보호·Undo·3D 열기·모바일을
검수했고 브라우저 미처리 오류는 0건이었습니다. 캡처/결과는 `data/ui_checks/`에 보존합니다.
플랜트의 양 층·기존 규칙 수정·기기 드래그·저장은 P07h 대표 흐름에서 확인했습니다.
경유점·규칙 생성과 모든 편집 조합의 브라우저 회귀는 추가로 필요합니다.

API 테스트는 정상 응답, 허용/비허용 origin과 preflight, 잘못된 HTTP 메서드,
존재하지 않는 URL, JSON 참조·단위·치수·필수 출처와 버전을 검사합니다.
현재 설치된 Starlette는 TestClient의 httpx
사용에 대해 폐기 예정 경고를 출력합니다. 테스트 실패는 아니며 경고를 숨기지 않습니다.

수동 확인:

기본은 빈 건물입니다. 아래 기존 플랜트 확인은 프로젝트 탭에서 합성 플랜트 예제를 먼저 불러옵니다.
`소형 데모`로 표시한 항목에서는 예제를 전환하고,
PIPE-102·L2 등 플랜트 객체를 사용하는 항목에서는 플랜트 예제로 다시 전환하세요.
기술 ID는 속성창의 상세 정보나 프로젝트의 JSON 편집 탭에서 확인합니다. 저장·3D·결과는 작업 탭으로 전환합니다.

1. 두 서버를 실행하고 `http://127.0.0.1:5173`에서 `백엔드 연결됨`과 빈 건물을 확인합니다. 프로젝트 탭에서 플랜트 예제를 불러옵니다.
2. 2D 도면 위 `경로 계산`을 눌러 계산 완료·길이·검증 위반 요약을 확인하고 계산 결과 탭에서 비용·좌표 표를 확인합니다.
3. 프로젝트 탭에서 `서버에 저장` 후 저장된 프로젝트 목록의 해당 이름에서 `불러오기`를 눌러 JSON 편집 탭의 내용과 저장 개정 번호를 확인합니다.
4. JSON 편집 탭에서 `from_port_id`를 없는 ID로 바꿔 검증 오류의 필드 위치를 확인합니다.
5. 규칙 `status`를 `draft`로 바꾸고 실행해 `UNAPPROVED_RULE` 표시를 확인합니다.
6. (P07, 소형 데모 선택) `경로 계산 실행` 후 도면에 파란 경로가 보이는지 확인합니다. `WALL-01`을 드래그해 위쪽
   또는 다른 위치로 옮기고, 속성 패널 좌표와 하단 커서 좌표(m)가 일치하는지 확인한 뒤 다시 실행해
   경로가 바뀌는 것을 확인합니다. `실행 취소`로 원위치, `다시 실행`으로 이동 상태를 복원합니다.
7. (P07c) 속성 패널에서 크기를 0/음수로 넣거나 건물 밖 위치를 넣으면 JSON에 반영되지 않는지 확인합니다.
8. (P07, 소형 데모) `벽 추가`로 드래그해 벽을 그리고, Delete 키로 지웁니다. `ZONE-A`를 삭제하려 하면 RULE-001 때문에 거부됩니다.
9. (P07) `건물·격자 설정`을 열어 격자 0.1을 입력하면 칸 수 한도 초과 안내가 나오는지, X 최대를 80으로 적용하면 도면이 넓어지는지 확인합니다.
   소형 데모에서는 X 최대 8로 줄이면 PORT-B 때문에 거부됩니다.
10. (P07c) 배관 2(PIPE-102)를 선택해 오른쪽 `추가 여유 두께`의 마진을 100 mm로 적용하면 JSON의 `clearance_margin_m=0.1`인지 확인합니다.
    계산 외곽 지름은 394.3 mm이며 마진은 실제 몸체 두께로 그리지 않습니다.
11. (P07, 소형 데모) `제약 규칙 · 승인 관리`를 열어 RULE-001 상태를 `draft`로 적용하면 도면 경고와 구역 점선, 실행 시 `UNAPPROVED_RULE`을 확인합니다.
12. (P08/P07d) `3D 보기` 탭 또는 `3D 함께 보기`를 열고 경로 계산 후 파란 원통 경로가 연결점 사이에 나타나는지, 경로 좌표 표와 같은 꺾임점을 지나는지 확인합니다.
13. (P08) `평면도`를 누르고 L2 케이블트레이(`ZONE-CABLE-L2`)를 클릭하면 2D 층이 L2로 바뀌고 속성 패널에 같은 ID가 나오는지 확인합니다.
14. (P08) 속성 패널에서 그 구역의 Y 위치 30, 깊이 1로 적용하면 3D에서도 북쪽으로 이동하고 카메라는 그대로인지 확인합니다.
15. (P08) `규칙 대상 강조`에서 `RULE-ELEC-KEEPOUT`을 고르면 `ZONE-ELEC` 외곽선이 자홍색으로 바뀌는지 확인합니다.
16. (P08b) 도면 위 배관 2(PIPE-102)를 선택하면 P-101-D가 초록 `S`, HX-201-IN이 보라 `E`로 2D·3D에 표시되는지 확인합니다.
17. (P08b) 배관 속성의 `+ 경유점 추가 · 도면 클릭` → 도면 클릭 → X 30.25, Y 30.75, Z 4.75, 통과 방향 X → `수정 적용` →
    `경로 계산`. 경로가 문이 아닌 WALL-A 슬리브를 X 방향으로 곧게 지나고 독립 검증이 VALID인지 확인합니다.
18. (P08b) 경유점 Y를 25.25로 바꾸면(벽 내부) `WAYPOINT_BLOCKED`가, 경유점을 두 개 만들어 ◀ ▶로 순서를 바꾸면
    경로가 바뀐 순서대로 지나가는지 확인합니다.
19. PIPE-103(층간)을 계산하면 L1 층 버튼과 L2 버튼 모두에 경로 점이, L1 도면의 수직 구간 위치에 `↑ L2`가, L2에서는 `↓ L1`이
    나오는지, 3D 원점에 X·Y·Z 라벨이 모두 보이는지 확인합니다.
20. 배관 2(PIPE-102)를 고르고 `제약 규칙 · 승인 관리` → `+ 규칙 추가` → 최소 이격 1.5 m, 대상 WALL-A2, 출처 입력 → `초안 규칙 만들기`. 요약에 실행 차단 안내가 나오고,
    승인으로 바꿔 검토자 이름을 입력하고 `현재 내용 승인·적용` 후 계산하면 결과의 적용 규칙에 새 규칙과 RULE-ELEC-KEEPOUT이 함께 나오는지 확인합니다.

health는 API 프로세스 응답만 확인하며 solver나 데이터 저장소의 준비 상태를
보장하지 않습니다. 경로·규칙 검증은 별도 결과에 표시됩니다.
