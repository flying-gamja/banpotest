"""실험실·시약 사용 허가증 PDF 생성."""
import io
import os

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

SCHOOL_NAME = os.environ.get("SCHOOL_NAME", "○○고등학교")


def _register_font() -> str:
    """fonts/ 폴더에 한글 TTF(NanumGothic 등)가 있으면 사용(PDF에 내장), 없으면 CID 폰트로 대체."""
    for p in ("fonts/NanumGothic.ttf", "fonts/NanumGothic-Regular.ttf", "fonts/NotoSansKR-Regular.ttf"):
        if os.path.exists(p):
            pdfmetrics.registerFont(TTFont("KR", p))
            return "KR"
    pdfmetrics.registerFont(UnicodeCIDFont("HYSMyeongJo-Medium"))
    return "HYSMyeongJo-Medium"


def build_permit(res: dict, items, ppe: list, warnings: list) -> bytes:
    font = _register_font()
    st = lambda size, **kw: ParagraphStyle("s", fontName=font, fontSize=size, leading=size * 1.5,
                                           wordWrap="CJK", **kw)
    body, small, title = st(10), st(9), st(20, alignment=1)
    cell = lambda t: Paragraph(str(t), body)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=15 * mm, bottomMargin=15 * mm,
                            title=f"허가증 {res['permit_no']}")
    story = [Paragraph(SCHOOL_NAME, st(11, alignment=1)),
             Paragraph("실험실 및 시약 사용 허가증", title),
             Paragraph(f"허가번호: {res['permit_no']}", st(10, alignment=1)),
             Spacer(1, 6 * mm)]

    grid = TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                       ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#EEF3F8")),
                       ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                       ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)])

    info = [["신청자", f"{res['student_id']} {res['student_name']} (실험 인원 {res['team_size']}명)"],
            ["실험실", res["lab_name"]],
            ["사용 일시", f"{res['date']}  {res['start']} ~ {res['end']}"],
            ["입회 지도교사", res["teacher_name"]],
            ["실험 목적", res["purpose"]]]
    t = Table([[cell(a), cell(b)] for a, b in info], colWidths=[35 * mm, 139 * mm])
    t.setStyle(grid)
    story += [t, Spacer(1, 5 * mm), Paragraph("사용 허가 시약", st(12)), Spacer(1, 2 * mm)]

    rows = [[cell(h) for h in ["시약명", "CAS", "유해성", "사용량", "보관 위치"]]]
    for _, r in items.iterrows():
        hz = ", ".join(h for h in (r["hazard_1"], r["hazard_2"]) if h and h != "해당없음") or "-"
        rows.append([cell(r["name"]), cell(r["cas"] or "-"), cell(hz),
                     cell(f"{r['qty']:g} {r['unit']}"), cell(r["location"] or "-")])
    t = Table(rows, colWidths=[38 * mm, 26 * mm, 44 * mm, 24 * mm, 42 * mm], repeatRows=1)
    t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                           ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EEF3F8")),
                           ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
    story += [t, Spacer(1, 5 * mm), Paragraph("필수 보호구 및 안전 수칙", st(12)), Spacer(1, 2 * mm)]

    for p in ppe:
        story.append(Paragraph(f"[ ] {p}", body))
    if warnings:
        story += [Spacer(1, 2 * mm), Paragraph("교사 확인 사항", st(12))]
        story += [Paragraph(f"- {w}", small) for w in warnings]

    story += [Spacer(1, 3 * mm), Paragraph(
        "※ 본 허가증을 지참하고, 반드시 지도교사 입회 하에서만 실험하십시오. "
        "허가된 시약·사용량·시간 외의 사용은 금지됩니다. 사고 발생 시 즉시 교사에게 알리고, "
        "폐액은 지정된 폐액통에 분리 배출하십시오. 실험 종료 후 정리·청소를 마치고 교사 확인을 받으십시오.",
        small), Spacer(1, 8 * mm)]

    sign = [["신청 학생 서명", "지도교사 확인(입회)", "승인자"],
            ["<br/><br/>", "<br/><br/>", f"{res['approved_by'] or ''}<br/>{(res['approved_at'] or '')[:10]}"]]
    t = Table([[cell(c) for c in row] for row in sign], colWidths=[58 * mm] * 3)
    t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                           ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EEF3F8")),
                           ("ALIGN", (0, 0), (-1, -1), "CENTER")]))
    story.append(t)

    doc.build(story)
    return buf.getvalue()
