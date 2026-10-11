# AGENTS.md — plan_route Codex 작업 규칙

> 프로젝트 루트에 `AGENTS.md` 이름으로 저장하고, `ROADMAP.md`와 같이 사용한다.

## 프로젝트 목적

공개 자료와 **합성 3D 건물 모델만 사용**하여, 설계 제약조건을 구조화된 데이터로 관리하고 결정론적 3D 배관 경로 최적화 및 독립 기하 검증을 수행하는 연구용 도구를 만든다. 실제 원전 배관 설계 또는 인허가 적합성 판단에 사용하지 않는다.

## 최초 작업 지침

1. 반드시 루트의 `ROADMAP.md`를 읽고, 요청받은 **하나의 Phase**만 작업한다.
2. `uv init plan_route --python 3.12`, `uv sync`, FastAPI/Pydantic 설치, Vite React-TS `frontend/`는 **이미 완료**되었다고 가정한다. 실제 폴더 구조를 먼저 확인한다.
3. 사용자 허락 없이 프로젝트를 재초기화하거나 `pyproject.toml`/`package.json`을 통째로 덮어쓰지 않는다.
4. MVP 순서는 **Schema → Geometry → A* → Constraint Compiler → Validator → Web UI → 3D → 벤치마크**.
5. React Flow/LLM/온톨로지/RL/실제 규제기준 자동검토를 초기에 구현하지 않는다. 명시한 Phase일 때만 추가한다.

## 기술·구조 원칙

- Python 3.12, uv, FastAPI, Pydantic v2, pytest, ruff.
- React + TypeScript + Vite, React Konva(2D), React Three Fiber(3D): 해당 Phase에서만 추가.
- 도메인 데이터의 유일한 정본은 **EngineeringProject JSON**. UI 프레임워크 내부 JSON이나 픽셀 좌표가 아니다.
- 전체 세계좌표 단위는 **m**, 수직 `z`, 방위축 일관성 유지. UI 픽셀과 3D 렌더 좌표 변환은 별도 함수.
- `src/plan_route/models`는 계약, `src/plan_route/services`는 알고리즘, `src/plan_route/api`는 I/O.
- Python 백엔드는 uv의 `src/plan_route/` 패키지에 통일한다. 루트에 별도 백엔드 패키지를 만들지 않는다.
- API 실행은 `uv run uvicorn plan_route.main:app --reload --host 127.0.0.1 --port 8000`. import는 `plan_route.*`를 사용하고 임의의 `sys.path`/`PYTHONPATH` 조작 없이 uv가 설치한 패키지를 사용한다.
- Hard Constraint 위반은 높은 벌점으로만 처리하지 말고 그래프에서 제외/명시적 실패.
- A* 상태에는 **진입 방향**을 포함해 bend를 계산한다.
- Solver 내부 마스크만 재사용하는 검증기를 만들지 말고 원본 연속 기하에 기반한 별도 Validator를 만든다.
- 규칙 원문/출처/개정판/대상 객체/승인 상태를 추적. `status != approved`는 실행에 적용 금지.
- LLM은 자연어 → 후보 규칙 도출용 선택 기능. 출력은 신뢰할 수 없는 입력이고 승인 전 실행 금지.
- 도메인 모형·수치·규제 요구사항을 임의로 실재 원자력 설계기준이라고 주장하지 않는다.

## 코드 변경 및 검증

- 새 기능은 **먼저 작동 가능한 최소 구현**과 테스트를 만든다.
- 새 의존성 도입 전 필요성 확인. Python은 `uv add`, TS는 `npm install`; lockfile 유지.
- API 응답 타입을 명시하고 실패 상태(`NO_PATH`, `SEARCH_LIMIT_REACHED`, `INVALID_INPUT` 등)를 혼동하지 않는다.
- 정상 입력뿐 아니라 경계, 잘못된 참조 ID, 미승인 규칙, 완전 막힘, 검색한도 초과 등의 테스트를 작성.
- 필요시 `docs/decisions/`에 중요한 설계 선택을 기록.
- 실행 가능한 명령과 함께 **직접 테스트 실행한 결과**만 보고한다.

## 필수 검수 명령

```bash
# project root
uv run pytest -q
uv run ruff check .

# frontend
cd frontend
npm run build
```

실제 환경에 없거나 해당 Phase에서 불필요한 검사는 그 이유를 명시한다. 테스트를 하지 않았는데 통과했다고 쓰지 않는다.

## 보고 방식

```text
[Phase] P00 등
[Changed files] 파일 경로
[Implemented] 구현 사항
[Tests] 수행한 명령 및 결과
[Manual check] 재현 절차
[Known limitations] 남은 한계
[Next] 다음 Phase 안내(자동 진행 금지)
```

## 금지 사항

- ROADMAP 전체 일괄 구현 및 무분별한 대규모 리팩터링.
- 실제 발전소의 민감한 도면이나 기밀 규정 자료를 코드/데이터셋에 추가.
- 가상 이격거리/Zone 정책을 실제 규정 값으로 표현.
- `README`, `ROADMAP`, `AGENTS`를 승인 없이 삭제하거나 교체.
- LLM이 제안한 Hard Constraint를 사람 승인 없이 최적화에 적용.
- 좌표를 화면 픽셀로 저장하거나 2D/3D마다 별도 의미 JSON 사용.
