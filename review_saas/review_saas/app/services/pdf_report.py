
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import cm
from reportlab.lib.utils import ImageReader
from datetime import datetime
import io


def generate_company_report(buf, company, kpis: dict, charts: dict, samples: list):
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4
    y = height - 2*cm

    # Header
    c.setFont('Helvetica-Bold', 16)
    c.drawString(2*cm, y, f"Reputation Report: {company.name}")
    y -= 0.8*cm
    c.setFont('Helvetica', 10)
    c.drawString(2*cm, y, f"Date: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    y -= 1.2*cm

    # KPIs
    c.setFont('Helvetica-Bold', 12)
    c.drawString(2*cm, y, 'KPIs')
    y -= 0.6*cm
    c.setFont('Helvetica', 10)
    for k, v in kpis.items():
        c.drawString(2.2*cm, y, f"{k}: {v}")
        y -= 0.5*cm
    y -= 0.5*cm

    # Charts (if paths provided)
    for ch_name, path in charts.items():
        try:
            img = ImageReader(path)
            c.drawImage(img, 2*cm, y-6*cm, width=12*cm, height=6*cm, preserveAspectRatio=True)
            y -= 6.5*cm
        except Exception:
            c.drawString(2*cm, y, f"[Chart '{ch_name}' unavailable]")
            y -= 0.6*cm

    # Sample reviews
    c.setFont('Helvetica-Bold', 12)
    c.drawString(2*cm, y, 'Sample Reviews & Replies')
    y -= 0.8*cm
    c.setFont('Helvetica', 10)
    for s in samples:
        txt = c.beginText(2*cm, y)
        txt.textLines(f"- {s}")
        c.drawText(txt)
        y -= 2*cm
        if y < 4*cm:
            c.showPage(); y = height - 2*cm
    c.showPage()
    c.save()
