from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    from datetime import datetime

    def build_pdf(path: str, company_name: str, kpis: dict):
        c = canvas.Canvas(path, pagesize=A4)
        w, h = A4
        c.setFont("Helvetica-Bold", 16)
        c.drawString(40, h-60, f"Reputation Report — {company_name}")
        c.setFont("Helvetica", 10)
        c.drawString(40, h-80, f"Generated: {datetime.utcnow().isoformat()}Z")
        y = h-120
        for k, v in kpis.items():
            c.drawString(40, y, f"{k}: {v}")
            y -= 14
        c.showPage()
        c.save()
        return path