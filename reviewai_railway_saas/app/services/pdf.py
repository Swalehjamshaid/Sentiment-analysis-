from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import cm
from reportlab.lib import colors
from datetime import datetime
import io
from typing import List, Tuple


def _draw_kpi_line(c, x, y, label, value):
    c.setFont("Helvetica-Bold", 12)
    c.drawString(x, y, f"{label}:")
    c.setFont("Helvetica", 12)
    c.drawRightString(x + 10*cm, y, str(value))


def generate_company_report(company_name: str,
                            kpis: dict,
                            ratings_trend: List[Tuple[str, float]],
                            sentiment_breakdown: dict,
                            samples: dict) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4

    # Header
    c.setFillColor(colors.HexColor('#1f2937'))
    c.rect(0, height-2*cm, width, 2*cm, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(2*cm, height-1.2*cm, f"Review Report – {company_name}")
    c.setFont("Helvetica", 10)
    c.drawRightString(width-1.5*cm, height-1.2*cm, datetime.utcnow().strftime("%Y-%m-%d"))

    # KPIs
    c.setFillColor(colors.black)
    y = height-3*cm
    _draw_kpi_line(c, 2*cm, y, "Total Reviews", kpis.get("total_reviews", 0)); y -= 0.7*cm
    _draw_kpi_line(c, 2*cm, y, "Average Rating", round(kpis.get("average_rating", 0), 2)); y -= 0.7*cm
    _draw_kpi_line(c, 2*cm, y, "% Positive", f"{kpis.get('pct_positive', 0):.1f}%"); y -= 0.7*cm
    _draw_kpi_line(c, 2*cm, y, "% Neutral", f"{kpis.get('pct_neutral', 0):.1f}%"); y -= 0.7*cm
    _draw_kpi_line(c, 2*cm, y, "% Negative", f"{kpis.get('pct_negative', 0):.1f}%"); y -= 1.0*cm

    # Sentiment breakdown bar
    c.setFont("Helvetica-Bold", 12)
    c.drawString(2*cm, y, "Sentiment Breakdown")
    y -= 0.5*cm
    total = sum(sentiment_breakdown.values()) or 1
    bar_width = width - 4*cm
    start_x = 2*cm
    colors_map = {
        'Positive': colors.HexColor('#16a34a'),
        'Neutral': colors.HexColor('#64748b'),
        'Negative': colors.HexColor('#dc2626')
    }
    acc = start_x
    for label in ['Positive', 'Neutral', 'Negative']:
        pct = sentiment_breakdown.get(label, 0)/total
        w = bar_width * pct
        c.setFillColor(colors_map[label])
        c.rect(acc, y-0.4*cm, w, 0.4*cm, fill=1, stroke=0)
        acc += w
    y -= 1.2*cm

    # Sample reviews
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(2*cm, y, "Sample Reviews & Suggested Replies")
    y -= 0.6*cm
    c.setFont("Helvetica", 10)
    for sentiment, items in samples.items():
        if not items:
            continue
        c.setFont("Helvetica-Bold", 11)
        c.drawString(2*cm, y, f"{sentiment} review")
        y -= 0.4*cm
        c.setFont("Helvetica", 10)
        for it in items[:2]:
            text = it.get('text', '')[:280]
            reply = it.get('reply', '')[:280]
            # Review
            c.drawString(2*cm, y, f"• {text}")
            y -= 0.35*cm
            c.setFillColor(colors.HexColor('#2563eb'))
            c.drawString(2.5*cm, y, f"Suggested reply: {reply}")
            c.setFillColor(colors.black)
            y -= 0.6*cm
            if y < 4*cm:
                c.showPage(); y = height-2*cm

    c.showPage()
    c.save()
    pdf = buf.getvalue()
    buf.close()
    return pdf