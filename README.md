# 화학실험실·시약 예약 및 허가증 발급 (Streamlit)

## 실행
    pip install -r requirements.txt
    streamlit run app.py

## 구성
- `app.py`    : 화면(학생/교사)
- `db.py`     : SQLite DB (시약, 실험실, 예약)
- `safety.py` : 유해성 분류, 비호환 조합, 보호구 규칙 (학교 규정에 맞게 수정)
- `permit.py` : 허가증 PDF 생성 (`SCHOOL_NAME` 환경변수로 학교명 지정)

## 관리자 비밀번호
`.streamlit/secrets.toml` 에 `ADMIN_PASSWORD` 설정 (기본값 admin1234 는 반드시 변경).

## 한글 폰트
`fonts/NanumGothic.ttf` 를 넣으면 PDF에 폰트가 내장되어 어느 기기에서나 정상 출력됩니다.

## 배포 시 주의
- Streamlit Community Cloud는 재시작 시 `lab.db`가 초기화됩니다. 실제 운영 시 Supabase/Postgres,
  Google Sheets 등 외부 DB로 교체하세요 (db.py만 수정하면 됩니다).
- 학생 이름·학번이 저장되므로 `lab.db`를 GitHub에 올리지 말고, 저장소는 private 권장.
