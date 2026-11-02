"""화학실험실·시약 예약 및 허가증 발급 시스템 (Streamlit)."""
import datetime as dt
import os

import pandas as pd
import streamlit as st

import db
import permit
import safety

MIN_DAYS_AHEAD = 1       # 최소 며칠 전에 신청해야 하는지
MAX_HOURS = 3            # 1회 최대 사용 시간
ALLOW_WEEKEND = False
SLOTS = [f"{h:02d}:{m:02d}" for h in range(8, 19) for m in (0, 30)][:-1]  # 08:00 ~ 18:00

st.set_page_config(page_title="화학실험실 예약·허가", page_icon="🧪", layout="wide")
db.init_db()


def admin_password() -> str:
    try:
        return st.secrets["ADMIN_PASSWORD"]
    except Exception:
        return os.environ.get("ADMIN_PASSWORD", "admin1234")


def hours_between(a: str, b: str) -> float:
    fa = dt.datetime.strptime(a, "%H:%M")
    fb = dt.datetime.strptime(b, "%H:%M")
    return (fb - fa).seconds / 3600 if fb > fa else 0


def show_analysis(a: dict):
    if a["ppe"]:
        st.info("**필수 보호구·안전 수칙**\n\n" + "\n".join(f"- {p}" for p in a["ppe"]))
    for w in a["warnings"]:
        st.warning(w)
    for e in a["errors"]:
        st.error(e)


# =====================================================================
# 학생 화면
# =====================================================================
def page_reserve():
    st.header("실험실·시약 사용 예약 신청")
    labs = db.get_labs(include_inactive=False)
    reagents = db.get_reagents_available()
    if labs.empty:
        st.warning("등록된 실험실이 없습니다. 교사에게 문의하세요.")
        return

    c1, c2 = st.columns(2)
    with c1:
        sid = st.text_input("학번", placeholder="예: 20315")
        name = st.text_input("이름")
        team = st.number_input("실험 인원(명)", 1, 40, 1)
        teacher = st.text_input("입회 지도교사", help="실험은 반드시 교사 입회 하에서만 가능합니다.")
    with c2:
        lab_name = st.selectbox("실험실", labs["name"])
        lab = labs[labs["name"] == lab_name].iloc[0]
        min_date = dt.date.today() + dt.timedelta(days=MIN_DAYS_AHEAD)
        date = st.date_input("사용 날짜", value=min_date, min_value=min_date)
        t1, t2 = st.columns(2)
        start = t1.selectbox("시작 시간", SLOTS, index=2)
        end = t2.selectbox("종료 시간", SLOTS, index=6)

    day = db.get_reservations("v.lab_id=? AND v.date=? AND v.status IN ('대기','승인')",
                              (int(lab["id"]), date.isoformat()))
    if not day.empty:
        st.caption("이 날 이미 예약된 시간")
        st.dataframe(day[["start", "end", "status"]].rename(
            columns={"start": "시작", "end": "종료", "status": "상태"}), hide_index=True)

    purpose = st.text_area("실험 제목 및 목적·방법 요약")

    # 시약 선택 (만료·교사전용 제외 표시)
    usable = reagents[~reagents["restricted"]].copy()
    usable = usable[(pd.to_datetime(usable["expiry"], errors="coerce").isna())
                    | (pd.to_datetime(usable["expiry"], errors="coerce").dt.date >= date)]
    usable = usable[usable["available"] > 0]
    labels = {int(r["id"]): f"{r['name']} [{r['hazard_1']}] 가용 {r['available']:g}{r['unit']}"
              for _, r in usable.iterrows()}
    picked = st.multiselect("사용할 시약", list(labels), format_func=labels.get)
    st.caption("교사 전용 시약·재고 없음·유효기간 경과 시약은 목록에 나타나지 않습니다.")

    items, rows = [], []
    for rid in picked:
        r = usable[usable["id"] == rid].iloc[0]
        q = st.number_input(f"{r['name']} 사용량 ({r['unit']})", min_value=0.0,
                            max_value=float(r["available"]), value=min(1.0, float(r["available"])),
                            key=f"q{rid}")
        if q > 0:
            items.append((rid, q))
            row = r.to_dict()
            row["qty"] = q
            rows.append(row)

    analysis = None
    if rows:
        analysis = safety.analyze(pd.DataFrame(rows), lab, int(team))
        show_analysis(analysis)

    st.subheader("안전 서약")
    acks = [st.checkbox("사용할 시약의 물질안전보건자료(SDS)와 유해성을 확인했습니다."),
            st.checkbox("보호구(보안경·실험복·장갑)를 착용하고 지도교사 지시를 따르겠습니다."),
            st.checkbox("허가된 시약·사용량·시간 외에는 사용하지 않으며, 폐액은 분리 배출하겠습니다.")]

    if st.button("예약 신청", type="primary"):
        errs = []
        if not sid.strip() or not name.strip():
            errs.append("학번과 이름을 입력하세요.")
        if not teacher.strip():
            errs.append("입회 지도교사를 입력하세요.")
        if not purpose.strip():
            errs.append("실험 목적을 입력하세요.")
        if not items:
            errs.append("시약을 1개 이상 선택하세요.")
        h = hours_between(start, end)
        if h <= 0:
            errs.append("종료 시간이 시작 시간보다 늦어야 합니다.")
        elif h > MAX_HOURS:
            errs.append(f"1회 최대 {MAX_HOURS}시간까지 신청할 수 있습니다.")
        if not ALLOW_WEEKEND and date.weekday() >= 5:
            errs.append("주말에는 사용할 수 없습니다.")
        if not all(acks):
            errs.append("안전 서약에 모두 동의해야 합니다.")
        if analysis:
            errs += analysis["errors"]
        if errs:
            for e in errs:
                st.error(e)
            return
        try:
            rid = db.create_reservation(
                dict(student_id=sid.strip(), student_name=name.strip(), team_size=int(team),
                     lab_id=int(lab["id"]), date=date.isoformat(), start=start, end=end,
                     purpose=purpose.strip(), teacher_name=teacher.strip()), items)
            st.success(f"신청 완료! (신청번호 {rid}) 교사 승인 후 '내 예약·허가증'에서 허가증을 받을 수 있습니다.")
        except ValueError as e:
            st.error(str(e))


def page_my():
    st.header("내 예약 조회 · 허가증 출력")
    c1, c2 = st.columns(2)
    sid = c1.text_input("학번")
    name = c2.text_input("이름")
    if not (sid.strip() and name.strip()):
        return
    df = db.get_reservations("v.student_id=? AND v.student_name=?", (sid.strip(), name.strip()))
    if df.empty:
        st.info("예약 내역이 없습니다.")
        return
    for _, r in df.iterrows():
        r = r.to_dict()
        with st.container(border=True):
            st.markdown(f"**#{r['id']} · {r['date']} {r['start']}~{r['end']} · {r['lab_name']}** — `{r['status']}`")
            st.caption(r["purpose"])
            if r["status"] == db.REJECTED:
                st.error(f"반려 사유: {r['reject_reason'] or '(없음)'}")
            if r["status"] == db.PENDING and st.button("신청 취소", key=f"cancel{r['id']}"):
                db.set_status(r["id"], db.CANCELED)
                st.rerun()
            if r["status"] == db.APPROVED:
                items = db.get_items(r["id"])
                lab = db.get_labs()
                lab = lab[lab["id"] == r["lab_id"]].iloc[0]
                a = safety.analyze(items, lab, r["team_size"])
                pdf = permit.build_permit(r, items, a["ppe"], a["warnings"])
                st.download_button("📄 허가증 PDF 다운로드", pdf, file_name=f"{r['permit_no']}.pdf",
                                   mime="application/pdf", key=f"pdf{r['id']}")


# =====================================================================
# 교사(관리자) 화면
# =====================================================================
def page_approvals():
    st.header("예약 승인 관리")
    approver = st.session_state.get("admin_name") or "교사"
    pend = db.get_reservations("v.status='대기'")
    st.subheader(f"승인 대기 ({len(pend)}건)")
    labs = db.get_labs()
    for _, r in pend.iterrows():
        r = r.to_dict()
        items = db.get_items(r["id"])
        lab = labs[labs["id"] == r["lab_id"]].iloc[0]
        a = safety.analyze(items, lab, r["team_size"])
        with st.expander(f"#{r['id']} {r['date']} {r['start']}~{r['end']} · {r['lab_name']} · "
                         f"{r['student_id']} {r['student_name']}", expanded=True):
            st.write(f"**입회교사**: {r['teacher_name']}　**인원**: {r['team_size']}명")
            st.write(f"**목적**: {r['purpose']}")
            st.dataframe(items.drop(columns=["restricted"]), hide_index=True)
            show_analysis(a)
            reason = st.text_input("반려 사유", key=f"rs{r['id']}")
            b1, b2, _ = st.columns([1, 1, 4])
            if b1.button("승인", key=f"ok{r['id']}", type="primary", disabled=bool(a["errors"])):
                db.set_status(r["id"], db.APPROVED, approver=approver)
                st.rerun()
            if b2.button("반려", key=f"no{r['id']}"):
                db.set_status(r["id"], db.REJECTED, reason=reason or "사유 미기재")
                st.rerun()

    st.subheader("승인됨 (사용 완료 처리 시 재고 차감)")
    appr = db.get_reservations("v.status='승인'")
    for _, r in appr.iterrows():
        c1, c2, c3 = st.columns([5, 1, 1])
        c1.write(f"#{r['id']} {r['date']} {r['start']}~{r['end']} · {r['lab_name']} · "
                 f"{r['student_name']} ({r['permit_no']})")
        if c2.button("사용 완료", key=f"done{r['id']}"):
            db.complete_reservation(int(r["id"]))
            st.rerun()
        if c3.button("승인 취소", key=f"rev{r['id']}"):
            db.set_status(int(r["id"]), db.CANCELED)
            st.rerun()


def editor_page(title, table, cols, df, config, key):
    st.header(title)
    st.caption("표에서 직접 수정·추가(맨 아래 빈 행)·삭제(행 선택 후 Delete)한 뒤 [저장]을 누르세요. "
               "예약 이력이 있는 항목은 삭제 대신 '사용' 체크를 해제하세요.")
    edited = st.data_editor(df, num_rows="dynamic", hide_index=True, column_config=config,
                            use_container_width=True, key=key)
    if st.button("저장", type="primary", key=f"save_{key}"):
        try:
            db.save_table(table, edited, cols)
            st.success("저장되었습니다.")
            st.rerun()
        except ValueError as e:
            st.error(str(e))


def page_reagents():
    cfg = {
        "id": st.column_config.NumberColumn("ID", disabled=True),
        "name": st.column_config.TextColumn("시약명", required=True),
        "cas": "CAS 번호", "formula": "화학식",
        "hazard_1": st.column_config.SelectboxColumn("주 유해성", options=safety.HAZARDS),
        "hazard_2": st.column_config.SelectboxColumn("보조 유해성", options=safety.HAZARDS),
        "stock_qty": st.column_config.NumberColumn("재고량", min_value=0),
        "unit": st.column_config.SelectboxColumn("단위", options=["mL", "L", "g", "kg", "개"]),
        "location": "보관 위치",
        "expiry": st.column_config.DateColumn("유효기간"),
        "restricted": st.column_config.CheckboxColumn("교사 전용"),
        "sds_url": st.column_config.LinkColumn("SDS 링크"),
        "note": "비고",
        "active": st.column_config.CheckboxColumn("사용"),
    }
    editor_page("시약 데이터베이스", "reagents", db.REAGENT_COLS, db.get_reagents(), cfg, "reagent_editor")


def page_labs():
    cfg = {
        "id": st.column_config.NumberColumn("ID", disabled=True),
        "name": st.column_config.TextColumn("실험실명", required=True),
        "capacity": st.column_config.NumberColumn("수용 인원", min_value=1),
        "has_hood": st.column_config.CheckboxColumn("흄후드"),
        "has_eyewash": st.column_config.CheckboxColumn("눈 세척기"),
        "has_shower": st.column_config.CheckboxColumn("비상 샤워"),
        "notes": "비고",
        "active": st.column_config.CheckboxColumn("사용"),
    }
    editor_page("실험실 데이터베이스", "labs", db.LAB_COLS, db.get_labs(), cfg, "lab_editor")


def page_overview():
    st.header("전체 현황 · 허가증 확인")
    st.subheader("허가번호 확인 (실험실 입구용)")
    no = st.text_input("허가번호", placeholder="CHEM-20261110-0001")
    if no:
        df = db.get_reservations("v.permit_no=?", (no.strip(),))
        if df.empty:
            st.error("유효하지 않은 허가번호입니다.")
        else:
            r = df.iloc[0]
            ok = r["status"] == db.APPROVED and r["date"] == dt.date.today().isoformat()
            (st.success if ok else st.warning)(
                f"{r['student_name']} · {r['lab_name']} · {r['date']} {r['start']}~{r['end']} · 상태: {r['status']}"
                + ("" if ok else " (오늘 사용 가능한 승인 건이 아닙니다)"))
    st.subheader("전체 예약 내역")
    st.dataframe(db.get_reservations(), hide_index=True, use_container_width=True)
    st.subheader("재고 부족 · 유효기간 임박 시약")
    rg = db.get_reagents(include_inactive=False)
    soon = dt.date.today() + dt.timedelta(days=90)
    low = rg[(rg["stock_qty"] <= 0) | rg["expiry"].apply(lambda x: x is not None and x <= soon)]
    st.dataframe(low[["name", "stock_qty", "unit", "expiry", "location"]], hide_index=True)


# =====================================================================
# 라우팅
# =====================================================================
st.sidebar.title("🧪 화학실험실 예약·허가")
mode = st.sidebar.radio("구분", ["학생", "교사(관리자)"])

if mode == "학생":
    page = st.sidebar.radio("메뉴", ["예약 신청", "내 예약·허가증"])
    page_reserve() if page == "예약 신청" else page_my()
else:
    if not st.session_state.get("is_admin"):
        pw = st.sidebar.text_input("관리자 비밀번호", type="password")
        nm = st.sidebar.text_input("교사 이름")
        if st.sidebar.button("로그인"):
            if pw == admin_password() and nm.strip():
                st.session_state.update(is_admin=True, admin_name=nm.strip())
                st.rerun()
            else:
                st.sidebar.error("비밀번호 또는 이름을 확인하세요.")
        st.info("왼쪽에서 로그인하세요.")
    else:
        st.sidebar.success(f"{st.session_state['admin_name']} 선생님")
        if st.sidebar.button("로그아웃"):
            st.session_state.clear()
            st.rerun()
        page = st.sidebar.radio("메뉴", ["예약 승인", "시약 DB", "실험실 DB", "전체 현황"])
        {"예약 승인": page_approvals, "시약 DB": page_reagents,
         "실험실 DB": page_labs, "전체 현황": page_overview}[page]()
