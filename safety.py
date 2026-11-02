"""화학물질 안전 규칙 모듈.

학교 현장에 맞게 이 파일의 규칙만 수정하면 앱 전체에 반영됩니다.
"""
import pandas as pd

HAZARDS = [
    "해당없음", "인화성", "산화성", "부식성(산)", "부식성(염기)", "급성독성",
    "발암·변이원성", "물반응성", "폭발성", "환경유해", "자극성",
]

# 기본 보호구 (모든 실험 공통)
BASE_PPE = ["보안경(고글)", "실험복", "긴바지 및 앞이 막힌 신발", "니트릴 장갑"]

PPE_BY_HAZARD = {
    "인화성": ["화기(가스버너 등) 근처 사용 금지", "소량 사용 및 뚜껑 즉시 닫기"],
    "산화성": ["가연물·유기물과 분리하여 취급"],
    "부식성(산)": ["내화학 장갑", "안면보호구 또는 고글 필수", "희석 시 반드시 물에 산을 천천히 가함"],
    "부식성(염기)": ["내화학 장갑", "안면보호구 또는 고글 필수"],
    "급성독성": ["흄후드 내에서만 취급", "이중 장갑", "취급 후 즉시 손 씻기"],
    "발암·변이원성": ["흄후드 내에서만 취급", "이중 장갑"],
    "물반응성": ["물·수분 접촉 금지", "건조한 도구 사용"],
    "환경유해": ["폐액은 지정 폐액통에 분리 수거 (하수구 배출 금지)"],
    "자극성": ["환기 유지, 피부·눈 접촉 주의"],
}

# 같은 실험에서 함께 쓰면 주의가 필요한 조합 (교사 판단용 경고)
INCOMPATIBLE = [
    ({"산화성"}, {"인화성"}, "산화제와 인화성 물질을 함께 사용: 발화·폭발 위험"),
    ({"부식성(산)"}, {"부식성(염기)"}, "산과 염기를 함께 사용: 격렬한 발열 가능 (중화 실험이면 농도·양 확인)"),
    ({"물반응성"}, {"부식성(산)", "부식성(염기)"}, "물반응성 물질과 산/염기 수용액을 함께 사용: 격렬한 반응 위험"),
    ({"산화성"}, {"부식성(산)"}, "산화제와 산을 함께 사용: 유독가스 발생 가능"),
]

HOOD_REQUIRED = {"급성독성", "발암·변이원성"}
EYEWASH_REQUIRED = {"부식성(산)", "부식성(염기)", "급성독성"}
STUDENT_FORBIDDEN = {"폭발성"}  # 학생 신청 불가 (교사 직접 시연만)


def _hazard_set(row) -> set:
    s = {row.get("hazard_1"), row.get("hazard_2")}
    return {h for h in s if h and not pd.isna(h) and h != "해당없음"}


def analyze(items: pd.DataFrame, lab, team_size: int) -> dict:
    """선택한 시약/실험실/인원을 점검한다.

    errors   : 신청 자체가 불가능한 사유
    warnings : 승인 교사가 확인해야 할 사항
    ppe      : 허가증에 인쇄할 보호구·주의사항
    """
    errors, warnings = [], []
    all_h, per_item = set(), []

    for _, r in items.iterrows():
        hs = _hazard_set(r)
        per_item.append(hs)
        all_h |= hs
        if r.get("restricted"):
            errors.append(f"'{r['name']}'은(는) 교사 전용 시약입니다. 교사에게 직접 문의하세요.")
        if hs & STUDENT_FORBIDDEN:
            errors.append(f"'{r['name']}'은(는) 폭발성 물질로 학생 신청이 불가합니다.")

    if team_size > int(lab["capacity"]):
        errors.append(f"실험 인원({team_size}명)이 실험실 수용 인원({int(lab['capacity'])}명)을 초과합니다.")
    if all_h & HOOD_REQUIRED and not lab["has_hood"]:
        errors.append("선택한 시약은 흄후드가 필요하지만 이 실험실에는 후드가 없습니다.")
    if all_h & EYEWASH_REQUIRED and not lab["has_eyewash"]:
        errors.append("선택한 시약은 눈 세척기가 필요하지만 이 실험실에는 설치되어 있지 않습니다.")

    # 비호환 조합은 서로 다른 시약 사이에서만 검사
    seen = set()
    for i, hi in enumerate(per_item):
        for j, hj in enumerate(per_item):
            if i >= j:
                continue
            for a, b, msg in INCOMPATIBLE:
                if (hi & a and hj & b) or (hi & b and hj & a):
                    key = (min(i, j), max(i, j), msg)
                    if key not in seen:
                        seen.add(key)
                        warnings.append(f"[{items.iloc[i]['name']} + {items.iloc[j]['name']}] {msg}")

    ppe = list(BASE_PPE)
    for h in all_h:
        for p in PPE_BY_HAZARD.get(h, []):
            if p not in ppe:
                ppe.append(p)

    return {"errors": errors, "warnings": warnings, "ppe": ppe, "hazards": sorted(all_h)}
