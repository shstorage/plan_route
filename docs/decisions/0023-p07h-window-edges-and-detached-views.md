# ADR 0023 — P07h 보조 창의 전체 영역·테두리 조절·별도 브라우저 창

날짜: 2026-10-13. 사용자 요청의 창 관리 개선 하나로 수행한다.
P07g 저장 보호와 기존 P10 문서 작업은 유지한다. backend·solver·Validator·저장 계약은 바꾸지 않는다.

## 문제와 결정

웹 페이지 내부 dialog의 위치/크기는 브라우저 viewport로 제한되므로 다른 모니터로 옮길 수 없다.
P07g의 8 px 여백 보정과 모서리 손잡이만으로는 사용자가 기대하는 일반 창 조절에 부족했다.

- 내부 창의 상단·최대화 여백을 해제한다. 제목줄을 y=0까지 이동할 수 있고 최대화는
  left/top=0, width/height=전체 viewport를 사용한다. 기본 열림 위치는 초기 배치일 뿐 상단 이동 한도가 아니다.
- 네 변과 네 모서리에 pointer capture 기반 resize 영역을 추가한다.
  위/아래는 `ns-resize`, 좌/우는 `ew-resize`, 모서리는 각 대각 방향 cursor를 표시한다.
  반대편 변을 고정하고 끄는 변만 바꾸며 최소 크기/viewport 경계에서 멈춘다.
  기존 ◢ 손잡이와 방향키/Shift 조절도 유지한다.
- 내부 창의 “새 창으로 열기”와 작업 탭 옆 “2D/3D 새 창”으로 실제 브라우저 창을 연다.
  사용자는 OS 제목줄로 다른 모니터에 옮기고 브라우저 창 자체의 최대화·테두리 크기 조절을 사용한다.
  2D와 3D를 각각 하나씩 동시에 열 수 있으며 같은 보기 버튼을 다시 누르면 열린 창에 포커스를 준다.

`window.open`은 실제 클릭 처리에서 호출한다. 브라우저가 차단해 null을 반환하면 안내하고 기존 내부 보기를 유지한다.
팝업/탭 형태와 OS 창 테두리·초기 위치의 최종 결정은 브라우저에 따른다.
모니터 접근 권한이나 자동 OS 창 이동을 요구하지 않는다.
근거: [MDN Window.open](https://developer.mozilla.org/en-US/docs/Web/API/Window/open).

## 단일 데이터와 창 생명주기

새 창은 별도 프로젝트를 로드하지 않고 부모 React 트리의 portal로 같은 EngineeringProject·선택·규칙·결과를 표시한다.
기기 이동은 parent의 기존 commit 함수에 연결하며 몸체/Port JSON이 함께 갱신되고 기존 계산 결과를 무효화한다.
계산도 기존 API와 작업 상태를 공유한다. 메인 작업 탭을 바꿔도 별도 창은 유지한다.

별도 창에는 본문 뷰와 간략한 “메인 창 보기 / 보조 창 닫기” 헤더만 둔다.
parent의 CSS를 복사하고 lazy 3D CSS/개발 HMR의 style 변경을 관찰한다.
window context를 통해 2D 키보드와 설정 dialog를 실제 소속 문서로 연결한다.
탭 키보드 포커스는 currentTarget.ownerDocument 기준이고 3D cursor도 pointer event의 소속 문서를 사용한다.
설정 popup/Escape가 다른 창으로 전달되지 않도록 한다.

메인 창의 새 프로젝트/미저장 확인 중에는 별도 창 본문을 inert로 두며 2D 전역 키도 편집하지 않는다.
별도 창만 닫으면 메인 작업은 그대로 남는다. 메인 페이지가 실제로 떠나거나 새로고침되면 별도 창을 정리한다.
메인의 미저장 beforeunload 보호는 유지하므로 새로고침을 취소하면 문서와 별도 창도 유지된다.
별도 창을 새로고침하면 그 보기는 닫히며 메인에서 다시 열 수 있다.

개발 StrictMode의 effect setup/cleanup 재실행에서 새 창이 바로 닫히는 문제를 발견했다.
cleanup의 close를 다음 task로 미루고 같은 mount의 setup이 재실행된 경우 취소하도록 generation을 연결했다.
실제 unmount에서는 listener·timer·style observer·창을 정리한다.

## 직접 검수

| 명령 | 결과 |
|---|---|
| `uv run pytest -q` | 219 passed, 28.68 s; 기존 Starlette/httpx 경고 1건 |
| `uv run ruff check .` | 통과 |
| frontend `npm run test:editor` | 40 passed; 8방향 반대 변 고정·최소/경계 검사 추가 |
| frontend `npm run test:viewer` | 11 passed |
| frontend `npm run lint` | 통과, 추가 경고 없음 |
| frontend `npm run build` | 통과; 기존 번들 크기 경고 |
| `node scripts/check_editor_ui.mjs` | 실제 Edge 74개 흐름 통과, 미처리 오류 0건 |

기존 57개에 다음 17개 검수 흐름을 추가했다: 8개 변/모서리의 cursor와 실제 pointer drag,
상단 y=0 이동, viewport 전체 최대화, 차단 시 내부 보기 유지, 별도 3D WebGL,
별도 창 크기와 canvas 높이, 별도 창 API 계산과 메인 결과 공유, 열린 창 재사용,
2D/3D 동시 별도 창, 선택 동기화, 별도 키보드, 설정 modal/Escape의 소속 문서,
Konva 실제 몸체/Port 드래그 반영, 수정 시 결과 무효화, 메인 확인 중 inert,
보조 창 닫기 후 작업 보존, 메인 새로고침 시 창 정리.

처음의 드래그 테스트는 원본 quarter-metre 몸체가 0.5 m 격자로 스냅되는 점을 무시하고
정확히 +1 m를 요구했다. 실제 이동을 확인한 뒤, 진행 방향/범위 및 모든 Port가 몸체와 같은 변위로
이동하는지를 대조하도록 검수를 수정했다. 이 과정에서 생산 기하·스냅 로직은 바꾸지 않았다.
전체 흐름을 다시 실행해 통과했다. 2D/3D 별도 문서와 전체 크기 내부 창의 스크린샷을 직접 확인했다.

검수 기록: `data/ui_checks/p07h-1791858938748/` (Git 제외).
재현: API :8000, Vite :5173 실행 후 프로젝트 루트에서 `node scripts/check_editor_ui.mjs`.
스크립트는 테스트용 독립 프로젝트를 만들며 기존 사용자 저장 파일을 수정하지 않는다.

## 수동 확인과 한계

1. 보조 보기 제목줄을 화면 맨 위로 옮기고 4변/4모서리에서 방향 cursor·드래그를 확인한다.
2. “최대화”로 브라우저 내용 영역 전체를 사용하고 “원래 크기”로 복원한다.
3. “새 창으로 열기”를 눌러 OS 창 제목줄을 두 번째 모니터로 옮기고 그 모니터에서 최대화한다.
4. 별도 2D에서 기기를 움직여 메인 JSON·Port와 별도 3D가 함께 바뀌는지 확인한다.
5. 보조 창을 닫아도 메인의 도면이 남고, 메인 페이지를 떠나면 별도 창이 닫히는지 확인한다.

검수는 headless Edge의 실제 별도 browsing context와 viewport 변경을 이용했다.
**물리 듀얼 모니터 사이 이동·OS 제목줄 최대화, 실제 Chrome GUI는 이번 자동 검수에서 실행하지 않았다.**
별도 창은 메인 세션의 보조 보기이므로 메인 창을 계속 열어 두어야 한다.
브라우저가 새 창을 차단하면 사이트 팝업 허용이 필요하고 일부 설정에서는 탭으로 열릴 수 있다.
페이지 내부 dialog 자체를 브라우저 밖으로 끌어내거나 임의 OS 프레임을 제어하는 기능은 제공하지 않는다.
새 의존성·다중 프로젝트 JSON·백엔드/라우팅 변경은 없다.

## 후속 검수 — 전체 합성 플랜트 대표 흐름

2026-10-13 `continue` 요청으로 P07h 검수를 이어 수행했다. 생산 코드는 변경하지 않았으며,
`scripts/check_editor_ui.mjs`에 60×40×12 m 플랜트 대표 흐름 16개를 추가해 기존 74개와 함께 실행했다.

| 명령 | 이번 직접 실행 결과 |
|---|---|
| `uv run pytest -q` | 219 passed, 32.20 s; 기존 Starlette/httpx 경고 1건 |
| `uv run ruff check .` | 통과 |
| frontend `npm run test:editor` | 40 passed |
| frontend `npm run test:viewer` | 11 passed |
| frontend `npm run lint` | 통과 |
| frontend `npm run build` | 통과; 기존 500 kB 번들 크기 경고 |
| `node scripts/check_editor_ui.mjs` | 실제 headless Edge 90개 흐름 통과, 미처리 오류 0건 |

Node 단위 테스트의 샌드박스 실행은 프로세스 생성 `EPERM`으로 실패하여, 승인된 명령으로
샌드박스 밖에서 재실행한 통과 결과를 위에 기록했다. 브라우저도 샌드박스 밖에서 실행했다.

추가 흐름은 원본 예제를 수정하지 않는 작업 복사본에서 수행한다. 다음 결과를 확인했다.

- PIPE-101/102/103 각각 SUCCESS·VALID, 검증 위반 0건. PIPE-103의 L1/L2 경로 표시와 층간 표지를 캡처했다.
- RULE-CABLE-CLEARANCE의 출처 SP-02 표시와 이격 0.5→0.75 m 변경을 확인했다.
  변경 후 기존 결과가 사라지고 `needs_review` 상태에서는 HTTP 409·UNAPPROVED_RULE,
  경로 점 0개·탐색 상태 0개로 차단됐다. 범위에 없는 PIPE-101은 계속 SUCCESS·VALID였다.
- 검수용 이름 `P07h UI regression`으로 현재 내용을 UI에서 재승인했다.
  개정·출처를 보존하고 승인자와 64자리 내용 해시가 연결됐으며 변경 이격 조건의 계산이 SUCCESS·VALID였다.
- 별도 2D의 L2 탱크 TK-301을 클릭해 메인 2D의 L2 전환과 별도 3D 선택 표시를 확인했다.
  실제 pointer drag로 X 방향 1 m 이동해 몸체와 Port가 같은 변위로 갱신되고 모든 보기의 기존 결과가 무효화됐다.
  별도 3D에서 재계산한 결과는 메인과 별도 2D에 공유됐다.
- 저장 목록에서 다시 불러온 JSON은 저장된 기하·Port·승인 정보와 같았으며 starter 원본은 유지됐다.

실제 UI 응답 기록:

| 순서 | 배관/조건 | HTTP | 경로 상태 | 독립 검증 | 길이 m | bend |
|---|---|---|---|---|---|---|
| 1 | PIPE-101 원본 조건 | 200 | SUCCESS | VALID | 9 | 2 |
| 2 | PIPE-102 원본 조건 | 200 | SUCCESS | VALID | 39 | 5 |
| 3 | PIPE-103 원본 조건 | 200 | SUCCESS | VALID | 38.5 | 6 |
| 4 | PIPE-103 미승인 이격 변경 | 409 | UNAPPROVED_RULE | 미실행 | — | — |
| 5 | PIPE-101 다른 배관의 미승인 조건 | 200 | SUCCESS | VALID | 9 | 2 |
| 6 | PIPE-103 이격 0.75 m 재승인 | 200 | SUCCESS | VALID | 38.5 | 6 |
| 7 | PIPE-103 재승인 후 L2 탱크 이동 | 200 | SUCCESS | VALID | 37.5 | 6 |

응답은 실제 UI의 fetch 결과를 복제해 기록했고 요청·결과를 mock하지 않았다.
스크립트 보완 중 작업 탭 전환 누락, drag가 click 선택까지 수행한다는 가정,
별도 3D에 속성 패널이 있다는 잘못된 selector로 검수가 중단됐다.
UI의 실제 탭·클릭·하단 선택 표시를 사용하도록 수정한 뒤 전체 90개를 재실행해 통과했다.
이 과정에서 생산 코드·탐색·기하·스냅을 수정하지 않았다.

최종 기록: `data/ui_checks/p07h-1791865040192/` (Git 제외).
`result.json`은 90개 흐름과 오류 목록, `plant-reports.json`은 위 7개 응답이다.
`19-plant-l1.png`, `20-plant-l2.png`, `21-plant-native-2d.png`, `22-plant-native-3d.png`를 보존했다.
별도 2D/3D의 최종 캡처를 직접 열어 층간 표지·선택·규칙 대상 강조·결과 공유를 확인했다.

재현: API :8000과 Vite :5173을 실행하고 프로젝트 루트에서 `node scripts/check_editor_ui.mjs`를 실행한다.
수동으로는 프로젝트 탭의 starter 예제를 불러와 세 배관을 각각 계산하고, 규칙 패널에서
위 이격 변경·재승인을 수행한 다음 별도 2D의 L2 탱크를 클릭/이동하고 별도 3D에서 재계산한다.
승인은 합성 검수용 복사본에만 기록된다.

이는 플랜트의 대표 흐름 검수다. 경유점·새 규칙 생성·모든 편집 조합의 브라우저 회귀,
물리 듀얼 모니터 이동·OS 창 조절·Chrome GUI·외부 사용성 평가는 미실시다.
P10 반복 실험은 다시 실행하지 않았고 방법의 정확성·비교 우위 주장도 추가하지 않는다.
