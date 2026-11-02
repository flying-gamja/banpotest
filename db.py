"""SQLite 데이터베이스 계층."""
import datetime as dt
import os
import sqlite3
from contextlib import contextmanager

import pandas as pd

DB_PATH = os.environ.get("DB_PATH", "lab.db")

PENDING, APPROVED, REJECTED, CANCELED, DONE = "대기", "승인", "반려", "취소", "완료"

REAGENT_COLS = ["name", "cas", "formula", "hazard_1", "hazard_2", "stock_qty", "unit",
                "location", "expiry", "restricted", "sds_url", "note", "active"]
LAB_COLS = ["name", "capacity", "has_hood", "has_eyewash", "has_shower", "notes", "active"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS reagents(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL, cas TEXT, formula TEXT,
    hazard_1 TEXT DEFAULT '해당없음', hazard_2 TEXT DEFAULT '해당없음',
    stock_qty REAL DEFAULT 0, unit TEXT DEFAULT 'mL',
    location TEXT, expiry TEXT, restricted INTEGER DEFAULT 0,
    sds_url TEXT, note TEXT, active INTEGER DEFAULT 1);

CREATE TABLE IF NOT EXISTS labs(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL, capacity INTEGER DEFAULT 24,
    has_hood INTEGER DEFAULT 0, has_eyewash INTEGER DEFAULT 1, has_shower INTEGER DEFAULT 0,
    notes TEXT, active INTEGER DEFAULT 1);

CREATE TABLE IF NOT EXISTS reservations(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id TEXT NOT NULL, student_name TEXT NOT NULL, team_size INTEGER DEFAULT 1,
    lab_id INTEGER NOT NULL REFERENCES labs(id),
    date TEXT NOT NULL, start TEXT NOT NULL, end TEXT NOT NULL,
    purpose TEXT, teacher_name TEXT,
    status TEXT DEFAULT '대기', reject_reason TEXT,
    permit_no TEXT, approved_by TEXT, approved_at TEXT, created_at TEXT);

CREATE TABLE IF NOT EXISTS reservation_items(
    reservation_id INTEGER NOT NULL REFERENCES reservations(id),
    reagent_id INTEGER NOT NULL REFERENCES reagents(id),
    qty REAL NOT NULL);
"""


@contextmanager
def conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    try:
        yield c
        c.commit()
    finally:
        c.close()


def read_df(sql, params=()):
    with conn() as c:
        return pd.read_sql_query(sql, c, params=params)


def init_db():
    with conn() as c:
        c.executescript(SCHEMA)
        if c.execute("SELECT COUNT(*) FROM labs").fetchone()[0] == 0:
            c.executemany(
                "INSERT INTO labs(name,capacity,has_hood,has_eyewash,has_shower,notes) VALUES(?,?,?,?,?,?)",
                [("화학실험실 1", 30, 1, 1, 1, "샘플 데이터 - 수정하세요"),
                 ("화학실험실 2", 24, 0, 1, 0, "샘플 데이터 - 수정하세요")])
        if c.execute("SELECT COUNT(*) FROM reagents").fetchone()[0] == 0:
            c.executemany(
                "INSERT INTO reagents(name,cas,formula,hazard_1,hazard_2,stock_qty,unit,location,restricted,note) "
                "VALUES(?,?,?,?,?,?,?,?,?,?)",
                [("염산 1M", "7647-01-0", "HCl", "부식성(산)", "자극성", 1000, "mL", "산·염기 캐비닛 A", 0, "샘플"),
                 ("수산화나트륨", "1310-73-2", "NaOH", "부식성(염기)", "해당없음", 500, "g", "산·염기 캐비닛 B", 0, "샘플"),
                 ("에탄올 95%", "64-17-5", "C2H5OH", "인화성", "해당없음", 2000, "mL", "인화성 물질 보관함", 0, "샘플"),
                 ("과산화수소 3%", "7722-84-1", "H2O2", "산화성", "해당없음", 1000, "mL", "냉암소", 0, "샘플"),
                 ("질산은", "7761-88-8", "AgNO3", "산화성", "환경유해", 50, "g", "산화제 보관함", 0, "샘플"),
                 ("과망간산칼륨", "7722-64-7", "KMnO4", "산화성", "환경유해", 100, "g", "산화제 보관함", 0, "샘플"),
                 ("아세톤", "67-64-1", "C3H6O", "인화성", "자극성", 1000, "mL", "인화성 물질 보관함", 0, "샘플"),
                 ("염화나트륨", "7647-14-5", "NaCl", "해당없음", "해당없음", 1000, "g", "일반 시약장", 0, "샘플"),
                 ("나트륨(금속)", "7440-23-5", "Na", "물반응성", "부식성(염기)", 25, "g", "교사 전용 보관", 1, "샘플 - 교사 전용")])


# ---------- 조회 ----------
def get_reagents(include_inactive=True):
    df = read_df("SELECT * FROM reagents" + ("" if include_inactive else " WHERE active=1") + " ORDER BY id")
    df["restricted"] = df["restricted"].astype(bool)
    df["active"] = df["active"].astype(bool)
    df["expiry"] = pd.to_datetime(df["expiry"], errors="coerce").dt.date
    df["expiry"] = df["expiry"].apply(lambda x: None if pd.isna(x) else x)
    return df


def get_reagents_available():
    """학생에게 보여줄 시약 목록 (예약 대기·승인분을 뺀 가용량 포함)."""
    df = read_df("""
        SELECT r.*, r.stock_qty - COALESCE((
            SELECT SUM(i.qty) FROM reservation_items i JOIN reservations v ON v.id=i.reservation_id
            WHERE i.reagent_id=r.id AND v.status IN ('대기','승인')), 0) AS available
        FROM reagents r WHERE r.active=1 ORDER BY r.name""")
    df["restricted"] = df["restricted"].astype(bool)
    return df


def get_labs(include_inactive=True):
    df = read_df("SELECT * FROM labs" + ("" if include_inactive else " WHERE active=1") + " ORDER BY id")
    for c in ("has_hood", "has_eyewash", "has_shower", "active"):
        df[c] = df[c].astype(bool)
    return df


def get_reservations(where="1=1", params=()):
    return read_df(f"""SELECT v.*, l.name AS lab_name FROM reservations v
                       JOIN labs l ON l.id=v.lab_id WHERE {where}
                       ORDER BY v.date DESC, v.start""", params)


def get_items(reservation_id):
    return read_df("""SELECT r.name, r.cas, r.hazard_1, r.hazard_2, r.unit, r.location,
                             r.restricted, i.qty
                      FROM reservation_items i JOIN reagents r ON r.id=i.reagent_id
                      WHERE i.reservation_id=?""", (reservation_id,))


# ---------- 예약 ----------
def has_conflict(lab_id, date, start, end, c=None):
    sql = ("SELECT COUNT(*) FROM reservations WHERE lab_id=? AND date=? "
           "AND status IN ('대기','승인') AND start < ? AND end > ?")
    args = (lab_id, date, end, start)
    if c is not None:
        return c.execute(sql, args).fetchone()[0] > 0
    with conn() as c2:
        return c2.execute(sql, args).fetchone()[0] > 0


def create_reservation(d: dict, items: list):
    """items: [(reagent_id, qty), ...]. 시간 중복이면 ValueError."""
    with conn() as c:
        if has_conflict(d["lab_id"], d["date"], d["start"], d["end"], c):
            raise ValueError("해당 시간에 이미 다른 예약이 있습니다.")
        cur = c.execute(
            """INSERT INTO reservations(student_id,student_name,team_size,lab_id,date,start,end,
               purpose,teacher_name,status,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
            (d["student_id"], d["student_name"], d["team_size"], d["lab_id"], d["date"], d["start"],
             d["end"], d["purpose"], d["teacher_name"], PENDING, dt.datetime.now().isoformat(timespec="seconds")))
        rid = cur.lastrowid
        c.executemany("INSERT INTO reservation_items VALUES(?,?,?)", [(rid, a, b) for a, b in items])
        return rid


def set_status(rid, status, approver=None, reason=None):
    with conn() as c:
        if status == APPROVED:
            row = c.execute("SELECT date FROM reservations WHERE id=?", (rid,)).fetchone()
            permit_no = f"CHEM-{row['date'].replace('-', '')}-{rid:04d}"
            c.execute("UPDATE reservations SET status=?, permit_no=?, approved_by=?, approved_at=? WHERE id=?",
                      (status, permit_no, approver, dt.datetime.now().isoformat(timespec="seconds"), rid))
        else:
            c.execute("UPDATE reservations SET status=?, reject_reason=? WHERE id=?", (status, reason, rid))


def complete_reservation(rid):
    """사용 완료 처리: 신청량만큼 재고 차감."""
    with conn() as c:
        for r in c.execute("SELECT reagent_id, qty FROM reservation_items WHERE reservation_id=?", (rid,)):
            c.execute("UPDATE reagents SET stock_qty=MAX(stock_qty-?,0) WHERE id=?", (r["qty"], r["reagent_id"]))
        c.execute("UPDATE reservations SET status=? WHERE id=?", (DONE, rid))


# ---------- 관리자 편집 저장 ----------
def _clean(v):
    if v is None or (not isinstance(v, (list, dict)) and pd.isna(v)):
        return None
    if isinstance(v, (bool,)) or type(v).__name__ == "bool_":
        return int(v)
    if isinstance(v, (dt.date, dt.datetime, pd.Timestamp)):
        return v.strftime("%Y-%m-%d")
    if hasattr(v, "item"):
        return v.item()
    return v


def save_table(table: str, df: pd.DataFrame, cols: list):
    """data_editor 결과를 DB에 반영 (추가/수정/삭제). 예약 이력이 있는 행은 삭제 불가."""
    with conn() as c:
        existing = {r[0] for r in c.execute(f"SELECT id FROM {table}")}
        keep = set()
        for _, r in df.iterrows():
            if not str(r.get("name") or "").strip():
                continue
            vals = [_clean(r[k]) for k in cols]
            rid = r.get("id")
            if pd.notna(rid) and int(rid) in existing:
                keep.add(int(rid))
                c.execute(f"UPDATE {table} SET {', '.join(k + '=?' for k in cols)} WHERE id=?",
                          vals + [int(rid)])
            else:
                c.execute(f"INSERT INTO {table}({','.join(cols)}) VALUES({','.join('?' * len(cols))})", vals)
        for rid in existing - keep:
            try:
                c.execute(f"DELETE FROM {table} WHERE id=?", (rid,))
            except sqlite3.IntegrityError:
                raise ValueError(f"id {rid}번은 예약 이력이 있어 삭제할 수 없습니다. '사용' 체크를 해제하세요.")
