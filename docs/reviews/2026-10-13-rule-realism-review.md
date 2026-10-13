# 공간 제약 규칙의 현실성 검토

검토일: 2026-10-13. 범위: P10 논문 근거 검토. 알고리즘·예제·규칙 값은 변경하지 않았다.
공개 원문과 현재 소스/기본 예제를 비교한 결과이며 실제 원전의 설계 또는 인허가 적합성 평가가 아니다.

## 판단

진입 금지, 작업 공간 확보, 계통의 물리적 분리는 실제 설계 요구와 연결되는 제약 유형이다.
그러나 현재 기본 예제와 벤치마크의 수치·대상 선정은 합성 연구 가정이다.
특히 케이블 구역과 배관 사이 0.5 m를 실제 원전 법규의 보편적 최소거리로 뒷받침하는 근거는 이번 검토에서 확인하지 못했다.
따라서 현재 결과는 승인된 입력 제약에 대한 경로 생성·검증 결과이며 규제 적합성 입증으로 해석할 수 없다.

## 현재 입력 감사

| 항목 | 실제 저장 내용 | 평가 |
|---|---|---|
| 기본 demo RULE-001 | PIPE-101의 ZONE-A 진입 금지, synthetic_assumption / DEMO-SPEC | 합성 계약 검증용 |
| plant RULE-ELEC-KEEPOUT | 3개 배관 모두 전기실 전체 진입 금지, synthetic_assumption / SYNTH-PLANT-SPEC SP-01 | 전기설비 보호와 연결되는 개념이나 방 전체 금지는 자체 가정 |
| plant RULE-CABLE-CLEARANCE | PIPE-103과 L2 케이블 구역 간 0.5 m, synthetic_assumption / SP-02 | 파일에 illustrative value라고 명시된 가정값 |
| PIPE-102 자체 여유 | clearance_margin_m = 0.05 | 벽 전용 값이 아니라 모든 기하 검사에 더하는 배관 외피 여유 |
| P10 합성 벤치마크 | benchmark_cases/scenes/changes.py의 synthetic_assumption | 실제 법규 사례로 보고할 수 없음 |

근거 파일:
- [plant_starter_project.json](../../src/plan_route/fixtures/plant_starter_project.json)
- [demo_project.json](../../src/plan_route/fixtures/demo_project.json)
- [engineering.py](../../src/plan_route/models/engineering.py)
- [기존 여유값 설계 결정](../decisions/0010-p07-domain-pipe-margin-and-plant-starter.md)

## 확인한 공개 요구와 표현 가능성

### 1. 전기설비 전용 공간: KEEP_OUT에 적합한 후보

[미국 OSHA 29 CFR 1910.303(g)(1)(vii)(A)](https://www.osha.gov/laws-regs/regulations/standardnumber/1910/1910.303)는 특정 배전반·분전반·모터제어반 등의 실내 전용 공간과 외부 계통의 배치 제한을 규정한다.
기기 폭·깊이, 바닥에서 기기 상부 1.83 m 또는 구조 천장 중 낮은 높이까지의 공간 정의가 있으며, 격리·보호 조치 및 스프링클러 등에 관한 조건과 예외도 있다.
이는 전기실 전체나 모든 케이블 트레이 주변에 동일한 거리 규칙을 부여하는 근거가 아니다.

연구용 변환 후보: 보호 조치가 없는 사례와 적용 대상 배관을 명시하고, 전기기기의 전용 공간을 AABB Zone으로 만들어 KEEP_OUT을 적용한다.
이는 사람이 범위·조건·예외를 결정한 제한된 사례의 변환이다. 한국 원전 적용성 또는 OSHA 전체 준수는 별도 판단이다.

### 2. 벽·천장·바닥 작업 여유: MIN_CLEARANCE의 수치 후보

[UFGS 23 22 26.00 20, Steam System and Terminal Units](https://www.wbdg.org/FFC/DOD/UFGS/UFGS%2023%2022%2026.00%2020.pdf), 3.1.1, 인쇄 p.24/PDF p.24:
용접 작업을 위한 벽·천장·바닥 여유는 배관 호칭 크기 100 mm(4 in) 이하 150 mm, 그보다 큰 경우 250 mm로 제시한다.
모서리 작업 공간, 단열 시공 공간, 열팽창 등의 고려도 별도로 있다.
문서 버전 표시는 02/10, Change 1: 05/15이며 열람 PDF의 참고문헌 정렬 기준은 UMRL July 2026이다.
적용 범위는 건물 난방용 증기·응축수 계통이며 공정 증기 등은 범위에서 제외된다. 프로젝트에 맞게 편집하는 미국 공공시설 가이드 시방서다.

연구용 변환 후보: 해당 범위의 배관과 명시된 물리적 벽 객체 사이 MIN_CLEARANCE.
호칭 크기를 실제 외경과 혼동해서는 안 된다. 현재 Pipe에는 호칭경이 없다.
원문의 용접 작업 여유를 현재의 단열+추가 여유 외피 기준으로 옮길 때 측정 표면과 변환 가정을 명시해야 한다.
150/250 mm를 모든 원전 배관의 의무 값으로 가져오거나 문서 자체를 보편적 법규로 표현할 수 없다.

### 3. 안전계통 분리와 내부 위험: 요구는 실제, 거리 산정은 별도

[IAEA SSR-2/1 (Rev. 1), Requirement 21](https://nucleus.iaea.org/sites/nss-oui/Published%20Collections/m_daad92bb-3bb0-4445-a6ec-a287e55e9664/m_daad92bb-3bb0-4445-a6ec-a287e55e9664__65_0.Html)은 안전계통과 다중화 요소의 간섭 방지를 위한 물리적 분리 등의 수단을 요구한다.
Requirement 17/5.16은 내부 위험을, Requirement 29/5.45는 정비·검사를 가능하게 하는 배치를 다룬다.
여기서 특정 배관과 임의의 Zone 사이 보편적 0.5 m가 직접 도출되는 것은 아니다.
구역 또는 분리 거리의 구체화에는 적용 계통, 위험 분석, 차폐·방벽, 정비 공간 등의 설계 근거가 필요하다.

[미국 10 CFR Part 50 Appendix A, GDC 4](https://www.ecfr.gov/current/title-10/chapter-I/part-50/appendix-Appendix%20A%20to%20Part%2050)는 안전에 중요한 설비의 배관 휘두름·유체 방출 등 동적 영향 보호를 요구하며 승인된 분석에 따른 제외 조건도 규정한다.
현재 도구는 이러한 사고 영향 범위를 계산하지 않는다. 외부에서 결정한 단순 구역의 진입 금지/이격을 입력받는 기하 기능만 제공한다.

주의: [NRC RG 1.75의 명칭](https://www.nrc.gov/facilities-safety/fire-protection/related-information/regulatory-guides)은 Criteria for Independence of Electric Systems이다.
전기계통·케이블의 분리 수치를 배관 전체에 적용하는 수치 근거로 사용하지 않는다.

## 구현상의 간극

1. **배관 ID 지정과 계통 판별은 다르다.** scope.pipe_ids에 사람이 배관 목록을 지정할 수 있다. train_id는 저장되지만 compiler에서 적용 대상을 자동 선택하거나 train 간 분리를 계산하지 않는다. 계통 ID·유체·설계 온도/압력·안전등급·호칭경을 이용한 조건 판별은 없다.
2. **벽 충돌 방지와 작업 여유는 다르다.** 기존 물리 장애물/건물 경계 검사는 배관 외피 충돌을 막는다. 특정 벽에 대한 추가 이격은 해당 벽을 target_ids로 지정한 MIN_CLEARANCE로 표현할 수 있으나 기본 예제에는 없다. 건물 bounds 자체는 규칙 대상 ID가 아니므로 외벽 이격 사례에는 별도 벽 표현이 필요하다.
3. **배관끼리의 분리는 미구현이다.** MIN_CLEARANCE 대상은 obstacle 또는 Zone이며 다른 Pipe ID는 허용되지 않는다. 현재 단일 배관 탐색으로 여러 배관의 상호 간섭이나 안전 train 간 분리를 보장하지 않는다.
4. **기하 이격과 물리적 설계 검증은 다르다.** 열변위, 응력, 지지대, 실제 엘보 반경, 유동·압력손실 및 사고 영향 해석은 수행하지 않는다. 기기 위치와 연결 관계는 사용자 입력이며 기기 배치 자체를 최적화하지 않는다.
5. **출처 저장은 적용성 검증을 대신하지 않는다.** public_reference라는 표시나 사람의 앱 내 승인은 법규 해석·프로젝트 채택·규제기관 승인을 뜻하지 않는다. 현재 구조는 조건/예외, 관할, 거리 기준의 세부 의미를 충분히 표현하지 못한다.
6. **거리 기준과 해상도를 맞춰야 한다.** 현재 거리 기준 이름은 insulated_pipe_surface_to_target_surface이나 실제 계산에는 clearance_margin_m까지 포함된다. 원문이 맨 배관 표면을 기준으로 한다면 단열을 중복 적용하지 않도록 변환해야 한다. 0.5 m 격자는 0.15/0.25 m 규칙 차이를 가릴 수 있어 해상도/보수적 셀 제외의 영향도 평가해야 한다.

코드 근거: models/engineering.py, models/constraints.py, services/compiler.py, services/voxel_grid.py, services/path_validator.py.

## 논문 사례 보완 제안

첫 사례는 전기기기 전용 공간 KEEP_OUT, 두 번째는 범위를 명시한 증기배관의 벽 작업 여유 MIN_CLEARANCE가 적절하다.
각 사례에서 원문 요구 → 적용 조건/예외 → 사람이 지정한 배관·대상 → 거리 기준 변환 → 실행 규칙을 표로 남긴다.
안전계통 분리·위험 구역은 실제 요구에 착안한 합성 사례로 별도 표기하고 임의 거리값은 민감도 분석 변수로 사용한다.
원문 수치, 설계자가 선택한 값, 합성 실험 값은 출처/근거 문구에서 구분한다.
현재 예제는 그대로 유지하고 공개 기준 사례를 별도 버전의 합성 입력으로 추가하는 것이 기존 실험 재현에 유리하다.
이번에는 사례 추가나 다음 Phase 구현을 진행하지 않았다.

## 열람 및 검증 범위

UFGS·OSHA·IAEA·eCFR는 공개 원문 해당 부분을 열람했다. NRC 일부 CFR 페이지는 403이어서 eCFR 원문으로 확인했다.
한국 기준은 국가법령정보센터의 최신 법령 본문 접근에 실패했다.
[원안위 2025년 공개 자료](https://www.nssc.go.kr/attach/namo/files/000003/20250617095645544_X9F8MN88.pdf)의 검색 색인에서는 기술기준 규칙 제12조 및 제15조 언급을 확인했으나 PDF 본문 열람에 실패하여 국내 현행 조문 검증을 완료한 것으로 보고하지 않는다.
유료 KEPIC/ASME 전체 원문과 개별 발전소 인허가 기준은 열람하지 않았다.
확인하지 못한 세부 조항에서 배관 이격거리 요구가 없다고 단정하지 않는다.

검증은 로컬 JSON/모델/컴파일러/검증기 소스 대조와 공개 문서 열람으로 수행했다.
문서만 추가했으므로 pytest/Ruff/frontend build 및 신규 라우팅 실험은 실행하지 않았다.
