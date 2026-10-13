# 공개 기준을 참고한 합성 배관 사례

이 폴더의 JSON은 EngineeringProject 형식이며 실행 규칙은 모두 **draft**다.
기기 위치·건물·배관 치수는 합성이다. 공개 기준의 적용 조건과 정규화 가정을 사람이 검토한 후 승인한다.
기본 앱 예제나 기존 벤치마크 입력을 대체하지 않는다.

| 파일 | 적용 조건 |
|---|---|
| P10D-WALL-SMALL.json | UFGS 건물 난방 증기, 호칭 크기 100 mm, 벽 작업 여유 0.15 m |
| P10D-WALL-LARGE.json | 같은 범위, 호칭 크기 150 mm, 벽 작업 여유 0.25 m |
| P10D-ELECTRICAL.json | OSHA 실내 전기기기 전용 공간, 보호 예외 없는 외부 배관 |
| P10D-THERMAL-WALKWAY.json | 특정 Uppur 화력 프로젝트 LP overhead 배관·보행 공간 높이 2.5 m |

[출처 목록](../public_reference_sources.json),
[적용 가정·실험·논문 검토](../../docs/reviews/2026-10-13-public-reference-and-research-readiness.md).
호칭경을 외경으로 자동 추정하지 않는다. UFGS 거리의 외피 측정 기준과 OSHA 닿음 경계는 연구 해석이다.
화력 사례의 KEEP_OUT 닿음 계약은 정규화한 최소 높이 요구보다 엄격하다.

앱의 프로젝트 → JSON 편집에 원하는 파일의 전체 내용을 붙여넣고 ‘JSON 검증’을 누른다.
규칙을 승인하기 전 계산은 UNAPPROVED_RULE로 차단된다. 적용 조건·대상·측정 기준을 확인한 뒤
규칙 승인 관리에서 승인자 이름을 입력해 승인한다. 0.25 m 격자에서는 일부 사례가 최종 자기 간섭 검증에서 거부될 수 있다.
