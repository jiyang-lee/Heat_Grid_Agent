from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from schemas import AgentRunResponse, OpsAgentResultV4


def _font_name() -> str:
    candidates = (
        Path("/usr/share/fonts/truetype/nanum/NanumGothic.ttf"),
        Path("C:/Windows/Fonts/malgun.ttf"),
    )
    for path in candidates:
        if path.is_file():
            pdfmetrics.registerFont(TTFont("HeatGridKorean", str(path)))
            return "HeatGridKorean"
    return "Helvetica"


def render_incident_report_pdf(
    output_path: Path,
    *,
    run: AgentRunResponse,
    result: OpsAgentResultV4,
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    font = _font_name()
    styles = getSampleStyleSheet()
    title = ParagraphStyle(
        "HeatGridTitle",
        parent=styles["Title"],
        fontName=font,
        fontSize=20,
        leading=28,
        alignment=TA_CENTER,
        spaceAfter=10 * mm,
    )
    heading = ParagraphStyle(
        "HeatGridHeading",
        parent=styles["Heading2"],
        fontName=font,
        fontSize=12,
        leading=18,
        textColor=colors.HexColor("#0f172a"),
        spaceBefore=5 * mm,
        spaceAfter=2 * mm,
    )
    body = ParagraphStyle(
        "HeatGridBody",
        parent=styles["BodyText"],
        fontName=font,
        fontSize=9.5,
        leading=16,
        textColor=colors.HexColor("#334155"),
    )
    document = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        rightMargin=20 * mm,
        leftMargin=20 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=result.report.title,
    )
    metadata = Table(
        [
            ["문서 번호", run.run_id, "기계실", str(result.substation_id or "-")],
            ["작성 모델", "gpt-5.4-nano", "작성 일시", str(run.created_at or "-")],
        ],
        colWidths=[25 * mm, 70 * mm, 25 * mm, 50 * mm],
    )
    metadata.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), font),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#eff6ff")),
        ("BACKGROUND", (2, 0), (2, -1), colors.HexColor("#eff6ff")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story = [Paragraph("사고 조치 보고서", title), metadata, Spacer(1, 4 * mm)]
    sections = [
        ("1. 사고 요약", result.situation),
        ("2. 판단 근거", "<br/>".join(f"• {item.label}: {item.content}" for item in result.evidence)),
        ("3. 권장 작업지시", "<br/>".join(f"{item.priority}. {item.title}: {item.detail}" for item in result.actions)),
        ("4. 안전 유의사항", "<br/>".join(f"• {item}" for item in result.cautions)),
    ]
    for section_title, content in sections:
        story.extend((Paragraph(section_title, heading), Paragraph(content or "-", body)))
    document.build(story)
    return output_path
