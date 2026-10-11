# plan_route

공개 자료와 합성 3D 건물 모델을 사용하는 배관 경로 최적화 연구 도구입니다.
실제 원전 배관 설계 또는 인허가 적합성 판단에 사용하지 않습니다.

현재 구현 범위는 **P00~P07: API 연결, EngineeringProject 스키마, 3D 격자·탐색·규칙 컴파일·독립 검증·프로젝트 저장·결과 화면·층별 2D 도면 편집기**입니다.
3D 시각화는 후속 Phase(P08)에서 구현합니다.

## 개발 환경

기존 uv/Vite 프로젝트를 유지합니다. `uv init`이나 `npm create vite`를 다시 실행하지 않습니다.
확인한 환경: Python 3.12.14, uv 0.12.7, Node.js 22.23.2, React 19.3.0, Vite 8.3.4.
정확한 의존성 버전은 `uv.lock`과 `frontend/package-lock.json`을 따릅니다.

새 환경에서 의존성을 복원하려면 루트에서 `uv sync --locked`,
`frontend/`에서 `npm ci`를 실행합니다.

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

## 프로젝트 JSON과 입력 검증

`src/plan_route/fixtures/demo_project.json`이 유일한 합성 예제 JSON입니다.
좌표·치수는 m, 수직축은 z이며 `schema_version`은 현재 `1.0.0`만 지원합니다.
규칙 출처에는 `synthetic_assumption`을 명시합니다. 이 수치는 실제 설계기준이 아닙니다.
`draft`·`needs_review`·`rejected` 규칙도 기록할 수 있지만 라우팅 실행 대상은 아닙니다.
P01은 규칙 실행 기능을 제공하지 않습니다.

유효한 JSON 확인은 API 문서에서 `POST /api/projects/validate`의 예제 입력으로
할 수 있습니다. PowerShell에서는 다음처럼 실행합니다.

```powershell
$projectJson = Get-Content -Raw -Encoding UTF8 src/plan_route/fixtures/demo_project.json
Invoke-RestMethod -Uri http://127.0.0.1:8000/api/projects/validate -Method Post -ContentType 'application/json' -Body $projectJson
```

정상 입력은 `{"valid":true,"project_id":"SYNTH-DEMO-001","schema_version":"1.0.0"}`을
반환합니다. 잘못된 입력은 HTTP 422와 `error_code: INVALID_INPUT`, `details` 배열로
필드 위치와 오류를 반환합니다. 프로젝트 저장 API는 P06 범위입니다.

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

장애물 AABB는 배관 외경 반경과 보온 두께의 합으로 팽창합니다. 셀이 확장된
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
배관 외경 절반과 보온 두께만큼 확장합니다. 최소 이격은 여기에 `distance_m`을 더합니다.
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

프런트 화면(`http://127.0.0.1:5173`)은 백엔드에 연결되면 합성 데모 JSON을 자동으로
불러옵니다. `JSON 검증` → `경로 계산 실행`을 누르면 경로 길이·방향 전환·비용·위반
건수와 세계좌표(m) 목록이 보입니다. `서버에 저장` 후 같은 프로젝트 ID로 `불러오기`를
누르면 저장된 JSON과 개정 번호를 확인할 수 있습니다. JSON을 직접 수정했으면
다시 검증·실행하세요. 입력 필드 오류와 `NO_PATH`, `SEARCH_LIMIT_REACHED`,
`UNAPPROVED_RULE`, `RULE_CONFLICT`, `INVALID_ROUTE`는 서로 다른 메시지로 표시합니다.

## 층별 2D 도면 편집기 (P07)

React Konva(`konva`, `react-konva`)로 층별 배치도를 그립니다. 도메인 정본은 계속
EngineeringProject JSON이며 Konva `stage.toJSON()`이나 화면 픽셀을 저장하지 않습니다.
화면 px ↔ 세계좌표 m 변환은 `frontend/src/editor/coordinates.ts`에만 있으며
(평면 X 오른쪽, Y 위쪽, 화면 y는 반전), 편집 결과는 `model.ts`의 순수 함수가
AABB `min_m`/`max_m`와 Port `position_m`으로 되돌려 기록합니다.

- 도구: 선택, 화면 이동(pan), 벽 추가, Zone 추가, Port 추가, 휠/버튼 확대·축소, 화면 맞춤.
- 벽/Zone 추가: 도면에서 드래그해 직사각형을 그립니다(두 모서리 모두 스냅, z는 선택 층 범위).
  클릭만 하면 0.5 m 기본 정사각형이 생깁니다. 추가 도구에서는 기존 객체 위에도 그릴 수 있습니다.
- Port 추가: 클릭한 위치에 생성하며, 높이는 같은 층의 기존 Port 높이(없으면 바닥 + 1 m, 층 높이의 절반 이하)를 씁니다.
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
  `kind: slab` 장애물(층 바닥판)은 점선 외곽선으로만 그리고 내부 클릭은 아래 객체로 전달합니다.
- 스냅: 격자 간격과 같고 좌표계 원점 기준입니다. 끌 수 있습니다.
- 선택 객체를 드래그해 이동하고 모서리 점으로 크기를 바꿉니다. 속성 패널에서 m 좌표를 직접 입력할 수 있습니다.
- 잘못된 값(비숫자, 0.1 m 미만 변, 건물 경계 밖, 없는 ID, 거리 없는 MIN_CLEARANCE)은 반영하지 않고
  도면 위에 `반영되지 않음` 오류를 띄우며, 입력칸은 저장된 값으로 되돌립니다.
- Port를 선택한 배관의 시작/도착 Port로 지정할 수 있습니다.
- 규칙 타입·대상·거리·승인 상태를 편집하고, 선택한 형상에 출처를 갖춘 새 규칙을 `draft`로 만들 수 있습니다.
  미승인 규칙이 걸린 배관에는 실행 불가 안내가 나오며 서버는 `UNAPPROVED_RULE`을 반환합니다.
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

## 폴더 구조

```text
src/plan_route/main.py      FastAPI 앱과 로컬 CORS
src/plan_route/api/health.py GET /api/health 및 응답 타입
src/plan_route/api/projects.py 합성 예제 및 JSON 검증 API
src/plan_route/api/constraints.py 규칙 컴파일 API
src/plan_route/api/routing.py 경로 탐색·검증 API
src/plan_route/models/      EngineeringProject 및 참조 검증
src/plan_route/fixtures/    합성 예제 JSON 정본
src/plan_route/services/    기하·격자 및 후속 알고리즘 패키지
src/plan_route/services/geometry.py 연속 AABB 연산·배관 반경
src/plan_route/services/voxel_grid.py 좌표 변환·격자 마스크
src/plan_route/services/astar.py 방향 인지형 A*·Dijkstra
src/plan_route/services/compiler.py 승인 규칙 차단 마스크·출처 추적
src/plan_route/services/path_validator.py 독립 연속 기하 검증
src/plan_route/services/routing.py 컴파일·탐색·검증 실행
src/plan_route/services/report_store.py 결과 보고서 원자적 저장
src/plan_route/services/project_store.py 프로젝트 개정·해시·원자적 저장
src/plan_route/models/results.py 탐색 상태·비용 분해 결과
frontend/src/api/client.ts  프로젝트·라우팅 API 타입 및 호출
frontend/src/App.tsx        데모·JSON 검증·저장·경로 결과 화면·편집 기록
frontend/src/editor/coordinates.ts 화면 px ↔ 세계좌표 m 변환·스냅·줌
frontend/src/editor/model.ts 형상·Port·규칙 편집 순수 함수와 입력 검사
frontend/src/editor/history.ts JSON 스냅샷 Undo/Redo
frontend/src/editor/PlanEditor.tsx React Konva 층별 도면
frontend/src/editor/EditorInspector.tsx 좌표·규칙 속성 패널
frontend/src/editor/DomainPanel.tsx 탐색 도메인·격자, 배관 단면(외경·보온재·마진) 카드
src/plan_route/fixtures/plant_starter_project.json 합성 플랜트 예제(UI 시작값)
frontend/src/editor/editor.test.mjs 좌표·편집·기록 단위 테스트(node --test)
tests/test_health.py       HTTP 응답 및 CORS 테스트
tests/test_schemas.py      스키마·참조·422 응답 테스트
tests/test_voxel_grid.py   경계·충돌·Zone 분리 테스트
tests/test_astar.py        최적 비용·실패 상태·방향 테스트
tests/test_constraint_compiler.py 규칙 적용·오류·API 테스트
tests/test_path_validator.py 독립 검증·라우팅 API 테스트
tests/test_project_store.py 저장·재로드·개정·경로침입 방지 테스트
tests/test_p07_editor_scenario.py 벽 이동 후 경로 변화 시나리오
tests/test_plant_starter.py 플랜트 예제 라우팅·배관 마진 반영 테스트
scripts/export_schema.py   JSON Schema 생성
docs/schema/               생성된 JSON Schema
docs/decisions/            단계별 설계 결정
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
```

`test:editor`는 Node.js의 TypeScript 타입 제거 실행(Node 22.18+ 기본)과 `node --test`를 사용하므로
별도 테스트 의존성이 없습니다.

API 테스트는 정상 응답, 허용/비허용 origin과 preflight, 잘못된 HTTP 메서드,
존재하지 않는 URL, JSON 참조·단위·치수·필수 출처와 버전을 검사합니다.
현재 설치된 Starlette는 TestClient의 httpx
사용에 대해 폐기 예정 경고를 출력합니다. 테스트 실패는 아니며 경고를 숨기지 않습니다.

수동 확인:

1. 두 서버를 실행하고 `http://127.0.0.1:5173`에서 `백엔드 연결됨`과 합성 데모 JSON을 확인합니다.
2. `JSON 검증`, `경로 계산 실행`을 순서대로 눌러 `SUCCESS`, 길이·비용·좌표 표를 확인합니다.
3. `서버에 저장` 후 같은 ID로 `불러오기`를 눌러 JSON과 개정 번호를 확인합니다.
4. JSON의 `from_port_id`를 없는 ID로 바꿔 검증 오류의 필드 위치를 확인합니다.
5. 규칙 `status`를 `draft`로 바꾸고 실행해 `UNAPPROVED_RULE` 표시를 확인합니다.
6. (P07) `경로 계산 실행` 후 도면에 파란 경로가 보이는지 확인합니다. `WALL-01`을 드래그해 위쪽
   또는 다른 위치로 옮기고, 속성 패널 좌표와 하단 커서 좌표(m)가 일치하는지 확인한 뒤 다시 실행해
   경로가 바뀌는 것을 확인합니다. `실행 취소`로 원위치, `다시 실행`으로 이동 상태를 복원합니다.
7. (P07) 속성 패널에 X 최소를 X 최대보다 크게 넣거나 건물 밖 좌표를 넣으면 반영되지 않고 오류가 표시되는지 확인합니다.
8. (P07) `벽 추가`로 드래그해 벽을 그리고, Delete 키로 지웁니다. `ZONE-A`를 삭제하려 하면 RULE-001 때문에 거부됩니다.
9. (P07) `탐색 도메인`을 펼쳐 격자 0.1을 입력하면 칸 수 한도 초과 안내가 나오는지, X 최대를 80으로 적용하면 도면이 넓어지는지 확인합니다.
   소형 데모에서는 X 최대 8로 줄이면 PORT-B 때문에 거부됩니다.
10. (P07) `배관 단면`에서 PIPE-102 마진을 100 mm로 적용하면 외곽 지름 394.3 mm와 단면 그림이 바뀌는지 확인합니다.
11. (P07) 규칙 패널에서 `RULE-001` 승인 상태를 `draft`로 적용하면 도면 경고와 Zone 점선, 실행 시 `UNAPPROVED_RULE`을 확인합니다.

health는 API 프로세스 응답만 확인하며 solver나 데이터 저장소의 준비 상태를
보장하지 않습니다. 경로·규칙 검증은 별도 결과에 표시됩니다.
