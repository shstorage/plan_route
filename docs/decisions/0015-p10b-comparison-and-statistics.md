# 0015 — P10B: 합성 비교 실험과 표본·통계의 범위

상태: 적용 / 2026-10-11. P10C 규칙 변경 대조는 구현하지 않는다.

## 고정 실험 설계

기본 설정은 `benchmarks/comparison.json`이며 실행 명령은 다음과 같다.

```bash
uv run python scripts/run_benchmark.py --config benchmarks/comparison.json
```

| 항목 | 정의 |
|---|---|
| 개발 장면 | 7개 family × 시드 11, 23, 42, 71, 101 = 35개 |
| 별도 평가 장면 | 같은 family × 시드 211, 307 = 14개 |
| family | sparse, dense, keep_out, clearance, ordered, closed_wall, narrow_gate |
| 물리 건물 | 12×10×4 m, 단일 배관; 진단은 별도 8×6×4 m |
| 격자 | 같은 물리 입력을 1.0 / 0.5 m로 계산 |
| 알고리즘 | A* / 같은 방향 상태 탐색의 h=0 Dijkstra |
| 반복 | 각 알고리즘 3회; 전체 49×2×2×3 = 588회 |
| 별도 진단 | HEURISTIC_LEGS 성공 및 자기 간섭 INVALID_ROUTE 2개 × 2×3 = 12회 |
| 총 실행 | 600회 |

시드는 장애물 위치·크기·개수/벽 높이·가상 이격을 바꾼다. P10A의 좌표 이동과 구분된다.
각 seed/family의 원본 공간 객체·포트·규칙·경유점은 두 해상도에서 동일하다.
해상도만 바꾼 것을 독립 공간 표본으로 세지 않는다.
실행 순서는 별도 고정 시드 20261011로 섞고 `execution_plan.json`에 보존한다.
실험은 순차 실행한다. 실행 중 다른 무거운 작업을 피하고 같은 환경에서 시간 반복을 해석한다.

평가 시드는 개발 시드와 겹치지 않는다. 평가 장면도 같은 생성기 family를 사용하므로
외부 건물/실무 데이터에 대한 일반화 검증을 대신하지 않는다. 이번 단계에서 솔버를 평가 결과에 맞춰 튜닝하지 않았다.
P09 Soft Zone·관통부 승인·다배관은 실험 범위에 없다. 규칙을 제거하는 ablation과 변경 영향은 P10C로 남긴다.

## 정답 근거와 격자 보수성

정상 장면은 미리 지정한 직교 중심선 witness를 보존한다. 장애물/규칙 AABB와의 축 평행 선분 거리를
별도 식으로 계산해 witness가 차단되지 않음을 확인한다. 솔버 출력이나 Validator의 VALID로 정답을 생성하지 않는다.
전체 y/z를 막는 벽만 `SEPARATING_WALL`로 표기한다.

narrow_gate는 폭 1.2 m 개구부와 외곽 반경 0.1 m 배관의 명시적인 직선 witness를 갖는다.
1 m whole-cell 팽창에서는 개구부에 들어갈 셀이 없지만 0.5 m에서는 셀이 들어간다.
따라서 연속공간 known-feasible 장면의 coarse-grid NO_PATH를 연속공간 불가능으로 바꾸지 않는다.
실제 관통 승인/공차 모델을 도입한 것이 아니라, AABB 개구부에서 격자 보수성을 시험한다.

`explicit_graph`는 원본 AABB와 셀 경계의 대수적 교차 판정을 별도로 구현한다.
생산 voxelizer/compiler/geometry 함수나 그 마스크를 가져오지 않는다. 컴파일 자유 셀과 비교해 차이를 검출한다.
작은 그래프(기본 600셀 이하)는 명시적 간선의 Bellman–Ford 완화로 방향·경유점 비용을 확인한다.
간선 길이는 해상도, 연결선 비용은 포트–셀 중심 길이로 반영한다.
격자 disconnect는 별도 도달 검사로 확인한다. 큰 연결 그래프는 `NOT_COMPUTED`로 남기며
비용 정답을 임의로 채우지 않는다. 이 경우 exact A*/Dijkstra의 같은 입력·목적함수 비용을 대조한다.
두 생산 알고리즘은 코드를 공유하므로 그 일치만으로 독립 검증이 완료되었다고 주장하지 않는다.

기준 계약은 `explicit_graph_relaxation_v2`, 범위는 `EXPLICIT_REGULAR_GRID_EXCLUDING_SELF_CLEARANCE`다.
자기 간섭 회피의 전체 최적성과 연속공간 최적성을 다루지 않는다.
2개 진단 사례는 알고리즘 성능 집계와 exact 비용 비교에서 제외하며 원본 결과에는 남긴다.

## 표본 단위와 통계

각 case/algorithm의 반복 시간은 중앙값으로 먼저 묶는다. 길이·bend·확장 수·최소/최대 시간·위반 수는
`scene_metrics.csv`에 저장하고, 상태/경로/비용이 반복 간 달라지면 재현 실패로 표시한다.
해상도와 개발/평가 집합을 나눠 통계를 산출한다.

- 성공률 분모는 해당 해상도의 **연속 witness가 있는 고유 장면**이다. 반복 수를 분모에 더하지 않는다.
- 시간·비용 대조는 같은 case에서 두 알고리즘 모두 SUCCESS/EXACT_GRID일 때만 수행한다.
  한쪽 실패나 휴리스틱 결과를 비용 우위로 계산하지 않는다.
- 시간 차이는 `Dijkstra 장면 중앙값 − A* 장면 중앙값`이다. 양수는 이 측정에서 A*가 더 짧았음을 뜻한다.
- 같은 시드의 여러 family는 상관될 수 있어 시드 단위 cluster bootstrap으로 묶는다.
  2,000회 재표본화의 2.5/97.5 백분위 구간과 n_scenes/n_seed_clusters를 함께 기록한다.
  시드 하나뿐인 설정에는 신뢰구간을 출력하지 않는다.

개발 시드 cluster는 5개, 평가 cluster는 2개로 적다. 구간은 합성 생성기 표본의 기술 통계이며
실제 건물 모집단에 대한 보장이나 강한 유의성 주장에 사용하지 않는다.
모든 시드에 같은 좁은 개구부 family를 하나씩 넣어 성공률 구간이 0 폭일 수 있다.
이는 고정 family 구성의 결과이며 미래 장면의 불확실성이 없다는 뜻이 아니다.
타이밍 비교에서 coarse/fine의 성공 장면 집합이 달라질 수 있으므로 두 집계만으로 해상도 효과를 단정하지 않는다.

Validator 평가는 별도 해석적 입력 8개(정상 4, 고의 역행/대각선/벽/금지구역 위반 4)의
false_valid/false_invalid와 분모를 기록한다. 일반적인 검출률/완전성 증명으로 확대하지 않는다.
RAM 정보는 환경 메타데이터이며 실행별 최대 메모리를 계측한 값이 아니다.

## 출력과 관찰 결과

기존 run별 원본 입력·결과·Git/실제 소스·환경 보존을 유지한다. 추가 산출물은 다음과 같다.

- `comparison_statistics.json`: 표본 수, 시드 cluster 구간, 상태/모드별 분포, 독립 기준 계산 적용 범위
- `scene_metrics.csv`, `comparison_report.md`: 논문 표 작성용 장면 집계와 같은 조건의 paired 비교
- `validator_trials.json`: 정답 레이블·주입 경로·검증 결과
- `figures/`: 서비스 시간, known-feasible 성공률, 길이/bend·탐색 분포의 PNG/PDF

Matplotlib은 연구 그림 출력에만 필요해 dev 의존성으로 추가하고 uv.lock을 갱신했다.
첫 전체 실행은 600회 모두 기대 계약과 일치했다. SUCCESS 468, NO_PATH 126,
진단 INVALID_ROUTE 6이었다. HEURISTIC_LEGS 6회는 exact 집계에서 제외했다.
성공 exact 쌍의 최대 목적함수 차이는 0이었다. witness 장면의 성공률은 두 집합/알고리즘 모두
1 m에서 25/30 또는 10/12(83.3%), 0.5 m에서 30/30 또는 12/12(100%)였다.
정상/손상 8개 검사에서는 오탐·누락이 없었다. 시간 숫자는 각 배치의 보고서에서 직접 읽는다.

직접 검수: Python 189개, Ruff, frontend build 통과. weighted edge/connector 기준 비용,
해상도별 셀 대조, 재현성, 시드 분리, cluster 통계, CSV와 실제 PNG/PDF 출력을 검사했다.
기존 Starlette TestClient 폐기 예정 경고와 Vite 큰 청크 경고는 남아 있다.

이는 지정한 합성 장면군의 관찰이며 A* 자체의 신규성이나 실무 우월성을 입증하지 않는다.
논문의 후보 차별성인 규칙 provenance·변경 영향의 정량 연결은 P10C 대조 실험이 필요하다.
